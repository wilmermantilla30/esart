"""Parámetros de la regla de habilitación (revisión p0006_parametros_habilitacion)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

from aplicacion.base_datos.base import BaseModelo


class ParametroHabilitacion(BaseModelo):
    """Un parámetro de la regla APTO / NO APTO (por ejemplo, los cursos habilitantes)."""

    __table__ = sa.Table(
        "parametros_habilitacion",
        BaseModelo.metadata,
        sa.Column("codigo", sa.String(60), nullable=False),
        sa.Column("valor", postgresql.JSONB(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actualizado_por_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("codigo", name=conv("parametros_habilitacion_pkey")),
        sa.ForeignKeyConstraint(
            ["actualizado_por_id"],
            ["esart_ref.usuarios.id"],
            name=conv("fk_parametros_habilitacion_actualizado_por_id"),
            ondelete="SET NULL",
        ),
        schema="esart",
    )
