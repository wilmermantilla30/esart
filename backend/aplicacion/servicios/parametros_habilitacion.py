"""
Regla de habilitación editable desde el panel de Parámetros (pestaña Cursos y Capacitaciones).

- Los valores viven en esart.parametros_habilitacion y la verificación los lee en cada consulta:
  un cambio aplica de inmediato a todas las pantallas.
- Antes de guardar se puede SIMULAR: cuántos militares quedarían APTO / NO APTO y cuántos
  cambiarían de resultado. Así nadie vuelve NO APTO a media Escuela sin darse cuenta.
- Guardar exige el código TOTP (política PARAMETROS_MODIFICAR), queda auditado con los valores
  anteriores y nuevos, y rechaza el cambio si otro administrador guardó mientras tanto.
"""

from dataclasses import dataclass
from datetime import datetime

from fastapi import Request
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos import ParametroHabilitacion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp
from aplicacion.servicios.habilitacion import (
    ParametrosHabilitacion,
    cargar_parametros,
    resultados_por_militar,
    resumir_habilitacion,
)

POLITICA_TOTP = "PARAMETROS_MODIFICAR"

# Límites razonables de la regla (evitan errores de digitación como 120 meses o 0 días).
MESES_VIGENCIA_MINIMO, MESES_VIGENCIA_MAXIMO = 1, 60
DIAS_ALERTA_MINIMO, DIAS_ALERTA_MAXIMO = 1, 365
# Un mes tiene al menos 28 días: la alerta debe empezar antes de que el certificado venza.
DIAS_MINIMOS_POR_MES = 28

# Código del parámetro en la tabla -> campo de ParametrosHabilitacion.
CAMPOS = {
    "CURSOS_HABILITANTES": "cursos_habilitantes",
    "MESES_VIGENCIA_REENTRENAMIENTO": "meses_vigencia_reentrenamiento",
    "DIAS_ALERTA_VENCIMIENTO": "dias_alerta_vencimiento",
    "EXIGE_APTO_PARA_DISPARAR": "exige_apto_para_disparar",
}


@dataclass(frozen=True)
class CursoDisponible:
    codigo: str
    nombre: str


async def cursos_disponibles(sesion: AsyncSession) -> list[CursoDisponible]:
    """Tipos de curso activos: las opciones del selector de cursos habilitantes."""
    filas = await sesion.execute(
        text("SELECT codigo, nombre FROM esart.tipos_curso WHERE activo ORDER BY codigo")
    )
    return [CursoDisponible(fila.codigo, fila.nombre) for fila in filas]


async def version_vigente(sesion: AsyncSession) -> datetime | None:
    """Fecha del último cambio de la regla: el front la devuelve al guardar (control de concurrencia)."""
    return await sesion.scalar(text("SELECT max(actualizado_en) FROM esart.parametros_habilitacion"))


async def obtener_regla(sesion: AsyncSession) -> dict:
    """Valores vigentes, quién y cuándo los cambió por última vez, cursos posibles y el resumen actual."""
    parametros = await cargar_parametros(sesion)
    ultimo = (
        await sesion.execute(
            text("""
                SELECT p.actualizado_en, u.usuario AS actualizado_por
                FROM esart.parametros_habilitacion p
                LEFT JOIN esart_ref.usuarios u ON u.id = p.actualizado_por_id
                ORDER BY p.actualizado_en DESC LIMIT 1
            """)
        )
    ).one_or_none()
    return {
        "parametros": parametros,
        "actualizado_en": ultimo.actualizado_en if ultimo else None,
        "actualizado_por": ultimo.actualizado_por if ultimo else None,
        "cursos_disponibles": await cursos_disponibles(sesion),
        "resumen": await resumir_habilitacion(sesion, parametros),
    }


def validar_propuesta(
    cursos: list[str], meses: int, dias: int, exige_apto: bool, disponibles: list[CursoDisponible]
) -> ParametrosHabilitacion:
    """Comprueba la propuesta y la devuelve normalizada (cursos sin repetir, en mayúsculas)."""
    codigos_validos = {curso.codigo for curso in disponibles}
    cursos_normalizados = sorted({codigo.strip().upper() for codigo in cursos if codigo.strip()})
    desconocidos = [codigo for codigo in cursos_normalizados if codigo not in codigos_validos]
    if desconocidos:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", f"Cursos que no existen o están inactivos: {', '.join(desconocidos)}."
        )
    if not MESES_VIGENCIA_MINIMO <= meses <= MESES_VIGENCIA_MAXIMO:
        raise ErrorAplicacion(
            422,
            "DATOS_INVALIDOS",
            f"La vigencia del reentrenamiento debe estar entre {MESES_VIGENCIA_MINIMO} y "
            f"{MESES_VIGENCIA_MAXIMO} meses.",
        )
    if not DIAS_ALERTA_MINIMO <= dias <= DIAS_ALERTA_MAXIMO:
        raise ErrorAplicacion(
            422,
            "DATOS_INVALIDOS",
            f"Los días de alerta deben estar entre {DIAS_ALERTA_MINIMO} y {DIAS_ALERTA_MAXIMO}.",
        )
    if dias >= meses * DIAS_MINIMOS_POR_MES:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "La alerta debe empezar antes de que venza el reentrenamiento."
        )
    return ParametrosHabilitacion(
        cursos_habilitantes=cursos_normalizados,
        meses_vigencia_reentrenamiento=meses,
        dias_alerta_vencimiento=dias,
        exige_apto_para_disparar=exige_apto,
    )


async def simular(sesion: AsyncSession, propuesta: ParametrosHabilitacion) -> dict:
    """Resumen actual frente al propuesto y cuántos militares cambiarían de resultado."""
    vigentes = await cargar_parametros(sesion)
    antes = await resultados_por_militar(sesion, vigentes)
    despues = await resultados_por_militar(sesion, propuesta)
    cambios = [(resultado, despues.get(militar_id)) for militar_id, resultado in antes.items()]
    return {
        "actual": await resumir_habilitacion(sesion, vigentes),
        "propuesto": await resumir_habilitacion(sesion, propuesta),
        "pasan_a_no_apto": cambios.count(("APTO", "NO_APTO")),
        "pasan_a_apto": cambios.count(("NO_APTO", "APTO")),
    }


async def guardar(
    sesion: AsyncSession,
    propuesta: ParametrosHabilitacion,
    version_esperada: datetime | None,
    *,
    usuario_id: int,
    nombre_usuario: str,
    codigo_totp: str | None,
    request: Request,
) -> dict:
    """Aplica la propuesta (solo los valores que cambian) y la audita con antes y después."""
    # Otro administrador guardó después de que este abrió el formulario: no se sobrescribe.
    if version_esperada != await version_vigente(sesion):
        raise ErrorAplicacion(
            409,
            "PARAMETROS_DESACTUALIZADOS",
            "Otro administrador cambió la regla mientras usted editaba. Recargue y revise los valores.",
        )
    vigentes = await cargar_parametros(sesion)
    cambios = {
        codigo: {"anterior": getattr(vigentes, campo), "nuevo": getattr(propuesta, campo)}
        for codigo, campo in CAMPOS.items()
        if getattr(vigentes, campo) != getattr(propuesta, campo)
    }
    if not cambios:
        raise ErrorAplicacion(422, "SIN_CAMBIOS", "Los valores son iguales a los vigentes.")

    await exigir_codigo_totp(
        sesion,
        usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        request,
        prefijo_auditoria="PARAMETROS",
        mensaje_requerido="Ingrese el código del autenticador para confirmar el cambio de la regla.",
    )
    ahora = await sesion.scalar(text("SELECT now()"))
    for codigo, cambio in cambios.items():
        await sesion.execute(
            update(ParametroHabilitacion)
            .where(ParametroHabilitacion.codigo == codigo)
            .values(valor=cambio["nuevo"], actualizado_en=ahora, actualizado_por_id=usuario_id)
        )
    # La auditoría va en la misma transacción: si no se puede registrar, no se aplica el cambio.
    await auditoria.registrar_evento(
        sesion,
        auditoria.PARAMETROS_ACTUALIZADOS,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={"cambios": cambios},
    )
    return await obtener_regla(sesion)
