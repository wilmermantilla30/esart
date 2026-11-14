"""
Configuración común de las pruebas.

Las variables de entorno se fijan AQUÍ, antes de importar la aplicación, para
que las pruebas nunca dependan del .env de quien las ejecuta ni toquen una base
de datos real. Las variables del sistema tienen prioridad sobre el .env.
"""

import os

# Valores falsos solo para pruebas. No son secretos reales.
VARIABLES_ENTORNO_PRUEBAS = {
    "ENTORNO": "pruebas",
    "NIVEL_REGISTRO": "WARNING",
    "URL_BASE_DATOS": "postgresql+asyncpg://usuario_pruebas:clave_pruebas@localhost:5432/esart_pruebas",
    "JWT_CLAVE_SECRETA": "clave-de-pruebas-que-tiene-mas-de-treinta-y-dos-caracteres",
    "COOKIE_SEGURA": "false",
    "ADMIN_USUARIO": "admin.pruebas",
    # Hash bcrypt con la forma correcta (no corresponde a ninguna contraseña real).
    "ADMIN_HASH_CONTRASENA": "$2b$12$" + "a" * 53,
}
os.environ.update(VARIABLES_ENTORNO_PRUEBAS)

import httpx  # noqa: E402
import pytest  # noqa: E402

from aplicacion.principal import aplicacion  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    """Las pruebas asíncronas corren sobre asyncio (el mismo motor que usa uvicorn)."""
    return "asyncio"


@pytest.fixture
async def cliente_api():
    """
    Cliente HTTP que llama a la aplicación en memoria, sin levantar un servidor.

    Al terminar cada prueba se limpian las dependencias reemplazadas, para que
    una prueba no afecte a la siguiente.
    """
    transporte = httpx.ASGITransport(app=aplicacion)
    async with httpx.AsyncClient(transport=transporte, base_url="http://pruebas") as cliente:
        yield cliente
    aplicacion.dependency_overrides.clear()
