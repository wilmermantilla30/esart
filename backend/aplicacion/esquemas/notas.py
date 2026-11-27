"""Esquemas de la carga de notas (S2-12, §5g), su revisión (S2-13, §5h) y la habilitación y el Consejo
Académico (S2-14, §5i)."""

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
    # S2-14: alumnos con nota oficial ordinaria bajo la mínima y el estado de su habilitación.
    alumnos_a_habilitar: int
    estado_habilitacion: str | None
    observacion_habilitacion: str | None
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
    # ORDINARIA (planilla de S2-12) o HABILITACION (formulario de S2-14).
    tipo: str
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
    # Nota aprobada antes del mismo tipo (null si no había): la ordinaria oficial o, en una
    # habilitación, la de la habilitación anterior.
    nota_oficial: float | None
    # Nota ordinaria oficial (en una habilitación, la que perdió la materia).
    nota_ordinaria: float | None


class DetalleEntrega(EntregaEnBandeja):
    notas: list[NotaEnRevision]


class SolicitudAprobarEntrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # subido_en de la entrega revisada (aprobar no pide TOTP desde 2026-11-27).
    version: datetime


class SolicitudDevolverEntrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: datetime
    observacion: str = Field(max_length=2000)


class SolicitudReabrirEntrega(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observacion: str = Field(max_length=2000)
    codigo_totp: str = Field(default="", max_length=6, repr=False)


# --- Habilitación (S2-14) -----------------------------------------------------------------------


class AlumnoAHabilitar(BaseModel):
    cedula: str
    grado: str | None
    apellidos: str
    nombres: str
    # Nota ordinaria oficial con la que perdió la materia.
    nota_ordinaria: float
    # Nota de habilitación ya registrada (null si todavía no).
    nota_habilitacion: float | None


class FormularioHabilitacion(BaseModel):
    curso_id: int
    codigo_curso: str
    materia: str
    nota_minima: float | None
    alumnos: list[AlumnoAHabilitar]
    # Estado de la entrega de habilitación (null = todavía no se registra).
    estado: str | None
    subido_en: datetime | None
    revisado_en: datetime | None
    observacion_revision: str | None


class NotaHabilitacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cedula: str = Field(max_length=20)
    # Número o texto con coma o punto (misma lectura que la planilla); null = falta.
    nota: float | str | None = None


class SolicitudHabilitacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notas: list[NotaHabilitacion] = Field(max_length=500)


# --- Consejo Académico (S2-14) ------------------------------------------------------------------


class CasoConsejo(BaseModel):
    """Alumno que perdió la habilitación de una materia y, si ya la hay, la decisión del Consejo."""

    id: int
    curso_id: int
    codigo_curso: str
    nombre_curso: str
    estado_curso: str
    tipo_curso: str
    malla_id: int
    codigo_materia: str
    materia: str
    nota_minima: float | None
    cedula: str
    grado: str | None
    apellidos: str
    nombres: str
    nota_ordinaria: float
    nota_habilitacion: float
    habilitacion_aprobada_en: datetime
    # null mientras el Consejo no decide.
    decision: str | None
    numero_acta: str | None
    fecha_acta: date | None
    observacion: str | None
    registrado_en: datetime | None
    registrado_por: str | None


class SolicitudDecisionConsejo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(max_length=20)
    numero_acta: str = Field(max_length=100)
    fecha_acta: date
    observacion: str | None = Field(default=None, max_length=2000)
    codigo_totp: str = Field(default="", max_length=6, repr=False)
