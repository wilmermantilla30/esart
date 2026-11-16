"""Inspección y carga restringidas a esart_hu03_pruebas, con evidencia JSON."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DESTINO = "esart_hu03_pruebas"
ARCHIVOS = {
    "roles": "01_roles.sql",
    "permisos": "02_permisos.sql",
    "unidades_militares": "03_unidades_militares.sql",
}


async def ejecutar(args, informe):
    import asyncpg
    from sqlalchemy.engine import make_url

    from aplicacion.base_datos.configuracion import ConfiguracionConexion
    from seeds.validar import validar_catalogos

    if not args.catalogo or any(tabla not in ARCHIVOS for tabla in args.catalogo):
        raise ValueError("Catalogo no autorizado")
    catalogos = json.loads((RAIZ / "catalogos.json").read_text(encoding="utf-8"))
    validar_catalogos(catalogos)

    config = ConfiguracionConexion(_env_file=args.archivo_env, entorno="pruebas")
    url = make_url(config.url_base_datos.get_secret_value())
    # Se conserva servidor/cuenta/contraseña y se cambia SOLO el destino en memoria.
    conexion = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=DESTINO,
        timeout=5,
        command_timeout=60,
    )
    try:
        identidad = await conexion.fetchrow(
            "SELECT current_database() AS base, current_user AS usuario, "
            "current_setting('server_version') AS version, "
            "(SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AS superusuario"
        )
        if identidad["base"] != DESTINO or identidad["superusuario"]:
            raise RuntimeError("Identidad de conexion no autorizada")
        informe["identidad"] = dict(identidad)
        if int(identidad["version"].split(".")[0]) != 18:
            raise RuntimeError("Se requiere PostgreSQL 18")
        if await conexion.fetchval("SELECT version_num FROM public.alembic_version") != "0001":
            raise RuntimeError("Se requiere revision 0001")
        informe["inventario"] = {}
        for tabla in ARCHIVOS:
            columnas = await conexion.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=$1",
                tabla,
            )
            informe["inventario"][tabla] = [c[0] for c in columnas]
            requeridas = {"id", "codigo", "nombre" if tabla != "permisos" else "descripcion"}
            if tabla == "unidades_militares":
                requeridas |= {"unidad_superior_id", "activa"}
            if not requeridas <= set(informe["inventario"][tabla]):
                raise RuntimeError("Tabla incompatible: " + tabla)

        # Huella de todas las tablas ajenas a esta carga (incluye usuarios y académicos).
        async def huellas():
            tablas = await conexion.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
            resultado = {}
            for fila in tablas:
                tabla = fila[0]
                if tabla in ARCHIVOS or tabla == "auditoria_eventos":
                    continue
                identificador = '"' + tabla.replace('"', '""') + '"'
                resultado[tabla] = await conexion.fetchval(
                    "SELECT md5(COALESCE(string_agg(row_to_json(t)::text, '' "  # noqa: S608
                    "ORDER BY row_to_json(t)::text), '')) FROM public." + identificador + " t"
                )
            return resultado

        antes = await huellas()
        informe["resultados"] = []

        def aviso(_conexion, mensaje):
            try:
                dato = json.loads(mensaje.message)
            except (ValueError, AttributeError):
                return
            if isinstance(dato, dict) and "insertados" in dato:
                informe["resultados"].append(dato)

        conexion.add_log_listener(aviso)
        if args.aplicar:
            for tabla in args.catalogo:
                # El SQL debe corresponder al mismo manifiesto validado, sin deriva.
                from seeds.generar import literal

                contenido = (RAIZ / ARCHIVOS[tabla]).read_text(encoding="utf-8")
                if literal(json.dumps(catalogos[tabla], ensure_ascii=False)) not in contenido:
                    raise RuntimeError("SQL y manifiesto diferentes; ejecutar seeds.generar")
                informe["script_en_curso"] = ARCHIVOS[tabla]
                inicio = len(informe["resultados"])
                try:
                    await conexion.execute(contenido)
                except Exception:
                    # Un NOTICE previo a un fallo no demuestra un COMMIT.
                    del informe["resultados"][inicio:]
                    await conexion.execute("ROLLBACK")
                    raise
                for resultado in informe["resultados"][inicio:]:
                    resultado["confirmado"] = True
            informe.pop("script_en_curso", None)
        informe["tablas_ajenas_sin_cambios"] = antes == await huellas()
        if not informe["tablas_ajenas_sin_cambios"]:
            raise RuntimeError("Cambio concurrente o inesperado en tablas ajenas")
        informe["validacion"] = {}
        informe["integridad"] = dict(
            await conexion.fetchrow(
                "SELECT "
                "(SELECT count(*) FROM public.unidades_militares u LEFT JOIN "
                "public.unidades_militares p ON p.id=u.unidad_superior_id "
                "WHERE u.unidad_superior_id IS NOT NULL AND p.id IS NULL) AS unidades_huerfanas, "
                "(SELECT count(*) FROM public.roles_permisos rp "
                "LEFT JOIN public.roles r ON r.id=rp.rol_id "
                "LEFT JOIN public.permisos p ON p.id=rp.permiso_id "
                "WHERE r.id IS NULL OR p.id IS NULL) AS asignaciones_huerfanas"
            )
        )
        if any(informe["integridad"].values()):
            raise RuntimeError("Integridad referencial invalida")
        await conexion.execute((RAIZ / "sql/validaciones.sql").read_text(encoding="utf-8"))
        informe["validaciones_sql_ejecutadas"] = True
        for tabla in args.catalogo:
            filas = await conexion.fetch("SELECT * FROM public." + tabla)  # noqa: S608 -- lista ARCHIVOS
            por_codigo = {f["codigo"]: f for f in filas}
            faltantes, diferencias = [], []
            ids = {f["id"]: f["codigo"] for f in filas}
            for esperado in catalogos[tabla]:
                actual = por_codigo.get(esperado["codigo"])
                if actual is None:
                    faltantes.append(esperado["codigo"])
                    continue
                campos = ("descripcion",) if tabla == "permisos" else ("nombre",)
                if any(actual[c] != esperado[c] for c in campos):
                    diferencias.append(esperado["codigo"])
                if tabla == "unidades_militares":
                    if ids.get(actual["unidad_superior_id"]) != esperado["padre"]:
                        raise RuntimeError("Jerarquia incompatible: " + esperado["codigo"])
            informe["validacion"][tabla] = {
                "total_tabla": len(filas),
                "esperados": len(catalogos[tabla]),
                "faltantes": faltantes,
                "diferencias_conservadas": diferencias,
            }
            if args.aplicar and faltantes:
                raise RuntimeError("Carga incompleta: " + tabla)
        informe["estado"] = "validado" if args.aplicar else "inspeccion_sin_inserciones"
    finally:
        await conexion.close()


def main(catalogo=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo-env", default=".env")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--catalogo", nargs="+", choices=list(ARCHIVOS), default=list(ARCHIVOS))
    parser.add_argument("--informe", type=Path, default=RAIZ / "ultima_ejecucion.json")
    args = parser.parse_args()
    if catalogo is not None:
        args.catalogo = [catalogo]
    informe = {
        "fecha_utc": datetime.now(UTC).isoformat(),
        "destino": DESTINO,
        "modo": "aplicar" if args.aplicar else "inspeccionar",
        "errores": [],
    }
    try:
        asyncio.run(ejecutar(args, informe))
    except Exception as error:
        # Nunca volcar URL, parámetros de conexión ni mensajes con secretos.
        informe["estado"] = "error"
        informe["errores"].append(
            {"tipo": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None)}
        )
    args.informe.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=True, indent=2))
    return 1 if informe["errores"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
