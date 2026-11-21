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
    from sqlalchemy.engine import make_url

    from aplicacion.base_datos.configuracion import obtener_configuracion_conexion

    configuracion = obtener_configuracion_conexion()
    url_aplicacion = make_url(configuracion.url_base_datos.get_secret_value())
    if (
        configuracion.entorno != "desarrollo"
        or url_aplicacion.database != "esart_db"
        or url_aplicacion.host not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise RuntimeError("Alembic operativo requiere la configuracion local de desarrollo.")
    identidad = conexion.execute(
        text("""
        SELECT current_database(), current_user, host(inet_server_addr()), r.rolsuper
        FROM pg_roles r WHERE r.rolname=current_user
    """)
    ).one_or_none()
    if identidad is None:
        raise RuntimeError("No fue posible validar la cuenta migradora.")
    base, usuario, servidor, superusuario = identidad
    prueba_p0018 = os.environ.get("ESART_VALIDAR_P0018_COPIA") == "1"

    bases_prueba_permitidas = {
        "esart_db_p0018_restore_test",
        "esart_ensayo",
    }

    base_permitida = base == "esart_db" or (prueba_p0018 and base in bases_prueba_permitidas)
    if (
        not base_permitida
        or usuario != "esart_migrador"
        or servidor not in ("127.0.0.1", "::1")
        or superusuario
    ):
        raise RuntimeError(
            "Alembic requiere esart_migrador no-superusuario en PostgreSQL local de desarrollo."
        )
    # PostgreSQL exige CREATE sobre la base incluso con IF NOT EXISTS.
    existe_esart = conexion.scalar(
        text("SELECT EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname = 'esart')")
    )
    if not existe_esart:
        puede_crear = conexion.scalar(
            text("SELECT pg_catalog.has_database_privilege(current_database(), 'CREATE')")
        )
        if not puede_crear:
            raise RuntimeError(
                f"Falta el esquema esart en {base}. El rol {usuario} requiere CREATE sobre la base."
            )
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
