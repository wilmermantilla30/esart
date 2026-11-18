"""Protecciones del paquete SQL: generación offline; ninguna ejecución en PostgreSQL."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from aplicacion.modelos.historico.base import BaseModelo
from herramientas import generar_sql_dbcode as generador

ORIGEN = Path(__file__).resolve().parents[1] / "sql/dbcode"


@pytest.fixture(scope="module")
def datos():
    return json.loads((ORIGEN / "datos_hu03_hu04.json").read_text(encoding="utf-8"))


def test_referencias_completas_jerarquia_y_futom(datos):
    generador.validar_datos(datos)
    assert {k: len(v) for k, v in datos.items()} == {
        "roles": 2,
        "cargos": 5,
        "cursos": 14,
        "permisos": 36,
        "tipos": 9,
        "unidades": 40,
    }
    assert sum(u["tipo_codigo"] is not None for u in datos["unidades"]) == 39
    assert not re.search(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", json.dumps(datos))


@pytest.mark.parametrize("cambio", ["futom", "padre", "duplicado", "id"])
def test_rechaza_datos_ambiguos_o_ids_de_pruebas(datos, cambio):
    valor = deepcopy(datos)
    if cambio == "futom":
        next(u for u in valor["unidades"] if u["codigo"] == "FUTOM")["tipo_codigo"] = "DIV"
    elif cambio == "padre":
        valor["unidades"][0]["superior_codigo"] = "ESART"
    elif cambio == "duplicado":
        valor["permisos"][0]["codigo"] = valor["permisos"][1]["codigo"]
    else:
        valor["unidades"][0]["id"] = "uuid_de_pruebas"
    with pytest.raises(ValueError):
        generador.validar_datos(valor)


def test_ddl_adaptado_no_cambia_pk_y_no_duplica_unidades():
    estructura = json.loads((ORIGEN / "estructura_origen.json").read_text(encoding="utf-8"))
    mapa, nuevas, columnas, ddl = generador.construir(estructura)
    assert str(mapa["unidades_militares"].c.id.type.compile(dialect=postgresql.dialect())) == "bigint"
    assert mapa["unidades_militares"].schema == "esart_ref"
    assert "uuid_publico" in mapa["unidades_militares"].c
    assert not any(t.name == "unidades_militares" for t in nuevas)
    assert len(nuevas) == 9 and len(columnas) == 54
    assert not any("ALTER COLUMN id" in s for s in ddl)
    assert all(c[2] != "id" for c in columnas)
    assert "FOREIGN KEY(usuario_id) REFERENCES esart_ref.usuarios (id)" in "\n".join(ddl)
    # El generador no modifica el contrato UUID histórico en memoria.
    assert BaseModelo.metadata.tables["unidades_militares"].c.id.type.python_type.__name__ == "UUID"


def test_generacion_reproducible_sin_ejecutar_sql(tmp_path, monkeypatch):
    for nombre in ("estructura_origen.json", "datos_hu03_hu04.json"):
        (tmp_path / nombre).write_bytes((ORIGEN / nombre).read_bytes())
    (tmp_path / "plantillas").mkdir()
    for ruta in (ORIGEN / "plantillas").glob("*.sql"):
        (tmp_path / "plantillas" / ruta.name).write_bytes(ruta.read_bytes())
    monkeypatch.setattr(generador, "SALIDA", tmp_path)
    generador.main()
    archivos = ("01_integrar_esart_db.sql", "02_verificar_esart_db.sql", "manifiesto.json")
    antes = {n: (tmp_path / n).read_bytes() for n in archivos}
    generador.main()
    assert antes == {n: (tmp_path / n).read_bytes() for n in archivos}
    sql = antes[archivos[0]].decode("utf-8")
    assert "current_database()<>'esart_db'" in sql
    assert "SET LOCAL ROLE esart_aplicacion" in sql
    assert "INSERT INTO esart.integraciones_control" in sql
    assert "INSERT INTO public.alembic_version" not in sql
    assert not re.search(r"__[A-Z_]+__", sql)
    assert not re.search(r"(?im)^\s*(DROP|TRUNCATE|DELETE)\b", sql)
    assert "ON CONFLICT" not in sql  # No intentar INSERT para después omitir y consumir secuencias.
    verificacion = antes[archivos[1]].decode("utf-8")
    assert "READ ONLY" in verificacion
    assert not re.search(
        r"(?im)^\s*(INSERT|UPDATE|CREATE|ALTER|GRANT|REVOKE|DELETE|TRUNCATE)\b", verificacion
    )
