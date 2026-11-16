"""Semillas propuestas de organización. Sin DDL; requiere 0002 previamente aprobada."""

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion.base_datos.configuracion import ConfiguracionConexion
from aplicacion.modelos.historico import TipoUnidad
from seeds.ejecutar import DESTINO, RAIZ

TEMPORAL = "esart_hu04_fase3_temporal"
DESTINOS_AUTORIZADOS = (DESTINO, TEMPORAL)

CATALOGOS = {
    "tipos_unidad": ("TIPOS_UNIDAD", 9),
}


def referencias():
    """Reutiliza los 9 tipos de unidad sin ejecutar initial_data.py."""
    fuente = json.loads((RAIZ / "catalogos.json").read_text(encoding="utf-8"))["sin_tabla"]
    resultado = {}
    for catalogo, (clave, cantidad) in CATALOGOS.items():
        filas = fuente[clave]
        if len(filas) != cantidad:
            raise ValueError("Cantidad de referencia inesperada: " + catalogo)
        vistos = set()
        for fila in filas:
            codigo, nombre = fila["codigo"], fila["nombre"]
            if not isinstance(codigo, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,19}", codigo):
                raise ValueError("Codigo de referencia invalido")
            if codigo in vistos or not isinstance(nombre, str) or not nombre.strip() or len(nombre) > 200:
                raise ValueError("Referencia duplicada o nombre invalido")
            vistos.add(codigo)
        resultado[catalogo] = filas
    return resultado


def motor_pruebas(archivo_env, destino=DESTINO):
    """Sustituye el destino antes de crear el motor; nunca conecta a esart_db."""
    if destino not in DESTINOS_AUTORIZADOS:
        raise ValueError("Base no autorizada")
    config = ConfiguracionConexion(_env_file=archivo_env, entorno="pruebas")
    url = make_url(config.url_base_datos.get_secret_value()).set(database=destino)
    return create_async_engine(url, echo=False, hide_parameters=True, connect_args={"timeout": 5})


async def comprobar_revision(conexion, destino=DESTINO):
    base, superusuario, version = (
        await conexion.execute(
            text(
                "SELECT current_database(), (SELECT rolsuper FROM pg_roles WHERE rolname=current_user), "
                "current_setting('server_version_num')::integer / 10000"
            )
        )
    ).one()
    if destino not in DESTINOS_AUTORIZADOS or base != destino or superusuario or version != 18:
        raise RuntimeError("Destino o identidad no autorizados")
    # Los modelos no fijan schema: evitar resolución a tablas homónimas de otra ruta.
    await conexion.execute(text("SET LOCAL search_path = public, pg_catalog"))
    revision = (await conexion.execute(text("SELECT version_num FROM public.alembic_version"))).scalar_one()
    if revision != "0002":
        raise RuntimeError("Se requiere 0002 aprobada y aplicada; no se ejecuta DDL desde seeds")


async def poblar_tipos_unidad(conexion, destino=DESTINO):
    """No confirma transacciones: el llamador controla commit o rollback de pruebas."""
    filas = referencias()["tipos_unidad"]
    await comprobar_revision(conexion, destino)
    await conexion.execute(text("LOCK TABLE public.tipos_unidad IN SHARE ROW EXCLUSIVE MODE"))
    nuevos = (
        (
            await conexion.execute(
                insert(TipoUnidad)
                .values(filas)
                .on_conflict_do_nothing(index_elements=["codigo"])
                .returning(TipoUnidad.codigo)
            )
        )
        .scalars()
        .all()
    )
    actuales = {
        fila.codigo: fila.nombre
        for fila in (await conexion.execute(select(TipoUnidad.codigo, TipoUnidad.nombre)))
    }
    faltantes = [fila["codigo"] for fila in filas if fila["codigo"] not in actuales]
    if faltantes:
        raise RuntimeError("Carga incompleta de tipos de unidad")
    return {
        "tabla": "tipos_unidad",
        "insertados": len(nuevos),
        "omitidos": len(filas) - len(nuevos),
        "diferencias_conservadas": [
            fila["codigo"] for fila in filas if actuales[fila["codigo"]] != fila["nombre"]
        ],
    }


async def ejecutar(args, informe):
    datos = referencias()
    informe["referencias"] = {clave: len(filas) for clave, filas in datos.items()}
    informe["diferidos"] = {
        clave: "Sin entidad consumidora en alcance ESART vigente"
        for clave in ("estados_operacionales", "estados_logisticos")
    }
    motor = motor_pruebas(args.archivo_env)
    try:
        async with motor.begin() as conexion:
            await comprobar_revision(conexion)
            if args.aplicar:
                resultado = await poblar_tipos_unidad(conexion)
            else:
                existentes = set((await conexion.execute(select(TipoUnidad.codigo))).scalars())
                resultado = {
                    "tabla": "tipos_unidad",
                    "insertados": 0,
                    "faltantes": [
                        fila["codigo"] for fila in datos["tipos_unidad"] if fila["codigo"] not in existentes
                    ],
                }
        informe["resultado"] = resultado
        informe["confirmado"] = args.aplicar
        informe["estado"] = "aplicado" if args.aplicar else "inspeccion_sin_inserciones"
    finally:
        await motor.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo-env", default=".env")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--informe", type=Path, default=RAIZ / "fase3_ejecucion.json")
    args = parser.parse_args()
    informe = {"fecha_utc": datetime.now(UTC).isoformat(), "destino": DESTINO, "errores": []}
    try:
        asyncio.run(ejecutar(args, informe))
    except Exception as error:
        # No volcar mensajes SQL ni datos de conexion, tampoco en fallos.
        informe["estado"] = "error"
        informe["errores"].append({"tipo": type(error).__name__})
    args.informe.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=True, indent=2))
    return 1 if informe["errores"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
