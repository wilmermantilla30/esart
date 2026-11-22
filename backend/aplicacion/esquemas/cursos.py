"""Esquemas del módulo Cursos (S2-02, contrato de API §5f)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CursoListado(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo_curso: str
    fecha_inicio: date
    fecha_fin: date
    estado: str
    alumnos: int
    comandante: str | None
    # Versión de malla con que se creó el curso (null = curso anterior a la malla).
    version_malla: int | None
    materias_con_nota: int
    # Materias con nota que ya tienen instructor titular.
    asignadas: int


class MateriaDelCurso(BaseModel):
    malla_id: int
    orden: int
    codigo_materia: str
    materia: str
    area: str | None
    modulo: str | None
    evaluable: bool
    instructor_id: int | None
    instructor: str | None
    tipo_instructor: str | None
    asignado_en: datetime | None
    asignado_por: str | None


class DetalleCurso(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo_curso: str
    nombre_tipo_curso: str
    fecha_inicio: date
    fecha_fin: date
    estado: str
    alumnos: int
    comandante: str | None
    nota_minima_aprobacion: float | None
    version_malla: int | None
    anio_malla: int | None
    estado_malla: str | None
    # Solo EN_CURSO y APLAZADO admiten cambios.
    editable: bool
    # Número de la versión vigente que se le puede asignar a un curso sin malla (null si no aplica).
    version_vigente_disponible: int | None
    materias: list[MateriaDelCurso]


class InstructorDisponible(BaseModel):
    id: int
    tipo: str
    nombre: str


class SolicitudAsignarInstructor(BaseModel):
    """instructor_id null quita el instructor de la materia."""

    model_config = ConfigDict(extra="forbid")

    instructor_id: int | None
