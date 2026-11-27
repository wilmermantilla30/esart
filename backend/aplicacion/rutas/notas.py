"""
Rutas de la carga de notas del instructor: /api/notas (S2-12, §5g) y su habilitación (S2-14, §5i).

Componente NOTAS_CARGA (se da por excepción al instructor): leer para ver sus materias, descargar
la plantilla y ver su entrega; crear para subir la planilla. Además del permiso, el usuario debe
ser el instructor titular de la materia en ese curso (S2-02): el servicio lo comprueba.
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.notas import (
    EntregaDeMateria,
    FormularioHabilitacion,
    MisMaterias,
    SolicitudHabilitacion,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import habilitaciones, notas
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.plantillas import TAMANO_MAXIMO_BYTES

COMPONENTE = "NOTAS_CARGA"

enrutador_notas = APIRouter(prefix="/notas", tags=["Notas"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer = requerir_permiso_componente(COMPONENTE, OperacionCRUD.READ, obtener_id_usuario_actual)
puede_crear = requerir_permiso_componente(COMPONENTE, OperacionCRUD.CREATE, obtener_id_usuario_actual)


@enrutador_notas.get("/mis-materias", response_model=MisMaterias, dependencies=[Depends(puede_leer)])
async def mis_materias(sesion: Sesion, usuario: UsuarioActual) -> MisMaterias:
    """Materias que dicta el usuario en cada curso y el estado de su entrega de notas."""
    return MisMaterias(**await notas.mis_materias(sesion, usuario))


@enrutador_notas.get("/plantilla/{curso_id}/{malla_id}", dependencies=[Depends(puede_leer)])
async def descargar_plantilla(
    curso_id: int, malla_id: int, sesion: Sesion, usuario: UsuarioActual
) -> Response:
    """Plantilla Excel de la materia con los alumnos del curso (firmada para detectar cambios)."""
    nombre, contenido = await notas.generar_plantilla(sesion, usuario, curso_id, malla_id)
    return Response(
        content=contenido,
        media_type=notas.TIPO_MIME_XLSX,
        headers={
            # filename* (RFC 5987) admite cualquier nombre sin riesgo de inyectar cabeceras.
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@enrutador_notas.get(
    "/entregas/{curso_id}/{malla_id}", response_model=EntregaDeMateria, dependencies=[Depends(puede_leer)]
)
async def ver_entrega(
    curso_id: int, malla_id: int, sesion: Sesion, usuario: UsuarioActual
) -> EntregaDeMateria:
    """La entrega del instructor para esa materia, con la nota de cada alumno."""
    return EntregaDeMateria(**await notas.entrega(sesion, usuario, curso_id, malla_id))


@enrutador_notas.post(
    "/entregas/{curso_id}/{malla_id}",
    response_model=EntregaDeMateria,
    dependencies=[Depends(verificar_csrf), Depends(puede_crear)],
)
async def subir_planilla(
    curso_id: int,
    malla_id: int,
    archivo: UploadFile,
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
) -> EntregaDeMateria:
    """Sube la planilla con las notas: queda EN_REVISION hasta que el Inspector la apruebe."""
    try:
        # Se lee como máximo un byte más del límite: suficiente para saber que lo supera.
        contenido = await archivo.read(TAMANO_MAXIMO_BYTES + 1)
    finally:
        await archivo.close()
    resultado = await notas.subir_planilla(
        sesion, usuario, curso_id, malla_id, archivo.filename, contenido, actor=Actor.web(usuario, request)
    )
    return EntregaDeMateria(**resultado)


# --- Habilitación (S2-14) -----------------------------------------------------------------------


@enrutador_notas.get(
    "/habilitaciones/{curso_id}/{malla_id}",
    response_model=FormularioHabilitacion,
    dependencies=[Depends(puede_leer)],
)
async def ver_habilitacion(
    curso_id: int, malla_id: int, sesion: Sesion, usuario: UsuarioActual
) -> FormularioHabilitacion:
    """Alumnos que deben habilitar la materia y la nota de habilitación registrada, si la hay."""
    return FormularioHabilitacion(**await habilitaciones.formulario(sesion, usuario, curso_id, malla_id))


@enrutador_notas.post(
    "/habilitaciones/{curso_id}/{malla_id}",
    response_model=FormularioHabilitacion,
    dependencies=[Depends(verificar_csrf), Depends(puede_crear)],
)
async def registrar_habilitacion(
    curso_id: int,
    malla_id: int,
    datos: SolicitudHabilitacion,
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
) -> FormularioHabilitacion:
    """Registra las notas de habilitación: quedan EN_REVISION hasta que el Inspector las apruebe."""
    resultado = await habilitaciones.registrar(
        sesion,
        usuario,
        curso_id,
        malla_id,
        [nota.model_dump() for nota in datos.notas],
        actor=Actor.web(usuario, request),
    )
    return FormularioHabilitacion(**resultado)
