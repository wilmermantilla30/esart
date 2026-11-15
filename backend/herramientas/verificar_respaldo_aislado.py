"""Restaura un archivo en un clúster NUEVO local; nunca conecta al servidor operativo."""

# SQL dinámico limitado a identificadores escapados y nombres regclass del catálogo.
# ruff: noqa: S608

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import socket
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

BINARIOS = Path("C:/Program Files/PostgreSQL/18/bin")


def ejecutar(nombre, argumentos, entorno, carpeta, entrada=None):
    # pg_ctl puede dejar handles heredados al servidor en Windows: usar archivos,
    # no pipes cuya lectura esperaría a que termine el servidor de larga duración.
    log = carpeta / (nombre + "_ejecucion_privada.log")
    with log.open("ab") as salida:
        resultado = subprocess.run(  # noqa: S603
            [str(BINARIOS / nombre), *argumentos],
            env=entorno,
            input=entrada,
            stdout=salida,
            stderr=salida,
            timeout=180,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if resultado.returncode:
        raise RuntimeError("Fallo de herramienta: " + nombre)
    return b""


def identificador(valor):
    return '"' + valor.replace('"', '""') + '"'


async def comprobar(puerto, clave, directorio, origen):
    conexion = await asyncpg.connect(
        host="127.0.0.1",
        port=puerto,
        user="postgres",
        password=clave,
        database="postgres",
        timeout=5,
        command_timeout=60,
    )
    try:
        real = await conexion.fetchval("SHOW data_directory")
        if Path(real).resolve() != directorio.resolve():
            raise RuntimeError("El servidor no es la instancia aislada")
        if await conexion.fetchval("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='esart_db')"):
            raise RuntimeError("La instancia nueva ya contiene el destino")
        # Roles sin credenciales copiados solo como identidades de propiedad/ACL.
        await conexion.execute("CREATE ROLE esart_aplicacion NOLOGIN")

        def literal(valor):
            return "'" + valor.replace("'", "''") + "'"

        await conexion.execute(
            "CREATE DATABASE esart_db OWNER esart_aplicacion TEMPLATE template0 ENCODING 'UTF8' "
            "LC_COLLATE "
            + literal(origen["datcollate"])
            + " LC_CTYPE "
            + literal(origen["datctype"])
            + " LOCALE_PROVIDER libc"
        )
    finally:
        await conexion.close()


async def inventariar(puerto, clave, directorio):
    conexion = await asyncpg.connect(
        host="127.0.0.1",
        port=puerto,
        user="postgres",
        password=clave,
        database="esart_db",
        timeout=5,
        command_timeout=60,
    )
    try:
        async with conexion.transaction(readonly=True, isolation="repeatable_read"):
            real = await conexion.fetchval("SHOW data_directory")
            if Path(real).resolve() != directorio.resolve():
                raise RuntimeError("Destino de lectura no aislado")
            tablas = await conexion.fetch(
                "SELECT schemaname esquema,tablename tabla FROM pg_tables "
                "WHERE schemaname !~ '^pg_' AND schemaname <> 'information_schema' ORDER BY 1,2"
            )
            resultado = {
                "tablas": [],
                "catalogos": {},
                "identidad": {
                    "base": await conexion.fetchval("SELECT current_database()"),
                    "data_directory": str(directorio),
                    "servidor": "instancia_aislada_nueva",
                    "puerto_aislado": puerto,
                },
            }
            for tabla in tablas:
                nombre = identificador(tabla["esquema"]) + "." + identificador(tabla["tabla"])
                total = await conexion.fetchval("SELECT count(*) FROM " + nombre)
                resultado["tablas"].append({**dict(tabla), "filas": total})
                if tabla["tabla"] in ("tipos_cargo", "tipos_curso", "roles", "unidades_militares"):
                    columnas = await conexion.fetch(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema=$1 "
                        "AND table_name=$2 ORDER BY ordinal_position",
                        tabla["esquema"],
                        tabla["tabla"],
                    )
                    permitidas = [
                        f[0]
                        for f in columnas
                        if f[0]
                        in (
                            "id",
                            "codigo",
                            "nombre",
                            "descripcion",
                            "tipo",
                            "modalidad",
                            "duracion_semanas",
                            "cuenta_para_coofu",
                            "activo",
                            "activa",
                        )
                    ]
                    resultado["catalogos"][tabla["esquema"] + "." + tabla["tabla"]] = [
                        dict(f)
                        for f in await conexion.fetch(
                            "SELECT " + ",".join(identificador(c) for c in permitidas) + " FROM " + nombre
                        )
                    ]
            resultado["restricciones_no_validadas"] = await conexion.fetchval(
                "SELECT count(*) FROM pg_constraint co JOIN pg_namespace n ON n.oid=co.connamespace "
                "WHERE n.nspname IN ('esart','esart_ref','public') AND NOT co.convalidated"
            )
            resultado["indices_invalidos"] = await conexion.fetchval(
                "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname IN ('esart','esart_ref','public') AND NOT i.indisvalid"
            )
            fks = await conexion.fetch(
                "SELECT co.conname,co.conrelid::regclass::text origen,co.confrelid::regclass::text destino, "
                "ARRAY(SELECT attname FROM unnest(co.conkey) WITH ORDINALITY x(num,pos) "
                "JOIN pg_attribute a ON a.attrelid=co.conrelid AND a.attnum=x.num ORDER BY pos) columnas, "
                "ARRAY(SELECT attname FROM unnest(co.confkey) WITH ORDINALITY x(num,pos) "
                "JOIN pg_attribute a ON a.attrelid=co.confrelid AND a.attnum=x.num ORDER BY pos) referencias "
                "FROM pg_constraint co JOIN pg_namespace n ON n.oid=co.connamespace "
                "WHERE co.contype='f' AND n.nspname IN ('esart','esart_ref','public')"
            )
            resultado["fk_revisadas"] = len(fks)
            resultado["huerfanos"] = 0
            for fk in fks:
                presentes = " AND ".join("o." + identificador(c) + " IS NOT NULL" for c in fk["columnas"])
                union = " AND ".join(
                    "o." + identificador(c) + "=d." + identificador(r)
                    for c, r in zip(fk["columnas"], fk["referencias"], strict=True)
                )
                # Los nombres regclass proceden del catálogo de la instancia aislada.
                resultado["huerfanos"] += await conexion.fetchval(
                    "SELECT count(*) FROM "
                    + fk["origen"]
                    + " o WHERE "
                    + presentes
                    + " AND NOT EXISTS(SELECT 1 FROM "
                    + fk["destino"]
                    + " d WHERE "
                    + union
                    + ")"
                )
            if any(resultado[k] for k in ("restricciones_no_validadas", "indices_invalidos", "huerfanos")):
                raise RuntimeError("La restauracion presenta inconsistencias")
            return resultado
    finally:
        await conexion.close()


async def probar_propuesta_unidades(puerto, clave, directorio):
    """Prueba acotada de los SQL propuestos; la principal nunca es un destino permitido."""
    carpeta_propuesta = Path(__file__).resolve().parents[1] / "propuestas/integracion_principal"
    datos = json.loads((carpeta_propuesta / "datos_aprobados.json").read_text(encoding="utf-8"))
    conexion = await asyncpg.connect(
        host="127.0.0.1",
        port=puerto,
        user="postgres",
        password=clave,
        database="esart_db",
        timeout=5,
        command_timeout=60,
    )
    try:
        if Path(await conexion.fetchval("SHOW data_directory")).resolve() != directorio.resolve():
            raise RuntimeError("La prueba SQL no esta en la instancia aislada")
        if await conexion.fetchval("SELECT count(*) FROM esart_ref.unidades_militares") != 0:
            raise RuntimeError("La propuesta requiere homologar IDs heredados antes de insertar")
        tablas = await conexion.fetch(
            "SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('esart','esart_ref')"
        )

        async def huellas():
            resultado = {}
            for t in tablas:
                nombre = identificador(t[0]) + "." + identificador(t[1])
                resultado[nombre] = await conexion.fetchval(
                    "SELECT md5(coalesce(string_agg(row_to_json(t)::text,'' "
                    "ORDER BY row_to_json(t)::text),'')) FROM " + nombre + " t"
                )
            return resultado

        antes = await huellas()
        fk_sql = (
            "SELECT co.conname,pg_get_constraintdef(co.oid) definicion FROM pg_constraint co "
            "WHERE co.contype='f' AND co.confrelid='esart_ref.unidades_militares'::regclass ORDER BY 1"
        )
        fks = await conexion.fetch(fk_sql)
        for nombre in (
            "02_estructura_NO_EJECUTAR.sql",
            "03_tipos_NO_EJECUTAR.sql",
            "05_unidades_NO_EJECUTAR.sql",
        ):
            await conexion.execute((carpeta_propuesta / nombre).read_text(encoding="utf-8"))
        reales = await conexion.fetch(
            "SELECT u.codigo,u.nombre,u.sigla,u.activa,p.codigo superior_codigo,t.codigo tipo_codigo "
            "FROM esart_ref.unidades_militares u LEFT JOIN esart_ref.unidades_militares p "
            "ON p.id=u.unidad_superior_id LEFT JOIN esart.tipos_unidad t ON t.id=u.tipo_unidad_id "
            "ORDER BY u.codigo"
        )
        esperado = sorted(datos["unidades_militares"], key=lambda f: f["codigo"])
        if [dict(f) for f in reales] != esperado:
            raise RuntimeError("Los datos no coinciden con las 40 referencias aprobadas")
        despues = await huellas()
        if any(despues[n] != h for n, h in antes.items() if n != '"esart_ref"."unidades_militares"'):
            raise RuntimeError("La propuesta modifico tablas ajenas")
        # La ampliación añade una FK autorreferente; conservar las cinco anteriores,
        # sin confundir esa dependencia nueva con una modificación de las entrantes.
        fks_despues = {f["conname"]: f["definicion"] for f in await conexion.fetch(fk_sql)}
        if any(fks_despues.get(f["conname"]) != f["definicion"] for f in fks):
            raise RuntimeError("Cambiaron las cinco FK entrantes")
        estado_sql = "SELECT * FROM esart_ref.unidades_militares ORDER BY codigo"
        estado = await conexion.fetch(estado_sql)
        secuencia_sql = "SELECT last_value,is_called FROM esart_ref.unidades_militares_id_seq"
        secuencia = await conexion.fetchrow(secuencia_sql)
        for nombre in ("03_tipos_NO_EJECUTAR.sql", "05_unidades_NO_EJECUTAR.sql"):
            await conexion.execute((carpeta_propuesta / nombre).read_text(encoding="utf-8"))
        if estado != await conexion.fetch(estado_sql) or secuencia != await conexion.fetchrow(secuencia_sql):
            raise RuntimeError("La repeticion cambio filas, fechas o secuencia")
        return {
            "alcance": "propuesta SQL de unidades y tipos, no despliegue HU03 completo",
            "unidades": len(reales),
            "clasificadas": sum(f["tipo_codigo"] is not None for f in reales),
            "pendientes": [f["codigo"] for f in reales if f["tipo_codigo"] is None],
            "tipos": await conexion.fetchval("SELECT count(*) FROM esart.tipos_unidad"),
            "fk_entrantes_conservadas": len(fks),
            "tablas_ajenas_sin_cambios": True,
            "segunda_carga_sin_cambios_incluidas_fechas_y_secuencia": True,
            "entorno": "solo_instancia_nueva_aislada",
            "alembic_aplicado_en_principal": False,
        }
    finally:
        await conexion.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carpeta", type=Path, required=True)
    parser.add_argument("--probar-propuesta-unidades", action="store_true")
    args = parser.parse_args()
    carpeta = args.carpeta.resolve()
    archivo = json.loads((carpeta / "archivo_verificado.json").read_text(encoding="utf-8"))
    respaldo = Path(archivo["archivo"])
    if hashlib.sha256(respaldo.read_bytes()).hexdigest() != archivo["sha256"]:
        raise RuntimeError("Cambio el archivo de respaldo")
    directorio = carpeta / "cluster_aislado"
    if directorio.exists():
        raise RuntimeError("No se reutiliza ni se elimina un cluster existente")
    with socket.socket() as reserva:
        reserva.bind(("127.0.0.1", 0))
        puerto = reserva.getsockname()[1]
    if puerto == 5432:
        raise RuntimeError("Puerto reservado a servidor operativo")
    clave = secrets.token_urlsafe(40)
    # El secreto efímero nunca se crea dentro del repositorio, ni siquiera ignorado.
    descriptor, nombre_temporal = tempfile.mkstemp(prefix="esart_cluster_", suffix=".tmp")
    temporal = Path(nombre_temporal)
    with os.fdopen(descriptor, "w", encoding="utf-8") as salida_clave:
        salida_clave.write(clave + "\n")
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
    entorno.update(PGHOST="127.0.0.1", PGPORT=str(puerto), PGUSER="postgres", PGPASSWORD=clave)
    iniciado = False
    informe = {"fecha_utc": datetime.now(UTC).isoformat(), "respaldo": archivo, "errores": []}
    try:
        ejecutar(
            "initdb.exe",
            [
                "-D",
                str(directorio),
                "-U",
                "postgres",
                "--encoding=UTF8",
                "--no-locale",
                "--auth=scram-sha-256",
                "--pwfile=" + str(temporal),
            ],
            entorno,
            carpeta,
        )
        ejecutar(
            "pg_ctl.exe",
            [
                "-D",
                str(directorio),
                "-l",
                str(carpeta / "servidor_privado.log"),
                "-o",
                "-h 127.0.0.1 -p " + str(puerto),
                "-w",
                "start",
            ],
            entorno,
            carpeta,
        )
        iniciado = True
        asyncio.run(comprobar(puerto, clave, directorio, archivo["origen"]))
        ejecutar(
            "pg_restore.exe",
            ["--no-password", "--exit-on-error", "--dbname=esart_db", str(respaldo)],
            entorno,
            carpeta,
        )
        informe["restauracion"] = asyncio.run(inventariar(puerto, clave, directorio))
        if args.probar_propuesta_unidades:
            informe["prueba_propuesta_unidades"] = asyncio.run(
                probar_propuesta_unidades(puerto, clave, directorio)
            )
        informe["estado"] = "restaurado_y_validado_en_instancia_independiente"
    except Exception as error:
        informe["estado"] = "error"
        informe["errores"].append({"tipo": type(error).__name__})
        if isinstance(error, RuntimeError):
            informe["errores"][-1]["detalle_seguro"] = str(error)
    finally:
        if iniciado:
            try:
                ejecutar("pg_ctl.exe", ["-D", str(directorio), "-m", "fast", "-w", "stop"], entorno, carpeta)
                informe["servidor_aislado_detenido"] = True
            except RuntimeError:
                informe["estado"] = "error"
                informe["errores"].append({"tipo": "FalloDetencionInstanciaAislada"})
        temporal.unlink(missing_ok=True)  # Solo el secreto temporal creado por este proceso.
        (carpeta / "restauracion_verificada.json").write_text(
            json.dumps(informe, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "estado": informe["estado"],
                "errores": informe["errores"],
                "informe": str(carpeta / "restauracion_verificada.json"),
                "tablas": informe.get("restauracion", {}).get("tablas"),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 1 if informe["errores"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
