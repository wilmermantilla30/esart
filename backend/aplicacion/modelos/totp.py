"""Mapeo de las tablas existentes de seguridad; no ejecuta DDL ni reflexión en producción."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase


class BaseSeguridad(DeclarativeBase):
    pass


class UsuarioTotp(BaseSeguridad):
    __tablename__ = "usuario_totp"
    __table_args__ = {"schema": "seguridad"}
    id = sa.Column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    usuario_id = sa.Column(sa.BigInteger, nullable=False, unique=True)
    secreto_cifrado = sa.Column(sa.Text, nullable=False)
    estado = sa.Column(sa.String(15), nullable=False, default="PENDIENTE")
    creado_en = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    activado_en = sa.Column(sa.DateTime(timezone=True))
    expira_configuracion_en = sa.Column(sa.DateTime(timezone=True))
    revocado_en = sa.Column(sa.DateTime(timezone=True))
    ultimo_intervalo_aceptado = sa.Column(sa.BigInteger)
    actualizado_en = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())


class PoliticaAccion(BaseSeguridad):
    __tablename__ = "politicas_accion"
    __table_args__ = {"schema": "seguridad"}
    id = sa.Column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    codigo = sa.Column(sa.String(100), unique=True, nullable=False)
    nombre = sa.Column(sa.String(160), nullable=False)
    descripcion = sa.Column(sa.Text)
    modulo = sa.Column(sa.String(80), nullable=False)
    permiso_requerido = sa.Column(sa.String(100))
    requiere_totp = sa.Column(sa.Boolean, nullable=False, default=True)
    activa = sa.Column(sa.Boolean, nullable=False, default=True)
    vigencia_segundos = sa.Column(sa.Integer, nullable=False, default=120)
    creado_en = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())


class DesafioTotp(BaseSeguridad):
    __tablename__ = "desafios"
    __table_args__ = {"schema": "seguridad"}
    id = sa.Column(sa.Uuid, primary_key=True)
    usuario_id = sa.Column(sa.BigInteger, nullable=False)
    politica_id = sa.Column(sa.BigInteger, sa.ForeignKey("seguridad.politicas_accion.id"), nullable=False)
    recurso_tipo = sa.Column(sa.String(100))
    recurso_id = sa.Column(sa.String(150))
    operacion_hash = sa.Column(sa.String(64), nullable=False)
    estado = sa.Column(sa.String(20), nullable=False, default="PENDIENTE")
    intentos = sa.Column(sa.Integer, nullable=False, default=0)
    creado_en = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    expira_en = sa.Column(sa.DateTime(timezone=True), nullable=False)
    verificado_en = sa.Column(sa.DateTime(timezone=True))
    consumido_en = sa.Column(sa.DateTime(timezone=True))
    ip_origen = sa.Column(INET)
    correlacion_id = sa.Column(sa.Uuid)


class AutorizacionTotp(BaseSeguridad):
    __tablename__ = "autorizaciones"
    __table_args__ = {"schema": "seguridad"}
    id = sa.Column(sa.Uuid, primary_key=True)
    desafio_id = sa.Column(sa.Uuid, sa.ForeignKey("seguridad.desafios.id"), nullable=False, unique=True)
    usuario_id = sa.Column(sa.BigInteger, nullable=False)
    politica_id = sa.Column(sa.BigInteger, sa.ForeignKey("seguridad.politicas_accion.id"), nullable=False)
    operacion_hash = sa.Column(sa.String(64), nullable=False)
    autorizada_en = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    expira_en = sa.Column(sa.DateTime(timezone=True), nullable=False)
    consumida_en = sa.Column(sa.DateTime(timezone=True))
    resultado = sa.Column(sa.String(20), nullable=False, default="AUTORIZADA")


class AuditoriaSeguridad(BaseSeguridad):
    __tablename__ = "auditoria"
    __table_args__ = {"schema": "seguridad"}
    id = sa.Column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    evento_id = sa.Column(sa.Uuid, nullable=False, unique=True)
    correlacion_id = sa.Column(sa.Uuid)
    usuario_id = sa.Column(sa.BigInteger)
    actor_tipo = sa.Column(sa.String(30), nullable=False, default="USUARIO")
    modulo = sa.Column(sa.String(80), nullable=False)
    accion = sa.Column(sa.String(100), nullable=False)
    recurso_tipo = sa.Column(sa.String(100))
    recurso_id = sa.Column(sa.String(150))
    autorizacion_id = sa.Column(sa.Uuid, sa.ForeignKey("seguridad.autorizaciones.id"))
    resultado = sa.Column(sa.String(30), nullable=False)
    motivo = sa.Column(sa.Text)
    ip_origen = sa.Column(INET)
    agente_usuario = sa.Column(sa.Text)
    fecha_evento = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    datos = sa.Column("metadata", JSONB, nullable=False, default=dict)


class CambioSeguridad(BaseSeguridad):
    __tablename__ = "auditoria_cambios"
    __table_args__ = {"schema": "seguridad"}
    id = sa.Column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    auditoria_id = sa.Column(sa.BigInteger, sa.ForeignKey("seguridad.auditoria.id"), nullable=False)
    campo = sa.Column(sa.String(120), nullable=False)
    valor_anterior = sa.Column(JSONB)
    valor_nuevo = sa.Column(JSONB)
    creado_en = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())


class RecuperacionTotp(BaseSeguridad):
    __tablename__ = "totp_recuperacion"
    __table_args__ = {"schema": "seguridad"}
    id = sa.Column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    usuario_id = sa.Column(sa.BigInteger, nullable=False)
    codigo_hash = sa.Column(sa.Text, nullable=False)
    creado_en = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    usado_en = sa.Column(sa.DateTime(timezone=True))
    revocado_en = sa.Column(sa.DateTime(timezone=True))
