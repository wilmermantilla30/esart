"""Esquemas de la carga de notas del instructor (S2-12, contrato de API §5g)."""

from datetime import date, datetime

from pydantic import BaseModel


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
