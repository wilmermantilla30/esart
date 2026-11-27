"""
Rutas del módulo Cursos: /api/cursos (S2-02, contrato de API §5f).

Componente CURSOS de la malla: leer para ver la lista y el detalle; actualizar para asignar el
instructor titular de cada materia con nota y la malla vigente a un curso que no tenía. Al
Inspector de Estudios se le da por excepción (no hay roles nuevos).

S2-15 (§5j): leer también muestra la nota final y el puesto (provisionales hasta el cierre);
actualizar cierra el curso con TOTP.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.cursos import (
    CursoListado,
    DetalleCurso,
    InstructorDisponible,
    ResultadosCurso,
    SolicitudAsignarInstructor,
    SolicitudCerrarCurso,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import cursos, resultados_curso
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado

COMPONENTE = "CURSOS"

enrutador_cursos = APIRouter(prefix="/cursos", tags=["Cursos"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer = requerir_permiso_componente(COMPONENTE, OperacionCRUD.READ, obtener_id_usuario_actual)
puede_actualizar = requerir_permiso_componente(COMPONENTE, OperacionCRUD.UPDATE, obtener_id_usuario_actual)


@enrutador_cursos.get("", response_model=list[CursoListado], dependencies=[Depends(puede_leer)])
async def listar(
    sesion: Sesion,
    estado: Literal["EN_CURSO", "APLAZADO", "CULMINADO", "CANCELADO"] | None = None,
    tipo: Annotated[str | None, Query(max_length=20)] = None,
    texto: Annotated[str | None, Query(max_length=100)] = None,
) -> list[CursoListado]:
    """Cursos más recientes primero (máximo 500), filtrables por estado, tipo y código o nombre."""
    return [CursoListado(**fila) for fila in await cursos.listar(sesion, estado, tipo, texto)]


@enrutador_cursos.get(
    "/instructores-disponibles",
    response_model=list[InstructorDisponible],
    dependencies=[Depends(puede_actualizar)],
)
async def instructores_disponibles(sesion: Sesion) -> list[InstructorDisponible]:
    """Instructores activos para el selector (sin exigir el permiso del panel de Instructores)."""
    return [InstructorDisponible(**fila) for fila in await cursos.instructores_disponibles(sesion)]


@enrutador_cursos.get("/{curso_id}", response_model=DetalleCurso, dependencies=[Depends(puede_leer)])
async def detalle(curso_id: int, sesion: Sesion) -> DetalleCurso:
    """El curso con su malla y el instructor titular de cada materia."""
    return DetalleCurso(**await cursos.detalle(sesion, curso_id))


@enrutador_cursos.put(
    "/{curso_id}/materias/{malla_id}/instructor",
    response_model=DetalleCurso,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def asignar_instructor(
    curso_id: int,
    malla_id: int,
    datos: SolicitudAsignarInstructor,
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
) -> DetalleCurso:
    """Pone, cambia o quita (instructor_id null) el instructor titular de la materia."""
    resultado = await cursos.asignar_instructor(
        sesion, curso_id, malla_id, datos.instructor_id, actor=Actor.web(usuario, request)
    )
    return DetalleCurso(**resultado)


@enrutador_cursos.post(
    "/{curso_id}/malla",
    response_model=DetalleCurso,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def asignar_malla(
    curso_id: int, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> DetalleCurso:
    """Liga la malla vigente de su tipo a un curso en curso que se creó sin malla."""
    return DetalleCurso(
        **await cursos.asignar_malla_vigente(sesion, curso_id, actor=Actor.web(usuario, request))
    )


# --- Nota final, puesto y cierre (S2-15) --------------------------------------------------------


@enrutador_cursos.get(
    "/{curso_id}/resultados", response_model=ResultadosCurso, dependencies=[Depends(puede_leer)]
)
async def ver_resultados(curso_id: int, sesion: Sesion) -> ResultadosCurso:
    """Nota final y puesto de cada alumno: guardados si el curso se cerró, si no provisionales."""
    return ResultadosCurso(**await resultados_curso.resultados(sesion, curso_id))


@enrutador_cursos.post(
    "/{curso_id}/cerrar",
    response_model=ResultadosCurso,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def cerrar_curso(
    curso_id: int, datos: SolicitudCerrarCurso, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> ResultadosCurso:
    """Cierra el curso (con TOTP): quedan los resultados, pasa a CULMINADO y se actualiza el historial."""
    resultado = await resultados_curso.cerrar(
        sesion, curso_id, actor=Actor.web(usuario, request), codigo_totp=datos.codigo_totp
    )
    return ResultadosCurso(**resultado)
