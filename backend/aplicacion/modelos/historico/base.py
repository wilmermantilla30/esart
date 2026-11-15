"""
Clase base de todos los modelos SQLAlchemy de ESART.

Todos los modelos de app/modelos heredan de BaseModelo. Así comparten los mismos
metadatos y Alembic puede detectar todas las tablas para generar migraciones.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Convención de nombres de índices y restricciones.
# Por qué: sin esto PostgreSQL inventa nombres distintos en cada máquina y
# Alembic no puede borrar ni modificar las restricciones de forma confiable.
# Los prefijos coinciden con los de docs/esquema_referencia.sql.
CONVENCION_NOMBRES_RESTRICCIONES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class BaseModelo(DeclarativeBase):
    """Clase base declarativa: todo modelo de tabla debe heredar de esta clase."""

    metadata = MetaData(naming_convention=CONVENCION_NOMBRES_RESTRICCIONES)
