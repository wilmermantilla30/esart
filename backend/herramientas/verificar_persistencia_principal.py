"""Verificación exclusivamente de lectura de esart_db; nunca migra ni puebla."""

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion.base_datos.configuracion import obtener_configuracion_conexion, opciones_tls_local
from aplicacion.modelos import TipoCargo, TipoCurso, TipoUnidad, UnidadMilitar

BACKEND = Path(__file__).parents[1]


async def verificar():
    configuracion = obtener_configuracion_conexion()
    url = configuracion.url_base_datos.get_secret_value()
    motor = create_async_engine(url, echo=False, hide_parameters=True, connect_args=opciones_tls_local(url))
    resultado = {"modo": "solo_lectura", "modificaciones": 0, "bloqueos": []}
    try:
        async with motor.connect() as conexion:
            await conexion.execute(text("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            identidad = (
                (await conexion.execute(text("SELECT current_database() base,current_user usuario")))
                .mappings()
                .one()
            )
            if identidad["base"] != "esart_db" or identidad["usuario"] != "esart_aplicacion":
                raise RuntimeError("Conexión operativa incorrecta")
            resultado["conexion"] = dict(identidad)
            ruta = BACKEND / "migraciones_principal/versions/p0001_estructura_real.py"
            spec = importlib.util.spec_from_file_location("base_real_verificacion", ruta)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            await conexion.run_sync(modulo.validar_estructura)
            resultado["estructura"] = "equivalente_a_p0001_propuesta_sin_registrar_revision"
            resultado["conteos"] = {}
            for modelo, esperado in [
                (UnidadMilitar, 40),
                (TipoUnidad, 9),
                (TipoCargo, 5),
                (TipoCurso, 14),
            ]:
                tabla = modelo.__table__
                permiso = await conexion.scalar(
                    text("""
                  SELECT has_schema_privilege(n.oid,'USAGE') AND has_table_privilege(t.oid,'SELECT')
                  FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
                  WHERE n.nspname=:s AND t.relname=:t
                """),
                    {"s": tabla.schema, "t": tabla.name},
                )
                if not permiso:
                    resultado["bloqueos"].append("Sin USAGE/SELECT: " + tabla.fullname)
                    resultado["conteos"][tabla.fullname] = None
                    continue
                # Consultar con los modelos reales comprueba todas las columnas mapeadas.
                filas = (await conexion.execute(select(tabla))).mappings().all()
                resultado["conteos"][tabla.fullname] = len(filas)
                if len(filas) != esperado:
                    raise RuntimeError("Conteo diferente de la línea base: " + tabla.fullname)
                if modelo is UnidadMilitar:
                    if sum(u["tipo_unidad_id"] is not None for u in filas) != 39:
                        raise RuntimeError("Clasificación diferente de la línea base")
                    if not any(u["codigo"] == "FUTOM" and u["tipo_unidad_id"] is None for u in filas):
                        raise RuntimeError("FUTOM no está pendiente")
                    resultado["huella_unidades"] = hashlib.sha256(
                        json.dumps([dict(u) for u in filas], sort_keys=True, default=str).encode()
                    ).hexdigest()
            await conexion.rollback()
        respaldo = BACKEND / "respaldos/esart_db_pre_alembic.dump"
        resultado["respaldo"] = {
            "disponible": respaldo.is_file(),
            "sha256": hashlib.sha256(respaldo.read_bytes()).hexdigest() if respaldo.is_file() else None,
        }
        resultado["estado"] = "bloqueado_por_permisos" if resultado["bloqueos"] else "lectura_validada"
        return resultado
    finally:
        await motor.dispose()


if __name__ == "__main__":
    try:
        informe = asyncio.run(verificar())
        (BACKEND.parent / "docs/ESART_VERIFICACION_PRINCIPAL.json").write_text(
            json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(informe, ensure_ascii=True, indent=2))
        raise SystemExit(1 if informe["bloqueos"] else 0)
    except Exception as error:
        # No imprimir excepciones del controlador que puedan incluir parámetros.
        print("Verificación detenida: " + type(error).__name__)
        raise SystemExit(1) from None
