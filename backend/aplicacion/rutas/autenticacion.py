"""Rutas de autenticación: /api/auth (contrato de API, §2)."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.esquemas.autenticacion import (
    RespuestaInicioSesion,
    RespuestaUsuarioActual,
    SolicitudInicioSesion,
    UsuarioEnSesion,
)
from aplicacion.seguridad.sesion_http import (
    borrar_cookies_sesion,
    escribir_cookies_sesion,
    obtener_usuario_actual,
    verificar_csrf,
)
from aplicacion.servicios.autenticacion import (
    UsuarioAutenticado,
    cerrar_sesion,
    iniciar_sesion,
    obtener_nombre_completo,
)

enrutador_autenticacion = APIRouter(prefix="/auth", tags=["Autenticación"])

SEGUNDOS_POR_MINUTO = 60


def segundos_de_inactividad_permitidos() -> int:
    """Tiempo de inactividad tras el cual se cierra la sesión (MINUTOS_INACTIVIDAD_SESION)."""
    return obtener_configuracion().minutos_inactividad_sesion * SEGUNDOS_POR_MINUTO


@enrutador_autenticacion.post("/login", response_model=RespuestaInicioSesion)
async def iniciar_sesion_usuario(
    solicitud: SolicitudInicioSesion,
    request: Request,
    respuesta: Response,
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
) -> RespuestaInicioSesion:
    """
    Verifica usuario y contraseña y entrega la sesión en cookies.

    No exige cabecera CSRF: antes del login no hay sesión que robar, y la cookie
    SameSite=Strict impide que otro sitio la use. El JWT nunca va en el cuerpo.
    """
    resultado = await iniciar_sesion(
        sesion,
        nombre_usuario=solicitud.nombre_usuario,
        contrasena=solicitud.contrasena,
        direccion_ip=request.client.host if request.client else None,
        agente_usuario=request.headers.get("user-agent"),
    )
    escribir_cookies_sesion(respuesta, resultado.token_sesion)
    return RespuestaInicioSesion(
        usuario=UsuarioEnSesion(
            nombre_usuario=resultado.nombre_usuario,
            nombre_completo=resultado.nombre_completo,
            rol=resultado.rol,
        ),
        expira_por_inactividad_segundos=segundos_de_inactividad_permitidos(),
    )


@enrutador_autenticacion.get("/yo", response_model=RespuestaUsuarioActual)
async def obtener_datos_usuario_actual(
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
) -> RespuestaUsuarioActual:
    """Datos del usuario en sesión. El front lo llama al recargar para recuperar la sesión."""
    return RespuestaUsuarioActual(
        nombre_usuario=usuario.nombre_usuario,
        nombre_completo=await obtener_nombre_completo(
            sesion, usuario.documento_identidad, usuario.nombre_usuario
        ),
        rol=usuario.rol,
        permisos=[],
        expira_por_inactividad_segundos=segundos_de_inactividad_permitidos(),
    )


@enrutador_autenticacion.post(
    "/cerrar-sesion", status_code=204, response_class=Response, dependencies=[Depends(verificar_csrf)]
)
async def cerrar_sesion_usuario(
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
) -> Response:
    """Revoca la sesión en el servidor y borra las cookies. 204 sin cuerpo."""
    await cerrar_sesion(sesion, usuario.sesion_id)
    respuesta = Response(status_code=204)
    borrar_cookies_sesion(respuesta)
    return respuesta
