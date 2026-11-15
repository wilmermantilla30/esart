"""Inventario HU-03 de solo lectura, sin mostrar credenciales ni datos de negocio."""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Column, MetaData, String, Table, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from aplicacion.base_datos.configuracion import ConfiguracionConexion, obtener_configuracion_conexion


async def inspeccionar(configuracion: ConfiguracionConexion) -> dict:
    """Consulta identidad, tablas y revisiones en una transacción READ ONLY."""
    motor = create_async_engine(
        configuracion.url_base_datos.get_secret_value(),
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={"timeout": configuracion.segundos_espera_conexion, "command_timeout": 30},
    )
    try:
        async with motor.connect() as conexion, conexion.begin():
            await conexion.execute(text("SET TRANSACTION READ ONLY"))
            identidad = (await conexion.execute(text(
                "SELECT current_database() AS base_datos, current_user AS usuario, "
                "inet_server_port() AS puerto, current_schema() AS esquema, "
                "current_setting('search_path') AS search_path"
            ))).mappings().one()
            tablas = (await conexion.execute(text(
                "SELECT schemaname AS esquema, tablename AS tabla FROM pg_catalog.pg_tables "
                "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
                "AND schemaname NOT LIKE 'pg_toast%' ORDER BY schemaname, tablename"
            ))).mappings().all()
            revisiones = []
            for tabla in tablas:
                if tabla["tabla"] == "alembic_version":
                    version = Table(
                        "alembic_version", MetaData(), Column("version_num", String),
                        schema=tabla["esquema"],
                    )
                    valores = (await conexion.execute(select(version.c.version_num))).scalars().all()
                    revisiones.append({"esquema": tabla["esquema"], "revisiones": valores})
            return {
                "conexion": dict(identidad),
                "tablas": [dict(tabla) for tabla in tablas],
                "alembic": revisiones,
            }
    finally:
        await motor.dispose()


def main() -> int:
    """Permite seleccionar explícitamente el .env sin modificarlo."""
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--archivo-env", type=Path)
    opciones = argumentos.parse_args()
    try:
        configuracion = (
            ConfiguracionConexion(_env_file=opciones.archivo_env)
            if opciones.archivo_env is not None else obtener_configuracion_conexion()
        )
        inventario = asyncio.run(inspeccionar(configuracion))
    except ValidationError as error:
        for detalle in error.errors(include_input=False, include_context=False, include_url=False):
            campo = ".".join(str(parte) for parte in detalle["loc"]) or "configuracion"
            print(f"Configuración inválida: {campo} ({detalle['type']}).")
        return 1
    except Exception as error:
        # No imprimir excepciones SQLAlchemy/asyncpg: pueden contener datos de conexión.
        print(f"No se completó la inspección ({type(error).__name__}); no se muestran secretos.")
        return 1
    print(json.dumps(inventario, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
