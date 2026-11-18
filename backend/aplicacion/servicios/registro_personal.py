"""
Registro manual de un efectivo en esart.personal_militar (componente PERSONAL_CARGUE_MANUAL).

Reglas:
- Cédula: solo dígitos (5 a 15), sin puntos ni guiones; única en personal_militar.
- Grado: debe pertenecer a la categoría elegida (catálogo GRADOS_POR_CATEGORIA).
- Unidad: opcional; si se envía debe existir y estar activa en esart_ref.unidades_militares.
- Todo se valida antes de escribir; el registro y su auditoría se confirman juntos.

No crea tablas ni cambia privilegios: usa las mismas columnas de INSERT que ya tiene la cuenta
de la API para el cargue por Excel (migración p0011). La acción de auditoría PERSONAL_REGISTRADO
la agrega la migración p0015; si falta, se responde 503 sin guardar nada.
"""

import logging
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.auditoria import PERSONAL_REGISTRADO
from aplicacion.servicios.habilitacion import normalizar_cedula

registrador = logging.getLogger(__name__)

# Catálogo de grados del Ejército por categoría (sigla que se guarda → nombre que se muestra).
# personal_militar.grado es texto libre (VARCHAR 20); el formulario solo ofrece estas siglas.
GRADOS_POR_CATEGORIA: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "OFICIAL": (
        "Oficial",
        (
            ("ST", "Subteniente"),
            ("TE", "Teniente"),
            ("CT", "Capitán"),
            ("MY", "Mayor"),
            ("TC", "Teniente Coronel"),
            ("CR", "Coronel"),
            ("BG", "Brigadier General"),
            ("MG", "Mayor General"),
            ("GR", "General"),
        ),
    ),
    "SUBOFICIAL": (
        "Suboficial",
        (
            ("C3", "Cabo Tercero"),
            ("CS", "Cabo Segundo"),
            ("CP", "Cabo Primero"),
            ("SS", "Sargento Segundo"),
            ("SV", "Sargento Viceprimero"),
            ("SP", "Sargento Primero"),
            ("SM", "Sargento Mayor"),
            ("SMC", "Sargento Mayor de Comando"),
            ("SMCC", "Sargento Mayor de Comando Conjunto"),
        ),
    ),
    "SOLDADO_PROFESIONAL": ("Soldado profesional", (("SLP", "Soldado Profesional"),)),
}

RESTRICCION_AUDITORIA = "ck_auditoria_eventos_ck_auditoria_eventos_accion"
MENSAJE_SIN_MIGRACION = (
    "El registro manual aún no está habilitado en la base de datos (migración p0015 pendiente). "
    "Contacte al administrador; no se guardó el registro."
)


@dataclass(frozen=True)
class DatosPersonal:
    """Datos del formulario, tal como llegan (se normalizan en registrar)."""

    documento_identidad: str
    nombres: str
    apellidos: str
    grado: str
    genero: str
    categoria: str
    unidad_actual_id: int | None
    especialidad_actual: str | None
    activo: bool


def _texto(valor: str | None) -> str:
    """Quita espacios al inicio, al final y repetidos."""
    return " ".join((valor or "").split())


def _obligatorio(valor: str | None, campo: str, maximo: int) -> str:
    limpio = _texto(valor)
    if not limpio:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", f"Diligencie {campo}.")
    if len(limpio) > maximo:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", f"{campo.capitalize()}: máximo {maximo} caracteres.")
    return limpio


def opciones_categorias() -> list[dict]:
    """Categorías con sus grados, para los selectores del formulario."""
    return [
        {
            "codigo": codigo,
            "nombre": nombre,
            "grados": [{"codigo": sigla, "nombre": texto} for sigla, texto in grados],
        }
        for codigo, (nombre, grados) in GRADOS_POR_CATEGORIA.items()
    ]


async def opciones_unidades(sesion: AsyncSession) -> list[dict]:
    """Unidades activas para el selector (id, código y nombre)."""
    filas = await sesion.execute(
        text("SELECT id, codigo, nombre FROM esart_ref.unidades_militares WHERE activo ORDER BY nombre")
    )
    return [dict(fila) for fila in filas.mappings()]


def normalizar(datos: DatosPersonal) -> dict:
    """Valida formato y catálogo; devuelve los valores listos para insertar."""
    categoria = _texto(datos.categoria).upper()
    if categoria not in GRADOS_POR_CATEGORIA:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Seleccione una categoría válida.")
    grado = _texto(datos.grado).upper()
    if grado not in {sigla for sigla, _ in GRADOS_POR_CATEGORIA[categoria][1]}:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "El grado no corresponde a la categoría seleccionada.")
    genero = _texto(datos.genero).upper()
    if genero not in ("M", "F"):
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Seleccione el género (M o F).")
    especialidad = _texto(datos.especialidad_actual) or None
    if especialidad and len(especialidad) > 100:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Especialidad: máximo 100 caracteres.")
    return {
        "documento_identidad": normalizar_cedula(datos.documento_identidad),
        "nombres": _obligatorio(datos.nombres, "los nombres", 150),
        "apellidos": _obligatorio(datos.apellidos, "los apellidos", 150),
        "grado": grado,
        "genero": genero,
        "categoria": categoria,
        "unidad_actual_id": datos.unidad_actual_id,
        "especialidad_actual": especialidad,
        "activo": bool(datos.activo),
    }


async def registrar(
    sesion: AsyncSession,
    datos: DatosPersonal,
    *,
    usuario_id: int,
    nombre_usuario: str,
    request: Request | None = None,
) -> dict:
    """Inserta el efectivo y su evento de auditoría en una sola transacción. Devuelve el registro."""
    valores = normalizar(datos)
    if await sesion.scalar(
        text("SELECT 1 FROM esart.personal_militar WHERE documento_identidad = :doc"),
        {"doc": valores["documento_identidad"]},
    ):
        raise ErrorAplicacion(
            409, "DOCUMENTO_EXISTENTE", "Ya existe un militar registrado con ese documento de identidad."
        )
    unidad = None
    if valores["unidad_actual_id"] is not None:
        unidad = (
            await sesion.execute(
                text("SELECT nombre, activo FROM esart_ref.unidades_militares WHERE id = :id"),
                {"id": valores["unidad_actual_id"]},
            )
        ).one_or_none()
        if unidad is None or not unidad.activo:
            raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La unidad seleccionada no existe o está inactiva.")
    try:
        nuevo_id = await sesion.scalar(
            text("""
                INSERT INTO esart.personal_militar
                  (documento_identidad, nombres, apellidos, grado, genero, categoria,
                   unidad_actual_id, especialidad_actual, activo)
                VALUES (:documento_identidad, :nombres, :apellidos, :grado, :genero, :categoria,
                        :unidad_actual_id, :especialidad_actual, :activo)
                RETURNING id
            """),
            valores,
        )
        # registrar_evento confirma (commit): el efectivo y su auditoría quedan juntos o ninguno.
        await auditoria.registrar_evento(
            sesion,
            PERSONAL_REGISTRADO,
            request,
            usuario_id=usuario_id,
            nombre_usuario=nombre_usuario,
            documento=valores["documento_identidad"],
            resultado="EXITOSO",
            detalle={
                "personal_id": nuevo_id,
                "grado": valores["grado"],
                "categoria": valores["categoria"],
                "unidad_actual_id": valores["unidad_actual_id"],
                "activo": valores["activo"],
            },
        )
    except IntegrityError as error:
        await sesion.rollback()
        if RESTRICCION_AUDITORIA in str(error.orig):
            registrador.error("REGISTRO_PERSONAL_RECHAZADO motivo=accion_auditoria_no_habilitada")
            raise ErrorAplicacion(503, "REGISTRO_NO_DISPONIBLE", MENSAJE_SIN_MIGRACION) from None
        # Otro registro con la misma cédula se guardó entre la consulta y el INSERT.
        raise ErrorAplicacion(
            409, "DOCUMENTO_EXISTENTE", "Ya existe un militar registrado con ese documento de identidad."
        ) from None
    return {
        "id": nuevo_id,
        **{clave: valores[clave] for clave in ("documento_identidad", "nombres", "apellidos", "grado")},
        "categoria": valores["categoria"],
        "genero": valores["genero"],
        "unidad_actual_id": valores["unidad_actual_id"],
        "unidad_nombre": unidad.nombre if unidad else None,
        "especialidad_actual": valores["especialidad_actual"],
        "activo": valores["activo"],
        "nombre_completo": f"{valores['grado']} {valores['nombres']} {valores['apellidos']}",
    }
