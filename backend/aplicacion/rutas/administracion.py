"""
Rutas de administración: /api/administracion.

- Malla de permisos (componente PERMISOS): leer exige 'leer'; guardar exige 'actualizar' y CSRF.
- Auditoría (componente AUDITORIA): solo lectura, para todos (la tabla es inmutable).
"""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.administracion import (
    EventoAuditoria,
    PaginaAuditoria,
    RespuestaPermisosRol,
    RespuestaPermisosUsuario,
    ResumenRol,
    SolicitudPermisosRol,
    SolicitudPermisosUsuario,
    UsuarioMalla,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import malla_permisos
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.habilitacion import total_paginas

enrutador_administracion = APIRouter(prefix="/administracion", tags=["Administración"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer_malla = requerir_permiso_componente("PERMISOS", OperacionCRUD.READ, obtener_id_usuario_actual)
puede_editar_malla = requerir_permiso_componente("PERMISOS", OperacionCRUD.UPDATE, obtener_id_usuario_actual)
puede_leer_auditoria = requerir_permiso_componente("AUDITORIA", OperacionCRUD.READ, obtener_id_usuario_actual)

TAMANO_PAGINA_POR_DEFECTO = 50
TAMANO_PAGINA_MAXIMO = 200


# --- Malla de permisos -------------------------------------------------------------------


@enrutador_administracion.get(
    "/permisos/roles", response_model=list[ResumenRol], dependencies=[Depends(puede_leer_malla)]
)
async def listar_roles(sesion: Sesion) -> list[ResumenRol]:
    return await malla_permisos.listar_roles(sesion)


@enrutador_administracion.get(
    "/permisos/roles/{codigo_rol}",
    response_model=RespuestaPermisosRol,
    dependencies=[Depends(puede_leer_malla)],
)
async def obtener_permisos_rol(codigo_rol: str, sesion: Sesion) -> RespuestaPermisosRol:
    return await malla_permisos.obtener_permisos_rol(sesion, codigo_rol)


@enrutador_administracion.put(
    "/permisos/roles/{codigo_rol}",
    response_model=RespuestaPermisosRol,
    dependencies=[Depends(verificar_csrf), Depends(puede_editar_malla)],
)
async def guardar_permisos_rol(
    codigo_rol: str, solicitud: SolicitudPermisosRol, request: Request, sesion: Sesion, actor: UsuarioActual
) -> RespuestaPermisosRol:
    return await malla_permisos.guardar_permisos_rol(sesion, codigo_rol, solicitud.permisos, actor, request)


@enrutador_administracion.get(
    "/permisos/usuarios", response_model=list[UsuarioMalla], dependencies=[Depends(puede_leer_malla)]
)
async def listar_usuarios(
    sesion: Sesion, texto: str | None = Query(default=None, max_length=80)
) -> list[UsuarioMalla]:
    return await malla_permisos.listar_usuarios(sesion, texto)


@enrutador_administracion.get(
    "/permisos/usuarios/{usuario_id}",
    response_model=RespuestaPermisosUsuario,
    dependencies=[Depends(puede_leer_malla)],
)
async def obtener_permisos_usuario(usuario_id: int, sesion: Sesion) -> RespuestaPermisosUsuario:
    return await malla_permisos.obtener_permisos_usuario(sesion, usuario_id)


@enrutador_administracion.put(
    "/permisos/usuarios/{usuario_id}",
    response_model=RespuestaPermisosUsuario,
    dependencies=[Depends(verificar_csrf), Depends(puede_editar_malla)],
)
async def guardar_permisos_usuario(
    usuario_id: int,
    solicitud: SolicitudPermisosUsuario,
    request: Request,
    sesion: Sesion,
    actor: UsuarioActual,
) -> RespuestaPermisosUsuario:
    return await malla_permisos.guardar_permisos_usuario(
        sesion, usuario_id, solicitud.cambios, actor, request
    )


# --- Auditoría ---------------------------------------------------------------------------


@enrutador_administracion.get(
    "/auditoria", response_model=PaginaAuditoria, dependencies=[Depends(puede_leer_auditoria)]
)
async def consultar_auditoria(
    sesion: Sesion,
    accion: str | None = Query(default=None, max_length=40),
    usuario: str | None = Query(default=None, max_length=80),
    documento: str | None = Query(default=None, max_length=15),
    desde: date | None = None,
    hasta: date | None = None,
    pagina: int = Query(default=1, ge=1),
    tamano_pagina: int = Query(default=TAMANO_PAGINA_POR_DEFECTO, ge=1, le=TAMANO_PAGINA_MAXIMO),
) -> PaginaAuditoria:
    """Eventos más recientes primero. Todos los filtros son opcionales y van como parámetros."""
    filtros = """
        WHERE (CAST(:accion AS text) IS NULL OR accion = :accion)
          AND (CAST(:usuario AS text) IS NULL OR nombre_usuario ILIKE :patron_usuario)
          AND (CAST(:documento AS text) IS NULL OR numero_documento_consultado = :documento)
          AND (CAST(:desde AS date) IS NULL OR fecha >= CAST(:desde AS date))
          AND (CAST(:hasta AS date) IS NULL OR fecha < CAST(:hasta_exclusivo AS date))
    """
    valores = {
        "accion": accion or None,
        "usuario": usuario or None,
        "patron_usuario": f"%{(usuario or '').strip()}%",
        "documento": documento or None,
        "desde": desde,
        "hasta": hasta,
        "hasta_exclusivo": hasta + timedelta(days=1) if hasta else None,
    }
    # SQL fijo de este archivo; los valores van como parámetros enlazados.
    total = await sesion.scalar(text("SELECT count(*) FROM esart.auditoria_eventos" + filtros), valores)  # noqa: S608
    filas = (
        await sesion.execute(
            text(
                "SELECT id, fecha, usuario_id, nombre_usuario, accion, numero_documento_consultado,"  # noqa: S608
                " resultado, host(direccion_ip) AS direccion_ip, detalle FROM esart.auditoria_eventos"
                + filtros
                + " ORDER BY fecha DESC, id DESC LIMIT :limite OFFSET :desplazamiento"
            ),
            {**valores, "limite": tamano_pagina, "desplazamiento": (pagina - 1) * tamano_pagina},
        )
    ).mappings()
    return PaginaAuditoria(
        elementos=[EventoAuditoria(**fila) for fila in filas],
        pagina=pagina,
        tamano_pagina=tamano_pagina,
        total_elementos=total or 0,
        total_paginas=total_paginas(total or 0, tamano_pagina),
    )
