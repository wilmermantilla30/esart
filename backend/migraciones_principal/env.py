"""Historial operativo independiente: nunca aplica 0001/0002 UUID a esart_db."""

import asyncio
import os

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion import modelos  # noqa: F401
from aplicacion.base_datos.base import BaseModelo
from aplicacion.base_datos.configuracion import opciones_tls_local

target_metadata = BaseModelo.metadata


def ejecutar(conexion):
    if conexion.scalar(text("SELECT current_database()")) != "esart_db":
        raise RuntimeError("Alembic operativo solo admite esart_db")
    # La tabla de versiones vive en el esquema esart: en una base vacía hay que crearlo
    # antes de que Alembic la cree (p0000 instala el resto de la estructura).
    conexion.execute(text("CREATE SCHEMA IF NOT EXISTS esart"))
    context.configure(
        connection=conexion,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
        version_table_schema="esart",
    )
    with context.begin_transaction():
        context.run_migrations()


async def principal():
    # Credencial administrativa efímera del operador; nunca reutilizar la de FastAPI.
    url = os.environ.get("ESART_MIGRACIONES_URL")
    if not url:
        raise RuntimeError("No hay conexión de migraciones; no se utiliza la cuenta de FastAPI")
    motor = create_async_engine(
        url, poolclass=pool.NullPool, hide_parameters=True, connect_args=opciones_tls_local(url)
    )
    try:
        async with motor.begin() as conexion:
            await conexion.run_sync(ejecutar)
    finally:
        await motor.dispose()


if context.is_offline_mode():
    raise RuntimeError("Esta línea base requiere comprobar el catálogo real; no admite stamp ni SQL offline")
if getattr(context.config.cmd_opts, "autogenerate", False):
    raise RuntimeError(
        "Autogenerate pendiente de conciliar funciones y triggers; revisar migraciones manualmente"
    )
if context.config.attributes.get("connection") is not None:
    ejecutar(context.config.attributes["connection"])
else:
    asyncio.run(principal())
