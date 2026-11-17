"""Crea un clúster PostgreSQL efímero independiente para pruebas; nunca conecta al puerto operativo."""

import asyncio
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import asyncpg

RAIZ = Path(__file__).resolve().parents[1]
PG = Path(r"C:\Program Files\PostgreSQL\18\bin")


def ejecutar_comando(args, *, entorno=None):
    # pg_ctl deja handles heredados en Windows: archivos, no pipes que esperan al servidor.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as salida:
        resultado = subprocess.run(  # noqa: S603 -- argumentos internos, sin shell
            args,
            cwd=RAIZ,
            env=entorno,
            stdout=salida,
            stderr=salida,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        salida.seek(0)
        contenido = salida.read()
    if resultado.returncode:
        error = contenido
        error = re.sub(r"postgresql\+asyncpg://[^\s]+", "<conexion-oculta>", error)
        (RAIZ / "respaldos/hu06_ultimo_error.log").write_text(error, encoding="utf-8")
        # No mostrar traceback de bibliotecas ni entorno con URLs de conexión.
        raise RuntimeError(
            "Falló comando " + Path(str(args[0])).name + "; revisar pruebas sin publicar secretos"
        )
    return contenido


def main():
    carpeta = (RAIZ / "respaldos" / ("hu06_" + uuid.uuid4().hex)).resolve()
    carpeta.mkdir(parents=True)
    (carpeta / "ESART_SOLO_PRUEBAS").write_text("Clúster independiente autorizado para HU seguridad\n")
    datos = carpeta / "datos"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        puerto = sock.getsockname()[1]
    if puerto == 5432:
        raise RuntimeError("No se utiliza puerto operativo")
    clave = secrets.token_urlsafe(32)
    descriptor, temporal = tempfile.mkstemp(prefix="esart_hu06_", suffix=".tmp")
    with os.fdopen(descriptor, "w") as archivo:
        archivo.write(clave)
    iniciado = False
    try:
        ejecutar_comando(
            [
                str(PG / "initdb.exe"),
                "-D",
                str(datos),
                "-U",
                "esart_operador_pruebas",
                "--encoding=UTF8",
                "--locale=C",
                "--auth=scram-sha-256",
                "--pwfile=" + temporal,
            ]
        )
        ejecutar_comando(
            [
                str(PG / "pg_ctl.exe"),
                "-D",
                str(datos),
                "-l",
                str(carpeta / "postgres.log"),
                "-o",
                f"-p {puerto} -h 127.0.0.1",
                "-w",
                "start",
            ]
        )
        iniciado = True

        async def preparar():
            c = await asyncpg.connect(
                host="127.0.0.1",
                port=puerto,
                user="esart_operador_pruebas",
                password=clave,
                database="postgres",
                ssl=False,
            )
            try:
                if Path(await c.fetchval("SHOW data_directory")).resolve() != datos:
                    raise RuntimeError("Directorio de clúster inesperado")
                # Secreto generado localmente; no es dato externo ni se registra la sentencia.
                await c.execute("CREATE ROLE esart_aplicacion LOGIN PASSWORD '" + clave + "'")
                await c.execute("CREATE DATABASE esart_db")
            finally:
                await c.close()

        asyncio.run(preparar())
        entorno = os.environ.copy()
        admin = f"postgresql+asyncpg://esart_operador_pruebas:{clave}@127.0.0.1:{puerto}/esart_db"
        entorno["ESART_MIGRACIONES_URL"] = admin
        entorno["ESART_SEGURIDAD_TEST_ADMIN"] = admin
        entorno["ESART_SEGURIDAD_TEST_URL"] = admin.replace("esart_operador_pruebas:", "esart_aplicacion:")
        entorno["ESART_SEGURIDAD_TEST_DIR"] = str(datos)
        for nombre in ("ESART_URL_BD_INTEGRACION", "ESART_SEEDS_INTEGRACION", "ESART_FASE3_DDL_APROBADO"):
            entorno.pop(nombre, None)
        ejecutar_comando(
            [sys.executable, "-m", "alembic", "upgrade", "p0003_control_intentos"], entorno=entorno
        )
        compatibilidad = ejecutar_comando(
            [
                sys.executable,
                "-m",
                "pytest",
                "pruebas/test_seguridad_login_pg.py::test_http_real_login_cookie_y_sesion_actual",
                "-o",
                "addopts=",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            entorno=entorno,
        )
        ejecutar_comando([sys.executable, "-m", "alembic", "upgrade", "p0004_captcha_local"], entorno=entorno)

        async def preparar_seguridad():
            c = await asyncpg.connect(
                host="127.0.0.1",
                port=puerto,
                user="esart_operador_pruebas",
                password=clave,
                database="esart_db",
                ssl=False,
            )
            try:
                if Path(await c.fetchval("SHOW data_directory")).resolve() != datos:
                    raise RuntimeError("Destino aislado inesperado")
                if await c.fetchval("SELECT to_regclass('seguridad.usuario_totp')") is not None:
                    raise RuntimeError("No recrear tablas seguridad existentes")
                await c.execute((RAIZ / "aplicacion/base_datos/seguridad.sql").read_text(encoding="utf-8"))
            finally:
                await c.close()

        asyncio.run(preparar_seguridad())
        ejecutar_comando([sys.executable, "-m", "alembic", "upgrade", "head"], entorno=entorno)
        salida = ejecutar_comando(
            [
                sys.executable,
                "-m",
                "pytest",
                "pruebas/test_seguridad_login_pg.py",
                "pruebas/test_captcha_local_pg.py",
                "pruebas/test_totp_pg.py",
                "-o",
                "addopts=",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            entorno=entorno,
        )
        print(salida)
        (carpeta / "resultado.json").write_text(
            json.dumps(
                {
                    "estado": "pruebas_aprobadas",
                    "puerto_aislado": puerto,
                    "principal_modificada": False,
                    "resultado": salida,
                    "compatibilidad_p0003": compatibilidad,
                }
            ),
            encoding="utf-8",
        )
    finally:
        Path(temporal).unlink(missing_ok=True)
        if iniciado:
            ejecutar_comando([str(PG / "pg_ctl.exe"), "-D", str(datos), "-m", "fast", "-w", "stop"])
    print("Clúster detenido; evidencia conservada en " + str(carpeta))


if __name__ == "__main__":
    main()
