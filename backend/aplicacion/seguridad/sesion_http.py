"""
Cookies de sesión, protección CSRF y dependencia del usuario autenticado.

Contrato de API, §1.1:
- 'esart_sesion': JWT, HttpOnly (JavaScript no la puede leer), SameSite=Strict.
- 'esart_csrf': valor aleatorio legible por Angular, que lo devuelve en la
  cabecera X-CSRF-Token en cada POST/PUT/DELETE (doble cookie).
Ninguna lleva Max-Age: son cookies de sesión del navegador.
"""

import secrets

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.tokens import TokenSesionInvalido, decodificar_token_sesion
from aplicacion.servicios.autenticacion import UsuarioAutenticado, validar_sesion

NOMBRE_COOKIE_SESION = "esart_sesion"
NOMBRE_COOKIE_CSRF = "esart_csrf"
NOMBRE_CABECERA_CSRF = "X-CSRF-Token"

# Bytes aleatorios del valor CSRF (32 bytes = 256 bits).
BYTES_TOKEN_CSRF = 32

# Métodos que no modifican datos y por eso no exigen la cabecera CSRF.
METODOS_SIN_VERIFICACION_CSRF = frozenset({"GET", "HEAD", "OPTIONS"})


def escribir_cookies_sesion(respuesta: Response, token_sesion: str) -> None:
    """Pone en la respuesta la cookie con el JWT y una cookie CSRF nueva."""
    cookie_segura = obtener_configuracion().cookie_segura
    respuesta.set_cookie(
        NOMBRE_COOKIE_SESION,
        token_sesion,
        httponly=True,
        secure=cookie_segura,
        samesite="strict",
        path="/",
    )
    # Esta NO es httponly a propósito: Angular necesita leerla para copiarla en la cabecera.
    respuesta.set_cookie(
        NOMBRE_COOKIE_CSRF,
        secrets.token_urlsafe(BYTES_TOKEN_CSRF),
        httponly=False,
        secure=cookie_segura,
        samesite="strict",
        path="/",
    )


def borrar_cookies_sesion(respuesta: Response) -> None:
    """Elimina las dos cookies en el navegador (cierre de sesión o sesión inválida)."""
    cookie_segura = obtener_configuracion().cookie_segura
    for nombre_cookie, solo_http in ((NOMBRE_COOKIE_SESION, True), (NOMBRE_COOKIE_CSRF, False)):
        respuesta.delete_cookie(
            nombre_cookie, path="/", secure=cookie_segura, httponly=solo_http, samesite="strict"
        )


async def verificar_csrf(request: Request) -> None:
    """
    Dependencia: en métodos que modifican datos exige que la cabecera X-CSRF-Token
    coincida con la cookie esart_csrf.

    Un sitio malicioso puede hacer que el navegador envíe las cookies, pero no
    puede leer esart_csrf para copiarla en la cabecera: así se frena el CSRF.
    """
    if request.method in METODOS_SIN_VERIFICACION_CSRF:
        return
    valor_cookie = request.cookies.get(NOMBRE_COOKIE_CSRF, "")
    valor_cabecera = request.headers.get(NOMBRE_CABECERA_CSRF, "")
    # compare_digest compara en tiempo constante (no revela cuántos caracteres coinciden).
    if not valor_cookie or not secrets.compare_digest(valor_cookie, valor_cabecera):
        raise ErrorAplicacion(403, "SIN_PERMISO", "No tiene permiso para esta acción.")


async def obtener_usuario_actual(
    request: Request,
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
) -> UsuarioAutenticado:
    """
    Dependencia: devuelve el usuario de la sesión, o responde 401.

    La identidad sale SOLO del JWT firmado de la cookie y de la fila de
    sesiones_usuario; nunca de datos enviados por el navegador. Cada llamada válida
    reinicia la ventana de inactividad (validar_sesion).
    """
    token_sesion = request.cookies.get(NOMBRE_COOKIE_SESION)
    if not token_sesion:
        raise ErrorAplicacion(401, "NO_AUTENTICADO", "Debe iniciar sesión.")
    try:
        datos_token = decodificar_token_sesion(token_sesion)
    except TokenSesionInvalido:
        raise ErrorAplicacion(401, "NO_AUTENTICADO", "Debe iniciar sesión.") from None
    return await validar_sesion(sesion, datos_token.usuario_id, datos_token.sesion_id)
