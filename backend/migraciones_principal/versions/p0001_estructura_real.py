"""Verifica y adopta el esquema real; no representa las revisiones UUID 0001/0002.

No ejecutar sin autorización: Alembic crea/escribe esart.alembic_version.
La instalación vacía requiere una migración inicial adicional, aún no aprobada.
"""

import json
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "p0001_real"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    validar_estructura(op.get_bind())


def validar_estructura(conexion):
    """Solo lectura; utilizable antes de solicitar la adopción por Alembic."""
    if conexion.scalar(text("SELECT current_database()")) != "esart_db":
        raise RuntimeError("Destino incorrecto")
    esperado = json.loads((Path(__file__).parents[1] / "estructura_p0001.json").read_text(encoding="utf-8"))
    # No hacer stamp: esta revisión comprueba cada efecto que declara adoptar.
    for c in esperado["columnas"]:
        real = (
            conexion.execute(
                text("""
          SELECT format_type(a.atttypid,a.atttypmod) tipo, NOT a.attnotnull permite_null,
                 a.attidentity identidad,a.attgenerated generada,pg_get_expr(d.adbin,d.adrelid) defecto
          FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid
          JOIN pg_namespace n ON n.oid=t.relnamespace
          LEFT JOIN pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum
          WHERE n.nspname=:s AND t.relname=:t AND a.attname=:c AND NOT a.attisdropped
        """),
                {"s": c["esquema"], "t": c["tabla"], "c": c["columna"]},
            )
            .mappings()
            .one_or_none()
        )
        if real is None:
            raise RuntimeError(f"Columna ausente: {c['esquema']}.{c['tabla']}.{c['columna']}")
        for key in ("tipo", "permite_null", "defecto", "identidad", "generada"):
            actual = real[key]
            if isinstance(actual, bytes):
                actual = repr(actual)
            if actual != c[key]:
                raise RuntimeError(f"Columna incompatible: {c['tabla']}.{c['columna']} / {key}")
    actuales = set(
        conexion.execute(
            text("""
      SELECT n.nspname,t.relname FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
      WHERE n.nspname IN ('esart','esart_ref','public') AND t.relkind='r'
      AND NOT (n.nspname='esart' AND t.relname='alembic_version')
    """)
        ).tuples()
    )
    if actuales != {(t["esquema"], t["tabla"]) for t in esperado["tablas"]}:
        raise RuntimeError("El conjunto de tablas difiere de la línea base")
    claves = set(
        conexion.execute(
            text("""
      SELECT n.nspname,t.relname,a.attname FROM pg_attribute a
      JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace
      WHERE n.nspname IN ('esart','esart_ref','public') AND t.relkind='r'
      AND a.attnum>0 AND NOT a.attisdropped
      AND NOT (n.nspname='esart' AND t.relname='alembic_version')
    """)
        ).tuples()
    )
    if claves != {(c["esquema"], c["tabla"], c["columna"]) for c in esperado["columnas"]}:
        raise RuntimeError("Existen columnas no conciliadas con la línea base")
    for categoria, funcion in (
        ("restricciones", "pg_get_constraintdef"),
        ("indices", "pg_get_indexdef"),
        ("triggers", "pg_get_triggerdef"),
    ):
        for r in esperado[categoria]:
            if categoria == "restricciones":
                origen = "pg_constraint x JOIN pg_class t ON t.oid=x.conrelid"
                nombre = "x.conname"
            elif categoria == "triggers":
                origen = "pg_trigger x JOIN pg_class t ON t.oid=x.tgrelid"
                nombre = "x.tgname"
            else:
                origen = (
                    "pg_class x JOIN pg_index i ON i.indexrelid=x.oid JOIN pg_class t ON t.oid=i.indrelid"
                )
                nombre = "x.relname"
            # Los fragmentos proceden de esta revisión, nunca de una petición externa.
            sql = f"""SELECT {funcion}(x.oid) FROM {origen}
              JOIN pg_namespace n ON n.oid=t.relnamespace
              WHERE n.nspname=:s AND t.relname=:t AND {nombre}=:n"""  # noqa: S608
            actual = conexion.scalar(text(sql), {"s": r["esquema"], "t": r["tabla"], "n": r["nombre"]})
            if actual != r["definicion"]:
                raise RuntimeError(f"Objeto incompatible: {r['esquema']}.{r['nombre']}")
    invalidos = conexion.scalar(
        text("""
      SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
      WHERE n.nspname IN ('esart','esart_ref') AND NOT c.convalidated
    """)
    )
    invalidos += conexion.scalar(
        text("""
      SELECT count(*) FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
      JOIN pg_namespace n ON n.oid=t.relnamespace
      WHERE n.nspname IN ('esart','esart_ref') AND NOT i.indisvalid
    """)
    )
    if invalidos:
        raise RuntimeError("Hay restricciones o índices no válidos")
    for r in esperado["funciones"]:
        actual = conexion.scalar(
            text("""
          SELECT md5(pg_get_functiondef(p.oid)) FROM pg_proc p
          JOIN pg_namespace n ON n.oid=p.pronamespace
          WHERE n.nspname=:s AND p.proname=:n AND p.prokind='f'
        """),
            {"s": r["esquema"], "n": r["nombre"]},
        )
        if actual != r["huella"]:
            raise RuntimeError("Función incompatible")
    # No crea ni modifica entidades, filas, identificadores ni catálogos.


def downgrade():
    raise RuntimeError("Reversión no autorizada: conservar el esquema y su historial real")
