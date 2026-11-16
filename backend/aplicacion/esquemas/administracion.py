"""Esquemas de /api/administracion: malla de permisos, gestión de usuarios y consulta de auditoría."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Operaciones(BaseModel):
    """Las cinco casillas de la malla. Sin 'acceder' no vale ninguna otra."""

    acceder: bool = False
    crear: bool = False
    leer: bool = False
    actualizar: bool = False
    eliminar: bool = False


class PermisoDeComponente(Operaciones):
    componente: str = Field(min_length=1, max_length=100)


class SolicitudPermisosRol(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permisos: list[PermisoDeComponente] = Field(max_length=200)


class CambioPermisoUsuario(BaseModel):
    """HEREDAR: lo que dé su rol. CONCEDER: las operaciones marcadas. QUITAR: nada en ese módulo."""

    model_config = ConfigDict(extra="forbid")
    componente: str = Field(min_length=1, max_length=100)
    modo: Literal["HEREDAR", "CONCEDER", "QUITAR"]
    crear: bool = False
    leer: bool = False
    actualizar: bool = False
    eliminar: bool = False


class SolicitudPermisosUsuario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cambios: list[CambioPermisoUsuario] = Field(max_length=200)


class ComponenteMalla(BaseModel):
    codigo: str
    nombre: str
    ruta: str | None
    codigo_padre: str | None
    # Permiso sin menú (por ejemplo, ver la cédula completa).
    especial: bool


class FilaPermisoRol(ComponenteMalla):
    permisos: Operaciones


class RespuestaPermisosRol(BaseModel):
    rol: str
    nombre: str
    # ADMINISTRADOR es fijo: se muestra completo y no se edita.
    editable: bool
    filas: list[FilaPermisoRol]


class ResumenRol(BaseModel):
    codigo: str
    nombre: str
    editable: bool


class UsuarioMalla(BaseModel):
    id: int
    usuario: str
    nombre_completo: str
    rol: str | None
    activo: bool


class FilaPermisoUsuario(ComponenteMalla):
    # Lo que le da su rol.
    rol: Operaciones
    # HEREDAR (sin excepción), CONCEDER o QUITAR.
    modo: Literal["HEREDAR", "CONCEDER", "QUITAR"]
    excepcion: Operaciones | None
    # Lo que finalmente puede hacer.
    efectivo: Operaciones


class RespuestaPermisosUsuario(BaseModel):
    usuario: UsuarioMalla
    # Los usuarios con rol ADMINISTRADOR tienen todo y no admiten excepciones.
    editable: bool
    filas: list[FilaPermisoUsuario]


class EventoAuditoria(BaseModel):
    id: int
    fecha: datetime
    usuario_id: int | None
    nombre_usuario: str | None
    accion: str
    numero_documento_consultado: str | None
    resultado: str | None
    direccion_ip: str | None
    detalle: dict | None


class PaginaAuditoria(BaseModel):
    elementos: list[EventoAuditoria]
    pagina: int
    tamano_pagina: int
    total_elementos: int
    total_paginas: int


# --- Gestión de usuarios (HU-10) ------------------------------------------------------------


class UsuarioGestion(BaseModel):
    """Fila de la tabla de Gestión de usuarios. Nunca incluye el hash de la contraseña."""

    id: int
    usuario: str
    rol: str | None
    activo: bool
    bloqueado: bool
    bloqueado_hasta: datetime | None
    intentos_fallidos: int
    documento_identidad: str | None
    nombre_completo: str | None
    requiere_cambio_contrasena: bool
    ultimo_acceso_en: datetime | None


class MilitarParaUsuario(BaseModel):
    """Resultado de buscar una cédula en Personal militar al crear un usuario."""

    documento_identidad: str
    grado: str
    nombres: str
    apellidos: str
    unidad: str | None
    activo: bool
    usuario_existente: str | None
    nombre_usuario_sugerido: str


class SolicitudCrearUsuario(BaseModel):
    """La contraseña es temporal: el usuario la cambia al entrar. Las reglas las valida el servicio."""

    model_config = ConfigDict(extra="forbid")
    documento_identidad: str = Field(min_length=5, max_length=15)
    nombre_usuario: str = Field(min_length=3, max_length=80)
    rol: Literal["USUARIO", "ADMINISTRADOR"]
    contrasena_temporal: str = Field(min_length=1, max_length=72)


class SolicitudRestablecerContrasena(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contrasena_temporal: str = Field(min_length=1, max_length=72)
