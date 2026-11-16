"""Esquemas de /api/verificar (contrato de API §3), adaptados a la regla acordada el 2026-11-16."""

from datetime import date, datetime

from pydantic import BaseModel


class UnidadResumida(BaseModel):
    sigla: str | None
    nombre: str | None


class ArtilleroVerificado(BaseModel):
    # Enmascarada (******5678) si el usuario no tiene VER_DOCUMENTO_COMPLETO.
    numero_documento: str
    nombre_completo: str
    grado: str
    categoria: str
    unidad_militar: UnidadResumida | None
    estado_servicio: str  # ACTIVO o INACTIVO


class CriterioVerificacion(BaseModel):
    descripcion: str
    # OBLIGATORIO: debe cumplirse. ALTERNATIVO: basta con que se cumpla uno de ellos.
    tipo: str
    cumple: bool
    detalle: str | None
    motivo: str | None


class CursoVerificacion(BaseModel):
    nombre: str
    codigo: str | None
    institucion: str
    fecha_inicio: date
    fecha_fin: date | None
    estado: str  # APROBADO o EN_CURSO
    habilitante: bool


class ReentrenamientoVerificacion(BaseModel):
    numero_certificado: str
    tipo: str
    calibre: str
    fecha_expedicion: date
    fecha_vencimiento: date
    # VIGENTE, POR_VENCER, VENCIDO o ANULADO (marcado no vigente / no apto para disparar).
    estado: str


class RespuestaVerificacion(BaseModel):
    artillero: ArtilleroVerificado
    resultado: str  # APTO o NO_APTO
    fecha_verificacion: datetime
    criterios: list[CriterioVerificacion]
    motivos: list[str]
    # Aviso para planear el próximo reentrenamiento (null si no aplica).
    alerta: str | None
    cursos: list[CursoVerificacion]
    reentrenamientos: list[ReentrenamientoVerificacion]


class ElementoHabilitacion(BaseModel):
    numero_documento: str
    nombre_completo: str
    grado: str
    unidad_militar_sigla: str | None
    activo: bool
    resultado: str
    motivos: list[str]
    curso_habilitante: str | None
    reentrenamiento_vence: date | None
    estado_reentrenamiento: str


class PaginaHabilitacion(BaseModel):
    """Formato único de paginación (contrato §1.3)."""

    elementos: list[ElementoHabilitacion]
    pagina: int
    tamano_pagina: int
    total_elementos: int
    total_paginas: int


class ResumenHabilitacion(BaseModel):
    total: int
    aptos: int
    no_aptos: int
    reentrenamiento_por_vencer: int
    activos: int
    unidades: int
    dias_alerta_vencimiento: int
