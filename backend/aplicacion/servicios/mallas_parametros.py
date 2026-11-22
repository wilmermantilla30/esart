"""
S2-09: pestaña "Mallas curriculares" del panel de Parámetros.

Quien tenga el permiso MALLAS_CURRICULARES (por rol o por excepción) puede:
- ver la malla vigente de cada tipo de curso y su historial de versiones (leer);
- guardar una malla editada: agregar, quitar, reordenar y marcar materias con o sin nota. Guardar
  crea una VERSIÓN NUEVA y la anterior queda histórica; los cursos ya creados conservan la suya
  (actualizar);
- crear un tipo de curso nuevo, por ejemplo uno que la Escuela abra este año (crear).

Guardar y crear exigen el código del autenticador (política MALLAS_MODIFICAR) y quedan en la
auditoría con el antes y el después. Reutiliza crear_version y validar_filas de malla_curricular.py
(la misma lógica que la carga inicial por consola).
"""

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos import TipoCurso
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp
from aplicacion.servicios.malla_curricular import (
    CLAVE_BLOQUEO_MALLA,
    FilaMalla,
    crear_version,
    normalizar_nombre,
    tipo_curso_por_codigo,
    validar_filas,
    version_vigente,
)

POLITICA_TOTP = "MALLAS_MODIFICAR"
PREFIJO_AUDITORIA_TOTP = "MALLAS"
# Valores que ya usa la Escuela en esart.tipos_curso.
TIPOS_DE_CURSO = ("EDUCACION_MILITAR", "ESPECIALIZACION", "EDUCACION_SUPERIOR")
MODALIDADES = ("PRESENCIAL", "VIRTUAL", "MIXTA")
PATRON_CODIGO_TIPO = re.compile(r"^[A-Z0-9_]{2,20}$")
DURACION_MAXIMA_SEMANAS = 104


@dataclass(frozen=True)
class NuevoTipoCurso:
    codigo: str
    nombre: str
    tipo: str
    modalidad: str
    duracion_semanas: int


# --- Consultas ----------------------------------------------------------------------------


async def listar_tipos(sesion: AsyncSession) -> list[dict]:
    """Tipos de curso con su versión vigente (o ninguna, como TECNICA al empezar)."""
    filas = await sesion.execute(
        text("""
            SELECT tc.codigo, tc.nombre, tc.tipo, tc.modalidad, tc.duracion_semanas, tc.activo,
                   v.numero AS version, v.anio,
                   count(m.id) AS materias,
                   count(m.id) FILTER (WHERE m.evaluable) AS evaluables
            FROM esart.tipos_curso tc
            LEFT JOIN esart.versiones_malla v ON v.tipo_curso_id = tc.id AND v.estado = 'VIGENTE'
            LEFT JOIN esart.malla_curricular m ON m.version_id = v.id
            GROUP BY tc.id, v.id
            ORDER BY tc.activo DESC, tc.codigo
        """)
    )
    return [dict(fila._mapping) for fila in filas]


async def _versiones(sesion: AsyncSession, tipo_curso_id: int) -> list[dict]:
    filas = await sesion.execute(
        text("""
            SELECT v.numero, v.anio, v.estado, v.observacion, v.creado_en, u.usuario AS creado_por,
                   (SELECT count(*) FROM esart.malla_curricular m WHERE m.version_id = v.id) AS materias,
                   (SELECT count(*) FROM esart.cursos c WHERE c.malla_version_id = v.id) AS cursos
            FROM esart.versiones_malla v
            LEFT JOIN esart_ref.usuarios u ON u.id = v.creado_por_id
            WHERE v.tipo_curso_id = :tipo
            ORDER BY v.numero DESC
        """),
        {"tipo": tipo_curso_id},
    )
    return [dict(fila._mapping) for fila in filas]


async def _filas_de_version(sesion: AsyncSession, version_id: int) -> list[dict]:
    filas = await sesion.execute(
        text("""
            SELECT m.orden, mt.codigo AS codigo_materia, mt.nombre AS materia, m.area, m.modulo, m.evaluable
            FROM esart.malla_curricular m
            JOIN esart.materias mt ON mt.id = m.materia_id
            WHERE m.version_id = :version
            ORDER BY m.orden
        """),
        {"version": version_id},
    )
    return [dict(fila._mapping) for fila in filas]


async def detalle(sesion: AsyncSession, codigo_tipo: str, numero: int | None = None) -> dict:
    """Un tipo de curso, la versión pedida (por defecto la vigente) con sus materias e historial."""
    tipo = await tipo_curso_por_codigo(sesion, codigo_tipo)
    versiones = await _versiones(sesion, tipo.id)
    if numero is None:
        elegida = next((v for v in versiones if v["estado"] == "VIGENTE"), None)
    else:
        elegida = next((v for v in versiones if v["numero"] == numero), None)
        if elegida is None:
            raise ErrorAplicacion(
                404, "VERSION_NO_ENCONTRADA", f"{tipo.codigo} no tiene la versión {numero}."
            )
    filas = []
    if elegida is not None:
        version_id = await sesion.scalar(
            text("SELECT id FROM esart.versiones_malla WHERE tipo_curso_id = :tipo AND numero = :numero"),
            {"tipo": tipo.id, "numero": elegida["numero"]},
        )
        filas = await _filas_de_version(sesion, version_id)
    return {
        "tipo_curso": {
            "codigo": tipo.codigo,
            "nombre": tipo.nombre,
            "tipo": tipo.tipo,
            "modalidad": tipo.modalidad,
            "duracion_semanas": tipo.duracion_semanas,
            "activo": tipo.activo,
        },
        "version": elegida,
        "filas": filas,
        "versiones": versiones,
    }


async def catalogo_materias(sesion: AsyncSession) -> list[dict]:
    """Materias ya registradas: el editor las sugiere para no crear duplicados con otro nombre."""
    filas = await sesion.execute(text("SELECT codigo, nombre FROM esart.materias ORDER BY nombre"))
    return [dict(fila._mapping) for fila in filas]


# --- Guardar una versión nueva --------------------------------------------------------------


def _clave_fila(fila: FilaMalla) -> tuple:
    """Lo que distingue una fila para saber si la malla cambió (nombre normalizado, sin espacios)."""
    return (
        fila.orden,
        normalizar_nombre(fila.materia),
        fila.evaluable,
        (fila.area or "").strip(),
        (fila.modulo or "").strip(),
    )


def comparar(anteriores: list[FilaMalla], nuevas: list[FilaMalla]) -> dict:
    """Resumen del cambio para la auditoría: qué materias entran, salen o cambian de nota."""
    antes = {normalizar_nombre(f.materia): f for f in anteriores}
    despues = {normalizar_nombre(f.materia): f for f in nuevas}
    return {
        "agregadas": sorted(set(despues) - set(antes)),
        "quitadas": sorted(set(antes) - set(despues)),
        "cambian_evaluable": sorted(
            nombre
            for nombre in set(antes) & set(despues)
            if antes[nombre].evaluable != despues[nombre].evaluable
        ),
        "orden_cambiado": [normalizar_nombre(f.materia) for f in sorted(anteriores, key=lambda f: f.orden)]
        != [normalizar_nombre(f.materia) for f in sorted(nuevas, key=lambda f: f.orden)],
    }


def _resumen_filas(filas: list[FilaMalla]) -> list[dict]:
    return [
        {"orden": f.orden, "materia": normalizar_nombre(f.materia), "evaluable": f.evaluable}
        for f in sorted(filas, key=lambda f: f.orden)
    ]


async def guardar_version(
    sesion: AsyncSession,
    codigo_tipo: str,
    anio: int,
    filas: list[FilaMalla],
    observacion: str | None,
    numero_esperado: int | None,
    *,
    actor: Actor,
    codigo_totp: str | None,
) -> dict:
    """
    Crea la versión nueva de la malla y la confirma. numero_esperado es la versión vigente que el
    usuario editó (None si el tipo no tenía malla): si otro usuario guardó antes, no se sobrescribe.
    """
    tipo = await tipo_curso_por_codigo(sesion, codigo_tipo)
    # Validar antes de pedir el código: el usuario no gasta un código en una malla inválida.
    validar_filas(filas)
    anteriores = await _filas_actuales(sesion, tipo)
    await _exigir_version(sesion, tipo, numero_esperado)
    if anteriores is not None and sorted(map(_clave_fila, anteriores)) == sorted(map(_clave_fila, filas)):
        raise ErrorAplicacion(422, "SIN_CAMBIOS", "La malla es igual a la versión vigente.")

    await exigir_codigo_totp(
        sesion,
        actor.usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        actor.request,
        prefijo_auditoria=PREFIJO_AUDITORIA_TOTP,
        mensaje_requerido="Ingrese el código del autenticador para guardar la nueva versión de la malla.",
    )
    # Con el bloqueo tomado se vuelve a comprobar: dos usuarios que guardan a la vez no se pisan.
    await sesion.execute(
        text("SELECT pg_advisory_xact_lock(:clave, :tipo)"), {"clave": CLAVE_BLOQUEO_MALLA, "tipo": tipo.id}
    )
    await _exigir_version(sesion, tipo, numero_esperado)
    await crear_version(
        sesion,
        tipo,
        anio,
        filas,
        actor,
        observacion=(observacion or "").strip() or None,
        detalle_extra={
            "origen": "PARAMETROS",
            "cambios": comparar(anteriores or [], filas),
            "antes": _resumen_filas(anteriores or []),
            "despues": _resumen_filas(filas),
        },
    )
    await sesion.commit()
    return await detalle(sesion, tipo.codigo)


async def _filas_actuales(sesion: AsyncSession, tipo: TipoCurso) -> list[FilaMalla] | None:
    """Materias de la versión vigente (None si el tipo todavía no tiene malla)."""
    vigente = await version_vigente(sesion, tipo.id)
    if vigente is None:
        return None
    return [
        FilaMalla(
            orden=fila["orden"],
            materia=fila["materia"],
            evaluable=fila["evaluable"],
            area=fila["area"],
            modulo=fila["modulo"],
        )
        for fila in await _filas_de_version(sesion, vigente.id)
    ]


async def _exigir_version(sesion: AsyncSession, tipo: TipoCurso, numero_esperado: int | None) -> None:
    vigente = await version_vigente(sesion, tipo.id)
    if (vigente.numero if vigente else None) != numero_esperado:
        raise ErrorAplicacion(
            409,
            "MALLA_DESACTUALIZADA",
            "Otro usuario guardó una versión de esta malla mientras usted editaba. Recargue y revise.",
        )


# --- Crear un tipo de curso -----------------------------------------------------------------


def validar_tipo(datos: NuevoTipoCurso) -> NuevoTipoCurso:
    """Código en mayúsculas sin espacios, nombre legible y valores de los catálogos de la Escuela."""
    codigo = datos.codigo.strip().upper()
    nombre = re.sub(r"\s+", " ", datos.nombre).strip()
    if not PATRON_CODIGO_TIPO.match(codigo):
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "El código debe tener de 2 a 20 letras mayúsculas, números o guion bajo."
        )
    if not 3 <= len(nombre) <= 200:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "El nombre debe tener entre 3 y 200 caracteres.")
    if datos.tipo not in TIPOS_DE_CURSO or datos.modalidad not in MODALIDADES:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Tipo o modalidad no válidos.")
    if not 1 <= datos.duracion_semanas <= DURACION_MAXIMA_SEMANAS:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", f"La duración debe estar entre 1 y {DURACION_MAXIMA_SEMANAS} semanas."
        )
    return NuevoTipoCurso(codigo, nombre, datos.tipo, datos.modalidad, datos.duracion_semanas)


async def crear_tipo(
    sesion: AsyncSession, datos: NuevoTipoCurso, *, actor: Actor, codigo_totp: str | None
) -> dict:
    """Registra un tipo de curso sin malla (se le carga después en la misma pestaña)."""
    nuevo = validar_tipo(datos)
    if await sesion.scalar(text("SELECT 1 FROM esart.tipos_curso WHERE codigo = :c"), {"c": nuevo.codigo}):
        raise ErrorAplicacion(409, "TIPO_CURSO_DUPLICADO", f"Ya existe el tipo de curso {nuevo.codigo}.")
    await exigir_codigo_totp(
        sesion,
        actor.usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        actor.request,
        prefijo_auditoria=PREFIJO_AUDITORIA_TOTP,
        mensaje_requerido="Ingrese el código del autenticador para crear el tipo de curso.",
    )
    try:
        await sesion.execute(
            text("""
                INSERT INTO esart.tipos_curso (codigo, nombre, tipo, modalidad, duracion_semanas)
                VALUES (:codigo, :nombre, :tipo, :modalidad, :duracion)
            """),
            {
                "codigo": nuevo.codigo,
                "nombre": nuevo.nombre,
                "tipo": nuevo.tipo,
                "modalidad": nuevo.modalidad,
                "duracion": nuevo.duracion_semanas,
            },
        )
    except IntegrityError:
        # Otro usuario lo creó entre la comprobación y el INSERT.
        await sesion.rollback()
        raise ErrorAplicacion(
            409, "TIPO_CURSO_DUPLICADO", f"Ya existe el tipo de curso {nuevo.codigo}."
        ) from None
    # registrar_evento confirma la transacción: el tipo y su auditoría quedan juntos o no quedan.
    await auditoria.registrar_evento(
        sesion,
        auditoria.TIPO_CURSO_CREADO,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "codigo": nuevo.codigo,
            "nombre": nuevo.nombre,
            "tipo": nuevo.tipo,
            "modalidad": nuevo.modalidad,
            "duracion_semanas": nuevo.duracion_semanas,
        },
    )
    return await detalle(sesion, nuevo.codigo)
