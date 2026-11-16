"""
Administración de usuarios (HU-10): crear con rol, desbloquear cuenta, desbloquear IP y listar.

Lo usa el comando de consola herramientas/administrar_usuarios.py y lo podrá usar el panel web de
la segunda entrega. Cada acción queda en la auditoría (HU-11). Nunca recibe ni guarda la
contraseña en claro más allá de lo necesario para calcular su hash bcrypt.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos import Rol, Usuario, UsuarioRoles
from aplicacion.modelos.seguridad import LimiteInicioIP
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.contrasenas import generar_hash_contrasena
from aplicacion.servicios import auditoria
from aplicacion.servicios.autenticacion import buscar_usuario_por_nombre, obtener_codigo_rol
from aplicacion.servicios.seguridad_login import ip_canonica, seudonimo

# Quien actúa desde la consola no tiene sesión web: así se identifica en la auditoría.
NOMBRE_ACTOR_CONSOLA = "consola"

PATRON_CEDULA = re.compile(r"^\d{5,15}$")
LONGITUD_MINIMA_CONTRASENA = 10


@dataclass(frozen=True)
class EstadoUsuario:
    id: int
    usuario: str
    rol: str | None
    activo: bool
    intentos_fallidos: int
    bloqueado_hasta: datetime | None
    bloqueado: bool


def validar_contrasena_nueva(contrasena: str) -> None:
    """Mínimo 10 caracteres, con letras y números; máximo 72 bytes (límite de bcrypt)."""
    if len(contrasena) < LONGITUD_MINIMA_CONTRASENA:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La contraseña debe tener al menos 10 caracteres.")
    if not (re.search(r"[A-Za-z]", contrasena) and re.search(r"\d", contrasena)):
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La contraseña debe combinar letras y números.")
    if len(contrasena.encode("utf-8")) > 72:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La contraseña no puede superar 72 bytes.")


async def crear_usuario(
    sesion: AsyncSession,
    *,
    nombre_usuario: str,
    codigo_rol: str,
    contrasena: str,
    documento_identidad: str | None,
    operador: str,
) -> int:
    """Crea un usuario activo con un rol. Devuelve su id. Queda auditado como USUARIO_CREADO."""
    nombre_usuario = nombre_usuario.strip()
    if not 3 <= len(nombre_usuario) <= 80 or not nombre_usuario.isprintable() or " " in nombre_usuario:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "El usuario debe tener de 3 a 80 caracteres, sin espacios."
        )
    if documento_identidad is not None and not PATRON_CEDULA.match(documento_identidad):
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La cédula debe tener solo números (5 a 15 dígitos).")
    validar_contrasena_nueva(contrasena)

    rol = await sesion.scalar(select(Rol).where(Rol.codigo == codigo_rol, Rol.activo.is_(True)))
    if rol is None:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", f"El rol {codigo_rol} no existe o está inactivo.")
    if await buscar_usuario_por_nombre(sesion, nombre_usuario) is not None:
        raise ErrorAplicacion(409, "USUARIO_EXISTENTE", f"Ya existe el usuario {nombre_usuario}.")
    if documento_identidad and await sesion.scalar(
        select(Usuario.id).where(Usuario.documento_identidad == documento_identidad)
    ):
        raise ErrorAplicacion(409, "USUARIO_EXISTENTE", "Ya existe un usuario con esa cédula.")

    usuario = Usuario(
        usuario=nombre_usuario,
        contrasena_hash=generar_hash_contrasena(contrasena),
        documento_identidad=documento_identidad,
        activo=True,
    )
    sesion.add(usuario)
    await sesion.flush()
    sesion.add(UsuarioRoles(usuario_id=usuario.id, rol_id=rol.id))
    await auditoria.registrar_evento(
        sesion,
        auditoria.USUARIO_CREADO,
        nombre_usuario=NOMBRE_ACTOR_CONSOLA,
        resultado="EXITOSO",
        detalle={"usuario_creado": nombre_usuario, "rol": codigo_rol, "operador": operador},
    )
    return usuario.id


async def desbloquear_usuario(sesion: AsyncSession, *, nombre_usuario: str, operador: str) -> EstadoUsuario:
    """Pone en cero los intentos fallidos y quita el bloqueo. Queda auditado (USUARIO_DESBLOQUEADO)."""
    usuario = await buscar_usuario_por_nombre(sesion, nombre_usuario)
    if usuario is None:
        raise ErrorAplicacion(404, "RECURSO_NO_ENCONTRADO", f"No existe el usuario {nombre_usuario}.")
    antes = {
        "intentos_fallidos": usuario.intentos_fallidos_consecutivos,
        "bloqueado_hasta": usuario.bloqueado_hasta.isoformat() if usuario.bloqueado_hasta else None,
    }
    await sesion.execute(
        update(Usuario)
        .where(Usuario.id == usuario.id)
        .values(intentos_fallidos_consecutivos=0, bloqueado_hasta=None)
    )
    await auditoria.registrar_evento(
        sesion,
        auditoria.USUARIO_DESBLOQUEADO,
        nombre_usuario=NOMBRE_ACTOR_CONSOLA,
        resultado="EXITOSO",
        detalle={
            "tipo": "CUENTA",
            "usuario_desbloqueado": usuario.usuario,
            "antes": antes,
            "operador": operador,
        },
    )
    return (await listar_usuarios(sesion, usuario.usuario))[0]


async def desbloquear_ip(sesion: AsyncSession, *, ip: str, operador: str) -> int:
    """
    Pone en cero el contador de intentos de una IP (bloqueo por IP de HU-06).
    La IP se guarda como seudónimo (HMAC), igual que la calcula el login. Devuelve los intentos que tenía.
    """
    canonica = ip_canonica(ip)
    if canonica is None:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La dirección IP no es válida.")
    clave = seudonimo("ip", canonica)
    limite = await sesion.get(LimiteInicioIP, clave)
    intentos_anteriores = limite.intentos if limite else 0
    if limite is not None:
        await sesion.execute(update(LimiteInicioIP).where(LimiteInicioIP.clave == clave).values(intentos=0))
    await auditoria.registrar_evento(
        sesion,
        auditoria.USUARIO_DESBLOQUEADO,
        nombre_usuario=NOMBRE_ACTOR_CONSOLA,
        resultado="EXITOSO",
        detalle={
            "tipo": "IP",
            "ip": canonica,
            "intentos_anteriores": intentos_anteriores,
            "operador": operador,
        },
    )
    return intentos_anteriores


async def listar_usuarios(sesion: AsyncSession, texto: str | None = None) -> list[EstadoUsuario]:
    """Usuarios con su rol y estado de bloqueo (hora del servidor de base de datos)."""
    ahora = await sesion.scalar(text("SELECT now()"))
    # populate_existing: relee los valores aunque el usuario ya esté en memoria (tras un desbloqueo).
    consulta = (
        select(Usuario)
        .where(Usuario.usuario.is_not(None))
        .order_by(Usuario.usuario)
        .execution_options(populate_existing=True)
    )
    if texto:
        consulta = consulta.where(func.lower(Usuario.usuario).contains(texto.strip().lower()))
    resultado = []
    for usuario in await sesion.scalars(consulta):
        resultado.append(
            EstadoUsuario(
                id=usuario.id,
                usuario=usuario.usuario,
                rol=await obtener_codigo_rol(sesion, usuario.id),
                activo=usuario.activo,
                intentos_fallidos=usuario.intentos_fallidos_consecutivos,
                bloqueado_hasta=usuario.bloqueado_hasta,
                bloqueado=bool(usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora),
            )
        )
    return resultado
