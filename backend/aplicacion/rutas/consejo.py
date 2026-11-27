"""
Rutas del Consejo Académico: /api/notas/consejo (S2-14, contrato de API §5i).

Componente CONSEJO_ACADEMICO (se da por excepción, normalmente al Inspector de Estudios): leer
para ver los alumnos que perdieron una habilitación; crear para registrar la decisión del
Consejo con el código del autenticador.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.notas import CasoConsejo, SolicitudDecisionConsejo
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import consejo
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado

COMPONENTE = "CONSEJO_ACADEMICO"

enrutador_consejo = APIRouter(prefix="/notas/consejo", tags=["Notas"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer = requerir_permiso_componente(COMPONENTE, OperacionCRUD.READ, obtener_id_usuario_actual)
puede_crear = requerir_permiso_componente(COMPONENTE, OperacionCRUD.CREATE, obtener_id_usuario_actual)


@enrutador_consejo.get("/casos", response_model=list[CasoConsejo], dependencies=[Depends(puede_leer)])
async def listar_casos(
    sesion: Sesion,
    filtro: Annotated[str, Query(description="PENDIENTES, DECIDIDOS o TODOS")] = "PENDIENTES",
) -> list[CasoConsejo]:
    """Alumnos que perdieron una habilitación (por defecto, los que esperan la decisión del Consejo)."""
    return [CasoConsejo(**caso) for caso in await consejo.casos(sesion, filtro)]


@enrutador_consejo.post(
    "/casos/{habilitacion_id}/decision",
    response_model=CasoConsejo,
    dependencies=[Depends(verificar_csrf), Depends(puede_crear)],
)
async def registrar_decision(
    habilitacion_id: int,
    datos: SolicitudDecisionConsejo,
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
) -> CasoConsejo:
    """Registra la decisión del Consejo (con TOTP). No se puede cambiar después."""
    caso = await consejo.registrar_decision(
        sesion,
        habilitacion_id,
        datos.decision,
        datos.numero_acta,
        datos.fecha_acta,
        datos.observacion,
        actor=Actor.web(usuario, request),
        codigo_totp=datos.codigo_totp,
    )
    return CasoConsejo(**caso)
