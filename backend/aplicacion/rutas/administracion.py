"""
Rutas de administración: /api/administracion.

- Malla de permisos (componente PERMISOS): leer exige 'leer'; guardar exige 'actualizar' y CSRF.
- Gestión de usuarios (componente USUARIOS): leer, crear y actualizar (activar, desactivar,
  desbloquear, restablecer contraseña). Todo con CSRF y auditado.
- Auditoría (componente AUDITORIA): solo lectura, para todos (la tabla es inmutable).
"""

from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.administracion import (
    EventoAuditoria,
    MilitarParaUsuario,
    PaginaAuditoria,
    RespuestaPermisosRol,
    RespuestaPermisosUsuario,
    ResumenRol,
    SolicitudCrearUsuario,
    SolicitudPermisosRol,
    SolicitudPermisosUsuario,
    SolicitudRestablecerContrasena,
    UsuarioGestion,
    UsuarioMalla,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.sesion_http import (
    obtener_id_usuario_actual,
    obtener_ip_cliente,
    obtener_usuario_actual,
    verificar_csrf,
)
from aplicacion.servicios import administracion_usuarios, malla_permisos
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.habilitacion import total_paginas

enrutador_administracion = APIRouter(prefix="/administracion", tags=["Administración"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer_malla = requerir_permiso_componente("PERMISOS", OperacionCRUD.READ, obtener_id_usuario_actual)
puede_editar_malla = requerir_permiso_componente("PERMISOS", OperacionCRUD.UPDATE, obtener_id_usuario_actual)
puede_leer_usuarios = requerir_permiso_componente("USUARIOS", OperacionCRUD.READ, obtener_id_usuario_actual)
puede_crear_usuarios = requerir_permiso_componente(
    "USUARIOS", OperacionCRUD.CREATE, obtener_id_usuario_actual
)
puede_editar_usuarios = requerir_permiso_componente(
    "USUARIOS", OperacionCRUD.UPDATE, obtener_id_usuario_actual
)
puede_restablecer_totp = requerir_permiso_componente(
    "USUARIOS",
    OperacionCRUD.UPDATE,
    obtener_id_usuario_actual,
    codigo_permiso="usuarios:restablecer_totp",
)
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


# --- Gestión de usuarios -------------------------------------------------------------------


@enrutador_administracion.get(
    "/usuarios", response_model=list[UsuarioGestion], dependencies=[Depends(puede_leer_usuarios)]
)
async def listar_usuarios_gestion(
    sesion: Sesion, texto: str | None = Query(default=None, max_length=80)
) -> list[UsuarioGestion]:
    """Usuarios con rol, militar asociado y estado. 'texto' busca en el usuario o la cédula."""
    return [UsuarioGestion(**asdict(u)) for u in await administracion_usuarios.listar_usuarios(sesion, texto)]


@enrutador_administracion.get(
    "/usuarios/militar/{documento_identidad}",
    response_model=MilitarParaUsuario,
    dependencies=[Depends(puede_crear_usuarios)],
)
async def buscar_militar_para_usuario(documento_identidad: str, sesion: Sesion) -> MilitarParaUsuario:
    """Paso 1 de "Nuevo usuario": el militar de esa cédula y el nombre de usuario sugerido."""
    militar = await administracion_usuarios.buscar_militar_para_usuario(sesion, documento_identidad)
    return MilitarParaUsuario(**asdict(militar))


@enrutador_administracion.post(
    "/usuarios",
    status_code=201,
    response_model=UsuarioGestion,
    dependencies=[Depends(verificar_csrf), Depends(puede_crear_usuarios)],
)
async def crear_usuario(
    solicitud: SolicitudCrearUsuario, request: Request, sesion: Sesion, actor: UsuarioActual
) -> UsuarioGestion:
    usuario_id = await administracion_usuarios.crear_usuario(
        sesion,
        nombre_usuario=solicitud.nombre_usuario,
        codigo_rol=solicitud.rol,
        contrasena=solicitud.contrasena_temporal,
        documento_identidad=solicitud.documento_identidad,
        actor=Actor.web(actor, request),
    )
    return UsuarioGestion(**asdict(await administracion_usuarios.obtener_estado_usuario(sesion, usuario_id)))


@enrutador_administracion.post(
    "/usuarios/{usuario_id}/activar",
    response_model=UsuarioGestion,
    dependencies=[Depends(verificar_csrf), Depends(puede_editar_usuarios)],
)
async def activar_usuario(
    usuario_id: int, request: Request, sesion: Sesion, actor: UsuarioActual
) -> UsuarioGestion:
    estado = await administracion_usuarios.cambiar_estado_activo(
        sesion, usuario_id=usuario_id, activo=True, actor=Actor.web(actor, request)
    )
    return UsuarioGestion(**asdict(estado))


@enrutador_administracion.post(
    "/usuarios/{usuario_id}/desactivar",
    response_model=UsuarioGestion,
    dependencies=[Depends(verificar_csrf), Depends(puede_editar_usuarios)],
)
async def desactivar_usuario(
    usuario_id: int, request: Request, sesion: Sesion, actor: UsuarioActual
) -> UsuarioGestion:
    """Cierra sus sesiones abiertas. Nadie se desactiva a sí mismo ni deja la malla sin administrador."""
    estado = await administracion_usuarios.cambiar_estado_activo(
        sesion, usuario_id=usuario_id, activo=False, actor=Actor.web(actor, request)
    )
    return UsuarioGestion(**asdict(estado))


@enrutador_administracion.post(
    "/usuarios/{usuario_id}/desbloquear",
    response_model=UsuarioGestion,
    dependencies=[Depends(verificar_csrf), Depends(puede_editar_usuarios)],
)
async def desbloquear_usuario(
    usuario_id: int, request: Request, sesion: Sesion, actor: UsuarioActual
) -> UsuarioGestion:
    actual = await administracion_usuarios.obtener_estado_usuario(sesion, usuario_id)
    estado = await administracion_usuarios.desbloquear_usuario(
        sesion, nombre_usuario=actual.usuario, actor=Actor.web(actor, request)
    )
    return UsuarioGestion(**asdict(estado))


@enrutador_administracion.post(
    "/usuarios/{usuario_id}/restablecer-contrasena",
    response_model=UsuarioGestion,
    dependencies=[Depends(verificar_csrf), Depends(puede_editar_usuarios)],
)
async def restablecer_contrasena(
    usuario_id: int,
    solicitud: SolicitudRestablecerContrasena,
    request: Request,
    sesion: Sesion,
    actor: UsuarioActual,
) -> UsuarioGestion:
    """Pone una contraseña temporal: el usuario deberá cambiarla al entrar. Cierra sus sesiones."""
    estado = await administracion_usuarios.restablecer_contrasena(
        sesion,
        usuario_id=usuario_id,
        contrasena_temporal=solicitud.contrasena_temporal,
        actor=Actor.web(actor, request),
    )
    return UsuarioGestion(**asdict(estado))


class SolicitudRestablecerTotp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contrasena: str = Field(min_length=1, max_length=72, repr=False)
    codigo_totp: str = Field(pattern=r"^[0-9]{6}$", repr=False)
    justificacion: str = Field(min_length=12, max_length=1000)


@enrutador_administracion.post(
    "/usuarios/{usuario_id}/restablecer-totp",
    status_code=200,
    dependencies=[Depends(verificar_csrf), Depends(puede_restablecer_totp)],
)
async def restablecer_totp(
    usuario_id: int,
    solicitud: SolicitudRestablecerTotp,
    request: Request,
    sesion: Sesion,
    actor: UsuarioActual,
) -> dict:
    """Exige permiso admin, contraseña y TOTP actual; conserva auditoría y fuerza nuevo enrolamiento."""
    justificacion = solicitud.justificacion.strip()
    if len(justificacion) < 12:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La justificación debe tener al menos 12 caracteres.")
    await administracion_usuarios.restablecer_totp(
        sesion,
        usuario_id=usuario_id,
        contrasena_administrador=solicitud.contrasena,
        codigo_totp=solicitud.codigo_totp,
        justificacion=justificacion,
        actor=actor,
        request=request,
        ip_cliente=obtener_ip_cliente(request),
    )
    return {"restablecido": True, "estado_totp": "PENDIENTE"}


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
