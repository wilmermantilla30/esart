"""
Registro manual de personal militar: /api/personal (componente PERSONAL_CARGUE_MANUAL).

- GET  /api/personal/opciones-registro → categorías con grados y unidades activas.
- POST /api/personal                   → registra un efectivo en esart.personal_militar.

Ambas exigen sesión, CSRF y la operación "crear" del componente en la malla de permisos;
el permiso se resuelve en PostgreSQL en cada petición (el front solo oculta botones).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.personal import (
    OpcionesRegistroPersonal,
    PersonalRegistrado,
    SolicitudRegistrarPersonal,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import registro_personal
from aplicacion.servicios.autenticacion import UsuarioAutenticado

COMPONENTE = "PERSONAL_CARGUE_MANUAL"

puede_registrar = requerir_permiso_componente(COMPONENTE, OperacionCRUD.CREATE, obtener_id_usuario_actual)

enrutador_personal = APIRouter(
    prefix="/personal",
    tags=["Registro manual de personal"],
    dependencies=[Depends(verificar_csrf), Depends(puede_registrar)],
)

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]


@enrutador_personal.get("/opciones-registro", response_model=OpcionesRegistroPersonal)
async def opciones_registro(sesion: Sesion) -> OpcionesRegistroPersonal:
    """Catálogos del formulario (el grado debe pertenecer a la categoría elegida)."""
    return OpcionesRegistroPersonal(
        categorias=registro_personal.opciones_categorias(),
        unidades=await registro_personal.opciones_unidades(sesion),
    )


@enrutador_personal.post("", status_code=201, response_model=PersonalRegistrado)
async def registrar_personal(
    solicitud: SolicitudRegistrarPersonal,
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
) -> PersonalRegistrado:
    """Registra un efectivo. 409 si la cédula ya existe; 422 si un dato no es válido."""
    registro = await registro_personal.registrar(
        sesion,
        registro_personal.DatosPersonal(**solicitud.model_dump()),
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        request=request,
    )
    return PersonalRegistrado(**registro)
