"""
Motor de conexión y sesiones asíncronas a la base de datos.

Regla del proyecto: toda consulta a la base de datos obtiene su sesión con la
dependencia obtener_sesion_base_datos(). No se crean motores ni sesiones en
otros módulos.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from aplicacion.base_datos.configuracion import opciones_tls_local
from aplicacion.configuracion import obtener_configuracion

# Segundos tras los cuales una conexión del grupo se renueva. Evita usar
# conexiones que un firewall o el servidor cerraron por inactividad.
SEGUNDOS_RECICLAJE_CONEXIONES = 1800

# Tiempo máximo de una consulta. Si una consulta tarda más, se cancela en lugar
# de dejar al comandante esperando indefinidamente.
SEGUNDOS_MAXIMOS_POR_CONSULTA = 30


@lru_cache
def obtener_motor_base_datos() -> AsyncEngine:
    """
    Devuelve el motor de conexión (uno solo para toda la aplicación).

    El motor administra un grupo de conexiones reutilizables; crear uno por
    petición agotaría las conexiones de PostgreSQL. create_async_engine no se
    conecta todavía: la primera conexión se abre con la primera consulta.
    """
    configuracion = obtener_configuracion()
    return create_async_engine(
        configuracion.url_base_datos.get_secret_value(),
        pool_size=configuracion.tamano_pool_conexiones,
        max_overflow=configuracion.tamano_pool_conexiones,
        # Verifica que la conexión siga viva antes de entregarla.
        pool_pre_ping=True,
        pool_recycle=SEGUNDOS_RECICLAJE_CONEXIONES,
        # Nunca escribir el SQL en los logs, y si una consulta falla, no incluir
        # los valores de los parámetros (cédulas, hashes) en el mensaje de error.
        echo=False,
        hide_parameters=True,
        connect_args={
            **opciones_tls_local(configuracion.url_base_datos.get_secret_value()),
            "timeout": configuracion.segundos_espera_conexion,
            "command_timeout": SEGUNDOS_MAXIMOS_POR_CONSULTA,
        },
    )


@lru_cache
def obtener_fabrica_sesiones() -> async_sessionmaker[AsyncSession]:
    """Devuelve la fábrica de sesiones ligada al motor único."""
    return async_sessionmaker(
        obtener_motor_base_datos(),
        # Permite seguir leyendo los objetos después del commit sin otra consulta.
        expire_on_commit=False,
        autoflush=False,
    )


async def obtener_sesion_base_datos() -> AsyncIterator[AsyncSession]:
    """
    Dependencia de FastAPI que entrega una sesión por petición y la cierra al terminar.

    La sesión no hace commit automático: cada servicio que modifica datos debe
    confirmar (commit) explícitamente. Si la petición falla antes, al cerrar la
    sesión se descartan los cambios pendientes.
    """
    async with obtener_fabrica_sesiones()() as sesion:
        yield sesion


async def cerrar_motor_base_datos() -> None:
    """Cierra todas las conexiones del grupo. Se llama al apagar la aplicación."""
    # Solo se cierra si el motor llegó a crearse (si no, crearlo para cerrarlo sobra).
    if obtener_motor_base_datos.cache_info().currsize > 0:
        await obtener_motor_base_datos().dispose()
