"""Provisiona cifrado local sin mostrar claves, reconfigurar factores ni escribir en PostgreSQL."""

import asyncio
import base64
import os
import re
import secrets

from sqlalchemy import text

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import RUTA_ARCHIVO_ENV, obtener_configuracion


def actualizar_variable(contenido, nombre, valor):
    patron = re.compile(r"^" + re.escape(nombre) + r"\s*=.*$", re.MULTILINE)
    if len(patron.findall(contenido)) > 1:
        raise ValueError("Configuración duplicada; revisar el archivo local antes de continuar.")
    linea = nombre + "=" + valor
    return (
        patron.sub(lambda _: linea, contenido)
        if patron.search(contenido)
        else contenido.rstrip() + "\n" + linea + "\n"
    )


async def configurar():
    cfg = obtener_configuracion()
    if cfg.entorno != "desarrollo":
        raise ValueError("Esta herramienta solo admite desarrollo local.")
    if any(k in os.environ for k in ("TOTP_HABILITADO", "TOTP_CLAVE_CIFRADO")):
        raise ValueError("TOTP se controla mediante el entorno del proceso; no sustituirlo con .env.")
    try:
        async with obtener_fabrica_sesiones()() as sesion:
            await sesion.execute(text("SET TRANSACTION READ ONLY"))
            base, rol = (await sesion.execute(text("SELECT current_database(),current_user"))).one()
            if (base, rol) != ("esart_db", "esart_aplicacion"):
                raise ValueError("Conexión local distinta del destino esperado.")
            factores = await sesion.scalar(text("SELECT count(*) FROM seguridad.usuario_totp"))
            await sesion.rollback()
        clave = cfg.totp_clave_cifrado.get_secret_value() if cfg.totp_clave_cifrado else ""
        if clave:
            if len(base64.b64decode(clave, validate=True)) != 32:
                raise ValueError("La clave existente no es válida; no se reemplazará automáticamente.")
        elif factores:
            raise ValueError("Existen factores cifrados sin clave configurada; recuperar la clave original.")
        else:
            clave = base64.b64encode(secrets.token_bytes(32)).decode()
        contenido = RUTA_ARCHIVO_ENV.read_text(encoding="utf-8")
        contenido = actualizar_variable(contenido, "TOTP_CLAVE_CIFRADO", clave)
        contenido = actualizar_variable(contenido, "TOTP_HABILITADO", "true")
        RUTA_ARCHIVO_ENV.write_text(contenido, encoding="utf-8")
        obtener_configuracion.cache_clear()
        from aplicacion.servicios.totp import TotpService

        TotpService.clave()
        print("Cifrado TOTP local configurado y validado; clave conservada en backend/.env, sin mostrarla.")
    finally:
        await cerrar_motor_base_datos()


if __name__ == "__main__":
    try:
        asyncio.run(configurar())
    except Exception as error:
        # No imprimir excepciones de drivers, URLs ni valores de configuración.
        print("No se modificó la base de datos. Configuración pendiente: " + type(error).__name__)
        raise SystemExit(1) from None
