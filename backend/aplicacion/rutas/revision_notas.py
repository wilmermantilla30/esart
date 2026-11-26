"""
Rutas de la revisión de notas por el Inspector de Estudios: /api/notas/revision (S2-13, §5h).

Componente NOTAS_REVISION (se da por excepción al Inspector): leer para ver la bandeja y el
detalle de cada entrega; actualizar para aprobar (TOTP), devolver (observación) o reabrir una
entrega aprobada (TOTP y observación).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.notas import (
    DetalleEntrega,
    EntregaEnBandeja,
    SolicitudAprobarEntrega,
    SolicitudDevolverEntrega,
    SolicitudReabrirEntrega,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import revision_notas
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado

COMPONENTE = "NOTAS_REVISION"

enrutador_revision_notas = APIRouter(prefix="/notas/revision", tags=["Notas"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer = requerir_permiso_componente(COMPONENTE, OperacionCRUD.READ, obtener_id_usuario_actual)
puede_actualizar = requerir_permiso_componente(COMPONENTE, OperacionCRUD.UPDATE, obtener_id_usuario_actual)
# Las acciones escriben: además del permiso, exigen el token CSRF.
dependencias_accion = [Depends(verificar_csrf), Depends(puede_actualizar)]


@enrutador_revision_notas.get(
    "/entregas", response_model=list[EntregaEnBandeja], dependencies=[Depends(puede_leer)]
)
async def bandeja(
    sesion: Sesion,
    estado: Annotated[str, Query(description="EN_REVISION, DEVUELTA, APROBADA o TODAS")] = "EN_REVISION",
) -> list[EntregaEnBandeja]:
    """Entregas de notas en ese estado (por defecto, las pendientes de revisión)."""
    filas = await revision_notas.bandeja(sesion, None if estado == "TODAS" else estado)
    return [EntregaEnBandeja(**fila) for fila in filas]


@enrutador_revision_notas.get(
    "/entregas/{entrega_id}", response_model=DetalleEntrega, dependencies=[Depends(puede_leer)]
)
async def ver_entrega(entrega_id: int, sesion: Sesion) -> DetalleEntrega:
    """La nota de cada alumno en la entrega, junto a la oficial vigente si la había."""
    return DetalleEntrega(**await revision_notas.detalle(sesion, entrega_id))


@enrutador_revision_notas.post(
    "/entregas/{entrega_id}/aprobar", response_model=DetalleEntrega, dependencies=dependencias_accion
)
async def aprobar(
    entrega_id: int, datos: SolicitudAprobarEntrega, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> DetalleEntrega:
    """Aprueba la entrega (con TOTP): sus notas pasan a ser las oficiales."""
    resultado = await revision_notas.aprobar(
        sesion,
        entrega_id,
        datos.version,
        actor=Actor.web(usuario, request),
        codigo_totp=datos.codigo_totp,
    )
    return DetalleEntrega(**resultado)


@enrutador_revision_notas.post(
    "/entregas/{entrega_id}/devolver", response_model=DetalleEntrega, dependencies=dependencias_accion
)
async def devolver(
    entrega_id: int, datos: SolicitudDevolverEntrega, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> DetalleEntrega:
    """Devuelve la entrega al instructor con la observación de lo que debe corregir."""
    resultado = await revision_notas.devolver(
        sesion, entrega_id, datos.version, datos.observacion, actor=Actor.web(usuario, request)
    )
    return DetalleEntrega(**resultado)


@enrutador_revision_notas.post(
    "/entregas/{entrega_id}/reabrir", response_model=DetalleEntrega, dependencies=dependencias_accion
)
async def reabrir(
    entrega_id: int, datos: SolicitudReabrirEntrega, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> DetalleEntrega:
    """Reabre una entrega aprobada (con TOTP) para que el instructor suba la corrección."""
    resultado = await revision_notas.reabrir(
        sesion,
        entrega_id,
        datos.observacion,
        actor=Actor.web(usuario, request),
        codigo_totp=datos.codigo_totp,
    )
    return DetalleEntrega(**resultado)
