"""Propuesta HU-04 fase 4. Por defecto solo consulta; no ejecutar --aplicar sin aprobación."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import text

from seeds.ejecutar import DESTINO, RAIZ
from seeds.fase3 import comprobar_revision, motor_pruebas
from seeds.test_integracion_fase3 import huellas

GRUPOS_REVISADOS = {
    "DIV": ("DIV01", "DIV02", "DIV03", "DIV04", "DIV05", "DIV06", "DIV07", "DIV08", "DIVFE", "DAAVA"),
    "BR": ("BR01", "BR03", "BR04", "BR05", "BR08", "BR09", "BR10", "BR13", "BR18", "BR27", "BR30"),
    "BAACA": (
        "BAACA1",
        "BAACA2",
        "BAACA3",
        "BAACA4",
        "BAACA5",
        "BAACA6",
        "BAACA8",
        "BAACA9",
        "BAACA10",
        "BAACA13",
        "BAACA18",
        "BAACA27",
        "BAACA30",
    ),
    "BAADA": ("BAADA1", "BAADA2"),
    "CEDOC": ("CEDOC",),
    "CEM": ("CEMIL",),
    "ESART": ("ESART",),
}
CORRESPONDENCIAS = {codigo: tipo for tipo, codigos in GRUPOS_REVISADOS.items() for codigo in codigos}
SQL_ACTUALIZAR = text(
    "UPDATE public.unidades_militares SET tipo_unidad_id=:tipo_id "
    "WHERE id=:unidad_id AND tipo_unidad_id IS NULL RETURNING id"
)


def exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)


def serializar(filas):
    """Mismo formato que el snapshot, incluyendo UUID y fechas originales."""
    return json.loads(json.dumps([dict(fila) for fila in filas], default=str))


def cargar_documentos():
    ruta = RAIZ / "fase4_inspeccion.json"
    matriz = json.loads((RAIZ / "fase4_matriz.json").read_text(encoding="utf-8"))
    exigir(sha256(ruta.read_bytes()).hexdigest() == matriz["snapshot_sha256"], "Snapshot alterado")
    snapshot = json.loads(ruta.read_text(encoding="utf-8"))
    for nombre, huella in snapshot["migraciones_sha256"].items():
        exigir(
            sha256((RAIZ.parent / "migraciones/versions" / nombre).read_bytes()).hexdigest() == huella,
            "Migracion alterada",
        )
    return snapshot, matriz


def planificar(snapshot, matriz, actuales, tipos, permitir_fecha=False):
    """Valida toda la propuesta antes de permitir cambios; nunca infiere tipos nuevos."""
    exigir(matriz["destino"] == snapshot["destino"] == DESTINO, "Base de propuesta no autorizada")
    exigir(matriz["revision"] == snapshot["revision"] == "0002", "Revision incompatible")
    exigir(
        len(actuales) == len(snapshot["unidades"]) == len(matriz["filas"]) == 40,
        "Inventario de unidades inesperado",
    )
    exigir(len(tipos) == 9 and tipos == snapshot["tipos"], "Catalogo modificado")
    originales = {fila["id"]: fila for fila in snapshot["unidades"]}
    presentes = {fila["id"]: fila for fila in actuales}
    catalogo = {fila["codigo"]: fila for fila in tipos}
    exigir(
        len(originales) == len(presentes) == 40 and set(originales) == set(presentes),
        "Identificadores distintos",
    )
    for original in originales.values():
        camino = set()
        actual_id = original["id"]
        while actual_id is not None:
            exigir(actual_id in originales and actual_id not in camino, "Jerarquia con ciclo o huerfano")
            camino.add(actual_id)
            actual_id = originales[actual_id]["unidad_superior_id"]
    vistos, cambios, omitidas, pendientes = set(), [], [], []
    for fila in matriz["filas"]:
        unidad_id, codigo, tipo = fila["unidad_id"], fila["codigo"], fila["tipo_propuesto"]
        exigir(unidad_id not in vistos and unidad_id in originales, "Fila duplicada o desconocida")
        vistos.add(unidad_id)
        original, actual = originales[unidad_id], presentes[unidad_id]
        exigir(fila["nombre"] == original["nombre"] and codigo == original["codigo"], "Unidad distinta")
        padre = originales.get(original["unidad_superior_id"])
        exigir(fila["superior_codigo"] == (padre["codigo"] if padre else None), "Superior incompatible")
        ignoradas = {"tipo_unidad_id"}
        # Solo una clasificación ya correcta puede tener la fecha automática de una carga anterior.
        if permitir_fecha and tipo in catalogo and actual["tipo_unidad_id"] == catalogo[tipo]["id"]:
            exigir(
                datetime.fromisoformat(actual["fecha_actualizacion"])
                >= datetime.fromisoformat(original["fecha_actualizacion"]),
                "Fecha de clasificacion regresiva",
            )
            ignoradas.add("fecha_actualizacion")
        exigir(
            {k: v for k, v in original.items() if k not in ignoradas}
            == {k: v for k, v in actual.items() if k not in ignoradas},
            "Datos originales modificados",
        )
        exigir(tipo == CORRESPONDENCIAS.get(codigo), "Clasificacion fuera de la propuesta revisada")
        if tipo is None:
            exigir(
                codigo == "FUTOM" and actual["tipo_unidad_id"] is None and fila["estado"] == "pendiente",
                "Unidad pendiente clasificada",
            )
            pendientes.append(codigo)
            continue
        exigir(
            fila["estado"] == "propuesta" and tipo in catalogo and catalogo[tipo]["activo"],
            "Tipo ausente, inactivo o no propuesto",
        )
        destino = catalogo[tipo]["id"]
        exigir(actual["tipo_unidad_id"] in (None, destino), "Clasificacion previa incompatible")
        if actual["tipo_unidad_id"] == destino:
            omitidas.append(codigo)
        else:
            cambios.append({"unidad_id": unidad_id, "tipo_id": destino})
    return cambios, {
        "propuestas": 39,
        "por_actualizar": len(cambios),
        "omitidas": len(omitidas),
        "pendientes": pendientes,
    }


def verificar_solo_tipo(antes, despues, cambios, fecha_trigger=None):
    """Solo admite la fecha exacta de la transacción en filas realmente actualizadas."""
    esperadas = {fila["id"]: dict(fila) for fila in antes}
    for cambio in cambios:
        esperadas[cambio["unidad_id"]]["tipo_unidad_id"] = cambio["tipo_id"]
        if fecha_trigger is not None:
            esperadas[cambio["unidad_id"]]["fecha_actualizacion"] = fecha_trigger
    exigir(
        len(despues) == len(antes) and {fila["id"]: fila for fila in despues} == esperadas,
        "Cambio en columna distinta de tipo_unidad_id o filas inesperadas",
    )


async def leer_unidades(conexion):
    return serializar(
        (await conexion.execute(text("SELECT * FROM public.unidades_militares ORDER BY codigo")))
        .mappings()
        .all()
    )


async def actualizar_estricto(conexion, antes, cambios, trigger_fecha_activo, permitir_fecha=False):
    exigir(
        not cambios or not trigger_fecha_activo or permitir_fecha,
        "Trigger de fecha incompatible con conservar todas las demas columnas",
    )
    fecha_trigger = None
    if permitir_fecha and cambios:
        exigir(trigger_fecha_activo, "Se requiere el trigger existente activo")
        fecha_trigger = str(await conexion.scalar(text("SELECT now()")))
    for cambio in cambios:
        resultado = await conexion.execute(SQL_ACTUALIZAR, cambio)
        exigir(
            str(resultado.scalar_one_or_none()) == cambio["unidad_id"],
            "Actualizacion concurrente o incompleta",
        )
    verificar_solo_tipo(antes, await leer_unidades(conexion), cambios, fecha_trigger)


def huella_filas(filas):
    return sha256(json.dumps(filas, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


async def ejecutar(args, informe):
    snapshot, matriz = cargar_documentos()
    permitir_fecha = args.permitir_fecha_trigger
    escritura = args.aplicar or args.simular
    informe["matriz_sha256"] = sha256((RAIZ / "fase4_matriz.json").read_bytes()).hexdigest()
    informe["snapshot_sha256"] = matriz["snapshot_sha256"]
    informe["modo"] = "simular" if args.simular else "aplicar" if args.aplicar else "inspeccionar"
    informe["permiso_fecha_trigger"] = permitir_fecha
    motor = motor_pruebas(args.archivo_env)  # Sin opción de elegir otra base.
    try:
        async with motor.begin() as conexion:
            if not escritura:
                await conexion.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await comprobar_revision(conexion, DESTINO)
            if escritura:
                huellas_antes = await huellas(conexion)
                await conexion.execute(
                    text("LOCK TABLE public.unidades_militares IN SHARE ROW EXCLUSIVE MODE")
                )
                await conexion.execute(text("LOCK TABLE public.tipos_unidad IN SHARE MODE"))
            antes = await leer_unidades(conexion)
            tipos = serializar(
                (await conexion.execute(text("SELECT * FROM public.tipos_unidad ORDER BY codigo")))
                .mappings()
                .all()
            )
            cambios, informe["resumen"] = planificar(snapshot, matriz, antes, tipos, permitir_fecha)
            informe["huella_unidades_antes"] = huella_filas(antes)
            informe["huella_tipos"] = huella_filas(tipos)
            trigger = bool(
                await conexion.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_trigger "
                        "WHERE tgrelid='public.unidades_militares'::regclass "
                        "AND tgname='tr_unidades_militares_fecha' AND tgenabled::text <> 'D')"
                    )
                )
            )
            informe["bloqueo_fecha"] = trigger and bool(cambios) and not permitir_fecha
            if escritura:
                # El permiso nuevo no autoriza cambiar, reemplazar ni desactivar triggers.
                triggers = serializar(
                    (
                        await conexion.execute(
                            text(
                                "SELECT tgname,pg_get_triggerdef(oid) AS definicion FROM pg_trigger "
                                "WHERE tgrelid='public.unidades_militares'::regclass AND NOT tgisinternal"
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                funcion = await conexion.scalar(
                    text("SELECT pg_get_functiondef('public.actualizar_fecha_actualizacion()'::regprocedure)")
                )
                exigir(
                    triggers == snapshot["triggers"] and funcion == snapshot["funcion_actualizacion"],
                    "Trigger o funcion cambiaron desde la propuesta",
                )
                exigir(trigger, "Trigger existente deshabilitado")
                if args.aplicar and cambios:
                    simulacion = json.loads(args.simulacion_previa.read_text(encoding="utf-8"))
                    exigir(
                        simulacion["estado"] == "simulado_con_rollback"
                        and all(
                            simulacion[c] == informe[c]
                            for c in (
                                "destino",
                                "matriz_sha256",
                                "snapshot_sha256",
                                "huella_unidades_antes",
                                "huella_tipos",
                                "permiso_fecha_trigger",
                            )
                        ),
                        "Simulacion ausente o desactualizada",
                    )
                savepoint = await conexion.begin_nested() if args.simular else None
                await actualizar_estricto(conexion, antes, cambios, trigger, permitir_fecha)
                despues = await leer_unidades(conexion)
                huellas_despues = await huellas(conexion)
                exigir(
                    all(
                        huellas_despues[tabla] == huella
                        for tabla, huella in huellas_antes.items()
                        if tabla != "unidades_militares"
                    ),
                    "Cambio inesperado en otra tabla",
                )
                informe["tablas_ajenas_sin_cambios"] = True
                restantes, resumen = planificar(snapshot, matriz, despues, tipos, permitir_fecha)
                exigir(
                    not restantes and resumen["omitidas"] == 39 and resumen["pendientes"] == ["FUTOM"],
                    "Resultado distinto a 39 clasificadas y FUTOM pendiente",
                )
                informe["huella_unidades_resultado"] = huella_filas(despues)
                informe["fechas_modificadas"] = sum(
                    a["fecha_actualizacion"] != d["fecha_actualizacion"]
                    for a, d in zip(antes, despues, strict=True)
                )
                if savepoint:
                    await savepoint.rollback()
                    exigir(await leer_unidades(conexion) == antes, "Simulacion no revertida")
                    informe["rollback_verificado"] = True
        informe["actualizadas"] = len(cambios) if args.aplicar else 0
        informe["simuladas"] = len(cambios) if args.simular else 0
        informe["estado"] = (
            "simulado_con_rollback"
            if args.simular
            else "aplicado"
            if args.aplicar
            else "propuesta_sin_actualizaciones"
        )
    finally:
        await motor.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo-env", default=".env")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--aplicar", action="store_true")
    modo.add_argument("--simular", action="store_true")
    parser.add_argument("--permitir-fecha-trigger", action="store_true")
    parser.add_argument("--simulacion-previa", type=Path, default=RAIZ / "fase4_simulacion.json")
    parser.add_argument("--informe", type=Path, default=RAIZ / "fase4_revision.json")
    args = parser.parse_args()
    informe = {"destino": DESTINO, "fecha_utc": datetime.now(UTC).isoformat(), "errores": []}
    try:
        asyncio.run(ejecutar(args, informe))
    except Exception as error:
        informe["estado"] = "error_sin_confirmar_cambios"
        informe["errores"].append({"tipo": type(error).__name__})
    args.informe.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=True, indent=2))
    return 1 if informe["errores"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
