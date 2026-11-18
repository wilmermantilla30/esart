"""Valida Alembic sin conectarse a PostgreSQL ni modificar datos."""

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

from aplicacion.modelos.historico.base import BaseModelo


def test_alembic_carga_historial_y_entorno_sin_conexion():
    configuracion = Config(str(Path(__file__).resolve().parents[1] / "alembic_historico.ini"))
    assert ScriptDirectory.from_config(configuracion).get_heads() == ["0002"]
    salida = StringIO()
    configuracion.output_buffer = salida
    command.upgrade(configuracion, "head", sql=True)
    # Solo se genera SQL en memoria; ninguna conexión ni ejecución en PostgreSQL.
    sql = salida.getvalue()
    assert "CREATE TABLE artillero_cargos" in sql
    assert "CREATE TABLE usuario_permisos" in sql
    assert "CREATE FUNCTION public.actualizar_fecha_actualizacion" in sql
    assert "CREATE TRIGGER tr_auditoria_eventos_inmutable" in sql
    assert "CREATE TABLE instructores" not in sql
    assert "INSERT INTO usuarios" not in sql


def test_downgrade_offline_no_elimina_esquemas():
    configuracion = Config(str(Path(__file__).resolve().parents[1] / "alembic_historico.ini"))
    salida = StringIO()
    configuracion.output_buffer = salida
    command.downgrade(configuracion, "0001:base", sql=True)
    sql = salida.getvalue()
    assert "DROP TABLE artillero_cargos" in sql
    assert "DROP FUNCTION public.actualizar_fecha_actualizacion" in sql
    assert "DROP SCHEMA" not in sql
    assert "CASCADE" not in sql


def test_revisiones_congeladas_coinciden_con_modelos(monkeypatch):
    """Reconstruye 0001 + 0002, conservando la revisión histórica sin cambios."""
    ruta = Path(__file__).resolve().parents[1] / "migraciones/versions/0001_nucleo_inicial.py"
    especificacion = spec_from_file_location("revision_hu03", ruta)
    revision = module_from_spec(especificacion)
    especificacion.loader.exec_module(revision)
    metadatos = MetaData()

    def crear_tabla(nombre, *elementos, **opciones):
        return Table(nombre, metadatos, *elementos, **opciones)

    def crear_indice(nombre, tabla, columnas, **opciones):
        tabla = metadatos.tables[tabla]
        columnas = [tabla.c[c] if isinstance(c, str) else c for c in columnas]
        Index(nombre, *columnas, _table=tabla, **opciones)

    monkeypatch.setattr(revision.context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(revision.op, "create_table", crear_tabla)
    monkeypatch.setattr(revision.op, "create_index", crear_indice)
    monkeypatch.setattr(revision.op, "execute", lambda *_: None)
    monkeypatch.setattr(revision.op, "f", conv)
    revision.upgrade()
    assert "tipos_unidad" not in metadatos.tables
    assert "tipo_unidad_id" not in metadatos.tables["unidades_militares"].c
    ruta_0002 = ruta.with_name("0002_tipos_unidad.py")
    especificacion_0002 = spec_from_file_location("revision_hu04", ruta_0002)
    revision_0002 = module_from_spec(especificacion_0002)
    especificacion_0002.loader.exec_module(revision_0002)
    monkeypatch.setattr(
        revision_0002.op, "add_column", lambda tabla, columna: metadatos.tables[tabla].append_column(columna)
    )

    def crear_fk(nombre, origen, destino, locales, remotas, **opciones):
        metadatos.tables[origen].append_constraint(
            ForeignKeyConstraint(locales, [f"{destino}.{c}" for c in remotas], name=nombre, **opciones)
        )

    monkeypatch.setattr(revision_0002.op, "create_foreign_key", crear_fk)
    revision_0002.upgrade()
    dialecto = postgresql.dialect()

    def firma(tabla):
        return {
            "columnas": [
                (
                    c.name,
                    str(c.type.compile(dialect=dialecto)),
                    c.nullable,
                    str(c.server_default.arg)
                    if c.server_default is not None and c.identity is None
                    else None,
                    c.identity.always if c.identity else None,
                )
                for c in tabla.c
            ],
            "pk": tuple(tabla.primary_key.columns.keys()),
            "fk": {(f.parent.name, f.target_fullname, f.ondelete) for f in tabla.foreign_keys},
            "checks": {
                (str(c.name), str(c.sqltext)) for c in tabla.constraints if isinstance(c, CheckConstraint)
            },
            "indices": {(str(i.name), i.unique, tuple(str(e) for e in i.expressions)) for i in tabla.indexes},
            "unicos": {
                tuple(c.columns.keys())
                for c in tabla.constraints
                if c.__class__.__name__ == "UniqueConstraint"
            },
        }

    assert set(metadatos.tables) == set(BaseModelo.metadata.tables)
    for nombre, tabla in BaseModelo.metadata.tables.items():
        esperado, real = firma(tabla), firma(metadatos.tables[nombre])
        # El texto de un índice funcional no lleva prefijo de tabla en DDL.
        esperado["indices"] = {
            (n, u, tuple(e.replace(f"{nombre}.", "") for e in es)) for n, u, es in esperado["indices"]
        }
        real["indices"] = {
            (n, u, tuple(e.replace(f"{nombre}.", "") for e in es)) for n, u, es in real["indices"]
        }
        assert esperado == real, nombre
