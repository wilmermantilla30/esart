"""
Manejo único de errores de la API.

Todas las respuestas de error tienen la misma forma (docs/contrato_api.md, §1.2):

    {"error": {"codigo": "...", "mensaje": "...", "detalle": {...}}}

Así el front tiene un solo manejador de errores. Además, este módulo garantiza
que ninguna respuesta de error exponga detalles internos (trazas, SQL) ni
devuelva los datos enviados por el usuario (podrían incluir su contraseña).
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as ExcepcionHttpStarlette

registrador = logging.getLogger(__name__)

# Código del contrato para cada estado HTTP genérico (los que lanza el propio
# FastAPI, como una ruta inexistente). Los errores de negocio usan ErrorAplicacion.
CODIGOS_POR_ESTADO_HTTP = {
    401: "NO_AUTENTICADO",
    403: "SIN_PERMISO",
    404: "RECURSO_NO_ENCONTRADO",
    405: "METODO_NO_PERMITIDO",
}

MENSAJES_POR_ESTADO_HTTP = {
    401: "Debe iniciar sesión.",
    403: "No tiene permiso para esta acción.",
    404: "El recurso solicitado no existe.",
    405: "Método no permitido para este recurso.",
}


class ErrorAplicacion(Exception):
    """
    Error de negocio que se convierte en una respuesta con el formato del contrato.

    Uso en servicios y rutas:
        raise ErrorAplicacion(404, "ARTILLERO_NO_ENCONTRADO", "No se encontró un militar con esa cédula.")
    """

    def __init__(
        self,
        estado_http: int,
        codigo: str,
        mensaje: str,
        detalle: dict[str, Any] | None = None,
        cabeceras: dict[str, str] | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.estado_http = estado_http
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalle = detalle
        self.cabeceras = cabeceras


def construir_respuesta_error(
    estado_http: int,
    codigo: str,
    mensaje: str,
    detalle: dict[str, Any] | None = None,
    cabeceras: dict[str, str] | None = None,
) -> JSONResponse:
    """Construye la respuesta JSON de error con la forma única del contrato."""
    return JSONResponse(
        status_code=estado_http,
        content={"error": {"codigo": codigo, "mensaje": mensaje, "detalle": detalle}},
        headers=cabeceras,
    )


async def _manejar_error_aplicacion(_peticion: Request, error: ErrorAplicacion) -> JSONResponse:
    """Convierte un ErrorAplicacion lanzado por el código en su respuesta."""
    return construir_respuesta_error(
        error.estado_http, error.codigo, error.mensaje, error.detalle, error.cabeceras
    )


async def _manejar_error_http(_peticion: Request, error: ExcepcionHttpStarlette) -> JSONResponse:
    """Convierte los errores HTTP genéricos (404 de ruta, 405, etc.) al formato del contrato."""
    codigo = CODIGOS_POR_ESTADO_HTTP.get(error.status_code, "ERROR_HTTP")
    mensaje = MENSAJES_POR_ESTADO_HTTP.get(error.status_code, "No se pudo procesar la solicitud.")
    return construir_respuesta_error(
        error.status_code, codigo, mensaje, cabeceras=getattr(error, "headers", None)
    )


async def _manejar_error_validacion(_peticion: Request, error: RequestValidationError) -> JSONResponse:
    """
    Convierte los errores de validación de datos de entrada (422).

    Por qué no se usa la respuesta por defecto de FastAPI: esa respuesta repite
    el valor recibido en el campo "input", y si el error es en el login ese
    valor puede ser la contraseña. Aquí solo se devuelve el campo y el motivo.
    """
    campos = [
        {
            # La ubicación llega como ("body", "nombre_usuario"); se une con puntos.
            "campo": ".".join(str(parte) for parte in detalle_error.get("loc", ())),
            "motivo": detalle_error.get("msg", "Valor inválido"),
        }
        for detalle_error in error.errors()
    ]
    return construir_respuesta_error(
        422, "DATOS_INVALIDOS", "Los datos enviados no son válidos.", {"campos": campos}
    )


async def _manejar_error_inesperado(_peticion: Request, error: Exception) -> JSONResponse:
    """
    Último recurso para cualquier error no previsto (500).

    Al cliente solo se le da un mensaje genérico: los detalles técnicos ayudan
    a un atacante y no le sirven al usuario. La traza completa la escribe el
    servidor en los logs (que pasan por el filtro de datos sensibles).
    """
    registrador.error("Error inesperado procesando la solicitud: %s", type(error).__name__)
    return construir_respuesta_error(
        500, "ERROR_INTERNO", "Ocurrió un error interno. Intente de nuevo o contacte al administrador."
    )


def registrar_manejadores_errores(aplicacion: FastAPI) -> None:
    """Instala en la aplicación todos los manejadores de error de este módulo."""
    aplicacion.add_exception_handler(ErrorAplicacion, _manejar_error_aplicacion)
    aplicacion.add_exception_handler(ExcepcionHttpStarlette, _manejar_error_http)
    aplicacion.add_exception_handler(RequestValidationError, _manejar_error_validacion)
    aplicacion.add_exception_handler(Exception, _manejar_error_inesperado)
