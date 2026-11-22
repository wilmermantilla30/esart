"""Esquemas del panel de instructores (contrato de API §5d)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Especialidad(BaseModel):
    codigo: str
    nombre: str


class Instructor(BaseModel):
    id: int
    tipo: Literal["MILITAR", "CIVIL"]
    documento: str
    grado: str | None
    nombres: str | None
    apellidos: str | None
    nombre_completo: str
    unidad: str | None
    profesion: str | None
    fecha_ingreso_escuela: date
    activo: bool
    tiene_foto: bool
    # Cambia con cada edición: el front la agrega a la URL de la foto para no ver una vieja.
    version: datetime
    nombre_usuario: str | None
    especialidades: list[Especialidad]


class MilitarParaInstructor(BaseModel):
    documento: str
    nombre_completo: str
    unidad: str | None
    activo: bool
    ya_es_instructor: bool


class DatosEditablesInstructor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_ingreso_escuela: date
    especialidades: list[str] = Field(default_factory=list, max_length=30)
    profesion: str | None = Field(default=None, max_length=150)
    # Solo para civiles (de los militares se toman de Personal militar).
    nombres: str | None = Field(default=None, max_length=100)
    apellidos: str | None = Field(default=None, max_length=100)


class SolicitudRegistrarInstructor(DatosEditablesInstructor):
    tipo: Literal["MILITAR", "CIVIL"]
    documento: str = Field(min_length=5, max_length=20)


class CursoDelInstructor(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo_curso: str
    fecha_inicio: date
    fecha_fin: date
    # EN_CURSO, CULMINADO, CANCELADO o APLAZADO (estados del cargue por Excel, p0011).
    estado: str
    alumnos: int


class CursoConRol(CursoDelInstructor):
    rol_en_curso: str


class MateriaDelInstructor(BaseModel):
    """S2-02: materia que el instructor dicta como titular en un curso."""

    curso_id: int
    curso: str
    nombre_curso: str
    estado: str
    tipo_curso: str
    materia: str
    fecha_inicio: date


class CursosDelInstructor(BaseModel):
    """Detalle del instructor: dónde es comandante, dónde participa y qué materias dicta."""

    comandante: list[CursoDelInstructor]
    participa: list[CursoConRol]
    materias: list[MateriaDelInstructor] = []
