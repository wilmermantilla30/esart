"""Recorrido real Angular/FastAPI/esart_db local; sin DDL ni cambios en cuentas existentes."""

import argparse
import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.engine import make_url

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import Rol, SesionUsuario, Usuario, UsuarioRoles
from aplicacion.modelos.totp import DesafioTotp, RecuperacionTotp, UsuarioTotp
from aplicacion.seguridad.contrasenas import generar_hash_contrasena
from aplicacion.servicios.seguridad_login import reloj_servidor
from aplicacion.servicios.totp import TotpService
from herramientas.probar_flujo_publico_navegador import CHROME, FRONTEND, RAIZ, esperar, puerto_libre


async def crear_cuenta():
    cfg = obtener_configuracion()
    url = make_url(cfg.url_base_datos.get_secret_value())
    if (
        cfg.entorno != "desarrollo"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "esart_db"
        or url.username != "esart_aplicacion"
    ):
        raise ValueError("Solo se permite esart_db local en desarrollo con esart_aplicacion.")
    async with obtener_fabrica_sesiones()() as s:
        servicio = TotpService(s)
        await servicio.preparar()
        await servicio.politica("LOGIN_TOTP")
        await servicio.politica("DESBLOQUEO_TOTP")
        rol = await s.scalar(select(Rol).where(Rol.codigo == "USUARIO", Rol.activo.is_(True)))
        if rol is None:
            raise ValueError("Falta el rol USUARIO activo; esta herramienta no crea roles.")
        nombre, clave = "mfa.validacion." + uuid.uuid4().hex, secrets.token_urlsafe(24)
        usuario = Usuario(usuario=nombre, contrasena_hash=generar_hash_contrasena(clave), activo=True)
        s.add(usuario)
        await s.flush()
        s.add(UsuarioRoles(usuario_id=usuario.id, rol_id=rol.id))
        await s.commit()
        return usuario.id, nombre, clave


async def cerrar_cuenta(identificador, nombre):
    async with obtener_fabrica_sesiones()() as s:
        usuario = await s.scalar(
            select(Usuario).where(Usuario.id == identificador, Usuario.usuario == nombre)
        )
        if not nombre.startswith("mfa.validacion.") or usuario is None:
            raise ValueError("No desactivar cuentas ajenas a esta ejecución.")
        desactivada = bool(
            await s.scalar(text("SELECT has_column_privilege('esart_ref.usuarios','activo','UPDATE')"))
        )
        if desactivada:
            usuario.activo = False
        ahora = await reloj_servidor(s)
        await s.execute(
            update(SesionUsuario)
            .where(SesionUsuario.usuario_id == identificador)
            .values(revocada=True, fecha_revocacion=ahora)
        )
        await s.execute(
            update(UsuarioTotp)
            .where(UsuarioTotp.usuario_id == identificador)
            .values(estado="REVOCADO", revocado_en=ahora)
        )
        await s.execute(
            update(RecuperacionTotp)
            .where(RecuperacionTotp.usuario_id == identificador)
            .values(revocado_en=ahora)
        )
        await s.execute(
            update(DesafioTotp)
            .where(
                DesafioTotp.usuario_id == identificador, DesafioTotp.estado.in_(["PENDIENTE", "VERIFICADO"])
            )
            .values(estado="CANCELADO")
        )
        await s.commit()
        return desactivada


def navegador(nombre, clave, carpeta, captcha_manual=False):
    node = shutil.which("node")
    if not node or not CHROME.is_file():
        raise ValueError("Se requieren Node y Chrome locales.")
    backend, frontend, cdp = puerto_libre(), puerto_libre(), puerto_libre()
    proxy = carpeta / "proxy.json"
    proxy.write_text(
        json.dumps(
            {"/api": {"target": f"http://127.0.0.1:{backend}", "secure": False, "changeOrigin": False}}
        ),
        encoding="utf-8",
    )
    entorno = os.environ.copy()
    entorno.update(
        COOKIE_SEGURA="false",
        PYTHONIOENCODING="utf-8",
        ESART_CDP_PUERTO=str(cdp),
        ESART_USUARIO_PUBLICO=nombre,
        ESART_FRONTEND_PUBLICO=f"http://127.0.0.1:{frontend}",
        ESART_EVIDENCIA_PUBLICA=str(carpeta),
        ESART_CREDENCIAL_PRUEBA=clave,
        ESART_ESCENARIO_TOTP="totp",
        ESART_CAPTCHA_MANUAL="true" if captcha_manual else "false",
    )
    procesos, archivos = [], []

    def iniciar(args, directorio, log, visible=False):
        archivo = (carpeta / log).open("w", encoding="utf-8")
        archivos.append(archivo)
        proceso = subprocess.Popen(  # noqa: S603 -- argumentos locales constantes, sin shell
            args,
            cwd=directorio,
            env=entorno,
            stdout=archivo,
            stderr=archivo,
            creationflags=0 if visible else getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )  # noqa: S603
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
        chrome = iniciar(
            [
                str(CHROME),
                *([] if captcha_manual else ["--headless=new"]),
                "--disable-gpu",
                "--in-process-gpu",
                "--disable-software-rasterizer",
                "--no-sandbox",  # Solo este perfil local: el contenedor impide iniciar renderers sandbox.
                "--no-first-run",
                "--disable-background-networking",
                "--disable-component-update",
                f"--remote-debugging-port={cdp}",
                f"--user-data-dir={carpeta / 'perfil'}",
                "about:blank",
            ],
            RAIZ,
            "chrome.log",
            visible=captcha_manual,
        )
        esperar(f"http://127.0.0.1:{cdp}/json", chrome)
        resultado = subprocess.run(  # noqa: S603 -- script local fijo, sin shell
            [node, str(RAIZ / "herramientas/navegador_totp.mjs")],  # noqa: S603
            cwd=RAIZ,
            env=entorno,
            capture_output=True,
            timeout=600 if captcha_manual else 180,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if resultado.returncode:
            (carpeta / "fallo_navegador.txt").write_bytes(resultado.stderr)
            raise RuntimeError("Falló el recorrido real; revisar evidencia local sin publicar credenciales.")
        return json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))
    finally:
        for proceso in reversed(procesos):
            if proceso.poll() is None:
                subprocess.run(  # noqa: S603 -- únicamente PID de un hijo creado por esta función
                    [
                        str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),  # noqa: S603
                        "/PID",
                        str(proceso.pid),
                        "/T",
                        "/F",
                    ],
                    capture_output=True,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                proceso.wait(timeout=15)
        for archivo in archivos:
            archivo.close()


async def ejecutar(captcha_manual=False):
    carpeta = RAIZ / "respaldos" / ("validacion_totp_" + uuid.uuid4().hex)
    carpeta.mkdir(parents=True)
    identificador = None
    monitor = None
    try:
        identificador, nombre, clave = await crear_cuenta()
        monitor = asyncio.create_task(observar_contador(identificador, carpeta))
        print(json.dumps({"evidencia_en_curso": str(carpeta), "captcha_manual": captcha_manual}), flush=True)
        resultado = await asyncio.to_thread(navegador, nombre, clave, carpeta, captcha_manual)
        async with obtener_fabrica_sesiones()() as s:
            await s.execute(text("SET TRANSACTION READ ONLY"))
            final = (
                (
                    await s.execute(
                        select(
                            Usuario.intentos_fallidos_consecutivos,
                            Usuario.bloqueado_hasta,
                        ).where(Usuario.id == identificador)
                    )
                )
                .mappings()
                .one()
            )
            resultado["estado_final_sql"] = dict(final)
            await s.rollback()
        if captcha_manual and (
            final["intentos_fallidos_consecutivos"] != 0 or final["bloqueado_hasta"] is not None
        ):
            raise RuntimeError("El desbloqueo no reinició el estado real de PostgreSQL.")
    finally:
        if monitor is not None:
            monitor.cancel()
            try:
                await monitor
            except asyncio.CancelledError:
                pass
        if identificador is not None:
            desactivada = await cerrar_cuenta(identificador, nombre)
            if not desactivada:
                if not re.fullmatch(r"mfa\.validacion\.[0-9a-f]{32}", nombre):
                    raise ValueError("Nombre de prueba inesperado")
                (carpeta / "desactivar_cuenta_prueba.sql").write_text(
                    "-- Ejecutar como propietario; solo la cuenta exclusiva de esta prueba.\n"
                    f"UPDATE esart_ref.usuarios SET activo=false WHERE id={int(identificador)} "
                    f"AND usuario='{nombre}';\n",
                    encoding="utf-8",
                )
        await cerrar_motor_base_datos()
    resultado.update(
        base="esart_db",
        cuenta_prueba_desactivada=desactivada,
        sesiones_prueba_revocadas=True,
        sin_migraciones=True,
    )
    (carpeta / "resultado.json").write_text(json.dumps(resultado, indent=2), encoding="utf-8")
    print(json.dumps({"resultado": resultado, "evidencia": str(carpeta)}, ensure_ascii=False))


async def observar_contador(identificador, carpeta):
    anterior, registros = None, []
    while True:
        archivo = carpeta / "progreso.json"
        if archivo.exists():
            try:
                progreso = json.loads(archivo.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                await asyncio.sleep(0.2)
                continue
            if progreso != anterior:
                async with obtener_fabrica_sesiones()() as s:
                    await s.execute(text("SET TRANSACTION READ ONLY"))
                    fila = (
                        (
                            await s.execute(
                                text("""SELECT u.intentos_fallidos_consecutivos,
                        u.bloqueado_hasta, clock_timestamp() AS observado_en,
                        i.motivo_fallo,i.captcha_validado
                        FROM esart_ref.usuarios u LEFT JOIN LATERAL (
                          SELECT motivo_fallo,captcha_validado FROM esart.intentos_inicio_sesion
                          WHERE usuario_id=u.id ORDER BY fecha DESC,id DESC LIMIT 1) i ON true
                        WHERE u.id=:id"""),
                                {"id": identificador},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    registros.append({"etapa": progreso["etapa"], **dict(fila)})
                    await s.rollback()
                (carpeta / "registro_sql.json").write_text(
                    json.dumps(registros, default=str, indent=2), encoding="utf-8"
                )
                anterior = progreso
        await asyncio.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ejecutar",
        action="store_true",
        required=True,
        help="Crea una cuenta exclusiva de prueba y la desactiva al terminar.",
    )
    parser.add_argument(
        "--captcha-manual",
        action="store_true",
        help="Abre Chrome para que el usuario resuelva los CAPTCHA reales durante la prueba 3/7.",
    )
    argumentos = parser.parse_args()
    try:
        asyncio.run(ejecutar(argumentos.captcha_manual))
    except Exception as error:
        print(
            json.dumps(
                {
                    "estado": "no_aprobado",
                    "tipo": type(error).__name__,
                    "codigo": getattr(error, "codigo", "VALIDACION_INCOMPLETA"),
                }
            )
        )
        raise SystemExit(1) from None
