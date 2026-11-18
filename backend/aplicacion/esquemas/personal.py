"""Esquemas del registro manual de personal militar (POST /api/personal)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SolicitudRegistrarPersonal(BaseModel):
    """Formulario "Registro de Personal Militar". Las reglas de negocio las aplica el servicio."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    documento_identidad: str = Field(min_length=5, max_length=20)
    nombres: str = Field(min_length=1, max_length=150)
    apellidos: str = Field(min_length=1, max_length=150)
    grado: str = Field(min_length=1, max_length=20)
    genero: Literal["M", "F"]
    categoria: str = Field(min_length=1, max_length=30)
    unidad_actual_id: int | None = Field(default=None, gt=0)
    especialidad_actual: str | None = Field(default=None, max_length=100)
    activo: bool = True


class PersonalRegistrado(BaseModel):
    id: int
    documento_identidad: str
    nombres: str
    apellidos: str
    nombre_completo: str
    grado: str
    categoria: str
    genero: str
    unidad_actual_id: int | None
    unidad_nombre: str | None
    especialidad_actual: str | None
    activo: bool


class OpcionGrado(BaseModel):
    codigo: str
    nombre: str


class OpcionCategoria(BaseModel):
    codigo: str
    nombre: str
    grados: list[OpcionGrado]


class OpcionUnidad(BaseModel):
    id: int
    codigo: str
    nombre: str


class OpcionesRegistroPersonal(BaseModel):
    """Catálogos del formulario: categorías con sus grados y unidades activas."""

    categorias: list[OpcionCategoria]
    unidades: list[OpcionUnidad]
