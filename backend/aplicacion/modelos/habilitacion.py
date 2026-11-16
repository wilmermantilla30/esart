"""Parámetros de la regla de habilitación (p0006) y auditoría de eventos (p0007)."""

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


class AuditoriaEvento(BaseModelo):
    """Registro inmutable de acciones (HU-11, revisión p0007_auditoria_eventos)."""

    __table__ = sa.Table(
        "auditoria_eventos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        sa.Column("nombre_usuario", sa.String(80), nullable=True),
        sa.Column("accion", sa.String(40), nullable=False),
        sa.Column("numero_documento_consultado", sa.String(15), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=True),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("agente_usuario", sa.String(300), nullable=True),
        sa.Column("detalle", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=conv("auditoria_eventos_pkey")),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["esart_ref.usuarios.id"], name=conv("fk_auditoria_eventos_usuario_id")
        ),
        sa.Index("ix_auditoria_eventos_fecha", "fecha"),
        sa.Index("ix_auditoria_eventos_usuario_id_fecha", "usuario_id", "fecha"),
        sa.Index("ix_auditoria_eventos_documento", "numero_documento_consultado"),
        schema="esart",
    )
