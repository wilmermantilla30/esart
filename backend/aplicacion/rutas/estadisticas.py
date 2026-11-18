"""
Estadísticas del panel principal: /api/estadisticas (contrato de API §3b).

Lo ve todo el que tenga el componente DASHBOARD. Solo cifras agregadas: no expone
nombres ni cédulas de alumnos, por eso no se audita cada consulta.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual
from aplicacion.servicios import estadisticas

enrutador_estadisticas = APIRouter(prefix="/estadisticas", tags=["Estadísticas"])

puede_ver_panel = requerir_permiso_componente("DASHBOARD", OperacionCRUD.READ, obtener_id_usuario_actual)


class Periodo(BaseModel):
    anio: int | None
    semestre: int | None


class Indicadores(BaseModel):
    cursos_periodo: int
    alumnos_periodo: int
    egresados: int
    cursos_culminados: int
    cursos_en_curso: int
    alumnos_en_curso: int


class ResumenHabilitacionPanel(BaseModel):
    total: int
    aptos: int
    no_aptos: int
    reentrenamiento_por_vencer: int


class CursosDelAnio(BaseModel):
    anio: int
    semestre_1: int
    semestre_2: int


class Grado(BaseModel):
    sigla: str
    nombre: str
    categoria: str


class CursoEstadistica(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo_curso: str
    estado: str
    fecha_inicio: date
    fecha_fin: date
    comandante: str
    alumnos: int
    grados: dict[str, int] = {}
    genero: dict[str, int] = {}


class CursoEnSeguimiento(CursoEstadistica):
    dias_totales: int
    dias_transcurridos: int
    porcentaje: int
    dias_restantes: int
    vencido: bool


class PanelEstadisticas(BaseModel):
    periodo: Periodo
    hoy: date
    anios_disponibles: list[int]
    indicadores: Indicadores
    habilitacion: ResumenHabilitacionPanel
    cursos_por_anio: list[CursosDelAnio]
    grados: list[Grado]
    cursos: list[CursoEstadistica]
    en_curso: list[CursoEnSeguimiento]


@enrutador_estadisticas.get(
    "/panel", response_model=PanelEstadisticas, dependencies=[Depends(puede_ver_panel)]
)
async def panel(
    sesion: Annotated[AsyncSession, Depends(obtener_sesion_base_datos)],
    anio: int | None = Query(default=None, ge=2000, le=2100),
    # 1 = enero a junio, 2 = julio a diciembre (por la fecha de inicio del curso).
    semestre: int | None = Query(default=None, ge=1, le=2),
) -> PanelEstadisticas:
    """Indicadores, gráficas y seguimiento de cursos para el año y semestre pedidos (vacío = todos)."""
    return PanelEstadisticas(**await estadisticas.panel(sesion, anio, semestre))
