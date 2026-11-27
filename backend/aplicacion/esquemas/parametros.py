"""Esquemas del panel de Parámetros (contrato de API §6)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ValoresRegla(BaseModel):
    """Los cuatro valores de la regla APTO / NO APTO."""

    model_config = ConfigDict(extra="forbid")

    cursos_habilitantes: list[str] = Field(max_length=50)
    meses_vigencia_reentrenamiento: int
    dias_alerta_vencimiento: int
    exige_apto_para_disparar: bool


class CursoDisponible(BaseModel):
    codigo: str
    nombre: str


class ResumenRegla(BaseModel):
    total: int
    aptos: int
    no_aptos: int
    reentrenamiento_por_vencer: int


class ReglaHabilitacion(BaseModel):
    """Lo que muestra la pestaña Cursos y Capacitaciones."""

    valores: ValoresRegla
    actualizado_en: datetime | None
    actualizado_por: str | None
    cursos_disponibles: list[CursoDisponible]
    resumen: ResumenRegla


class SimulacionRegla(BaseModel):
    actual: ResumenRegla
    propuesto: ResumenRegla
    pasan_a_no_apto: int
    pasan_a_apto: int


class SolicitudGuardarRegla(ValoresRegla):
    """Guardar exige la versión que se editó (concurrencia) y, si aplica, el código TOTP."""

    version: datetime | None
    codigo_totp: str = Field(default="", max_length=6, repr=False)


class NotaMinima(BaseModel):
    """Nota mínima de aprobación (S2-10): la vigente y cuántos cursos en curso conservan la suya."""

    valor: float
    actualizado_en: datetime
    actualizado_por: str | None
    cursos_en_curso: int


class SolicitudGuardarNotaMinima(BaseModel):
    """Nota nueva (0 a 5, 2 decimales), versión editada (concurrencia) y, si aplica, el código TOTP."""

    model_config = ConfigDict(extra="forbid")

    valor: Decimal = Field(max_digits=3, decimal_places=2)
    version: datetime | None
    codigo_totp: str = Field(default="", max_length=6, repr=False)


# --- Mallas curriculares (S2-09) -------------------------------------------------------------


class TipoCursoMalla(BaseModel):
    """Un tipo de curso en el listado de la pestaña, con su versión vigente (si tiene)."""

    codigo: str
    nombre: str
    tipo: str | None
    modalidad: str
    duracion_semanas: int
    activo: bool
    version: int | None
    anio: int | None
    materias: int
    evaluables: int


class DatosTipoCurso(BaseModel):
    codigo: str
    nombre: str
    tipo: str | None
    modalidad: str
    duracion_semanas: int
    activo: bool


class VersionMallaResumen(BaseModel):
    numero: int
    anio: int
    estado: str
    observacion: str | None
    creado_en: datetime
    creado_por: str | None
    materias: int
    # Cursos creados con esta versión (la conservan aunque haya versiones nuevas).
    cursos: int


class FilaMallaRespuesta(BaseModel):
    orden: int
    codigo_materia: str
    materia: str
    area: str | None
    modulo: str | None
    evaluable: bool


class DetalleMalla(BaseModel):
    tipo_curso: DatosTipoCurso
    version: VersionMallaResumen | None
    filas: list[FilaMallaRespuesta]
    versiones: list[VersionMallaResumen]


class MateriaCatalogo(BaseModel):
    codigo: str
    nombre: str


class FilaMallaSolicitud(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orden: int = Field(ge=1, le=500)
    materia: str = Field(min_length=1, max_length=200)
    evaluable: bool
    area: str | None = Field(default=None, max_length=100)
    modulo: str | None = Field(default=None, max_length=100)


class SolicitudGuardarMalla(BaseModel):
    """Malla completa editada. version = número de la vigente que se editó (null si no tenía)."""

    model_config = ConfigDict(extra="forbid")

    anio: int = Field(ge=2000, le=2100)
    filas: list[FilaMallaSolicitud] = Field(min_length=1, max_length=200)
    observacion: str | None = Field(default=None, max_length=500)
    version: int | None
    codigo_totp: str = Field(default="", max_length=6, repr=False)


class SolicitudCrearTipoCurso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(min_length=2, max_length=20)
    nombre: str = Field(min_length=3, max_length=200)
    tipo: Literal["EDUCACION_MILITAR", "ESPECIALIZACION", "EDUCACION_SUPERIOR"]
    modalidad: Literal["PRESENCIAL", "VIRTUAL", "MIXTA"]
    duracion_semanas: int = Field(ge=1, le=104)
    codigo_totp: str = Field(default="", max_length=6, repr=False)


class Plantilla(BaseModel):
    id: int
    nombre_oficial: str
    nombre_archivo: str
    formato: str
    version: str
    descripcion: str
    tamano_bytes: int
    sha256: str
    subido_en: datetime
    subido_por: str | None


class PoliticaSeguridad(BaseModel):
    codigo: str
    nombre: str
    modulo: str
    requiere_totp: bool
    activa: bool


class ParametrosSeguridad(BaseModel):
    """Pestaña Parámetros de Seguridad: solo consulta (las políticas no se editan desde la web)."""

    totp_habilitado: bool
    usuarios_activos: int
    usuarios_con_autenticador: int
    minutos_inactividad_sesion: int
    intento_captcha: int
    intento_bloqueo: int
    horas_bloqueo: int
    politicas: list[PoliticaSeguridad]
