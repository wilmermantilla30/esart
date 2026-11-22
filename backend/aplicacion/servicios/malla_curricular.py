"""
S2-01: malla curricular versionada por tipo de curso.

- Catálogo único de materias (esart.materias): una materia existe una sola vez y se reutiliza en
  todas las mallas que la tengan (así los reportes comparan entre cursos).
- Cada tipo de curso tiene versiones de malla; solo una VIGENTE. Crear una versión nueva deja la
  anterior HISTORICA: los cursos ya creados conservan la suya (la asigna un trigger al crear el
  curso, migración p0017) y sus notas nunca cambian de materias.
- Cada materia de la malla es evaluable o "sin nota" (Tiempo del comandante, Entrenamiento
  físico): las que no llevan nota no cuentan en el promedio del curso.

Lo usan la herramienta de consola herramientas/cargar_malla_curricular.py (carga inicial desde el
Excel aprobado por la Escuela) y el panel de Parámetros (servicios/mallas_parametros.py, S2-09).
Ninguna función confirma la transacción: quien llama decide cuándo hacer commit, para cargar varias
mallas de una sola vez.
"""

import re
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos import MallaCurricular, Materias, TipoCurso, VersionMalla
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.administracion_usuarios import Actor

ESTADO_VIGENTE = "VIGENTE"
ESTADO_HISTORICA = "HISTORICA"
LONGITUD_NOMBRE_MATERIA = 200
LONGITUD_AREA_MODULO = 100
PREFIJO_CODIGO_MATERIA = "MAT-"
# Clave de los bloqueos consultivos de esta tabla: serializa dos versiones del mismo tipo de curso.
CLAVE_BLOQUEO_MALLA = 17


@dataclass(frozen=True)
class FilaMalla:
    """Una materia dentro de la malla de un tipo de curso."""

    orden: int
    materia: str
    evaluable: bool
    area: str | None = None
    modulo: str | None = None


@dataclass(frozen=True)
class ResumenVersion:
    """Versión vigente de un tipo de curso con sus conteos (para listados y la consola)."""

    tipo_curso: str
    numero: int
    anio: int
    materias: int
    evaluables: int


def normalizar_nombre(nombre: str) -> str:
    """Espacios simples y mayúsculas: 'Liderazgo ' y 'LIDERAZGO' son la misma materia."""
    return re.sub(r"\s+", " ", nombre).strip().upper()


def _error(mensaje: str, detalle: dict | None = None) -> ErrorAplicacion:
    return ErrorAplicacion(422, "MALLA_INVALIDA", mensaje, detalle)


def validar_filas(filas: list[FilaMalla]) -> None:
    """Reglas de una malla antes de guardarla (todas las del mismo tipo de curso)."""
    if not filas:
        raise _error("La malla debe tener al menos una materia.")
    ordenes = [fila.orden for fila in filas]
    if any(orden < 1 for orden in ordenes) or len(set(ordenes)) != len(ordenes):
        raise _error("El orden de las materias debe ser 1, 2, 3... sin repetirse.")
    nombres = [normalizar_nombre(fila.materia) for fila in filas]
    repetidas = sorted({nombre for nombre in nombres if nombres.count(nombre) > 1})
    if repetidas:
        raise _error("Una materia aparece dos veces en la misma malla.", {"materias": repetidas})
    for fila, nombre in zip(filas, nombres, strict=True):
        if not nombre or len(nombre) > LONGITUD_NOMBRE_MATERIA:
            raise _error("Nombre de materia vacío o demasiado largo.", {"orden": fila.orden})
        for texto in (fila.area, fila.modulo):
            if texto and len(texto) > LONGITUD_AREA_MODULO:
                raise _error("Área o módulo demasiado largo.", {"orden": fila.orden})
    if not any(fila.evaluable for fila in filas):
        raise _error("La malla debe tener al menos una materia con nota.")


async def tipo_curso_por_codigo(sesion: AsyncSession, codigo: str) -> TipoCurso:
    tipo = await sesion.scalar(select(TipoCurso).where(TipoCurso.codigo == codigo))
    if tipo is None:
        raise ErrorAplicacion(404, "TIPO_CURSO_NO_ENCONTRADO", f"No existe el tipo de curso {codigo}.")
    return tipo


async def version_vigente(sesion: AsyncSession, tipo_curso_id: int) -> VersionMalla | None:
    return await sesion.scalar(
        select(VersionMalla).where(
            VersionMalla.tipo_curso_id == tipo_curso_id, VersionMalla.estado == ESTADO_VIGENTE
        )
    )


async def _siguiente_codigo_materia(sesion: AsyncSession) -> int:
    """Número siguiente de MAT-001, MAT-002... (solo cuenta los códigos con ese formato)."""
    codigos = await sesion.scalars(
        select(Materias.codigo).where(Materias.codigo.like(f"{PREFIJO_CODIGO_MATERIA}%"))
    )
    sufijos = (codigo[len(PREFIJO_CODIGO_MATERIA) :] for codigo in codigos)
    return max((int(sufijo) for sufijo in sufijos if sufijo.isdigit()), default=0) + 1


async def asegurar_materias(sesion: AsyncSession, nombres: list[str]) -> dict[str, Materias]:
    """
    Devuelve la materia de cada nombre (normalizado) y crea en el catálogo las que falten, en el
    orden recibido: con el catálogo vacío, el primer nombre queda MAT-001, el segundo MAT-002...
    """
    normalizados = list(dict.fromkeys(normalizar_nombre(nombre) for nombre in nombres))
    existentes = {
        materia.nombre.upper(): materia
        for materia in await sesion.scalars(
            select(Materias).where(func.upper(Materias.nombre).in_(normalizados))
        )
    }
    siguiente = await _siguiente_codigo_materia(sesion)
    for nombre in normalizados:
        if nombre in existentes:
            continue
        materia = Materias(codigo=f"{PREFIJO_CODIGO_MATERIA}{siguiente:03d}", nombre=nombre)
        sesion.add(materia)
        existentes[nombre] = materia
        siguiente += 1
    await sesion.flush()
    return existentes


async def crear_version(
    sesion: AsyncSession,
    tipo_curso: TipoCurso,
    anio: int,
    filas: list[FilaMalla],
    actor: Actor,
    observacion: str | None = None,
    detalle_extra: dict | None = None,
) -> VersionMalla:
    """
    Crea la versión nueva de la malla de un tipo de curso, deja HISTORICA la que estaba vigente y
    lo registra en la auditoría. No confirma la transacción.

    detalle_extra se suma al detalle de la auditoría (el panel de Parámetros agrega el antes y el
    después de la malla).
    """
    validar_filas(filas)
    if not 2000 <= anio <= 2100:
        raise _error("Año de la malla fuera de rango.", {"anio": anio})
    # Dos cargas simultáneas del mismo tipo de curso esperan en fila (no requiere permisos extra).
    await sesion.execute(
        text("SELECT pg_advisory_xact_lock(:clave, :tipo)"),
        {"clave": CLAVE_BLOQUEO_MALLA, "tipo": tipo_curso.id},
    )
    anterior = await version_vigente(sesion, tipo_curso.id)
    numero_maximo = await sesion.scalar(
        select(func.max(VersionMalla.numero)).where(VersionMalla.tipo_curso_id == tipo_curso.id)
    )
    if anterior is not None:
        anterior.estado = ESTADO_HISTORICA
        await sesion.flush()  # libera el índice de "una sola vigente" antes de insertar la nueva

    version = VersionMalla(
        tipo_curso_id=tipo_curso.id,
        numero=(numero_maximo or 0) + 1,
        anio=anio,
        estado=ESTADO_VIGENTE,
        observacion=observacion,
        creado_por_id=actor.usuario_id,
    )
    sesion.add(version)
    materias = await asegurar_materias(sesion, [fila.materia for fila in filas])
    await sesion.flush()
    for fila in filas:
        sesion.add(
            MallaCurricular(
                tipo_curso_id=tipo_curso.id,
                version_id=version.id,
                materia_id=materias[normalizar_nombre(fila.materia)].id,
                orden=fila.orden,
                evaluable=fila.evaluable,
                area=fila.area,
                modulo=fila.modulo,
            )
        )
    await sesion.flush()

    await auditoria.registrar_evento(
        sesion,
        auditoria.MALLA_CURRICULAR_CARGADA,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "tipo_curso": tipo_curso.codigo,
            "version": version.numero,
            "anio": anio,
            "version_anterior": anterior.numero if anterior else None,
            "materias": len(filas),
            "evaluables": sum(1 for fila in filas if fila.evaluable),
            "operador": actor.operador,
            **(detalle_extra or {}),
        },
        confirmar=False,
    )
    return version


async def resumen_vigentes(sesion: AsyncSession) -> list[ResumenVersion]:
    """Versión vigente de cada tipo de curso con cuántas materias y cuántas evaluables tiene."""
    consulta = (
        select(
            TipoCurso.codigo,
            VersionMalla.numero,
            VersionMalla.anio,
            func.count(MallaCurricular.id),
            func.count(MallaCurricular.id).filter(MallaCurricular.evaluable),
        )
        .join(VersionMalla, VersionMalla.tipo_curso_id == TipoCurso.id)
        .join(MallaCurricular, MallaCurricular.version_id == VersionMalla.id)
        .where(VersionMalla.estado == ESTADO_VIGENTE)
        .group_by(TipoCurso.codigo, VersionMalla.numero, VersionMalla.anio)
        .order_by(TipoCurso.codigo)
    )
    return [ResumenVersion(*fila) for fila in (await sesion.execute(consulta)).all()]
