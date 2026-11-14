"""
Ruta de salud: permite saber si la aplicación y la base de datos responden.

No requiere autenticación porque la usan herramientas de monitoreo. Por eso no
devuelve versiones, nombres de servidores ni mensajes de error técnicos.
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos

registrador = logging.getLogger(__name__)

enrutador_salud = APIRouter(prefix="/salud", tags=["Salud"])


@enrutador_salud.get("", summary="Estado de la aplicación y de la base de datos")
async def consultar_salud(
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
) -> JSONResponse:
    """
    Responde 200 si la base de datos contesta, o 503 si no.

    Se hace una consulta mínima (SELECT 1) para comprobar la conexión real,
    no solo que el proceso de la aplicación esté vivo.
    """
    try:
        await sesion.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001
        # Se captura cualquier error a propósito: la ruta de salud nunca debe
        # fallar con 500; su trabajo es informar que la base de datos no responde.
        # Solo se registra el tipo de error, no su mensaje (podría incluir el servidor o el usuario).
        registrador.warning(
            "La base de datos no respondió a la verificación de salud: %s", type(error).__name__
        )
        return JSONResponse(status_code=503, content={"estado": "degradado", "base_datos": "error"})

    return JSONResponse(status_code=200, content={"estado": "ok", "base_datos": "ok"})
