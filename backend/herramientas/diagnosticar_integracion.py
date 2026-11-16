"""Fases 1 y 2: inventario READ ONLY y pg_dump de esart_db, sin migraciones ni seeds."""

# Los únicos identificadores dinámicos vienen de pg_catalog y se entrecomillan;
# los demás fragmentos SQL concatenados son constantes de este módulo.
# ruff: noqa: S608

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion import modelos  # noqa: F401
from aplicacion.base_datos.base import BaseModelo
from aplicacion.base_datos.configuracion import ConfiguracionConexion

BASE = "esart_db"
RAIZ = Path(__file__).resolve().parents[1]
BINARIOS = Path("C:/Program Files/PostgreSQL/18/bin")


def identificador(valor):
    return '"' + valor.replace('"', '""') + '"'


def completo(esquema, tabla):
    return identificador(esquema) + "." + identificador(tabla)


def guardar(ruta, valor):
    ruta.write_text(json.dumps(valor, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def verificar_proceso(argumentos, entorno=None):
    # Jamás imprimir stderr del cliente: podría contener detalles de conexión.
    resultado = subprocess.run(argumentos, env=entorno, capture_output=True, timeout=300, check=False)  # noqa: S603
    if resultado.returncode:
        raise RuntimeError("Fallo de herramienta PostgreSQL: " + Path(argumentos[0]).name)
    return resultado.stdout


def respaldar(url, carpeta, snapshot):
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
    entorno.update(
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGUSER=url.username,
        PGPASSWORD=url.password,
        PGDATABASE=BASE,
        PGOPTIONS="-c default_transaction_read_only=on",
    )
    archivo = carpeta / "esart_db_completo.dump"
    try:
        verificar_proceso(
            [
                str(BINARIOS / "pg_dump.exe"),
                "--no-password",
                "--format=custom",
                "--create",
                "--snapshot=" + snapshot,
                "--file=" + str(archivo),
            ],
            entorno,
        )
    except RuntimeError:
        # Se conserva el archivo fallido como evidencia, pero nunca como respaldo válido.
        estructura = carpeta / "esart_db_solo_estructura.dump"
        try:
            verificar_proceso(
                [
                    str(BINARIOS / "pg_dump.exe"),
                    "--no-password",
                    "--format=custom",
                    "--schema-only",
                    "--create",
                    "--snapshot=" + snapshot,
                    "--file=" + str(estructura),
                ],
                entorno,
            )
        except RuntimeError:
            return {
                "respaldo_completo_valido": False,
                "estado": "bloqueado_por_privilegios_de_lectura",
                "archivo_completo_inutilizable": str(archivo),
                "archivo_estructura_inutilizable": str(estructura),
                "estructura_listada_y_decodificada": False,
                "restauracion_real_probada": False,
            }
        verificar_proceso([str(BINARIOS / "pg_restore.exe"), "--list", str(estructura)])
        verificar_proceso(
            [
                str(BINARIOS / "pg_restore.exe"),
                "--file=" + str(carpeta / "estructura_decodificada.sql"),
                str(estructura),
            ]
        )
        return {
            "respaldo_completo_valido": False,
            "estado": "bloqueado_por_privilegios_de_lectura",
            "archivo_completo_inutilizable": str(archivo),
            "estructura_sin_datos": str(estructura),
            "bytes_estructura": estructura.stat().st_size,
            "sha256_estructura": hashlib.sha256(estructura.read_bytes()).hexdigest(),
            "estructura_listada_y_decodificada": True,
            "restauracion_real_probada": False,
        }
    listado = verificar_proceso([str(BINARIOS / "pg_restore.exe"), "--list", str(archivo)])
    (carpeta / "contenido_respaldo.txt").write_bytes(listado)
    # Decodifica todo el archivo, incluidas secciones de datos. No conecta ni ejecuta el SQL.
    decodificado = carpeta / "restauracion_decodificada.sql"
    verificar_proceso([str(BINARIOS / "pg_restore.exe"), "--file=" + str(decodificado), str(archivo)])
    return {
        "archivo": str(archivo),
        "bytes": archivo.stat().st_size,
        "sha256": hashlib.sha256(archivo.read_bytes()).hexdigest(),
        "pg_dump_correcto": True,
        "pg_restore_list_correcto": True,
        "decodificacion_completa_correcta": True,
        "restauracion_real_probada": False,
        "bytes_sql_decodificado": decodificado.stat().st_size,
    }


async def filas(conexion, sql):
    return [dict(fila) for fila in (await conexion.execute(text(sql))).mappings()]


async def diagnosticar(carpeta, con_respaldo):
    config = ConfiguracionConexion(_env_file=RAIZ / ".env", entorno="pruebas")
    origen = make_url(config.url_base_datos.get_secret_value())
    url = origen.set(database=BASE)
    motor = create_async_engine(
        url, echo=False, hide_parameters=True, connect_args={"timeout": 5, "command_timeout": 120}
    )
    informe = {
        "fecha_utc": datetime.now(UTC).isoformat(),
        "modo": "solo_lectura",
        "archivo_env_apunta_base_principal": origen.database == BASE,
    }
    try:
        async with motor.connect() as conexion, conexion.begin():
            await conexion.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            informe["identidad"] = (
                await filas(
                    conexion,
                    "SELECT current_database() base, current_user usuario, current_schema() esquema, "
                    "current_setting('server_version') version, current_setting('search_path') search_path, "
                    "current_setting('transaction_read_only') solo_lectura, "
                    "pg_get_userbyid(datdba) propietario FROM pg_database WHERE datname=current_database()",
                )
            )[0]
            if informe["identidad"]["base"] != BASE or informe["identidad"]["solo_lectura"] != "on":
                raise RuntimeError("Destino o transaccion no autorizados")
            informe["esquemas"] = await filas(
                conexion,
                "SELECT nspname esquema,pg_get_userbyid(nspowner) propietario,nspacl::text permisos "
                "FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema' "
                "ORDER BY nspname",
            )
            informe["privilegios_esquemas"] = await filas(
                conexion,
                "SELECT nspname esquema,has_schema_privilege(oid,'USAGE') uso, "
                "has_schema_privilege(oid,'CREATE') creacion FROM pg_namespace "
                "WHERE nspname !~ '^pg_' AND nspname <> 'information_schema' ORDER BY nspname",
            )
            filtro = "n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"
            informe["tablas"] = await filas(
                conexion,
                "SELECT n.nspname esquema,c.relname tabla,c.relkind::text clase, "
                "pg_get_userbyid(c.relowner) propietario,c.relrowsecurity rls,c.relacl::text permisos, "
                "has_table_privilege(c.oid,'SELECT') seleccion_permitida FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
                + filtro
                + " AND c.relkind IN ('r','p','f') ORDER BY n.nspname,c.relname",
            )
            informe["columnas"] = await filas(
                conexion,
                "SELECT n.nspname esquema,c.relname tabla,a.attname columna, a.attnum posicion, "
                "format_type(a.atttypid,a.atttypmod) tipo,NOT a.attnotnull permite_null, "
                "a.attidentity::text identidad,a.attgenerated::text generada, "
                "pg_get_expr(d.adbin,d.adrelid) defecto FROM pg_attribute a "
                "JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE "
                + filtro
                + " AND c.relkind IN ('r','p','f') AND a.attnum>0 AND NOT a.attisdropped "
                "ORDER BY n.nspname,c.relname,a.attnum",
            )
            informe["restricciones"] = await filas(
                conexion,
                "SELECT n.nspname esquema,c.relname tabla,co.conname nombre,co.contype::text tipo, "
                "co.convalidated validada,co.condeferrable diferible, "
                "pg_get_constraintdef(co.oid) definicion FROM pg_constraint co "
                "JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
                + filtro
                + " ORDER BY n.nspname,c.relname,co.conname",
            )
            informe["indices"] = await filas(
                conexion,
                "SELECT n.nspname esquema,t.relname tabla,c.relname nombre,i.indisunique unico, "
                "i.indisprimary primario,i.indisvalid valido,pg_get_indexdef(i.indexrelid) definicion "
                "FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid JOIN pg_class c ON c.oid=i.indexrelid "
                "JOIN pg_namespace n ON n.oid=t.relnamespace WHERE "
                + filtro
                + " ORDER BY n.nspname,t.relname,c.relname",
            )
            informe["secuencias"] = await filas(
                conexion,
                "SELECT schemaname esquema,sequencename nombre,sequenceowner propietario, "
                "data_type::text tipo,start_value,min_value,max_value,increment_by,cycle, "
                "cache_size,last_value "
                "FROM pg_sequences WHERE schemaname !~ '^pg_' ORDER BY schemaname,sequencename",
            )
            informe["triggers"] = await filas(
                conexion,
                "SELECT n.nspname esquema,c.relname tabla,t.tgname nombre,t.tgenabled::text habilitado, "
                "pg_get_triggerdef(t.oid) definicion FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
                + filtro
                + " AND NOT t.tgisinternal ORDER BY n.nspname,c.relname,t.tgname",
            )
            informe["funciones"] = await filas(
                conexion,
                "SELECT n.nspname esquema,p.proname nombre, "
                "pg_get_function_identity_arguments(p.oid) argumentos, "
                "l.lanname lenguaje,md5(pg_get_functiondef(p.oid)) huella_definicion "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "JOIN pg_language l ON l.oid=p.prolang WHERE "
                + filtro
                + " AND p.prokind IN ('f','p') ORDER BY n.nspname,p.proname",
            )
            informe["vistas"] = await filas(
                conexion,
                "SELECT schemaname esquema,viewname nombre,definition definicion FROM pg_views "
                "WHERE schemaname !~ '^pg_' AND schemaname <> 'information_schema'",
            )
            informe["extensiones"] = await filas(
                conexion, "SELECT extname nombre,extversion version FROM pg_extension ORDER BY extname"
            )
            informe["alembic"], informe["duplicados"], informe["catalogos_existentes"] = [], [], {}
            for tabla in informe["tablas"]:
                esquema, nombre = tabla["esquema"], tabla["tabla"]
                destino = completo(esquema, nombre)
                if not tabla["seleccion_permitida"]:
                    tabla["filas"], tabla["huella_filas"] = None, None
                    tabla["verificacion_datos"] = "bloqueada_sin_SELECT"
                    continue
                tabla["filas"] = await conexion.scalar(text("SELECT count(*) FROM " + destino))
                tabla["huella_filas"] = await conexion.scalar(
                    text(
                        "SELECT md5(coalesce(string_agg(row_to_json(t)::text,'' "  # noqa: S608
                        "ORDER BY row_to_json(t)::text),'')) FROM " + destino + " t"
                    )
                )
                columnas = [
                    c["columna"]
                    for c in informe["columnas"]
                    if c["esquema"] == esquema and c["tabla"] == nombre
                ]
                if nombre == "alembic_version":
                    informe["alembic"].append(
                        {
                            "esquema": esquema,
                            "revisiones": list(
                                (await conexion.execute(text("SELECT version_num FROM " + destino))).scalars()
                            ),
                        }
                    )
                campos = [campo for campo in ("codigo", "nombre") if campo in columnas]
                for campo in campos:
                    columna = identificador(campo)
                    duplicados = await conexion.scalar(
                        text(
                            f"SELECT count(*) FROM (SELECT {columna} FROM {destino} "  # noqa: S608
                            f"WHERE {columna} IS NOT NULL GROUP BY {columna} HAVING count(*)>1) d"
                        )
                    )
                    normalizados = await conexion.scalar(
                        text(
                            f"SELECT count(*) FROM (SELECT lower(btrim({columna}::text)) FROM {destino} "  # noqa: S608
                            f"WHERE {columna} IS NOT NULL GROUP BY lower(btrim({columna}::text)) "
                            "HAVING count(*)>1) d"
                        )
                    )
                    informe["duplicados"].append(
                        {
                            "esquema": esquema,
                            "tabla": nombre,
                            "campo": campo,
                            "grupos_exactos": duplicados,
                            "grupos_normalizados": normalizados,
                        }
                    )
                if nombre in (
                    "roles",
                    "permisos",
                    "tipos_cargo",
                    "tipos_curso",
                    "tipos_unidad",
                    "unidades_militares",
                ):
                    permitidos = [
                        c
                        for c in columnas
                        if c
                        in (
                            "id",
                            "codigo",
                            "nombre",
                            "descripcion",
                            "activo",
                            "activa",
                            "tipo",
                            "modalidad",
                            "duracion_semanas",
                            "cuenta_para_coofu",
                            "unidad_superior_id",
                            "unidad_padre_id",
                            "tipo_unidad_id",
                        )
                    ]
                    if permitidos:
                        informe["catalogos_existentes"][esquema + "." + nombre] = await filas(
                            conexion,
                            "SELECT " + ",".join(identificador(c) for c in permitidos) + " FROM " + destino,
                        )
            informe["fk"] = await filas(
                conexion,
                "SELECT n.nspname esquema,c.relname tabla,co.conname nombre,nr.nspname esquema_destino, "
                "r.relname tabla_destino,co.convalidated validada, "
                "ARRAY(SELECT a.attname FROM unnest(co.conkey) WITH ORDINALITY k(attnum,pos) "
                "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum ORDER BY pos) columnas, "
                "ARRAY(SELECT a.attname FROM unnest(co.confkey) WITH ORDINALITY k(attnum,pos) "
                "JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum=k.attnum ORDER BY pos) referencias "
                "FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_class r ON r.oid=co.confrelid "
                "JOIN pg_namespace nr ON nr.oid=r.relnamespace WHERE co.contype='f' AND " + filtro,
            )
            for fk in informe["fk"]:
                permisos = {(t["esquema"], t["tabla"]): t["seleccion_permitida"] for t in informe["tablas"]}
                if not permisos.get((fk["esquema"], fk["tabla"])) or not permisos.get(
                    (fk["esquema_destino"], fk["tabla_destino"])
                ):
                    fk["huerfanos"] = None
                    fk["verificacion"] = "bloqueada_sin_SELECT"
                    continue
                condicion = " AND ".join("t." + identificador(c) + " IS NOT NULL" for c in fk["columnas"])
                union = " AND ".join(
                    "t." + identificador(c) + "=r." + identificador(r)
                    for c, r in zip(fk["columnas"], fk["referencias"], strict=True)
                )
                fk["huerfanos"] = await conexion.scalar(
                    text(
                        "SELECT count(*) FROM "
                        + completo(fk["esquema"], fk["tabla"])
                        + " t WHERE "
                        + condicion
                        + " AND NOT EXISTS (SELECT 1 FROM "
                        + completo(fk["esquema_destino"], fk["tabla_destino"])
                        + " r WHERE "
                        + union
                        + ")"
                    )
                )
            dialecto = postgresql.dialect()
            informe["modelos_0002"] = {
                nombre: {
                    "columnas": [
                        {
                            "columna": c.name,
                            "tipo": str(c.type.compile(dialect=dialecto)),
                            "permite_null": c.nullable,
                            "pk": c.primary_key,
                        }
                        for c in tabla.c
                    ],
                    "fk": [
                        {"columna": f.parent.name, "destino": f.target_fullname} for f in tabla.foreign_keys
                    ],
                }
                for nombre, tabla in BaseModelo.metadata.tables.items()
            }
            informe["comparacion"] = []
            for nombre, esperado in informe["modelos_0002"].items():
                reales = [c for c in informe["columnas"] if c["tabla"] == nombre and c["esquema"] == "public"]
                homologas = [t["esquema"] for t in informe["tablas"] if t["tabla"] == nombre]
                informe["comparacion"].append(
                    {
                        "tabla_esperada": "public." + nombre,
                        "existe_public": bool(reales),
                        "esquemas_homonimos": homologas,
                        "columnas_esperadas": esperado["columnas"],
                        "columnas_public_actuales": reales,
                        "columnas_homonimas": [c for c in informe["columnas"] if c["tabla"] == nombre],
                    }
                )
            if con_respaldo:
                guardar(carpeta / "inventario.json", informe)
                snapshot = await conexion.scalar(text("SELECT pg_export_snapshot()"))
                informe["respaldo"] = await asyncio.to_thread(respaldar, url, carpeta, snapshot)
            informe["estado"] = (
                "diagnostico_metadatos_con_bloqueos_de_datos_y_respaldo"
                if any(not t["seleccion_permitida"] for t in informe["tablas"])
                else "diagnostico_completado_sin_modificaciones"
            )
        guardar(carpeta / "inventario.json", informe)
    finally:
        await motor.dispose()
    return informe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--respaldo", action="store_true")
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=False)
    try:
        informe = asyncio.run(diagnosticar(args.salida.resolve(), args.respaldo))
        print(
            json.dumps(
                {
                    "estado": informe["estado"],
                    "base": BASE,
                    "esquemas": [e["esquema"] for e in informe["esquemas"]],
                    "tablas": len(informe["tablas"]),
                    "alembic": informe["alembic"],
                    "tablas_con_datos": [
                        {"tabla": t["esquema"] + "." + t["tabla"], "filas": t["filas"]}
                        for t in informe["tablas"]
                        if t["filas"]
                    ],
                    "respaldo": informe.get("respaldo"),
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0
    except Exception as error:
        guardar(args.salida / "error.json", {"tipo": type(error).__name__})
        print("Diagnostico interrumpido: " + type(error).__name__ + "; sin mostrar secretos")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
