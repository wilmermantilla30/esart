"""Servicios y Chrome separados, únicamente para el clúster marcado de pruebas."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parents[1]
FRONTEND = RAIZ.parent / "frontend/esart"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def esperar(url, proceso):
    for _ in range(900):
        if proceso.poll() is not None:
            raise RuntimeError("Un servicio aislado terminó antes de estar disponible")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Tiempo de inicio agotado en servicio aislado")


def ejecutar(nombre: str) -> dict:
    url = os.environ["ESART_SEGURIDAD_TEST_URL"]
    conexion = make_url(url)
    datos = Path(os.environ["ESART_SEGURIDAD_TEST_DIR"]).resolve()
    if (
        conexion.host != "127.0.0.1"
        or conexion.port == 5432
        or conexion.database != "esart_db"
        or not datos.is_relative_to(RAIZ / "respaldos")
        or not (datos.parent / "ESART_SOLO_PRUEBAS").is_file()
        or not nombre.startswith("hu06.")
    ):
        raise RuntimeError("El navegador solo admite la cuenta y clúster aislados marcados")
    carpeta = datos.parent / "navegador_publico"
    carpeta.mkdir(exist_ok=True)
    backend, frontend, cdp = puerto_libre(), puerto_libre(), puerto_libre()
    proxy = carpeta / "proxy.json"
    proxy.write_text(
        json.dumps(
            {"/api": {"target": f"http://127.0.0.1:{backend}", "secure": False, "changeOrigin": False}}
        )
    )
    entorno = os.environ.copy()
    entorno.update(
        URL_BASE_DATOS=url,
        ENTORNO="pruebas",
        COOKIE_SEGURA="false",
        JWT_CLAVE_SECRETA=secrets.token_urlsafe(48),
        PYTHONIOENCODING="utf-8",
    )
    for variable in ("ESART_MIGRACIONES_URL", "ESART_SEGURIDAD_TEST_ADMIN"):
        entorno.pop(variable, None)
    procesos = []
    archivos = []

    def iniciar(argumentos, directorio, archivo):
        log = (carpeta / archivo).open("w", encoding="utf-8")
        archivos.append(log)
        proceso = subprocess.Popen(  # noqa: S603 -- argumentos locales, sin shell
            argumentos,
            cwd=directorio,
            env=entorno,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        procesos.append(proceso)
        return proceso

    try:
        api = iniciar(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "aplicacion.principal:aplicacion",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend),
                "--no-proxy-headers",
            ],
            RAIZ,
            "api.log",
        )
        esperar(f"http://127.0.0.1:{backend}/api/openapi.json", api)
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node no está disponible para la prueba real")
        web = iniciar(
            [
                node,
                str(FRONTEND / "node_modules/@angular/cli/bin/ng.js"),
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(frontend),
                "--proxy-config",
                str(proxy),
            ],
            FRONTEND,
            "angular.log",
        )
        esperar(f"http://127.0.0.1:{frontend}", web)
        navegador = iniciar(
            [
                str(CHROME),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-component-update",
                f"--remote-debugging-port={cdp}",
                f"--user-data-dir={carpeta / 'perfil'}",
                "about:blank",
            ],
            RAIZ,
            "chrome.log",
        )
        esperar(f"http://127.0.0.1:{cdp}/json", navegador)
        entorno.update(
            ESART_CDP_PUERTO=str(cdp),
            ESART_USUARIO_PUBLICO=nombre,
            ESART_FRONTEND_PUBLICO=f"http://127.0.0.1:{frontend}",
            ESART_EVIDENCIA_PUBLICA=str(carpeta),
        )
        resultado = subprocess.run(  # noqa: S603 -- script local fijo, sin shell
            [node, str(RAIZ / "herramientas/navegador_publico.mjs")],
            cwd=RAIZ,
            env=entorno,
            capture_output=True,
            timeout=150,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if resultado.returncode:
            # El script solo emite errores de aserción, nunca cuerpos de login o cookies.
            (carpeta / "fallo_navegador.txt").write_bytes(resultado.stderr)
            raise RuntimeError("Falló la prueba pública real; revisar evidencia local aislada")
        return json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))
    finally:
        for proceso in reversed(procesos):
            if proceso.poll() is None:
                if os.name == "nt":
                    subprocess.run(  # noqa: S603 -- PID del proceso hijo creado por esta función
                        [
                            str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                            "/PID",
                            str(proceso.pid),
                            "/T",
                            "/F",
                        ],
                        capture_output=True,
                        check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                else:
                    proceso.terminate()
                proceso.wait(timeout=15)
        for archivo in archivos:
            archivo.close()
