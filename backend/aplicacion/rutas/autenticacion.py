"""Rutas de autenticación: /api/auth (contrato de API, §2)."""

import ipaddress
import math
from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.autenticacion import (
    RespuestaInicioSesion,
    RespuestaUsuarioActual,
    SolicitudInicioSesion,
    UsuarioEnSesion,
)
from aplicacion.modelos import IntentoInicioSesion, Usuario
from aplicacion.nucleo.errores import ErrorAplicacion, construir_respuesta_error
from aplicacion.seguridad import comprobante_bloqueo
from aplicacion.seguridad.captcha import VerificadorCaptcha, obtener_verificador_captcha
from aplicacion.seguridad.sesion_http import (
    borrar_cookies_sesion,
    escribir_cookies_sesion,
    obtener_usuario_actual,
    segundos_de_inactividad_permitidos,
    verificar_csrf,
)
from aplicacion.servicios import estado_bloqueo
from aplicacion.servicios.autenticacion import (
    UsuarioAutenticado,
    cerrar_sesion,
    iniciar_sesion,
    obtener_nombre_completo,
)
from aplicacion.servicios.menu import obtener_menu_y_permisos
from aplicacion.servicios.seguridad_login import reloj_servidor

enrutador_autenticacion = APIRouter(prefix="/auth", tags=["Autenticación"])


def obtener_ip_cliente(request: Request) -> str | None:
    if any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-real-ip")):
        return None
    return request.client.host if request.client else None


@enrutador_autenticacion.get("/captcha")
async def emitir_captcha(
    request: Request,
    respuesta: Response,
    nombre_usuario: str = Header(
        alias="X-ESART-Usuario",
        min_length=3,
        max_length=80,
        description="Usuario del intento: vincula el desafío, no acredita identidad. No requiere JWT.",
    ),
    anterior: str | None = Header(default=None, alias="X-ESART-Captcha-Anterior", max_length=64),
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
):
    from aplicacion.servicios.captcha_local import generar

    respuesta.headers["Cache-Control"] = "no-store"
    return await generar(sesion, nombre_usuario, obtener_ip_cliente(request), anterior)


@enrutador_autenticacion.post("/login", response_model=RespuestaInicioSesion)
async def iniciar_sesion_usuario(
    solicitud: SolicitudInicioSesion,
    request: Request,
    respuesta: Response,
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
    captcha: VerificadorCaptcha = Depends(obtener_verificador_captcha),
) -> RespuestaInicioSesion:
    """
    Verifica usuario y contraseña y entrega la sesión en cookies.

    No exige cabecera CSRF: antes del login no hay sesión que robar, y la cookie
    SameSite=Strict impide que otro sitio la use. El JWT nunca va en el cuerpo.
    """
    try:
        resultado = await iniciar_sesion(
            sesion,
            nombre_usuario=solicitud.nombre_usuario,
            contrasena=solicitud.contrasena,
            # Si llegan cabeceras de proxy, no usar una IP posiblemente reescrita por ASGI.
            # Los orígenes ambiguos comparten un bucket persistente, nunca una IP elegida por el cliente.
            direccion_ip=obtener_ip_cliente(request),
            agente_usuario=request.headers.get("user-agent"),
            captcha_id=solicitud.captcha_id,
            captcha_respuesta=solicitud.captcha_respuesta,
            verificador_captcha=captcha,
        )
    except ErrorAplicacion as error:
        if error.estado_http != 423 or error.codigo != "CUENTA_BLOQUEADA":
            raise
        salida = construir_respuesta_error(423, error.codigo, error.mensaje, error.detalle, error.cabeceras)
        nombre = await sesion.scalar(select(func.lower(solicitud.nombre_usuario.strip())))
        comprobante_bloqueo.escribir(
            salida, nombre, error.detalle["bloqueado_hasta"], error.detalle.get("intento_actual")
        )
        return salida
    comprobante_bloqueo.borrar(respuesta)
    escribir_cookies_sesion(respuesta, resultado.token_sesion)
    return RespuestaInicioSesion(
        usuario=UsuarioEnSesion(
            nombre_usuario=resultado.nombre_usuario,
            nombre_completo=resultado.nombre_completo,
            rol=resultado.rol,
        ),
        expira_por_inactividad_segundos=segundos_de_inactividad_permitidos(),
    )


@enrutador_autenticacion.get("/bloqueo")
async def recuperar_bloqueo(
    request: Request, respuesta: Response, sesion: AsyncSession = Depends(obtener_sesion_base_datos)
):
    comprobante = comprobante_bloqueo.leer_datos(request.cookies.get(comprobante_bloqueo.COOKIE))
    if comprobante is None:
        comprobante_bloqueo.borrar(respuesta)
        return {"bloqueado": False}
    salida = await estado_bloqueo.consultar(sesion, comprobante["sub"])
    if salida["bloqueado"]:
        # Instantánea del envío firmado, no la IP de esta lectura ni el último intento de la cuenta.
        salida["intento_actual"] = comprobante.get("intento_actual")
    if not salida["bloqueado"]:
        comprobante_bloqueo.borrar(respuesta)
    return salida


@enrutador_autenticacion.get("/administracion/bloqueos/{usuario_id}")
async def consultar_bloqueo_administrativo(
    usuario_id: int,
    identidad: UsuarioAutenticado = Depends(obtener_usuario_actual),
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
):
    # Política explícita de esta consulta de seguridad: solo rol administrativo activo.
    if identidad.rol != "ADMINISTRADOR":
        raise ErrorAplicacion(403, "SIN_PERMISO", "No tiene permiso para esta acción.")
    usuario = (
        await sesion.execute(
            select(
                Usuario.id, Usuario.usuario, Usuario.intentos_fallidos_consecutivos, Usuario.bloqueado_hasta
            ).where(Usuario.id == usuario_id)
        )
    ).one_or_none()
    if usuario is None:
        raise ErrorAplicacion(404, "RECURSO_NO_ENCONTRADO", "No se encontró el recurso solicitado.")
    ahora = await reloj_servidor(sesion)
    intento = (
        await sesion.execute(
            select(
                func.host(IntentoInicioSesion.direccion_ip).label("direccion_ip"),
                IntentoInicioSesion.fecha,
                IntentoInicioSesion.motivo_fallo,
            )
            .where(IntentoInicioSesion.usuario_id == usuario_id)
            .order_by(IntentoInicioSesion.fecha.desc(), IntentoInicioSesion.id.desc())
            .limit(1)
        )
    ).one_or_none()
    direccion = intento.direccion_ip if intento else None
    loopback = ipaddress.ip_address(direccion).is_loopback if direccion else None
    return {
        "usuario_id": usuario.id,
        "usuario_intentado": usuario.usuario,
        "detalles_autorizados": True,
        "intentos_fallidos_consecutivos": usuario.intentos_fallidos_consecutivos,
        "bloqueado_hasta": usuario.bloqueado_hasta,
        "bloqueado": bool(usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora),
        "ahora_servidor": ahora,
        "segundos_restantes": max(0, math.ceil((usuario.bloqueado_hasta - ahora).total_seconds()))
        if usuario.bloqueado_hasta
        else 0,
        "direccion_ip": direccion,
        "ip_es_loopback": loopback,
        "ip_terminal_verificada": False,
        "ip_observacion": (
            "Dirección local observada por el backend; no identifica una terminal remota."
            if loopback
            else "Origen observado por el backend; atribución a terminal no verificada."
        )
        if direccion
        else None,
        "ultimo_intento": intento.fecha if intento else None,
        "motivo_ultimo_intento": intento.motivo_fallo if intento else None,
    }


@enrutador_autenticacion.get("/yo", response_model=RespuestaUsuarioActual)
async def obtener_datos_usuario_actual(
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
) -> RespuestaUsuarioActual:
    """Datos del usuario en sesión, su menú y sus permisos (el front arma el sidebar con esto)."""
    menu_y_permisos = await obtener_menu_y_permisos(sesion, usuario.id)
    return RespuestaUsuarioActual(
        nombre_usuario=usuario.nombre_usuario,
        nombre_completo=await obtener_nombre_completo(
            sesion, usuario.documento_identidad, usuario.nombre_usuario
        ),
        rol=usuario.rol,
        permisos=menu_y_permisos.permisos,
        menu=[asdict(elemento) for elemento in menu_y_permisos.menu],
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
