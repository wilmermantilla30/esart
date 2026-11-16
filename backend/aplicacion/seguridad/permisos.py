"""Autorización en servidor; el proveedor de identidad se conectará en el login."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends
from sqlalchemy import and_, false, func, select, text
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


@dataclass(frozen=True)
class PermisoEfectivo:
    """Lo que un usuario puede hacer sobre un componente, ya resuelto (rol + excepción)."""

    codigo: str
    nombre: str
    ruta_angular: str | None
    orden: int
    codigo_padre: str | None
    puede_acceder: bool
    puede_crear: bool
    puede_leer: bool
    puede_actualizar: bool
    puede_eliminar: bool


# Misma regla que tiene_permiso_componente, para TODOS los componentes activos en una consulta:
# - por rol: basta que uno de sus roles activos lo conceda (bool_or), siempre junto con puede_acceder;
# - la excepción del usuario (usuario_permisos), si existe, SUSTITUYE a la de sus roles;
# - sin fila, se niega. Usuario inactivo: ningún permiso.
CONSULTA_PERMISOS_EFECTIVOS = text("""
    WITH por_rol AS (
        SELECT rp.componente_id,
               bool_or(rp.puede_acceder) AS acceder,
               bool_or(rp.puede_acceder AND rp.puede_crear) AS crear,
               bool_or(rp.puede_acceder AND rp.puede_leer) AS leer,
               bool_or(rp.puede_acceder AND rp.puede_actualizar) AS actualizar,
               bool_or(rp.puede_acceder AND rp.puede_eliminar) AS eliminar
        FROM esart.rol_permisos rp
        JOIN esart.usuario_roles ur ON ur.rol_id = rp.rol_id
        JOIN esart.roles r ON r.id = ur.rol_id AND r.activo
        WHERE ur.usuario_id = :usuario_id
        GROUP BY rp.componente_id
    ),
    excepcion AS (
        SELECT componente_id,
               puede_acceder AS acceder,
               puede_acceder AND puede_crear AS crear,
               puede_acceder AND puede_leer AS leer,
               puede_acceder AND puede_actualizar AS actualizar,
               puede_acceder AND puede_eliminar AS eliminar
        FROM esart.usuario_permisos
        WHERE usuario_id = :usuario_id
    )
    SELECT c.codigo, c.nombre, c.ruta_angular, c.orden, padre.codigo AS codigo_padre,
           coalesce(e.acceder, r.acceder, false) AS puede_acceder,
           coalesce(e.crear, r.crear, false) AS puede_crear,
           coalesce(e.leer, r.leer, false) AS puede_leer,
           coalesce(e.actualizar, r.actualizar, false) AS puede_actualizar,
           coalesce(e.eliminar, r.eliminar, false) AS puede_eliminar
    FROM esart.componentes c
    LEFT JOIN esart.componentes padre ON padre.id = c.componente_padre_id
    LEFT JOIN por_rol r ON r.componente_id = c.id
    LEFT JOIN excepcion e ON e.componente_id = c.id
    WHERE c.activo
      AND EXISTS (SELECT 1 FROM esart_ref.usuarios u WHERE u.id = :usuario_id AND u.activo)
    ORDER BY c.orden, c.codigo
""")


async def obtener_permisos_efectivos(sesion: AsyncSession, usuario_id: int) -> list[PermisoEfectivo]:
    """Permisos del usuario sobre cada componente activo (los que no tiene vienen en False)."""
    filas = (await sesion.execute(CONSULTA_PERMISOS_EFECTIVOS, {"usuario_id": usuario_id})).mappings()
    return [PermisoEfectivo(**fila) for fila in filas]
