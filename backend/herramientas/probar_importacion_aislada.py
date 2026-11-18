"""Ejecuta pruebas del cargue en un clúster efímero; nunca usa la base del .env.

Uso desde backend/: python herramientas/probar_importacion_aislada.py
PG_BIN permite indicar el directorio de ejecutables PostgreSQL de otra instalación.
"""

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import asyncpg

RAIZ = Path(__file__).resolve().parents[1]
PG = Path(os.environ.get("PG_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
SUFIJO = ".exe" if os.name == "nt" else ""


def ejecutar(argumentos, *, entorno=None):
    """Ejecuta argumentos literales sin shell ni ventanas auxiliares visibles."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as salida:
        resultado = subprocess.run(  # noqa: S603 -- ejecutables y argumentos internos, sin shell
            argumentos,
            cwd=RAIZ,
            env=entorno,
            stdout=salida,
            stderr=salida,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        salida.seek(0)
        texto = salida.read()
    if resultado.returncode:
        print(texto)
        raise RuntimeError(f"Falló {Path(str(argumentos[0])).name}")
    return texto


def main():
    """Prepara, marca, comprueba y destruye únicamente su propio clúster temporal."""
    temporal = Path(tempfile.mkdtemp(prefix="esart-importacion-")).resolve()
    datos = temporal / "datos"
    (temporal / "ESART_SOLO_PRUEBAS_IMPORTACION").write_text("Clúster independiente de pruebas\n")
    iniciado = False
    with socket.socket() as conexion:
        conexion.bind(("127.0.0.1", 0))
        puerto = conexion.getsockname()[1]
    if puerto in (5432, 5433):
        raise RuntimeError("No se utilizan puertos operativos")
    try:
        ejecutar(
            [
                str(PG / ("initdb" + SUFIJO)),
                "-D",
                str(datos),
                "-A",
                "trust",
                "-U",
                "esart_pruebas",
                "--no-locale",
                "--encoding=UTF8",
            ]
        )
        ejecutar(
            [
                str(PG / ("pg_ctl" + SUFIJO)),
                "-D",
                str(datos),
                "-l",
                str(temporal / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {puerto}",
                "-w",
                "start",
            ]
        )
        iniciado = True

        async def preparar():
            conexion = await asyncpg.connect(
                host="127.0.0.1", port=puerto, user="esart_pruebas", database="postgres", ssl=False
            )
            try:
                directorio = Path(await conexion.fetchval("SHOW data_directory")).resolve()
                if directorio != datos:
                    raise RuntimeError("El servidor no pertenece a este laboratorio")
                await conexion.execute("CREATE DATABASE esart_importacion_pruebas")
                await conexion.execute(
                    "COMMENT ON DATABASE esart_importacion_pruebas IS 'ESART_SOLO_PRUEBAS_IMPORTACION'"
                )
            finally:
                await conexion.close()

        asyncio.run(preparar())
        entorno = os.environ.copy()
        entorno.pop("ESART_URL_BD_INTEGRACION", None)
        entorno.pop("ESART_SEGURIDAD_TEST_URL", None)
        entorno["ESART_IMPORTACION_TEST_URL"] = (
            f"postgresql+asyncpg://esart_pruebas@127.0.0.1:{puerto}/esart_importacion_pruebas"
        )
        print(
            ejecutar(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "pruebas/test_importacion_personal.py",
                    "pruebas/test_importacion_personal_aislada.py",
                    "pruebas/test_diagnostico_importacion.py",
                    "pruebas/test_administrador_aislado.py",
                    "--tb=short",
                    "-rs",
                ],
                entorno=entorno,
            )
        )
    finally:
        detener = True
        if iniciado:
            try:
                ejecutar([str(PG / ("pg_ctl" + SUFIJO)), "-D", str(datos), "-m", "fast", "-w", "stop"])
            except RuntimeError:
                detener = False
                print("No se eliminó el clúster porque no se confirmó su detención.")
        raiz_temporal = Path(tempfile.gettempdir()).resolve()
        if (
            detener
            and temporal.parent == raiz_temporal
            and temporal.name.startswith("esart-importacion-")
            and (temporal / "ESART_SOLO_PRUEBAS_IMPORTACION").is_file()
        ):
            shutil.rmtree(temporal)


if __name__ == "__main__":
    main()
