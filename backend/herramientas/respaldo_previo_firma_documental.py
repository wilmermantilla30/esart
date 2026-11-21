"""Genera y verifica respaldo local previo a p0018; nunca ejecuta migraciones."""

import asyncio
import hashlib
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion.base_datos.configuracion import obtener_configuracion_conexion, opciones_tls_local

RAIZ_BACKEND = Path(__file__).resolve().parents[1]


def leer_url_respaldo() -> str:
    valor = os.environ.get("ESART_RESPALDO_URL")
    if not valor:
        raise RuntimeError(
            "Defina ESART_RESPALDO_URL solo en el proceso del respaldo; no se lee desde archivos .env."
        )
    try:
        make_url(valor)
    except Exception:
        raise RuntimeError("ESART_RESPALDO_URL no tiene un formato válido; se omitió su valor.") from None
    return valor


async def validar_destino(url: str) -> None:
    configuracion = obtener_configuracion_conexion()
    try:
        destino = make_url(url)
    except Exception:
        raise RuntimeError("La URL de respaldo no tiene un formato válido; se omitió su valor.") from None
    aplicacion = make_url(configuracion.url_base_datos.get_secret_value())
    if (
        configuracion.entorno != "desarrollo"
        or destino.database != "esart_db"
        or destino.host not in {"127.0.0.1", "localhost", "::1"}
        or destino.username != "esart_respaldo"
        or (destino.host, destino.port, destino.database)
        != (aplicacion.host, aplicacion.port, aplicacion.database)
    ):
        raise RuntimeError("Destino rechazado: el respaldo solo admite el PostgreSQL local de desarrollo.")
    motor = create_async_engine(url, connect_args=opciones_tls_local(url), hide_parameters=True)
    try:
        async with motor.connect() as conexion:
            await conexion.execute(text("SET TRANSACTION READ ONLY"))
            fila = (
                await conexion.execute(
                    text("""
                        SELECT current_database(), current_user, host(inet_server_addr()), r.rolsuper
                        FROM pg_roles r WHERE r.rolname=current_user
                    """)
                )
            ).one()
            if fila[0] != "esart_db" or fila[2] not in {"127.0.0.1", "::1"} or fila[3]:
                raise RuntimeError(
                    "PostgreSQL rechazado: requiere desarrollo local y un rol migrador no-superusuario."
                )
            print(
                f"Destino validado: base={fila[0]}, rol={fila[1]}, servidor={fila[2]}, "
                f"superusuario={fila[3]}"
            )
    finally:
        await motor.dispose()


def respaldar(url: str) -> Path:
    try:
        destino = make_url(url)
    except Exception:
        raise RuntimeError("La URL de respaldo no tiene un formato válido; se omitió su valor.") from None
    if (
        destino.username != "esart_respaldo"
        or destino.database != "esart_db"
        or destino.host not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise RuntimeError("pg_dump solo admite esart_respaldo en el PostgreSQL local de desarrollo.")
    raiz_pg = Path("C:/Program Files/PostgreSQL/18/bin")
    pg_dump = shutil.which("pg_dump") or str(raiz_pg / "pg_dump.exe")
    pg_restore = shutil.which("pg_restore") or str(raiz_pg / "pg_restore.exe")
    if not Path(pg_dump).is_file() or not Path(pg_restore).is_file():
        raise RuntimeError("Se requieren pg_dump y pg_restore para crear y validar el respaldo.")

    directorio = RAIZ_BACKEND / "respaldos" / "p0018_privado"
    if not directorio.is_dir():
        raise RuntimeError("Falta el directorio privado precreado con ACL revisadas para respaldos.")
    sello = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archivo = directorio / f"esart_db_pre_p0018_{sello}.dump"
    entorno = os.environ.copy()
    entorno["PGPASSWORD"] = destino.password or ""
    entorno["PGSSLMODE"] = "disable" if destino.host in {"127.0.0.1", "localhost", "::1"} else "prefer"
    argumentos = [
        pg_dump,
        "--format=custom",
        "--no-owner",
        "--host",
        destino.host or "127.0.0.1",
        "--port",
        str(destino.port or 5432),
        "--username",
        destino.username or "",
        "--dbname",
        destino.database or "",
        "--file",
        str(archivo),
    ]
    resultado = subprocess.run(  # noqa: S603 - argumentos validados, ejecutable pg_dump de PostgreSQL
        argumentos, env=entorno, capture_output=True, check=False
    )
    entorno.pop("PGPASSWORD", None)
    if resultado.returncode:
        archivo.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump fallo con codigo {resultado.returncode}; no se muestra salida sensible.")
    if not archivo.is_file() or archivo.stat().st_size == 0:
        raise RuntimeError("pg_dump no produjo un archivo de respaldo valido.")
    validacion = subprocess.run(  # noqa: S603 - ejecutable pg_restore de PostgreSQL
        [pg_restore, "--list", str(archivo)], capture_output=True, check=False
    )
    if validacion.returncode or not validacion.stdout:
        archivo.unlink(missing_ok=True)
        raise RuntimeError("pg_restore no pudo leer el archivo; el respaldo se elimino.")
    hash_archivo = hashlib.sha256()
    with archivo.open("rb") as flujo:
        for bloque in iter(lambda: flujo.read(1024 * 1024), b""):
            hash_archivo.update(bloque)
    huella = hash_archivo.hexdigest()
    print(f"Respaldo verificado: {archivo}")
    print(f"Tamano: {archivo.stat().st_size} bytes; SHA-256: {huella}")
    return archivo


def main() -> None:
    credenciales = leer_url_respaldo()
    asyncio.run(validar_destino(credenciales))
    respaldar(credenciales)
    print("No se ejecuto ninguna migracion.")


if __name__ == "__main__":
    main()
