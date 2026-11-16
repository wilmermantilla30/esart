"""Operador local de p0004: contraseña oculta, precondiciones y transacción única."""

import argparse
import asyncio
import getpass
import hashlib
import subprocess
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion.base_datos.configuracion import ConfiguracionConexion, opciones_tls_local

RAIZ = Path(__file__).resolve().parents[1]
RESPALDO = Path(r"D:\2026\esart\respaldos\esart_db_pre_hu04.backup")
HUELLA = "4d6ecc85006e37b16e92d6fdc0cafd577384fc842e49b6efcd3cd03e0f99dfcb"
PG_RESTORE = Path(r"C:\Program Files\PostgreSQL\18\bin\pg_restore.exe")


def comprobar_respaldo():
    if not RESPALDO.is_file():
        raise RuntimeError("No se encuentra el respaldo restaurado y validado.")
    with RESPALDO.open("rb") as archivo:
        huella = hashlib.file_digest(archivo, "sha256").hexdigest()
    if huella != HUELLA:
        raise RuntimeError("El respaldo no coincide con la restauración validada; detenerse.")
    resultado = subprocess.run(  # noqa: S603 -- ejecutable y archivo locales fijos
        [str(PG_RESTORE), "--list", str(RESPALDO)],
        capture_output=True,
        check=False,
    )
    if resultado.returncode:
        raise RuntimeError("pg_restore no puede leer el respaldo validado.")


async def ejecutar(aplicar: bool, usuario: str):
    comprobar_respaldo()
    print("Respaldo disponible: huella y catálogo coinciden con la restauración previamente validada.")
    original = make_url(ConfiguracionConexion().url_base_datos.get_secret_value())
    if original.database != "esart_db":
        raise RuntimeError("La configuración no apunta a esart_db.")
    clave = getpass.getpass("Contraseña del operador PostgreSQL (no se guardará): ")
    url = original.set(username=usuario, password=clave)
    motor = create_async_engine(
        url,
        hide_parameters=True,
        echo=False,
        connect_args=opciones_tls_local(url.render_as_string(hide_password=False)),
    )
    del clave
    try:
        async with motor.begin() as c:
            identidad = (
                (
                    await c.execute(
                        text("""
                SELECT current_database() AS base, current_user AS usuario,
                       (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AS administrador
            """)
                    )
                )
                .mappings()
                .one()
            )
            if identidad["base"] != "esart_db" or identidad["usuario"] == "esart_aplicacion":
                raise RuntimeError("Destino o identidad no autorizados.")
            if not identidad["administrador"]:
                raise RuntimeError("Este procedimiento requiere la cuenta administrativa autorizada.")
            revision = (
                (await c.execute(text("SELECT version_num FROM esart.alembic_version"))).scalars().all()
            )
            if revision != ["p0003_control_intentos"]:
                raise RuntimeError("La revisión no es exactamente p0003_control_intentos; detenerse.")
            existente = await c.scalar(text("SELECT to_regclass('esart.desafios_captcha')::text"))
            columnas = (
                (
                    await c.execute(
                        text("""
                SELECT attname FROM pg_attribute WHERE attrelid='esart.auditoria_acceso'::regclass
                AND attnum>0 AND NOT attisdropped ORDER BY attnum
            """)
                    )
                )
                .scalars()
                .all()
            )
            if existente or columnas != ["id", "intento_id", "evento", "fecha"]:
                raise RuntimeError("Estructura distinta de la precondición revisada; detenerse.")
            historicos = await c.scalar(text("SELECT count(*) FROM esart.auditoria_acceso"))
            print("Destino esart_db; operador administrativo verificado; revisión p0003 compatible.")
            print("Sin cambios de usuarios, contraseñas, roles, permisos previos o registros históricos.")
            if not aplicar:
                print("Solo verificación: no se ejecutó la migración. Utilice --aplicar para ejecutarla.")
                return
            await c.execute(text("SET LOCAL lock_timeout='5s'"))
            await c.execute(text("SET LOCAL statement_timeout='30s'"))

            def migrar(conexion):
                configuracion = Config(str(RAIZ / "alembic.ini"))
                configuracion.attributes["connection"] = conexion
                command.upgrade(configuracion, "p0004_captcha_local")

            await c.run_sync(migrar)
            final = (await c.execute(text("SELECT version_num FROM esart.alembic_version"))).scalars().all()
            if final != ["p0004_captcha_local"]:
                raise RuntimeError("Revisión final inesperada; rollback.")
            if await c.scalar(text("SELECT count(*) FROM esart.auditoria_acceso")) != historicos:
                raise RuntimeError("La auditoría histórica cambió durante la operación; rollback.")
            permisos = (
                (
                    await c.execute(
                        text("""
                SELECT has_table_privilege('esart_aplicacion','esart.desafios_captcha','SELECT') AS leer,
                has_table_privilege('esart_aplicacion','esart.desafios_captcha','INSERT') AS insertar,
                has_column_privilege('esart_aplicacion','esart.desafios_captcha','consumido_en','UPDATE')
                  AS consumir,
                has_table_privilege('esart_aplicacion','esart.desafios_captcha','UPDATE') AS actualizar_todo,
                has_table_privilege('esart_aplicacion','esart.desafios_captcha','DELETE') AS borrar
            """)
                    )
                )
                .mappings()
                .one()
            )
            if not all(permisos[k] for k in ("leer", "insertar", "consumir")):
                raise RuntimeError("Faltan permisos mínimos; rollback.")
            if permisos["actualizar_todo"] or permisos["borrar"]:
                raise RuntimeError("Se detectaron permisos excesivos; rollback sin revocaciones automáticas.")
        print("COMMIT: p0004_captcha_local aplicada; permisos mínimos comprobados; auditoría conservada.")
    finally:
        await motor.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--operador", default="postgres")
    args = parser.parse_args()
    try:
        asyncio.run(ejecutar(args.aplicar, args.operador))
    except (Exception, KeyboardInterrupt) as error:
        # No publicar traceback, parámetros SQL, URLs ni mensajes del controlador.
        print("DETENIDO sin confirmar la migración. Tipo de error:", type(error).__name__)
        if isinstance(error, RuntimeError):
            print(str(error))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
