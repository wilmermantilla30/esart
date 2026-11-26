"""Esquemas de la carga de notas (S2-12, §5g) y de su revisión por el Inspector (S2-13, §5h)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MateriaDelInstructor(BaseModel):
    """Una materia que el instructor dicta en un curso, con el estado de su entrega."""

    curso_id: int
    codigo_curso: str
    nombre_curso: str
    tipo_curso: str
    estado_curso: str
    fecha_inicio: date
    fecha_fin: date
    malla_id: int
    orden: int
    codigo_materia: str
    materia: str
    nota_minima: float | None
    alumnos: int
    # null = todavía no ha subido notas.
    estado_entrega: str | None
    subido_en: datetime | None
    revisado_en: datetime | None
    observacion_revision: str | None
    notas_entregadas: int
    # Verdadero si la materia ya tiene notas aprobadas (siguen vigentes durante una corrección).
    tiene_notas_oficiales: bool
    # Falso si el curso está cancelado o el Inspector ya aprobó la entrega.
    puede_subir: bool


class MisMaterias(BaseModel):
    # Falso si el usuario no corresponde a un instructor activo (no ve materias).
    es_instructor: bool
    materias: list[MateriaDelInstructor]


class NotaAlumno(BaseModel):
    cedula: str
    grado: str | None
    apellidos: str
    nombres: str
    nota: float


class DatosEntrega(BaseModel):
    estado: str
    nombre_archivo: str
    subido_en: datetime
    subido_por: str | None
    revisado_en: datetime | None
    observacion_revision: str | None
    notas: list[NotaAlumno]


class EntregaDeMateria(BaseModel):
    curso_id: int
    codigo_curso: str
    materia: str
    nota_minima: float | None
    entrega: DatosEntrega | None


# --- Revisión por el Inspector de Estudios (S2-13) ----------------------------------------------


class EntregaEnBandeja(BaseModel):
    """Una entrega de notas en la bandeja del Inspector, con el resumen de sus notas."""

    id: int
    estado: str
    nombre_archivo: str
    # Versión de la entrega: aprobar y devolver la exigen (el instructor pudo subir otra).
    subido_en: datetime
    subido_por: str | None
    revisado_en: datetime | None
    revisado_por: str | None
    observacion_revision: str | None
    curso_id: int
    codigo_curso: str
    nombre_curso: str
    estado_curso: str
    tipo_curso: str
    malla_id: int
    orden: int
    codigo_materia: str
    materia: str
    nota_minima: float | None
    instructor: str
    alumnos: int
    promedio: float | None
    por_debajo_de_la_minima: int
    tiene_notas_oficiales: bool


class NotaEnRevision(BaseModel):
    cedula: str
    grado: str | None
    apellidos: str
    nombres: str
    nota: float
    # Nota oficial vigente (null si la materia aún no tiene notas aprobadas).
    nota_oficial: float | None


class DetalleEntrega(EntregaEnBandeja):
    notas: list[NotaEnRevision]


class SolicitudAprobarEntrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: datetime
    codigo_totp: str = Field(default="", max_length=6, repr=False)


class SolicitudDevolverEntrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: datetime
    observacion: str = Field(max_length=2000)


class SolicitudReabrirEntrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observacion: str = Field(max_length=2000)
    codigo_totp: str = Field(default="", max_length=6, repr=False)
