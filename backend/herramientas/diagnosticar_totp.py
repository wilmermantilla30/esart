"""Diagnóstico TOTP de solo lectura: metadatos y permisos, nunca credenciales ni factores."""

import asyncio
import base64
import json

from sqlalchemy import text

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos.totp import BaseSeguridad
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.requisitos_totp import permisos_faltantes
from aplicacion.servicios.totp import TotpService


async def diagnosticar():
    try:
        async with obtener_fabrica_sesiones()() as sesion:
            await sesion.execute(text("SET TRANSACTION READ ONLY"))
            identidad = (
                (
                    await sesion.execute(
                        text(
                            "SELECT current_database() AS base, current_user AS rol, "
                            "inet_server_addr()::text AS servidor,inet_server_port() AS puerto, "
                            "pg_postmaster_start_time()::text AS inicio_instancia"
                        )
                    )
                )
                .mappings()
                .one()
            )
            if identidad["base"] != "esart_db":
                raise ValueError("Destino distinto de esart_db")
            consultas = {
                "columnas": """SELECT c.relname AS tabla,a.attname AS columna,
                    format_type(a.atttypid,a.atttypmod) AS tipo,a.attnotnull AS obligatorio
                    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='seguridad' AND a.attnum>0 AND NOT a.attisdropped
                    AND c.relkind='r' ORDER BY c.relname,a.attnum""",
                "restricciones": """SELECT c.relname AS tabla,k.conname,k.convalidated,
                    pg_get_constraintdef(k.oid) AS definicion FROM pg_constraint k
                    JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='seguridad' ORDER BY c.relname,k.conname""",
                "permisos_columnas": """SELECT table_name,column_name,privilege_type
                    FROM information_schema.column_privileges
                    WHERE table_schema='seguridad' AND grantee='esart_aplicacion'
                    ORDER BY table_name,column_name,privilege_type""",
                "permisos_tablas": """SELECT table_name,privilege_type
                    FROM information_schema.table_privileges
                    WHERE table_schema='seguridad' AND grantee='esart_aplicacion'
                    ORDER BY table_name,privilege_type""",
                "triggers": """SELECT c.relname AS tabla,t.tgname,t.tgenabled
                    FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='seguridad' AND NOT t.tgisinternal""",
                "accesos_efectivos": """SELECT c.relname AS tabla,
                    has_table_privilege('esart_aplicacion',c.oid,'SELECT') AS lectura,
                    has_table_privilege('esart_aplicacion',c.oid,'INSERT') AS insercion,
                    has_table_privilege('esart_aplicacion',c.oid,'UPDATE') AS actualizacion
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='seguridad' AND c.relkind='r' ORDER BY c.relname""",
                "secuencias": """SELECT c.relname AS secuencia,
                    has_sequence_privilege('esart_aplicacion',c.oid,'USAGE') AS uso
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='seguridad' AND c.relkind='S' ORDER BY c.relname""",
                "generacion_ids": """SELECT c.relname AS tabla,a.attidentity::text AS identidad,
                    pg_get_serial_sequence(format('%I.%I',n.nspname,c.relname),'id') AS secuencia,
                    pg_get_expr(d.adbin,d.adrelid) AS defecto
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='id'
                    LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
                    WHERE n.nspname='seguridad' AND c.relkind='r' ORDER BY c.relname""",
            }
            salida = {"conexion": dict(identidad)}
            for nombre, consulta in consultas.items():
                salida[nombre] = [dict(fila) for fila in (await sesion.execute(text(consulta))).mappings()]
            reales = {(fila["tabla"], fila["columna"]) for fila in salida["columnas"]}
            salida["columnas_mapeadas_ausentes"] = [
                f"{tabla.name}.{columna.name}"
                for tabla in BaseSeguridad.metadata.tables.values()
                for columna in tabla.columns
                if (tabla.name, columna.name) not in reales
            ]
            cfg = obtener_configuracion()
            presente = bool(cfg.totp_clave_cifrado and cfg.totp_clave_cifrado.get_secret_value())
            valida = False
            if presente:
                try:
                    valida = (
                        len(base64.b64decode(cfg.totp_clave_cifrado.get_secret_value(), validate=True)) == 32
                    )
                except (ValueError, TypeError):
                    pass
            salida["configuracion"] = {
                "totp_habilitado": cfg.totp_habilitado,
                "clave_presente": presente,
                "clave_base64_32_bytes": valida,
            }
            salida["permisos_faltantes_login"] = await permisos_faltantes(sesion)
            try:
                await TotpService(sesion).preparar()
                salida["preparacion_login"] = {"disponible": True}
            except ErrorAplicacion as error:
                salida["preparacion_login"] = {
                    "disponible": False,
                    "http": error.estado_http,
                    "codigo": error.codigo,
                    "mensaje": error.mensaje,
                }
            puede_leer = await sesion.scalar(
                text("SELECT has_table_privilege('seguridad.politicas_accion','SELECT')")
            )
            salida["politicas_login"] = {"lectura_autorizada": bool(puede_leer)}
            if puede_leer:
                salida["politicas_login"]["filas"] = [
                    dict(r)
                    for r in (
                        await sesion.execute(
                            text(
                                "SELECT codigo,activa,requiere_totp,vigencia_segundos "
                                "FROM seguridad.politicas_accion "
                                "WHERE codigo IN ('LOGIN_TOTP','DESBLOQUEO_TOTP') ORDER BY codigo"
                            )
                        )
                    ).mappings()
                ]
            politicas = salida["politicas_login"].get("filas", [])
            validas = {
                r["codigo"]
                for r in politicas
                if r["activa"] and r["requiere_totp"] and 30 <= r["vigencia_segundos"] <= 600
            }
            salida["listo_para_autenticar"] = bool(
                salida["preparacion_login"]["disponible"]
                and {"LOGIN_TOTP", "DESBLOQUEO_TOTP"}.issubset(validas)
            )
            print(json.dumps(salida, ensure_ascii=False, indent=2))
            await sesion.rollback()
    except Exception as error:
        # No imprimir mensajes de drivers ni URLs de conexión.
        print(json.dumps({"diagnostico": "no_disponible", "tipo_error": type(error).__name__}))
        return False
    finally:
        await cerrar_motor_base_datos()
    return True


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(diagnosticar()) else 1)
