"""
Rutas del panel de instructores: /api/instructores (contrato de API §5d).

Componente INSTRUCTORES de la malla: leer para consultar (incluida la foto), crear para
registrar y actualizar para editar, cambiar la foto, activar o desactivar.
El documento sale enmascarado a quien no tenga VER_DOCUMENTO_COMPLETO.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.instructores import (
    CursosDelInstructor,
    DatosEditablesInstructor,
    Especialidad,
    Instructor,
    MilitarParaInstructor,
    SolicitudRegistrarInstructor,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import instructores
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.instructores import DatosInstructor

COMPONENTE = "INSTRUCTORES"

enrutador_instructores = APIRouter(prefix="/instructores", tags=["Instructores"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer = requerir_permiso_componente(COMPONENTE, OperacionCRUD.READ, obtener_id_usuario_actual)
puede_crear = requerir_permiso_componente(COMPONENTE, OperacionCRUD.CREATE, obtener_id_usuario_actual)
puede_actualizar = requerir_permiso_componente(COMPONENTE, OperacionCRUD.UPDATE, obtener_id_usuario_actual)


async def ver_documento_completo(sesion: AsyncSession, usuario_id: int) -> bool:
    # Reutiliza la misma regla de la verificación de artilleros.
    from aplicacion.rutas.verificacion import puede_ver_cedula_completa

    return await puede_ver_cedula_completa(sesion, usuario_id)


def _datos(solicitud: DatosEditablesInstructor) -> DatosInstructor:
    return DatosInstructor(
        fecha_ingreso_escuela=solicitud.fecha_ingreso_escuela,
        especialidades=solicitud.especialidades,
        profesion=solicitud.profesion,
        nombres=solicitud.nombres,
        apellidos=solicitud.apellidos,
    )


async def _respuesta(sesion: AsyncSession, instructor_id: int, usuario_id: int) -> Instructor:
    return Instructor(
        **await instructores.obtener(sesion, instructor_id, await ver_documento_completo(sesion, usuario_id))
    )


@enrutador_instructores.get("", response_model=list[Instructor], dependencies=[Depends(puede_leer)])
async def listar(
    sesion: Sesion,
    usuario: UsuarioActual,
    texto: str | None = Query(default=None, max_length=100),
    especialidad: str | None = Query(default=None, max_length=20),
    estado: Literal["ACTIVOS", "INACTIVOS", "TODOS"] = "ACTIVOS",
) -> list[Instructor]:
    """Directorio de instructores con sus especialidades (sin la foto: va por su propia ruta)."""
    filas = await instructores.listar(
        sesion,
        texto=texto,
        especialidad=especialidad,
        estado=estado,
        ver_documento_completo=await ver_documento_completo(sesion, usuario.id),
    )
    return [Instructor(**fila) for fila in filas]


@enrutador_instructores.get(
    "/especialidades", response_model=list[Especialidad], dependencies=[Depends(puede_leer)]
)
async def listar_especialidades(sesion: Sesion) -> list[Especialidad]:
    return [Especialidad(**fila) for fila in await instructores.especialidades(sesion)]


@enrutador_instructores.get(
    "/militar/{cedula}", response_model=MilitarParaInstructor, dependencies=[Depends(puede_crear)]
)
async def buscar_militar(cedula: str, sesion: Sesion, usuario: UsuarioActual) -> MilitarParaInstructor:
    """Datos del militar (Personal militar) antes de registrarlo como instructor."""
    return MilitarParaInstructor(
        **await instructores.buscar_militar(sesion, cedula, await ver_documento_completo(sesion, usuario.id))
    )


@enrutador_instructores.post(
    "",
    status_code=201,
    response_model=Instructor,
    dependencies=[Depends(verificar_csrf), Depends(puede_crear)],
)
async def registrar(
    solicitud: SolicitudRegistrarInstructor, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> Instructor:
    instructor_id = await instructores.registrar(
        sesion,
        tipo=solicitud.tipo,
        documento=solicitud.documento,
        datos=_datos(solicitud),
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        request=request,
    )
    return await _respuesta(sesion, instructor_id, usuario.id)


@enrutador_instructores.put(
    "/{instructor_id}",
    response_model=Instructor,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def actualizar(
    instructor_id: int,
    solicitud: DatosEditablesInstructor,
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
) -> Instructor:
    await instructores.actualizar(
        sesion,
        instructor_id,
        _datos(solicitud),
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        request=request,
    )
    return await _respuesta(sesion, instructor_id, usuario.id)


@enrutador_instructores.put(
    "/{instructor_id}/foto",
    response_model=Instructor,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def cambiar_foto(
    instructor_id: int, archivo: UploadFile, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> Instructor:
    """Recibe JPG, PNG o WebP (hasta 5 MB) y la guarda como JPEG reducido y sin metadatos."""
    try:
        contenido = await archivo.read(instructores.TAMANO_MAXIMO_FOTO_SUBIDA + 1)
    finally:
        await archivo.close()
    foto = instructores.preparar_foto(contenido)
    await instructores.cambiar_foto(
        sesion,
        instructor_id,
        foto,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        request=request,
    )
    return await _respuesta(sesion, instructor_id, usuario.id)


@enrutador_instructores.delete(
    "/{instructor_id}/foto",
    response_model=Instructor,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def quitar_foto(
    instructor_id: int, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> Instructor:
    await instructores.cambiar_foto(
        sesion,
        instructor_id,
        None,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        request=request,
    )
    return await _respuesta(sesion, instructor_id, usuario.id)


@enrutador_instructores.get(
    "/{instructor_id}/cursos", response_model=CursosDelInstructor, dependencies=[Depends(puede_leer)]
)
async def cursos_del_instructor(instructor_id: int, sesion: Sesion) -> CursosDelInstructor:
    """Cursos donde es comandante y cursos donde participa con otro rol."""
    return CursosDelInstructor(**await instructores.cursos_del_instructor(sesion, instructor_id))


@enrutador_instructores.get("/{instructor_id}/foto", dependencies=[Depends(puede_leer)])
async def ver_foto(instructor_id: int, sesion: Sesion) -> Response:
    """La foto como imagen. Privada: el navegador puede guardarla, ningún intermediario."""
    return Response(
        content=await instructores.leer_foto(sesion, instructor_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@enrutador_instructores.post(
    "/{instructor_id}/{accion}",
    response_model=Instructor,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def cambiar_estado(
    instructor_id: int,
    accion: Literal["activar", "desactivar"],
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
) -> Instructor:
    await instructores.cambiar_estado(
        sesion,
        instructor_id,
        accion == "activar",
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        request=request,
    )
    return await _respuesta(sesion, instructor_id, usuario.id)
