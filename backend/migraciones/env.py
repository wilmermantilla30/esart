"""Entorno Alembic asíncrono; no crea tablas al importar la aplicación."""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion import modelos  # noqa: F401: registra los modelos en los metadatos
from aplicacion.base_datos.base import BaseModelo
from aplicacion.base_datos.configuracion import ConfiguracionConexion, obtener_configuracion_conexion
from aplicacion.nucleo.registro import configurar_registro

opciones_cli = context.get_x_argument(as_dictionary=True)
archivo_env = opciones_cli.get("archivo_env")
configuracion = (
    ConfiguracionConexion(_env_file=archivo_env)
    if archivo_env
    else context.config.attributes.get("configuracion_conexion") or obtener_configuracion_conexion()
)
configurar_registro(configuracion.nivel_registro)
target_metadata = BaseModelo.metadata

# Con metadatos vacíos, autogenerate podría proponer borrar tablas existentes.
if getattr(context.config.cmd_opts, "autogenerate", False) and not target_metadata.tables:
    raise RuntimeError("No se puede autogenerar una revisión sin modelos registrados.")


def configurar_contexto(**opciones: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        **opciones,
    )


def ejecutar_migraciones_sin_conexion() -> None:
    configurar_contexto(
        url=configuracion.url_base_datos.get_secret_value(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_con_conexion(conexion: Connection) -> None:
    configurar_contexto(connection=conexion)
    with context.begin_transaction():
        context.run_migrations()


async def ejecutar_migraciones_asincronas() -> None:
    motor = create_async_engine(
        configuracion.url_base_datos.get_secret_value(),
        poolclass=pool.NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={"timeout": configuracion.segundos_espera_conexion},
    )
    try:
        async with motor.connect() as conexion:
            await conexion.run_sync(ejecutar_con_conexion)
    finally:
        await motor.dispose()


if context.is_offline_mode():
    ejecutar_migraciones_sin_conexion()
elif context.config.attributes.get("connection") is not None:
    ejecutar_con_conexion(context.config.attributes["connection"])
else:
    asyncio.run(ejecutar_migraciones_asincronas())
