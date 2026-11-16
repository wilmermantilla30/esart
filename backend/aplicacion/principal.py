"""
Punto de entrada de ESART.

Arranque local (desde la carpeta backend/):
    python -m uvicorn aplicacion.principal:aplicacion --reload --port 8081
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aplicacion import VERSION_APLICACION
from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import registrar_manejadores_errores
from aplicacion.nucleo.registro import configurar_registro
from aplicacion.rutas.autenticacion import enrutador_autenticacion
from aplicacion.rutas.salud import enrutador_salud
from aplicacion.rutas.unidades import enrutador as enrutador_catalogos
from aplicacion.servicios.autenticacion import asegurar_administrador_inicial

registrador = logging.getLogger(__name__)

# Todas las rutas de la API viven bajo /api; las páginas del dashboard quedan
# fuera de este prefijo (ver docs/contrato_api.md, §1).
PREFIJO_API = "/api"


@asynccontextmanager
async def ciclo_de_vida(_aplicacion: FastAPI) -> AsyncIterator[None]:
    """Tareas al arrancar y al apagar la aplicación."""
    configuracion = obtener_configuracion()
    registrador.info("ESART %s iniciando en entorno '%s'", VERSION_APLICACION, configuracion.entorno)
    await crear_administrador_inicial_si_falta()
    yield
    # Al apagar se devuelven las conexiones a PostgreSQL.
    await cerrar_motor_base_datos()
    registrador.info("ESART detenido")


async def crear_administrador_inicial_si_falta() -> None:
    """
    Crea el administrador del .env si no existe (ver servicios/autenticacion.py).

    Si la base no responde o le falta la migración, la API arranca igual: /api/salud
    mostrará el problema y el registro guarda solo el tipo de error, sin datos de conexión.
    """
    try:
        async with obtener_fabrica_sesiones()() as sesion:
            await asegurar_administrador_inicial(sesion)
    except Exception as error:  # noqa: BLE001 - el arranque no debe caerse por esto
        registrador.error(
            "No se pudo verificar el administrador inicial (%s). Revise la base de datos.",
            type(error).__name__,
        )


def crear_aplicacion() -> FastAPI:
    """
    Construye la aplicación FastAPI con su configuración, errores y rutas.

    Se usa una función (en vez de crear la aplicación suelta en el módulo) para
    que las pruebas puedan construir aplicaciones con configuraciones distintas.
    """
    # Lee y valida el .env: si algo es inseguro, la aplicación no arranca aquí.
    configuracion = obtener_configuracion()
    configurar_registro(configuracion.nivel_registro)

    # En producción no se publica la documentación interactiva de la API:
    # le daría a un atacante el mapa completo de rutas.
    documentacion_visible = not configuracion.es_produccion

    aplicacion = FastAPI(
        title=configuracion.nombre_aplicacion,
        description="Verificación de habilitación de artilleros — Escuela de Artillería",
        version=VERSION_APLICACION,
        lifespan=ciclo_de_vida,
        docs_url=f"{PREFIJO_API}/documentacion" if documentacion_visible else None,
        openapi_url=f"{PREFIJO_API}/openapi.json" if documentacion_visible else None,
        redoc_url=None,
    )

    registrar_manejadores_errores(aplicacion)
    aplicacion.include_router(enrutador_salud, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_autenticacion, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_catalogos, prefix=PREFIJO_API)

    return aplicacion


aplicacion = crear_aplicacion()
