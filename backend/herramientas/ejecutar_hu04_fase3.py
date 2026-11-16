"""Ejecución autorizada de HU-04: temporal independiente antes del destino final."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from alembic import command
from sqlalchemy import text

from herramientas.migrar_fase3 import configurar
from seeds.ejecutar import DESTINO, RAIZ
from seeds.fase3 import TEMPORAL, motor_pruebas, poblar_tipos_unidad, referencias
from seeds.test_integracion_fase3 import huellas

HUELLA_0001 = "4ce5b478f34fa2cf5e584f4a6cb69e9ecc986f56f129b6067fed991ebcca07e0"


def exigir(condicion, mensaje):
    if not condicion:
        raise RuntimeError(mensaje)


async def identidad(conexion, destino, revision):
    """Precondición explícita dentro de la misma transacción que ejecuta cada DDL."""
    fila = (
        (
            await conexion.execute(
                text(
                    "SELECT current_database() AS base, current_user AS usuario, "
                    "pg_get_userbyid(datdba) AS propietario, "
                    "current_setting('server_version_num')::integer / 10000 AS version, "
                    "(SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AS superusuario "
                    "FROM pg_database WHERE datname=current_database()"
                )
            )
        )
        .mappings()
        .one()
    )
    exigir(
        fila["base"] == destino and not fila["superusuario"] and fila["version"] == 18,
        "Identidad no autorizada",
    )
    if destino == TEMPORAL:
        exigir(fila["propietario"] == "esart_aplicacion", "Propietario temporal incorrecto")
    existe = await conexion.scalar(text("SELECT to_regclass('public.alembic_version')"))
    actual = await conexion.scalar(text("SELECT version_num FROM public.alembic_version")) if existe else None
    exigir(actual == revision, "Revision inicial inesperada")
    return {**dict(fila), "revision": actual}


async def migrar(conexion, destino, inicial, final, informe):
    informe.setdefault("migraciones", []).append(await identidad(conexion, destino, inicial))
    exigir(final in ("0001", "0002"), "Revision no autorizada")
    config = configurar(RAIZ.parent / ".env")

    def ejecutar(sincrona):
        config.attributes["connection"] = sincrona
        command.upgrade(config, final)

    await conexion.run_sync(ejecutar)
    await identidad(conexion, destino, final)
    informe["migraciones"][-1]["revision_final"] = final


async def unidades(conexion, ampliada=False):
    filas = (
        (await conexion.execute(text("SELECT * FROM public.unidades_militares ORDER BY codigo")))
        .mappings()
        .all()
    )
    if ampliada:
        exigir(all(fila["tipo_unidad_id"] is None for fila in filas), "Unidad reclasificada")
    return [
        {k: str(v) if v is not None else None for k, v in fila.items() if k != "tipo_unidad_id"}
        for fila in filas
    ]


async def validar(conexion):
    tipos = (
        (await conexion.execute(text("SELECT codigo,nombre FROM public.tipos_unidad ORDER BY codigo")))
        .mappings()
        .all()
    )
    exigir(
        [dict(f) for f in tipos] == sorted(referencias()["tipos_unidad"], key=lambda f: f["codigo"]),
        "Catalogo final distinto a las nueve referencias",
    )
    exigir(
        await conexion.scalar(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE table_schema='public' "
                "AND table_name='unidades_militares' AND column_name='tipo_unidad_id'"
            )
        )
        == "YES",
        "La FK debe ser opcional",
    )
    exigir(
        await conexion.scalar(
            text(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public' "
                "AND tablename IN ('estados_operacionales','estados_logisticos')"
            )
        )
        == 0,
        "Tablas fuera de alcance",
    )
    # Consulta de huérfanos y ciclos, incluyendo toda la jerarquía existente.
    huerfanas = await conexion.scalar(
        text(
            "SELECT count(*) FROM public.unidades_militares u LEFT JOIN public.unidades_militares p "
            "ON p.id=u.unidad_superior_id WHERE u.unidad_superior_id IS NOT NULL AND p.id IS NULL"
        )
    )
    ciclos = await conexion.scalar(
        text(
            "WITH RECURSIVE j AS (SELECT id,unidad_superior_id,ARRAY[id] camino,false ciclo "
            "FROM public.unidades_militares UNION ALL SELECT p.id,p.unidad_superior_id,j.camino||p.id, "
            "p.id=ANY(j.camino) FROM j JOIN public.unidades_militares p ON p.id=j.unidad_superior_id "
            "WHERE NOT j.ciclo) SELECT count(*) FROM j WHERE ciclo"
        )
    )
    exigir(huerfanas == ciclos == 0, "Jerarquia inconsistente")
    return {
        "tipos": len(tipos),
        "unidades": len(await unidades(conexion, True)),
        "huerfanas": huerfanas,
        "ciclos": ciclos,
        "fk_opcional": True,
    }


async def ejecutar(fase, informe):
    revision = RAIZ.parent / "migraciones/versions/0001_nucleo_inicial.py"
    exigir(
        sha256(revision.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == HUELLA_0001, "HU-03 modificada"
    )
    destino = DESTINO if fase == "aplicar" else TEMPORAL
    informe["destino"] = destino
    motor = motor_pruebas(RAIZ.parent / ".env", destino)
    try:
        async with motor.begin() as conexion:
            if fase == "preparar_temporal":
                await identidad(conexion, TEMPORAL, None)
                exigir(
                    await conexion.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'"))
                    == 0,
                    "Temporal no vacia",
                )
                await migrar(conexion, TEMPORAL, None, "0001", informe)
                datos = json.loads((RAIZ / "catalogos.json").read_text(encoding="utf-8"))
                for tabla, campo in (("roles", "nombre"), ("permisos", "descripcion")):
                    for fila in datos[tabla]:
                        await conexion.execute(
                            text(
                                f"INSERT INTO public.{tabla}(codigo,{campo}) VALUES (:codigo,:{campo})"  # noqa: S608
                            ),
                            fila,
                        )
                padres = {}
                for fila in datos["unidades_militares"]:
                    padres[fila["codigo"]] = await conexion.scalar(
                        text(
                            "INSERT INTO public.unidades_militares(codigo,nombre,unidad_superior_id) "
                            "VALUES (:codigo,:nombre,:padre) RETURNING id"
                        ),
                        {**fila, "padre": padres[fila["padre"]] if fila["padre"] else None},
                    )
                informe["datos_prueba"] = {"roles": 2, "permisos": 36, "unidades": len(padres)}
            else:
                if fase == "aplicar":
                    evidencia = json.loads(
                        (RAIZ / "fase3_temporal_validada.json").read_text(encoding="utf-8")
                    )
                    exigir(
                        evidencia["estado"] == "confirmado" and evidencia["integracion_aprobada"],
                        "Falta evidencia de pruebas temporales",
                    )
                await identidad(conexion, destino, "0001")
                antes = await unidades(conexion)
                exigir(len(antes) == 40, "Se requieren 40 unidades")
                huellas_antes = await huellas(conexion)
                if fase == "aplicar":
                    # Comparación adicional con la evidencia previa de las 40 unidades.
                    previo = json.loads((RAIZ / "fase3_preflight_aprobado.json").read_text(encoding="utf-8"))
                    esperado = [
                        {k: str(v) if v is not None else None for k, v in f.items()}
                        for f in previo["unidades"]
                    ]
                    exigir(antes == esperado, "Las unidades difieren de la evidencia previa")
                await migrar(conexion, destino, "0001", "0002", informe)
                informe["cargas"] = []
                for numero in (1, 2):
                    carga = await poblar_tipos_unidad(conexion, destino)
                    exigir(
                        (carga["insertados"], carga["omitidos"]) == ((9, 0) if numero == 1 else (0, 9)),
                        "Idempotencia inesperada",
                    )
                    informe["cargas"].append(carga)
                exigir(antes == await unidades(conexion, True), "Unidades modificadas")
                huellas_despues = await huellas(conexion)
                exigir(
                    all(
                        huellas_despues[t] == valor
                        for t, valor in huellas_antes.items()
                        if t not in ("unidades_militares", "alembic_version")
                    ),
                    "Tablas ajenas modificadas",
                )
                informe["validacion"] = await validar(conexion)
                informe["unidades_sin_cambios"] = True
                informe["tablas_ajenas_sin_cambios"] = True
            informe["revision_final"] = await conexion.scalar(
                text("SELECT version_num FROM public.alembic_version")
            )
        informe["estado"] = "confirmado"
    finally:
        await motor.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fase", choices=["preparar_temporal", "finalizar_temporal", "aplicar"], required=True
    )
    parser.add_argument("--informe", type=Path, required=True)
    args = parser.parse_args()
    informe = {"fecha_utc": datetime.now(UTC).isoformat(), "fase": args.fase, "errores": []}
    try:
        if args.fase == "finalizar_temporal":
            # Ejecutar la prueba automatizada antes de dejar la temporal en 0002.
            import io
            import unittest

            from seeds.test_integracion_fase3 import IntegracionFase3

            IntegracionFase3.__unittest_skip__ = False
            resultado = unittest.TextTestRunner(stream=io.StringIO()).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(IntegracionFase3)
            )
            exigir(
                resultado.wasSuccessful() and resultado.testsRun == 1, "Fallo en prueba estructural temporal"
            )
            informe["integracion_aprobada"] = True
        asyncio.run(ejecutar(args.fase, informe))
    except Exception as error:
        informe["estado"] = "error"
        informe["errores"].append({"tipo": type(error).__name__})
    args.informe.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=True, indent=2))
    return 0 if informe["estado"] == "confirmado" else 1


if __name__ == "__main__":
    raise SystemExit(main())
