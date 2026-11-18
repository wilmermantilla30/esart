"""
Confirmación con el código del autenticador (TOTP) para acciones sensibles.

Es el mismo procedimiento que usaba el cargue masivo por Excel, sacado aquí para que lo
reutilicen todas las acciones que lo exigen (importar personal, cambiar la regla de
habilitación, ...). Cada acción se identifica por su política en seguridad.politicas_accion.

- Sin TOTP habilitado en la configuración no se pide código (entornos de desarrollo).
- Sin código: 409 TOTP_REQUERIDO (el front abre la ventana del autenticador y reintenta).
- Código inválido: queda registrado en la auditoría de seguridad y responde 422.
- Usa el límite de intentos por IP y usuario del servicio TOTP.
"""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.permisos import tiene_permiso_codigo
from aplicacion.seguridad.sesion_http import obtener_ip_cliente


async def exigir_codigo_totp(
    sesion: AsyncSession,
    usuario_id: int,
    codigo_politica: str,
    codigo: str | None,
    request: Request,
    *,
    prefijo_auditoria: str,
    mensaje_requerido: str,
) -> None:
    """
    Verifica el código TOTP del usuario para la política indicada.

    prefijo_auditoria nombra los eventos de seguridad: <prefijo>_TOTP_VERIFICADO / _INVALIDO.
    """
    if not obtener_configuracion().totp_habilitado:
        return
    # Importación diferida: el servicio TOTP carga modelos y cifrado que no todos usan.
    from aplicacion.servicios.totp import TotpService

    servicio = TotpService(sesion)
    politica = await servicio.politica(codigo_politica)
    if politica.permiso_requerido not in (None, codigo_politica) and not await tiene_permiso_codigo(
        sesion, usuario_id, politica.permiso_requerido
    ):
        raise ErrorAplicacion(403, "SIN_PERMISO", "No tiene permiso para esta acción.")
    if not codigo:
        raise ErrorAplicacion(409, "TOTP_REQUERIDO", mensaje_requerido)
    ip = obtener_ip_cliente(request)
    await servicio.limitar(ip, usuario_id)
    await servicio.usuario(usuario_id)
    registro = await servicio.registro(usuario_id)
    if not registro or registro.estado != "ACTIVO" or not await servicio.verificar(registro, codigo):
        await servicio.auditar(usuario_id, f"{prefijo_auditoria}_TOTP_INVALIDO", "DENEGADO", ip)
        # Se confirma para conservar el límite de intentos y la auditoría; la acción no se aplicó.
        await sesion.commit()
        raise ErrorAplicacion(422, "TOTP_INVALIDO", "Código del autenticador inválido o ya utilizado.")
    await servicio.auditar(usuario_id, f"{prefijo_auditoria}_TOTP_VERIFICADO", "EXITOSO", ip)
