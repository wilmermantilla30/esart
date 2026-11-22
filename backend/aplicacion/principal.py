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
from aplicacion.base_datos.sesion import cerrar_motor_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import registrar_manejadores_errores
from aplicacion.nucleo.front_estatico import registrar_cabeceras_seguridad, registrar_front
from aplicacion.nucleo.registro import configurar_registro
from aplicacion.rutas.acciones_seguras import enrutador as enrutador_acciones
from aplicacion.rutas.administracion import enrutador_administracion
from aplicacion.rutas.autenticacion import enrutador_autenticacion
from aplicacion.rutas.cursos import enrutador_cursos
from aplicacion.rutas.estadisticas import enrutador_estadisticas
from aplicacion.rutas.importaciones import enrutador as enrutador_importaciones
from aplicacion.rutas.instructores import enrutador_instructores
from aplicacion.rutas.parametros import enrutador_parametros
from aplicacion.rutas.personal import enrutador_personal
from aplicacion.rutas.salud import enrutador_salud
from aplicacion.rutas.totp import enrutador as enrutador_totp
from aplicacion.rutas.unidades import enrutador as enrutador_catalogos
from aplicacion.rutas.verificacion import enrutador_verificacion

registrador = logging.getLogger(__name__)

# Todas las rutas de la API viven bajo /api; las páginas del dashboard quedan
# fuera de este prefijo (ver docs/contrato_api.md, §1).
PREFIJO_API = "/api"


@asynccontextmanager
async def ciclo_de_vida(_aplicacion: FastAPI) -> AsyncIterator[None]:
    """Tareas al arrancar y al apagar la aplicación."""
    configuracion = obtener_configuracion()
    registrador.info("ESART %s iniciando en entorno '%s'", VERSION_APLICACION, configuracion.entorno)
    # El alta inicial requiere el comando administrativo y autorización explícita.
    yield
    # Al apagar se devuelven las conexiones a PostgreSQL.
    await cerrar_motor_base_datos()
    registrador.info("ESART detenido")


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

    # Cabeceras de seguridad y no-store en los datos de la API (HU-21).
    registrar_cabeceras_seguridad(aplicacion, https=configuracion.cookie_segura)

    @aplicacion.middleware("http")
    async def no_cachear_autenticacion(request, call_next):
        respuesta = await call_next(request)
        if request.url.path.startswith(
            ("/api/auth/", "/api/v1/auth/", "/api/seguridad/", "/api/v1/seguridad/")
        ):
            respuesta.headers["Cache-Control"] = "no-store"
            respuesta.headers["Pragma"] = "no-cache"
        return respuesta

    aplicacion.include_router(enrutador_salud, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_autenticacion, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_catalogos, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_verificacion, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_estadisticas, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_importaciones, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_administracion, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_parametros, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_instructores, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_cursos, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_personal, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_totp, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_autenticacion, prefix="/api/v1")
    aplicacion.include_router(enrutador_totp, prefix="/api/v1")
    aplicacion.include_router(enrutador_acciones, prefix=PREFIJO_API)
    aplicacion.include_router(enrutador_acciones, prefix="/api/v1")

    # Al final: la ruta comodín del dashboard no debe tapar ninguna ruta de la API.
    registrar_front(aplicacion, configuracion.ruta_front)

    return aplicacion


aplicacion = crear_aplicacion()
