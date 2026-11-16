"""Autorización en servidor; el proveedor de identidad se conectará en el login."""

from collections.abc import Callable
from enum import StrEnum

from fastapi import Depends
from sqlalchemy import and_, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.modelos import Componente, Rol, RolPermiso, Usuario, UsuarioPermiso, UsuarioRoles
from aplicacion.nucleo.errores import ErrorAplicacion


class OperacionCRUD(StrEnum):
    CREATE = "puede_crear"
    READ = "puede_leer"
    UPDATE = "puede_actualizar"
    DELETE = "puede_eliminar"


async def tiene_permiso_componente(
    sesion: AsyncSession,
    usuario_id: int,
    componente: str,
    operacion: OperacionCRUD,
) -> bool:
    """La excepción del usuario sustituye la fila del rol; ausencia significa denegar."""
    operacion = OperacionCRUD(operacion)
    permiso_rol = (
        select(func.bool_or(and_(RolPermiso.puede_acceder, getattr(RolPermiso, operacion.value))))
        .join(UsuarioRoles, UsuarioRoles.rol_id == RolPermiso.rol_id)
        .join(Rol, Rol.id == UsuarioRoles.rol_id)
        .where(
            UsuarioRoles.usuario_id == usuario_id,
            Rol.activo.is_(True),
            RolPermiso.componente_id == Componente.id,
        )
        .correlate(Componente)
        .scalar_subquery()
    )
    excepcion = (
        select(and_(UsuarioPermiso.puede_acceder, getattr(UsuarioPermiso, operacion.value)))
        .where(UsuarioPermiso.usuario_id == usuario_id, UsuarioPermiso.componente_id == Componente.id)
        .correlate(Componente)
        .scalar_subquery()
    )
    consulta = (
        select(func.coalesce(excepcion, permiso_rol, false()))
        .select_from(Usuario)
        .join(Componente, Componente.codigo == componente)
        .where(Usuario.id == usuario_id, Usuario.activo.is_(True), Componente.activo.is_(True))
    )
    return bool(await sesion.scalar(consulta))


async def tiene_permiso_codigo(sesion: AsyncSession, usuario_id: int, codigo: str) -> bool:
    """Denegar hasta conciliar el catálogo granular ausente en la base principal.

    No convertir códigos granulares en concesiones CRUD por inferencia.
    """
    return False


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
        usuario_id: int = Depends(obtener_identidad),
        sesion: AsyncSession = Depends(obtener_sesion_base_datos),
    ) -> int:
        permitido = await tiene_permiso_componente(sesion, usuario_id, componente, operacion)
        if permitido and codigo_permiso is not None:
            permitido = await tiene_permiso_codigo(sesion, usuario_id, codigo_permiso)
        if not permitido:
            raise ErrorAplicacion(403, "SIN_PERMISO", "No tiene permiso para esta acción.")
        return usuario_id

    return verificar
