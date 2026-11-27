"""
Nota mínima de aprobación (S2-10), editable en Parámetros > Cursos y Capacitaciones.

- El valor vive en esart.parametros_habilitacion (código NOTA_MINIMA_APROBACION), escala 0 a 5
  con 2 decimales; el inicial es 3,00.
- Cada curso guarda la nota vigente al crearse (trigger de la migración p0019). Cambiarla aquí
  solo afecta a los cursos nuevos: los resultados ya aprobados por el Inspector no se recalculan.
- Guardar exige el código TOTP (misma política que la regla de habilitación), rechaza el cambio
  si otro administrador guardó mientras tanto y queda auditado con el valor anterior y el nuevo.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp
from aplicacion.servicios.parametros_habilitacion import POLITICA_TOTP

CODIGO_PARAMETRO = "NOTA_MINIMA_APROBACION"
# Límites de la propuesta: por debajo de 1,00 aprobar no tendría sentido; 5,00 es la nota máxima.
NOTA_MINIMA_PERMITIDA = Decimal("1.00")
NOTA_MAXIMA_PERMITIDA = Decimal("5.00")
DOS_DECIMALES = Decimal("0.01")


@dataclass(frozen=True)
class EstadoNotaMinima:
    """Lo que muestra la tarjeta de la nota mínima."""

    valor: Decimal
    actualizado_en: datetime
    actualizado_por: str | None
    # Cursos EN_CURSO que ya tienen su nota guardada: no cambian aunque se guarde otro valor.
    cursos_en_curso: int


async def obtener(sesion: AsyncSession) -> EstadoNotaMinima:
    """Valor vigente, quién y cuándo lo cambió, y cuántos cursos en curso conservan la suya."""
    fila = (
        await sesion.execute(
            text("""
                SELECT p.valor #>> '{}' AS valor, p.actualizado_en, u.usuario AS actualizado_por
                FROM esart.parametros_habilitacion p
                LEFT JOIN esart_ref.usuarios u ON u.id = p.actualizado_por_id
                WHERE p.codigo = :codigo
            """),
            {"codigo": CODIGO_PARAMETRO},
        )
    ).one_or_none()
    if fila is None:
        # Sin la migración p0019 no se puede decidir quién aprueba: error controlado, no un 500 crudo.
        raise ErrorAplicacion(
            500, "ERROR_INTERNO", "La nota mínima de aprobación no está configurada (migración p0019)."
        )
    cursos_en_curso = await sesion.scalar(
        text("""
            SELECT count(*) FROM esart.cursos
            WHERE estado = 'EN_CURSO' AND nota_minima_aprobacion IS NOT NULL
        """)
    )
    return EstadoNotaMinima(
        valor=Decimal(fila.valor).quantize(DOS_DECIMALES),
        actualizado_en=fila.actualizado_en,
        actualizado_por=fila.actualizado_por,
        cursos_en_curso=cursos_en_curso or 0,
    )


def validar_propuesta(valor: Decimal) -> Decimal:
    """La nota debe estar entre 1,00 y 5,00 y tener como máximo 2 decimales."""
    if valor != valor.quantize(DOS_DECIMALES):
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La nota mínima admite como máximo 2 decimales.")
    if not NOTA_MINIMA_PERMITIDA <= valor <= NOTA_MAXIMA_PERMITIDA:
        raise ErrorAplicacion(
            422,
            "DATOS_INVALIDOS",
            f"La nota mínima debe estar entre {NOTA_MINIMA_PERMITIDA} y {NOTA_MAXIMA_PERMITIDA}.",
        )
    return valor.quantize(DOS_DECIMALES)


async def guardar(
    sesion: AsyncSession,
    valor: Decimal,
    version_esperada: datetime | None,
    *,
    usuario_id: int,
    nombre_usuario: str,
    codigo_totp: str | None,
    request: Request,
) -> EstadoNotaMinima:
    """Aplica la nota nueva para los cursos que se creen desde ahora y la audita."""
    nuevo = validar_propuesta(valor)
    vigente = await obtener(sesion)
    # Otro administrador guardó después de que este abrió el formulario: no se sobrescribe.
    if version_esperada != vigente.actualizado_en:
        raise ErrorAplicacion(
            409,
            "PARAMETROS_DESACTUALIZADOS",
            "Otro administrador cambió la nota mínima mientras usted editaba. Recargue y revise el valor.",
        )
    if nuevo == vigente.valor:
        raise ErrorAplicacion(422, "SIN_CAMBIOS", "La nota es igual a la vigente.")

    await exigir_codigo_totp(
        sesion,
        usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        request,
        prefijo_auditoria="PARAMETROS",
        mensaje_requerido="Ingrese el código del autenticador para confirmar el cambio de la nota mínima.",
    )
    await sesion.execute(
        text("""
            UPDATE esart.parametros_habilitacion
            SET valor = CAST(:valor AS jsonb), actualizado_en = now(), actualizado_por_id = :usuario_id
            WHERE codigo = :codigo
        """),
        {"valor": str(nuevo), "usuario_id": usuario_id, "codigo": CODIGO_PARAMETRO},
    )
    # La auditoría va en la misma transacción: si no se puede registrar, no se aplica el cambio.
    # Los valores van como texto para conservar los 2 decimales exactos.
    await auditoria.registrar_evento(
        sesion,
        auditoria.PARAMETROS_ACTUALIZADOS,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "cambios": {CODIGO_PARAMETRO: {"anterior": str(vigente.valor), "nuevo": str(nuevo)}},
            "aplica_a": "cursos nuevos",
        },
    )
    return await obtener(sesion)
