"""
Tablas de sesión e intentos de inicio de sesión (revisión p0002_seguridad_sesiones).

Siguen el mismo estilo que persistencia.py (sa.Table con nombres de restricción exactos),
para que los modelos y la base real coincidan uno a uno.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import relationship
from sqlalchemy.sql.elements import conv

from aplicacion.base_datos.base import BaseModelo

from .persistencia import Usuario


class SesionUsuario(BaseModelo):
    """Una fila por sesión abierta. Su id es el 'jti' del JWT de la cookie."""

    __table__ = sa.Table(
        "sesiones_usuario",
        BaseModelo.metadata,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "fecha_inicio", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_ultima_actividad",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("agente_usuario", sa.String(300), nullable=True),
        sa.Column("revocada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fecha_revocacion", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=conv("sesiones_usuario_pkey")),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["esart_ref.usuarios.id"],
            name=conv("fk_sesiones_usuario_usuario_id"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(revocada AND fecha_revocacion IS NOT NULL) OR (NOT revocada AND fecha_revocacion IS NULL)",
            name=conv("ck_sesiones_usuario_revocacion"),
        ),
        sa.Index("ix_sesiones_usuario_usuario_id", "usuario_id"),
        schema="esart",
    )


class IntentoInicioSesion(BaseModelo):
    """Registro de cada intento de inicio de sesión. Nunca guarda la contraseña intentada."""

    __table__ = sa.Table(
        "intentos_inicio_sesion",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("nombre_usuario_intentado", sa.String(80), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("exitoso", sa.Boolean(), nullable=False),
        sa.Column("motivo_fallo", sa.String(40), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("intentos_inicio_sesion_pkey")),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["esart_ref.usuarios.id"],
            name=conv("fk_intentos_inicio_sesion_usuario_id"),
            ondelete="SET NULL",
        ),
        sa.Index("ix_intentos_inicio_sesion_usuario_id_fecha", "usuario_id", "fecha"),
        sa.Index("ix_intentos_inicio_sesion_direccion_ip_fecha", "direccion_ip", "fecha"),
        schema="esart",
    )


# lazy="raise": obliga a cargar el usuario de forma explícita (selectinload) en código async.
SesionUsuario.usuario = relationship(Usuario, foreign_keys=[SesionUsuario.usuario_id], lazy="raise")
