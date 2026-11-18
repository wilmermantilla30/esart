"""Contrato y SQL de la propuesta 0002; sin conexiones ni ejecución de DDL."""

from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import configure_mappers

from aplicacion.modelos.historico import TipoUnidad, UnidadMilitar
from seeds.fase3 import TEMPORAL, comprobar_revision, motor_pruebas, referencias

RAIZ = Path(__file__).resolve().parents[1]


def test_hu03_aprobada_permanece_intacta():
    contenido = (RAIZ / "migraciones/versions/0001_nucleo_inicial.py").read_bytes()
    # Normalizar saltos de línea permite checkouts Git tanto CRLF como LF.
    contenido = contenido.replace(b"\r\n", b"\n")
    assert sha256(contenido).hexdigest() == "4ce5b478f34fa2cf5e584f4a6cb69e9ecc986f56f129b6067fed991ebcca07e0"


def sql_revision(destino):
    config = Config(str(RAIZ / "alembic_historico.ini"))
    config.output_buffer = StringIO()
    if destino == "upgrade":
        command.upgrade(config, "0001:0002", sql=True)
    else:
        command.downgrade(config, "0002:0001", sql=True)
    return config.output_buffer.getvalue()


def test_upgrade_aditivo_con_guardia_previa_al_ddl():
    sql = sql_revision("upgrade")
    assert sql.index("current_database()") < sql.index("CREATE TABLE tipos_unidad")
    assert "esart_hu03_pruebas" in sql
    assert "ADD COLUMN tipo_unidad_id UUID" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "CREATE TRIGGER tr_tipos_unidad_fecha" in sql
    assert "actualizar_fecha_actualizacion()" in sql
    assert "INSERT INTO" not in sql
    assert "UPDATE unidades_militares" not in sql
    assert "estados_operacionales" not in sql
    assert "estados_logisticos" not in sql


def test_downgrade_protege_informacion_antes_de_eliminar_estructuras():
    sql = sql_revision("downgrade")
    assert sql.index("current_database()") < sql.index("DROP")
    assert sql.index("ACCESS EXCLUSIVE") < sql.index("DROP")
    assert sql.index("Reversion rechazada") < sql.index("DROP")
    assert "tipo_unidad_id IS NOT NULL" in sql
    assert "DROP TABLE tipos_unidad" in sql
    assert "DROP TABLE unidades_militares" not in sql
    assert "DELETE FROM" not in sql
    assert "CASCADE" not in sql
    assert "DROP FUNCTION" not in sql
    assert "IF current_database() <> 'esart_hu04_fase3_temporal'" in sql
    assert sql.index("Reversion 0002 solo autorizada") < sql.index("ACCESS EXCLUSIVE")


@pytest.mark.parametrize("operacion", ["upgrade", "downgrade"])
def test_sql_entregado_coincide_con_revision_propuesta(operacion):
    ruta = RAIZ / f"seeds/sql/fase3_{operacion}_propuesto.sql"
    assert ruta.read_text(encoding="utf-8") == sql_revision(operacion)


def test_modelo_clasifica_sin_alterar_jerarquia():
    configure_mappers()
    tabla = TipoUnidad.__table__
    assert tabla.c.id.type.python_type.__name__ == "UUID"
    assert tabla.c.codigo.unique
    assert len([c for c in tabla.constraints if isinstance(c, CheckConstraint)]) == 2
    assert UnidadMilitar.__table__.c.tipo_unidad_id.nullable
    assert UnidadMilitar.tipo_unidad.property.mapper.class_ is TipoUnidad
    assert UnidadMilitar.unidad_superior.property.mapper.class_ is UnidadMilitar
    assert next(iter(UnidadMilitar.__table__.c.tipo_unidad_id.foreign_keys)).ondelete == "RESTRICT"


def test_nueve_referencias_y_sql_idempotente_sin_actualizaciones():
    datos = referencias()
    assert set(datos) == {"tipos_unidad"}
    assert len(datos["tipos_unidad"]) == 9
    assert {f["codigo"] for f in datos["tipos_unidad"]} == {
        "DIV",
        "BR",
        "BAACA",
        "BATAR",
        "CECFU",
        "CEDOC",
        "CEM",
        "BAADA",
        "ESART",
    }
    sentencia = (
        insert(TipoUnidad).values(datos["tipos_unidad"]).on_conflict_do_nothing(index_elements=["codigo"])
    )
    sql = str(sentencia.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (codigo) DO NOTHING" in sql
    assert "UPDATE" not in sql


def test_motor_sustituye_base_antes_de_conectar(monkeypatch):
    monkeypatch.setenv("URL_BASE_DATOS", "postgresql+asyncpg://cuenta:clave@localhost:5432/esart_db")
    motor = motor_pruebas(None)
    assert motor.url.database == "esart_hu03_pruebas"


def test_motor_temporal_y_rechazo_de_otras_bases(monkeypatch):
    monkeypatch.setenv("URL_BASE_DATOS", "postgresql+asyncpg://cuenta:clave@localhost:5432/esart_db")
    assert motor_pruebas(None, TEMPORAL).url.database == TEMPORAL
    for nombre in ("esart_db", "postgres", "otra_base"):
        with pytest.raises(ValueError, match="Base no autorizada"):
            motor_pruebas(None, nombre)


@pytest.mark.anyio
async def test_seed_rechaza_0001_antes_de_insertar():
    conexion = AsyncMock()
    identidad, revision = AsyncMock(), AsyncMock()
    identidad.one = lambda: ("esart_hu03_pruebas", False, 18)
    revision.scalar_one = lambda: "0001"
    conexion.execute.side_effect = [identidad, None, revision]
    with pytest.raises(RuntimeError, match="Se requiere 0002"):
        await comprobar_revision(conexion)
    assert all("INSERT" not in str(c.args[0]) for c in conexion.execute.call_args_list)
