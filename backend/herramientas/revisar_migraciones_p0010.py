"""Inventario READ ONLY para aprobar HU-10/TOTP. No invoca env.py, Alembic ni DDL."""

import asyncio
import json

from sqlalchemy import text

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones


async def revisar():
    try:
        async with obtener_fabrica_sesiones()() as s:
            await s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            datos = {}
            consultas = {
                "conexion": """SELECT current_database() AS base,current_user AS rol,
                    inet_server_addr()::text AS servidor,inet_server_port() AS puerto,
                    current_setting('server_version') AS version,
                    pg_postmaster_start_time()::text AS inicio_instancia""",
                "objetos": """SELECT n.nspname AS esquema,c.relname AS nombre,c.relkind::text AS tipo,
                    pg_get_userbyid(c.relowner) AS propietario,c.relrowsecurity AS rls,
                    has_table_privilege(c.oid,'SELECT') AS lectura,
                    has_table_privilege(c.oid,'INSERT') AS insercion,
                    has_table_privilege(c.oid,'UPDATE') AS actualizacion,
                    has_table_privilege(c.oid,'DELETE') AS borrado,
                    has_table_privilege(c.oid,'TRUNCATE') AS truncado
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.relkind IN ('r','p') AND (n.nspname='seguridad' OR
                      (n.nspname='esart' AND c.relname IN ('alembic_version','componentes','roles',
                        'rol_permisos','usuario_permisos','parametros_habilitacion','auditoria_eventos',
                        'auditoria_acceso','desafios_captcha','limites_inicio_ip','estados_acceso_anonimos'))
                      OR (n.nspname='esart_ref' AND c.relname='usuarios')) ORDER BY n.nspname,c.relname""",
                "columnas": """SELECT n.nspname AS esquema,c.relname AS tabla,a.attname AS columna,
                    format_type(a.atttypid,a.atttypmod) AS tipo,a.attnotnull AS obligatorio,
                    a.attidentity::text AS identidad,pg_get_expr(d.adbin,d.adrelid) AS defecto
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
                    LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
                    WHERE c.relkind='r' AND (n.nspname='seguridad' OR
                      (n.nspname='esart' AND c.relname IN ('auditoria_eventos','parametros_habilitacion')) OR
                      (n.nspname='esart_ref' AND c.relname='usuarios'))
                    ORDER BY n.nspname,c.relname,a.attnum""",
                "restricciones": """SELECT n.nspname AS esquema,c.relname AS tabla,k.conname AS nombre,
                    k.convalidated AS validada,pg_get_constraintdef(k.oid) AS definicion
                    FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname IN ('seguridad','esart','esart_ref')
                    ORDER BY n.nspname,c.relname,k.conname""",
                "triggers": """SELECT n.nspname AS esquema,c.relname AS tabla,t.tgname AS nombre,
                    t.tgenabled::text AS habilitado,pg_get_triggerdef(t.oid) AS definicion
                    FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname IN ('seguridad','esart','esart_ref') AND NOT t.tgisinternal
                    ORDER BY n.nspname,c.relname,t.tgname""",
                "funciones_auditoria": """SELECT n.nspname AS esquema,p.proname AS funcion,
                    pg_get_userbyid(p.proowner) AS propietario FROM pg_proc p
                    JOIN pg_namespace n ON n.oid=p.pronamespace
                    WHERE (n.nspname='seguridad' AND p.proname='impedir_cambio_auditoria')
                       OR (n.nspname='esart' AND p.proname='impedir_modificacion_auditoria')""",
                "permisos_columnas_usuario": """SELECT a.attname AS columna,
                    has_column_privilege(c.oid,a.attname,'UPDATE') AS actualizable
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
                    WHERE n.nspname='esart_ref' AND c.relname='usuarios' ORDER BY a.attnum""",
            }
            for nombre, consulta in consultas.items():
                datos[nombre] = [dict(r) for r in (await s.execute(text(consulta))).mappings()]
            if datos["conexion"][0]["base"] != "esart_db":
                raise ValueError("Destino distinto de esart_db")
            objetos = {(r["esquema"], r["nombre"]): r for r in datos["objetos"]}
            historia = objetos.get(("esart", "alembic_version"))
            datos["historial_aplicado"] = (
                (await s.execute(text("SELECT version_num FROM esart.alembic_version"))).scalars().all()
                if historia and historia["lectura"]
                else "NO_VERIFICABLE_CON_ESTE_ROL"
            )
            datos["huerfanos_usuario"] = {}
            for tabla in ("usuario_totp", "totp_recuperacion", "desafios", "autorizaciones", "auditoria"):
                permitido = await s.scalar(
                    text("""SELECT COALESCE(has_column_privilege(
                    to_regclass(:tabla),'usuario_id','SELECT'),false)"""),
                    {"tabla": "seguridad." + tabla},
                )
                if permitido:
                    # Identificadores constantes de la lista anterior; salida solo agregada.
                    datos["huerfanos_usuario"][tabla] = await s.scalar(
                        text(
                            f"SELECT count(*) FROM seguridad.{tabla} t LEFT JOIN esart_ref.usuarios u "  # noqa: S608
                            "ON u.id=t.usuario_id WHERE t.usuario_id IS NOT NULL AND u.id IS NULL"
                        )
                    )  # noqa: S608
                else:
                    datos["huerfanos_usuario"][tabla] = "PENDIENTE_PROPIETARIO"
            datos["contextos_autorizacion_incompatibles"] = "PENDIENTE_PROPIETARIO"
            if objetos.get(("seguridad", "autorizaciones"), {}).get("lectura"):
                datos["contextos_autorizacion_incompatibles"] = await s.scalar(
                    text("""
                    SELECT count(*) FROM seguridad.autorizaciones a LEFT JOIN seguridad.desafios d
                    ON (a.desafio_id,a.usuario_id,a.politica_id,a.operacion_hash)=
                       (d.id,d.usuario_id,d.politica_id,d.operacion_hash) WHERE d.id IS NULL""")
                )
            if objetos.get(("seguridad", "politicas_accion"), {}).get("lectura"):
                datos["politicas"] = [
                    dict(r)
                    for r in (
                        await s.execute(
                            text(
                                "SELECT codigo,activa,requiere_totp,vigencia_segundos,permiso_requerido "
                                "FROM seguridad.politicas_accion ORDER BY codigo"
                            )
                        )
                    ).mappings()
                ]
            if objetos.get(("esart", "auditoria_eventos"), {}).get("lectura"):
                datos["acciones_auditadas"] = [
                    dict(r)
                    for r in (
                        await s.execute(
                            text(
                                "SELECT accion,count(*) AS cantidad "
                                "FROM esart.auditoria_eventos GROUP BY accion"
                            )
                        )
                    ).mappings()
                ]
            await s.rollback()
            print(json.dumps(datos, ensure_ascii=False, indent=2))
    except Exception as error:
        print(json.dumps({"estado": "diagnostico_incompleto", "tipo": type(error).__name__}))
        return False
    finally:
        await cerrar_motor_base_datos()
    return True


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(revisar()) else 1)
