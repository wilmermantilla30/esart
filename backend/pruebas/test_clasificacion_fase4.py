"""Pruebas de propuesta y protección; no ejecutan actualizaciones en ninguna base."""

from copy import deepcopy
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from seeds import fase4


@pytest.fixture
def documentos():
    return fase4.cargar_documentos()


def test_matriz_completa_y_pendiente_sin_inferir_tipo(documentos):
    snapshot, matriz = documentos
    cambios, resumen = fase4.planificar(snapshot, matriz, snapshot["unidades"], snapshot["tipos"])
    assert len(cambios) == 39
    assert resumen["pendientes"] == ["FUTOM"]
    assert {c["unidad_id"] for c in cambios} != {u["id"] for u in snapshot["unidades"]}
    assert next(f for f in matriz["filas"] if f["codigo"] == "CEMIL")["tipo_propuesto"] == "CEM"


def test_idempotencia_omite_las_39_correspondencias_sin_cambiar_pendiente(documentos):
    snapshot, matriz = documentos
    actuales = deepcopy(snapshot["unidades"])
    cambios, _ = fase4.planificar(snapshot, matriz, actuales, snapshot["tipos"])
    por_id = {u["id"]: u for u in actuales}
    for cambio in cambios:
        por_id[cambio["unidad_id"]]["tipo_unidad_id"] = cambio["tipo_id"]
    repeticion, resumen = fase4.planificar(snapshot, matriz, actuales, snapshot["tipos"])
    assert repeticion == []
    assert resumen["omitidas"] == 39
    assert resumen["pendientes"] == ["FUTOM"]


@pytest.mark.parametrize(
    "campo",
    [
        "id",
        "codigo",
        "nombre",
        "sigla",
        "unidad_superior_id",
        "activa",
        "fecha_creacion",
        "fecha_actualizacion",
    ],
)
def test_rechaza_cambios_en_otras_columnas(documentos, campo):
    snapshot, matriz = documentos
    actuales = deepcopy(snapshot["unidades"])
    actuales[0][campo] = "CAMBIO_NO_AUTORIZADO"
    with pytest.raises(ValueError):
        fase4.planificar(snapshot, matriz, actuales, snapshot["tipos"])


@pytest.mark.parametrize("alteracion", ["futom", "duplicada", "tipo", "inactivo", "clasificada", "superior"])
def test_rechaza_ambiguedades_y_conflictos(documentos, alteracion):
    snapshot, matriz = documentos
    matriz, actuales, tipos = deepcopy(matriz), deepcopy(snapshot["unidades"]), deepcopy(snapshot["tipos"])
    if alteracion == "futom":
        next(f for f in matriz["filas"] if f["codigo"] == "FUTOM")["tipo_propuesto"] = "DIV"
    elif alteracion == "duplicada":
        matriz["filas"][-1] = deepcopy(matriz["filas"][0])
    elif alteracion == "tipo":
        matriz["filas"][0]["tipo_propuesto"] = "INVENTADO"
    elif alteracion == "inactivo":
        tipos[0]["activo"] = False
    elif alteracion == "clasificada":
        actuales[0]["tipo_unidad_id"] = "TIPO_DISTINTO"
    else:
        matriz["filas"][0]["superior_codigo"] = "CEDOC"
    with pytest.raises(ValueError):
        fase4.planificar(snapshot, matriz, actuales, tipos)


def test_sentencia_set_exclusivamente_tipo_unidad():
    sql = str(fase4.SQL_ACTUALIZAR)
    assert sql.split(" SET ")[1].split(" WHERE ")[0] == "tipo_unidad_id=:tipo_id"
    assert "tipo_unidad_id IS NULL" in sql
    assert "RETURNING id" in sql


def test_verificacion_final_detecta_efectos_de_trigger(documentos):
    snapshot, matriz = documentos
    antes = snapshot["unidades"]
    cambios, _ = fase4.planificar(snapshot, matriz, antes, snapshot["tipos"])
    despues = deepcopy(antes)
    por_id = {u["id"]: u for u in despues}
    for cambio in cambios:
        por_id[cambio["unidad_id"]]["tipo_unidad_id"] = cambio["tipo_id"]
    fase4.verificar_solo_tipo(antes, despues, cambios)
    despues[0]["fecha_actualizacion"] = "FECHA_CAMBIADA_POR_TRIGGER"
    with pytest.raises(ValueError, match="columna distinta"):
        fase4.verificar_solo_tipo(antes, despues, cambios)


@pytest.mark.anyio
async def test_trigger_conocido_bloquea_antes_de_cualquier_update(documentos):
    snapshot, matriz = documentos
    cambios, _ = fase4.planificar(snapshot, matriz, snapshot["unidades"], snapshot["tipos"])
    conexion = AsyncMock()
    with pytest.raises(ValueError, match="Trigger de fecha incompatible"):
        await fase4.actualizar_estricto(conexion, snapshot["unidades"], cambios, True)
    conexion.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_efecto_secundario_no_previsto_aborta_transaccion(documentos, monkeypatch):
    snapshot, _ = documentos
    antes = snapshot["unidades"]
    cambio = {"unidad_id": antes[0]["id"], "tipo_id": snapshot["tipos"][0]["id"]}
    despues = deepcopy(antes)
    despues[0]["tipo_unidad_id"] = cambio["tipo_id"]
    despues[0]["nombre"] = "EFECTO_SECUNDARIO"
    monkeypatch.setattr(fase4, "leer_unidades", AsyncMock(return_value=despues))
    conexion = AsyncMock()
    conexion.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=cambio["unidad_id"]))
    with pytest.raises(ValueError, match="columna distinta"):
        await fase4.actualizar_estricto(conexion, antes, [cambio], False)


def clasificar_en_memoria(snapshot, matriz, fecha):
    actuales = deepcopy(snapshot["unidades"])
    cambios, _ = fase4.planificar(snapshot, matriz, actuales, snapshot["tipos"], True)
    por_id = {u["id"]: u for u in actuales}
    for cambio in cambios:
        por_id[cambio["unidad_id"]]["tipo_unidad_id"] = cambio["tipo_id"]
        por_id[cambio["unidad_id"]]["fecha_actualizacion"] = fecha
    return actuales, cambios


def test_excepcion_fecha_solo_admite_fecha_exacta_de_transaccion(documentos):
    snapshot, matriz = documentos
    fecha = "2099-01-01 00:00:00+00:00"
    despues, cambios = clasificar_en_memoria(snapshot, matriz, fecha)
    fase4.verificar_solo_tipo(snapshot["unidades"], despues, cambios, fecha)
    despues[0]["fecha_actualizacion"] = "2099-01-02 00:00:00+00:00"
    with pytest.raises(ValueError):
        fase4.verificar_solo_tipo(snapshot["unidades"], despues, cambios, fecha)


def test_excepcion_no_autoriza_fecha_de_futom_ni_campos_originales(documentos):
    snapshot, matriz = documentos
    despues, _ = clasificar_en_memoria(snapshot, matriz, "2099-01-01 00:00:00+00:00")
    pendientes = next(f for f in despues if f["codigo"] == "FUTOM")
    pendientes["fecha_actualizacion"] = "2099-01-01 00:00:00+00:00"
    with pytest.raises(ValueError):
        fase4.planificar(snapshot, matriz, despues, snapshot["tipos"], True)


def test_repeticion_con_fechas_del_trigger_no_programa_ningun_update(documentos):
    snapshot, matriz = documentos
    despues, _ = clasificar_en_memoria(snapshot, matriz, "2099-01-01 00:00:00+00:00")
    cambios, resumen = fase4.planificar(snapshot, matriz, despues, snapshot["tipos"], True)
    assert cambios == [] and resumen["omitidas"] == 39 and resumen["pendientes"] == ["FUTOM"]
    fase4.verificar_solo_tipo(despues, deepcopy(despues), cambios)


@pytest.mark.anyio
async def test_actualizador_autorizado_usa_now_sin_escribir_fechas(documentos, monkeypatch):
    snapshot, matriz = documentos
    fecha = "2099-01-01 00:00:00+00:00"
    despues, cambios = clasificar_en_memoria(snapshot, matriz, fecha)
    conexion = AsyncMock()
    conexion.scalar.return_value = datetime.fromisoformat(fecha)
    conexion.execute.side_effect = [
        Mock(scalar_one_or_none=Mock(return_value=c["unidad_id"])) for c in cambios
    ]
    monkeypatch.setattr(fase4, "leer_unidades", AsyncMock(return_value=despues))
    await fase4.actualizar_estricto(conexion, snapshot["unidades"], cambios, True, True)
    assert conexion.execute.await_count == 39
    assert all("fecha_actualizacion" not in str(c.args[0]) for c in conexion.execute.call_args_list)


@pytest.mark.anyio
async def test_actualizador_repetido_no_toca_trigger_ni_fechas(documentos, monkeypatch):
    snapshot, matriz = documentos
    actuales, _ = clasificar_en_memoria(snapshot, matriz, "2099-01-01 00:00:00+00:00")
    conexion = AsyncMock()
    monkeypatch.setattr(fase4, "leer_unidades", AsyncMock(return_value=deepcopy(actuales)))
    await fase4.actualizar_estricto(conexion, actuales, [], True, True)
    conexion.execute.assert_not_awaited()
    conexion.scalar.assert_not_awaited()
