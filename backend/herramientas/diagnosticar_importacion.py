"""Diagnóstico de solo lectura; no muestra credenciales ni registra personas.

Ejecutar desde backend/: python herramientas/diagnosticar_importacion.py
No prueba una cookie de navegador, no importa archivos ni cambia permisos.
"""

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones  # noqa: E402
from aplicacion.configuracion import obtener_configuracion  # noqa: E402
from aplicacion.principal import aplicacion  # noqa: E402
from aplicacion.servicios.importacion_personal import CAMPOS, estado_sql_seguro  # noqa: E402


async def diagnosticar():
    """Informa ruta, flags públicos y privilegios efectivos mediante una transacción read-only."""
    cfg = obtener_configuracion()
    salida = {
        "ruta_importacion_registrada": any(
            r.path == "/api/importaciones/excel" and "POST" in (getattr(r, "methods", None) or set())
            for r in aplicacion.routes
        ),
        "autenticacion": "JWT en cookie HttpOnly esart_sesion; sin Bearer",
        "cookie_segura": cfg.cookie_segura,
        "totp_habilitado": cfg.totp_habilitado,
        "sesion_del_navegador": "No inspeccionada; requiere cookie firmada y sesión vigente con MFA.",
    }
    try:
        async with obtener_fabrica_sesiones()() as sesion:
            await sesion.execute(text("SET TRANSACTION READ ONLY"))
            permisos = (
                (
                    await sesion.execute(
                        text("""
                SELECT nombre, has_column_privilege('esart.personal_militar', nombre, 'INSERT') AS permitido
                FROM unnest(CAST(:columnas AS text[])) AS columnas(nombre)
            """),
                        {"columnas": list(CAMPOS)},
                    )
                )
                .mappings()
                .all()
            )
            salida["conexion_postgresql"] = True
            salida["privilegios_auxiliares"] = dict(
                (
                    await sesion.execute(
                        text("""
                SELECT has_schema_privilege('esart','USAGE') AS uso_esart,
                       has_schema_privilege('esart_ref','USAGE') AS uso_esart_ref,
                       has_column_privilege('esart_ref.unidades_militares','id','SELECT')
                       AND has_column_privilege('esart_ref.unidades_militares','codigo','SELECT')
                       AND has_column_privilege('esart_ref.unidades_militares','nombre','SELECT')
                       AS leer_catalogo,
                       rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
                FROM pg_roles WHERE rolname=current_user
            """)
                    )
                )
                .mappings()
                .one()
            )
            salida["identidades"] = [
                dict(f)
                for f in (
                    await sesion.execute(
                        text("""
                SELECT c.relname AS tabla, a.attidentity::text AS identidad
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='esart' AND c.relname IN ('personal_militar','auditoria_eventos')
                  AND a.attname='id' AND NOT a.attisdropped
            """)
                    )
                )
                .mappings()
                .all()
            ]
            salida["columnas_sin_insert"] = [p["nombre"] for p in permisos if not p["permitido"]]
            salida["registros_personal_actuales"] = await sesion.scalar(
                text("SELECT count(*) FROM esart.personal_militar")
            )
            salida["importaciones_aplicadas_auditadas"] = await sesion.scalar(
                text(
                    "SELECT count(*) FROM esart.auditoria_eventos "
                    "WHERE accion='IMPORTACION_EXCEL' AND resultado='APLICADA'"
                )
            )
            salida["estado_guardado"] = (
                "BLOQUEADO_POR_PRIVILEGIOS"
                if salida["columnas_sin_insert"]
                else "PRIVILEGIOS_INSERT_DISPONIBLES"
            )
            salida["verificacion_archivo_especifico"] = (
                "No realizada: no se proporcionó un Excel para comparar documentos."
            )
    except SQLAlchemyError as error:
        salida["error_diagnostico_sql"] = {"tipo": type(error).__name__, "sqlstate": estado_sql_seguro(error)}
    finally:
        await cerrar_motor_base_datos()
    return salida


if __name__ == "__main__":
    print(json.dumps(asyncio.run(diagnosticar()), ensure_ascii=False, indent=2))
