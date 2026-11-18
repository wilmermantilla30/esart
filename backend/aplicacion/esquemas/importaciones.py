"""Respuesta de la importación masiva; conserva el contrato existente de ESART."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RespuestaImportacionPersonal(BaseModel):
    """Contadores reales de una transacción aplicada y referencia a su auditoría."""

    importacion_id: UUID
    estado: Literal["APLICADA"]
    mensaje: str = "Importación realizada correctamente."
    filas_totales: int = Field(ge=0)
    filas_validas: int = Field(ge=0)
    filas_rechazadas: int = Field(ge=0)
    curso_id: int
    curso_codigo: str
    registros_nuevos: int = Field(ge=0)
    grados_actualizados: int = Field(ge=0)


class OpcionCatalogo(BaseModel):
    """Opción de lista desplegable; el cliente envía solo el id."""

    id: int
    nombre: str
    codigo: str | None = None


class DatosFormularioCurso(BaseModel):
    """Catálogos del curso que se crea con la importación."""

    tipos_curso: list[OpcionCatalogo]
    instructores: list[OpcionCatalogo]
    siguiente_codigo: str
