"""Esquemas del módulo Cursos (S2-02, §5f) y de sus resultados finales (S2-15, §5j)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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
    # S2-16: fase de campaña por ítems; la registra el comandante del curso (sin instructor).
    por_items: bool
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


# --- Nota final, puesto y cierre (S2-15) --------------------------------------------------------


class ResultadoAlumno(BaseModel):
    cedula: str
    grado: str | None
    apellidos: str
    nombres: str
    # Promedio de las materias evaluables con nota (provisional si faltan materias).
    nota_final: float | None
    materias_evaluadas: int
    materias_habilitadas: int
    # Lo que falta para el resultado definitivo (vacío si está completo).
    pendientes: list[str]
    # APROBADO | REPROBADO; null mientras esté incompleto.
    resultado: str | None
    motivo: str | None
    # Solo los aprobados; empates comparten el puesto.
    puesto: int | None


class ResultadosCurso(BaseModel):
    curso_id: int
    codigo_curso: str
    estado_curso: str
    nota_minima: float | None
    # Verdadero cuando el curso ya se cerró: los resultados están guardados y no cambian.
    cerrado: bool
    cerrado_en: datetime | None
    cerrado_por: str | None
    materias_evaluables: int
    completo: bool
    puede_cerrar: bool
    # Pendientes del curso (entregas de notas sin aprobar).
    pendientes: list[str]
    alumnos: list[ResultadoAlumno]


class SolicitudCerrarCurso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo_totp: str = Field(default="", max_length=6, repr=False)
