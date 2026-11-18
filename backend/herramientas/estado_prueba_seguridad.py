"""Lectura acotada de la cuenta expresamente autorizada para el diagnóstico operativo."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from aplicacion.base_datos.sesion import obtener_motor_base_datos


async def main():
    motor = obtener_motor_base_datos()
    try:
        async with motor.connect() as c:
            await c.execute(text("SET TRANSACTION READ ONLY"))
            base = await c.scalar(text("SELECT current_database()"))
            if base != "esart_db":
                raise RuntimeError("Destino incorrecto")
            fila = (await c.execute(text("""
              SELECT u.id,u.usuario,u.intentos_fallidos_consecutivos,u.bloqueado_hasta,
                i.fecha,i.motivo_fallo,i.captcha_requerido,i.captcha_validado
              FROM esart_ref.usuarios u LEFT JOIN LATERAL (
                SELECT fecha,motivo_fallo,captcha_requerido,captcha_validado
                FROM esart.intentos_inicio_sesion WHERE usuario_id=u.id
                ORDER BY fecha DESC,id DESC LIMIT 1) i ON true
              WHERE u.id=3 AND u.usuario='prueba.seguridad'
            """))).mappings().one()
            datos = {"base": base, **dict(fila)}
            datos["contrasena_comprobada"] = datos["motivo_fallo"] == "CREDENCIALES_INVALIDAS"
            manifiesto = json.loads(Path("respaldos/captcha_local_actual.json").read_text())
            archivo = Path(manifiesto["carpeta"]) / "registro_sql.json"
            registro = json.loads(archivo.read_text()) if archivo.exists() else []
            registro.append(datos)
            archivo.write_text(json.dumps(registro, default=str, indent=2), encoding="utf-8")
            print(json.dumps(datos, default=str))
    finally:
        await motor.dispose()


if __name__ == "__main__":
    asyncio.run(main())
