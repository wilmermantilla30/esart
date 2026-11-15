"""Autorización en servidor; el proveedor de identidad se conectará en el login."""

from collections.abc import Callable
from enum import StrEnum
from uuid import UUID

from fastapi import Depends
from sqlalchemy import and_, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.modelos import Componente, Permiso, Rol, RolPermiso, RolPermisoCodigo, Usuario, UsuarioPermiso
from aplicacion.nucleo.errores import ErrorAplicacion


class OperacionCRUD(StrEnum):
    CREATE = "puede_crear"
    READ = "puede_leer"
    UPDATE = "puede_actualizar"
    DELETE = "puede_eliminar"


async def tiene_permiso_componente(
    sesion: AsyncSession,
    usuario_id: UUID,
    componente: str,
    operacion: OperacionCRUD,
) -> bool:
    """La excepción del usuario sustituye la fila del rol; ausencia significa denegar."""
    operacion = OperacionCRUD(operacion)
    acceso = func.coalesce(UsuarioPermiso.puede_acceder, RolPermiso.puede_acceder, false())
    accion = func.coalesce(
        getattr(UsuarioPermiso, operacion.value),
        getattr(RolPermiso, operacion.value),
        false(),
    )
    consulta = (
        select(and_(acceso, accion))
        .select_from(Usuario)
        .join(Rol, Rol.id == Usuario.rol_id)
        .join(Componente, Componente.codigo == componente)
        .outerjoin(
            RolPermiso,
            and_(
                RolPermiso.rol_id == Usuario.rol_id,
                RolPermiso.componente_id == Componente.id,
                Rol.activo.is_(True),
            ),
        )
        .outerjoin(
            UsuarioPermiso,
            and_(
                UsuarioPermiso.usuario_id == Usuario.id,
                UsuarioPermiso.componente_id == Componente.id,
            ),
        )
        .where(Usuario.id == usuario_id, Usuario.activo.is_(True), Componente.activo.is_(True))
    )
    return bool(await sesion.scalar(consulta))


async def tiene_permiso_codigo(sesion: AsyncSession, usuario_id: UUID, codigo: str) -> bool:
    """Conserva los permisos por código que exige el contrato de API."""
    consulta = (
        select(Permiso.id)
        .join(RolPermisoCodigo, RolPermisoCodigo.permiso_id == Permiso.id)
        .join(Rol, Rol.id == RolPermisoCodigo.rol_id)
        .join(Usuario, Usuario.rol_id == Rol.id)
        .where(
            Usuario.id == usuario_id,
            Usuario.activo.is_(True),
            Rol.activo.is_(True),
            Permiso.codigo == codigo,
        )
        .limit(1)
    )
    return (await sesion.scalar(consulta)) is not None


def requerir_permiso_componente(
    componente: str,
    operacion: OperacionCRUD,
    obtener_identidad: Callable,
    *,
    codigo_permiso: str | None = None,
) -> Callable:
    """Dependencia FastAPI: exige identidad confiable y opcionalmente un código API.

    obtener_identidad debe devolver UUID validado por autenticación del servidor,
    nunca un identificador recibido directamente del navegador. No implementa login.
    No hay bypass implícito para ADMINISTRADOR: los permisos deben estar asignados.
    """
    operacion = OperacionCRUD(operacion)

    async def verificar(
        usuario_id: UUID = Depends(obtener_identidad),
        sesion: AsyncSession = Depends(obtener_sesion_base_datos),
    ) -> UUID:
        permitido = await tiene_permiso_componente(sesion, usuario_id, componente, operacion)
        if permitido and codigo_permiso is not None:
            permitido = await tiene_permiso_codigo(sesion, usuario_id, codigo_permiso)
        if not permitido:
            raise ErrorAplicacion(403, "SIN_PERMISO", "No tiene permiso para esta acción.")
        return usuario_id

    return verificar
