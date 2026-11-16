"""Núcleo contractual HU-03 y malla CRUD aprobada; sin datos semilla."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModelo

if TYPE_CHECKING:
    from aplicacion.modelos.historico.catalogos_organizacion import TipoUnidad


class UnidadMilitar(BaseModelo):
    """Tabla `unidades_militares`."""

    __tablename__ = "unidades_militares"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    sigla: Mapped[str | None] = mapped_column(String(30), nullable=True)
    unidad_superior_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("unidades_militares.id"), index=True, nullable=True
    )
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    unidad_superior: Mapped["UnidadMilitar | None"] = relationship(
        foreign_keys=[unidad_superior_id], remote_side=lambda: [UnidadMilitar.id]
    )
    # Nullable: no se reclasifican las unidades aprobadas en la fase 2.
    tipo_unidad_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tipos_unidad.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    tipo_unidad: Mapped["TipoUnidad | None"] = relationship("TipoUnidad", foreign_keys=[tipo_unidad_id])


class PersonalMilitar(BaseModelo):
    """Tabla `personal_militar`."""

    __tablename__ = "personal_militar"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    numero_documento: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    primer_nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    segundo_nombre: Mapped[str | None] = mapped_column(String(60), nullable=True)
    primer_apellido: Mapped[str] = mapped_column(String(60), nullable=False)
    segundo_apellido: Mapped[str | None] = mapped_column(String(60), nullable=True)
    grado: Mapped[str] = mapped_column(String(40), nullable=False)
    categoria: Mapped[str] = mapped_column(String(20), nullable=False)
    arma: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unidad_militar_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("unidades_militares.id"), index=True, nullable=True
    )
    estado_servicio: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("numero_documento ~ '^[0-9]{6,10}$'", name="numero_documento"),
        CheckConstraint(
            "categoria IN ('OFICIAL','SUBOFICIAL','SOLDADO_PROFESIONAL','CIVIL')", name="categoria"
        ),
        CheckConstraint(
            "estado_servicio IN ('ACTIVO','RETIRADO','SUSPENDIDO','COMISION','LICENCIA')",
            name="estado_servicio",
        ),
        Index("ix_personal_militar_estado_servicio", "estado_servicio"),
    )
    unidad_militar: Mapped["UnidadMilitar | None"] = relationship(foreign_keys=[unidad_militar_id])


class HojaVidaArtillero(BaseModelo):
    """Tabla `hoja_vida_artillero`."""

    __tablename__ = "hoja_vida_artillero"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    personal_militar_id: Mapped[UUID] = mapped_column(
        ForeignKey("personal_militar.id"), index=True, unique=True, nullable=False
    )
    especialidad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fecha_ingreso_arma: Mapped[date | None] = mapped_column(Date, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    personal_militar: Mapped["PersonalMilitar"] = relationship(foreign_keys=[personal_militar_id])


class Rol(BaseModelo):
    """Tabla `roles`."""

    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    __table_args__ = (CheckConstraint("codigo IN ('ADMINISTRADOR', 'USUARIO')", name="codigo"),)


class Permiso(BaseModelo):
    """Tabla `permisos`."""

    __tablename__ = "permisos"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class RolPermisoCodigo(BaseModelo):
    """Tabla `roles_permisos`."""

    __tablename__ = "roles_permisos"

    rol_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), index=True, primary_key=True, nullable=False)
    permiso_id: Mapped[UUID] = mapped_column(
        ForeignKey("permisos.id"), index=True, primary_key=True, nullable=False
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    rol: Mapped["Rol"] = relationship(foreign_keys=[rol_id])
    permiso: Mapped["Permiso"] = relationship(foreign_keys=[permiso_id])


class Usuario(BaseModelo):
    """Tabla `usuarios`."""

    __tablename__ = "usuarios"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    nombre_usuario: Mapped[str] = mapped_column(String(60), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    hash_contrasena: Mapped[str] = mapped_column(String(100), nullable=False)
    rol_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), index=True, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    intentos_fallidos_consecutivos: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (Index("ux_usuarios_nombre_usuario", func.lower(nombre_usuario), unique=True),)
    rol: Mapped["Rol"] = relationship(foreign_keys=[rol_id])


class IntentoInicioSesion(BaseModelo):
    """Tabla `intentos_inicio_sesion`."""

    __tablename__ = "intentos_inicio_sesion"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True, nullable=False)
    nombre_usuario_intentado: Mapped[str] = mapped_column(String(60), nullable=False)
    usuario_id: Mapped[UUID | None] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=True)
    direccion_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    exitoso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    motivo_fallo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (
        Index("ix_intentos_inicio_sesion_direccion_ip_fecha", "direccion_ip", "fecha"),
        Index("ix_intentos_inicio_sesion_usuario_id_fecha", "usuario_id", "fecha"),
    )
    usuario: Mapped["Usuario | None"] = relationship(foreign_keys=[usuario_id])


class SesionUsuario(BaseModelo):
    """Tabla `sesiones_usuario`."""

    __tablename__ = "sesiones_usuario"

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_ultima_actividad: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    direccion_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    agente_usuario: Mapped[str | None] = mapped_column(String(300), nullable=True)
    revocada: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fecha_revocacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usuario: Mapped["Usuario"] = relationship(foreign_keys=[usuario_id])


class ImportacionExcel(BaseModelo):
    """Tabla `importaciones_excel`."""

    __tablename__ = "importaciones_excel"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    hash_sha256_archivo: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    filas_totales: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    filas_validas: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    filas_rechazadas: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    errores: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    __table_args__ = (CheckConstraint("estado IN ('PROCESANDO','APLICADA','RECHAZADA')", name="estado"),)
    usuario: Mapped["Usuario"] = relationship(foreign_keys=[usuario_id])


class AuditoriaEvento(BaseModelo):
    """Tabla `auditoria_eventos`."""

    __tablename__ = "auditoria_eventos"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True, nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    usuario_id: Mapped[UUID | None] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=True)
    nombre_usuario: Mapped[str | None] = mapped_column(String(60), nullable=True)
    accion: Mapped[str] = mapped_column(String(40), nullable=False)
    numero_documento_consultado: Mapped[str | None] = mapped_column(String(10), nullable=True)
    resultado: Mapped[str | None] = mapped_column(String(20), nullable=True)
    direccion_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    agente_usuario: Mapped[str | None] = mapped_column(String(300), nullable=True)
    detalle: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    __table_args__ = (
        CheckConstraint(
            "accion IN ('LOGIN_EXITOSO','LOGIN_FALLIDO','USUARIO_BLOQUEADO',"
            "'USUARIO_DESBLOQUEADO','CONSULTA_ARTILLERO','CONSULTA_HABILITADOS',"
            "'CONSULTA_NO_HABILITADOS','IMPORTACION_EXCEL','CIERRE_SESION')",
            name="accion",
        ),
        Index("ix_auditoria_eventos_fecha", "fecha"),
        Index("ix_auditoria_eventos_usuario_id_fecha", "usuario_id", "fecha"),
        Index("ix_auditoria_eventos_numero_documento_consultado", "numero_documento_consultado"),
    )
    usuario: Mapped["Usuario | None"] = relationship(foreign_keys=[usuario_id])


class TipoCurso(BaseModelo):
    """Tabla `tipos_curso`."""

    __tablename__ = "tipos_curso"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_sistema: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vigencia_meses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nota_minima_aprobacion: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("vigencia_meses > 0", name="vigencia_meses"),
        CheckConstraint("nota_minima_aprobacion BETWEEN 0 AND 5", name="nota_minima_aprobacion"),
    )


class ArtilleroCurso(BaseModelo):
    """Tabla `artillero_cursos`."""

    __tablename__ = "artillero_cursos"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    hoja_vida_artillero_id: Mapped[UUID] = mapped_column(
        ForeignKey("hoja_vida_artillero.id"), index=True, nullable=False
    )
    tipo_curso_id: Mapped[UUID] = mapped_column(ForeignKey("tipos_curso.id"), index=True, nullable=False)
    numero_cohorte: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    nota_final: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    numero_acta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    institucion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    importacion_excel_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("importaciones_excel.id"), index=True, nullable=True
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("estado IN ('EN_CURSO','APROBADO','REPROBADO','RETIRADO','ANULADO')", name="estado"),
        CheckConstraint("nota_final BETWEEN 0 AND 5", name="nota_final"),
        CheckConstraint(
            "fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio", name="coherencia"
        ),
        UniqueConstraint("hoja_vida_artillero_id", "tipo_curso_id", "numero_cohorte"),
        Index("ix_artillero_cursos_evaluacion", "hoja_vida_artillero_id", "tipo_curso_id", "estado"),
    )
    hoja_vida_artillero: Mapped["HojaVidaArtillero"] = relationship(foreign_keys=[hoja_vida_artillero_id])
    tipo_curso: Mapped["TipoCurso"] = relationship(foreign_keys=[tipo_curso_id])
    importacion_excel: Mapped["ImportacionExcel | None"] = relationship(foreign_keys=[importacion_excel_id])


class TipoCertificacion(BaseModelo):
    """Tabla `tipos_certificacion`."""

    __tablename__ = "tipos_certificacion"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    entidad_emisora: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_sistema: Mapped[str | None] = mapped_column(String(50), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ArtilleroCertificacion(BaseModelo):
    """Tabla `artillero_certificaciones`."""

    __tablename__ = "artillero_certificaciones"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    hoja_vida_artillero_id: Mapped[UUID] = mapped_column(
        ForeignKey("hoja_vida_artillero.id"), index=True, nullable=False
    )
    tipo_certificacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("tipos_certificacion.id"), index=True, nullable=False
    )
    numero_certificado: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fecha_expedicion: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    importacion_excel_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("importaciones_excel.id"), index=True, nullable=True
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("estado IN ('ACTIVA','SUSPENDIDA','REVOCADA')", name="estado"),
        CheckConstraint(
            "fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_expedicion", name="coherencia"
        ),
        Index(
            "ix_artillero_certificaciones_evaluacion",
            "hoja_vida_artillero_id",
            "tipo_certificacion_id",
            "estado",
            "fecha_vencimiento",
        ),
    )
    hoja_vida_artillero: Mapped["HojaVidaArtillero"] = relationship(foreign_keys=[hoja_vida_artillero_id])
    tipo_certificacion: Mapped["TipoCertificacion"] = relationship(foreign_keys=[tipo_certificacion_id])
    importacion_excel: Mapped["ImportacionExcel | None"] = relationship(foreign_keys=[importacion_excel_id])


class SistemaArtilleria(BaseModelo):
    """Tabla `sistemas_artilleria`."""

    __tablename__ = "sistemas_artilleria"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_sistema: Mapped[str] = mapped_column(String(50), nullable=False)
    calibre_milimetros: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    verificacion_habilitada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class RequisitoHabilitacion(BaseModelo):
    """Tabla `requisitos_habilitacion`."""

    __tablename__ = "requisitos_habilitacion"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    sistema_artilleria_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sistemas_artilleria.id"), index=True, nullable=True
    )
    tipo_requisito: Mapped[str] = mapped_column(String(20), nullable=False)
    tipo_curso_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tipos_curso.id"), index=True, nullable=True
    )
    tipo_certificacion_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tipos_certificacion.id"), index=True, nullable=True
    )
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint("tipo_requisito IN ('CURSO','CERTIFICACION')", name="tipo_requisito"),
        CheckConstraint(
            "(tipo_requisito = 'CURSO' AND tipo_curso_id IS NOT NULL AND tipo_certificacion_id IS NULL) "
            "OR (tipo_requisito = 'CERTIFICACION' AND tipo_certificacion_id IS NOT NULL "
            "AND tipo_curso_id IS NULL)",
            name="coherencia",
        ),
    )
    sistema_artilleria: Mapped["SistemaArtilleria | None"] = relationship(
        foreign_keys=[sistema_artilleria_id]
    )
    tipo_curso: Mapped["TipoCurso | None"] = relationship(foreign_keys=[tipo_curso_id])
    tipo_certificacion: Mapped["TipoCertificacion | None"] = relationship(
        foreign_keys=[tipo_certificacion_id]
    )


class TipoCargo(BaseModelo):
    """Tabla `tipos_cargo`."""

    __tablename__ = "tipos_cargo"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ArtilleroCargo(BaseModelo):
    """Tabla `artillero_cargos`."""

    __tablename__ = "artillero_cargos"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    hoja_vida_artillero_id: Mapped[UUID] = mapped_column(
        ForeignKey("hoja_vida_artillero.id"), index=True, nullable=False
    )
    tipo_cargo_id: Mapped[UUID] = mapped_column(ForeignKey("tipos_cargo.id"), index=True, nullable=False)
    unidad_militar_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("unidades_militares.id"), index=True, nullable=True
    )
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_resolucion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    __table_args__ = (CheckConstraint("fecha_fin IS NULL OR fecha_fin >= fecha_inicio", name="coherencia"),)
    hoja_vida_artillero: Mapped["HojaVidaArtillero"] = relationship(foreign_keys=[hoja_vida_artillero_id])
    tipo_cargo: Mapped["TipoCargo"] = relationship(foreign_keys=[tipo_cargo_id])
    unidad_militar: Mapped["UnidadMilitar | None"] = relationship(foreign_keys=[unidad_militar_id])


class Componente(BaseModelo):
    """Tabla `componentes`."""

    __tablename__ = "componentes"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    ruta_angular: Mapped[str | None] = mapped_column(String(250), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    componente_padre_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("componentes.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    componente_padre: Mapped["Componente | None"] = relationship(
        foreign_keys=[componente_padre_id], remote_side=lambda: [Componente.id]
    )


class RolPermiso(BaseModelo):
    """Tabla `rol_permisos`."""

    __tablename__ = "rol_permisos"

    rol_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True, primary_key=True, nullable=False
    )
    componente_id: Mapped[UUID] = mapped_column(
        ForeignKey("componentes.id", ondelete="CASCADE"), index=True, primary_key=True, nullable=False
    )
    puede_acceder: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_crear: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_leer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_actualizar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_eliminar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint(
            "puede_acceder OR NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar)",
            name="coherencia",
        ),
    )
    rol: Mapped["Rol"] = relationship(foreign_keys=[rol_id])
    componente: Mapped["Componente"] = relationship(foreign_keys=[componente_id])


class UsuarioPermiso(BaseModelo):
    """Tabla `usuario_permisos`."""

    __tablename__ = "usuario_permisos"

    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True, primary_key=True, nullable=False
    )
    componente_id: Mapped[UUID] = mapped_column(
        ForeignKey("componentes.id", ondelete="CASCADE"), index=True, primary_key=True, nullable=False
    )
    puede_acceder: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_crear: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_leer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_actualizar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    puede_eliminar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    actualizado_por_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True, nullable=True
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    __table_args__ = (
        CheckConstraint(
            "puede_acceder OR NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar)",
            name="coherencia",
        ),
    )
    usuario: Mapped["Usuario"] = relationship(foreign_keys=[usuario_id])
    componente: Mapped["Componente"] = relationship(foreign_keys=[componente_id])
    actualizado_por: Mapped["Usuario | None"] = relationship(foreign_keys=[actualizado_por_id])
