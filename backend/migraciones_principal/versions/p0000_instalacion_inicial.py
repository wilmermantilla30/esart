"""Instalación desde cero de la estructura base de esart_db (43 tablas de HU-04).

- Base VACÍA (sin tablas en esart/esart_ref): ejecuta estructura_p0000.sql, el DDL congelado
  y comprobado sin diferencias contra estructura_p0001.json.
- Base EXISTENTE (instalación de HU-04): no hace nada; p0001_real valida después que su
  estructura coincida con la fotografía.

Las bases que ya están en p0001_real no ejecutan esta revisión: Alembic la considera aplicada
porque es anterior a p0001_real en la cadena.
"""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "p0000_instalacion_inicial"
down_revision = None
branch_labels = None
depends_on = None

RUTA_ESTRUCTURA = Path(__file__).parents[1] / "estructura_p0000.sql"

# Cuenta tablas reales de ESART, sin contar la tabla de versiones de Alembic.
CONSULTA_TABLAS_EXISTENTES = text("""
    SELECT count(*) FROM pg_class t JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname IN ('esart', 'esart_ref') AND t.relkind IN ('r', 'p')
      AND NOT (n.nspname = 'esart' AND t.relname = 'alembic_version')
""")


def upgrade():
    conexion = op.get_bind()
    if conexion.scalar(CONSULTA_TABLAS_EXISTENTES):
        # Instalación existente: no se crea nada; p0001_real comprueba la estructura.
        return
    # asyncpg ejecuta una sentencia por llamada, así que el archivo se recorre sentencia por
    # sentencia. Todas van en la transacción de Alembic: si una falla, no queda nada a medias.
    for sentencia in sentencias_del_archivo(RUTA_ESTRUCTURA.read_text(encoding="ascii")):
        conexion.exec_driver_sql(sentencia)


def sentencias_del_archivo(contenido: str) -> list[str]:
    """
    Separa el DDL en sentencias. Cada una termina en ';' al final de línea; el DDL
    generado no tiene ';' dentro de cadenas ni comentarios con ';'.
    """
    sin_comentarios = "\n".join(
        linea for linea in contenido.splitlines() if not linea.lstrip().startswith("--")
    )
    partes = (parte.strip().rstrip(";").strip() for parte in sin_comentarios.split(";\n"))
    return [parte for parte in partes if parte]


def downgrade():
    raise RuntimeError("Reversión no permitida: borraría toda la estructura y sus datos.")
