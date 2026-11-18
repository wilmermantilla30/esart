"""Alta inicial explícita, sin DDL, contraseñas de archivo ni cambios a cuentas existentes."""

import argparse
import asyncio
import getpass
import hmac
import json
import warnings

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_motor_base_datos
from aplicacion.modelos import Rol, Usuario, UsuarioRoles
from aplicacion.seguridad.contrasenas import generar_hash_contrasena, verificar_contrasena
from aplicacion.servicios.autenticacion import CODIGO_ROL_ADMINISTRADOR


class AltaRechazada(ValueError):
    """Error operativo conocido; sus mensajes nunca contienen secretos."""


def validar_nombre(nombre: str) -> str:
    nombre = nombre.strip()
    if not 3 <= len(nombre) <= 80 or not nombre.isprintable():
        raise AltaRechazada("El nombre debe tener entre 3 y 80 caracteres imprimibles.")
    return nombre


def leer_contrasena(*, confirmar: bool) -> str:
    # getpass puede recurrir a entrada visible si no hay terminal: rechazar ese fallback.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            clave = getpass.getpass("Contraseña (entrada oculta): ")
            if not clave or len(clave.encode("utf-8")) > 72:
                raise AltaRechazada("La contraseña debe tener de 1 a 72 bytes UTF-8.")
            if confirmar:
                repeticion = getpass.getpass("Repita la contraseña (entrada oculta): ")
                if not hmac.compare_digest(clave.encode("utf-8"), repeticion.encode("utf-8")):
                    raise AltaRechazada("Las contraseñas no coinciden.")
            return clave
        except getpass.GetPassWarning:
            raise AltaRechazada("Se requiere una terminal con entrada oculta; no usar tuberías.") from None


async def inspeccionar(sesion: AsyncSession, nombre: str) -> dict:
    identidad = (await sesion.execute(text("SELECT current_database(),current_user"))).one()
    if tuple(identidad) != ("esart_db", "esart_aplicacion"):
        raise AltaRechazada("Se requiere esart_db y la cuenta operativa esart_aplicacion.")
    rol = await sesion.scalar(select(Rol).where(Rol.codigo == CODIGO_ROL_ADMINISTRADOR))
    usuario = await sesion.scalar(select(Usuario).where(func.lower(Usuario.usuario) == nombre.lower()))
    administradores = await sesion.scalar(
        select(func.count())
        .select_from(UsuarioRoles)
        .join(Rol, Rol.id == UsuarioRoles.rol_id)
        .where(Rol.codigo == CODIGO_ROL_ADMINISTRADOR)
    )
    return {
        "base": identidad[0],
        "cuenta": identidad[1],
        "usuario": nombre,
        "usuario_existe": usuario is not None,
        "rol_id": rol.id if rol is not None else None,
        "rol": CODIGO_ROL_ADMINISTRADOR,
        "rol_activo": rol is not None and rol.activo,
        "administradores_asignados": administradores,
    }


def exigir_alta_posible(plan: dict) -> None:
    if plan["usuario_existe"]:
        raise AltaRechazada("El usuario ya existe. No se modifica, reactiva ni restablece su contraseña.")
    if not plan["rol_activo"]:
        raise AltaRechazada("ADMINISTRADOR no existe o está inactivo. El comando no crea ni activa roles.")
    if plan["administradores_asignados"]:
        raise AltaRechazada("Ya hay un administrador asignado; este comando es solo para el primero.")


async def insertar(sesion: AsyncSession, nombre: str, hash_contrasena: str) -> int:
    # Serializa las ejecuciones de este comando. UNIQUE protege también el nombre en otras altas.
    await sesion.execute(text("SELECT pg_advisory_xact_lock(74104,1)"))
    plan = await inspeccionar(sesion, nombre)
    exigir_alta_posible(plan)
    nuevo = Usuario(
        usuario=nombre,
        contrasena_hash=hash_contrasena,
        activo=True,
        documento_identidad=None,
        requiere_cambio_contrasena=False,
    )
    sesion.add(nuevo)
    await sesion.flush()
    sesion.add(UsuarioRoles(usuario_id=nuevo.id, rol_id=plan["rol_id"], asignado_por_id=None))
    await sesion.flush()
    # Mismo criterio de rol activo que usa el login. No abrir una sesión ni probar JWT aquí.
    from aplicacion.servicios.autenticacion import obtener_codigo_rol

    if await obtener_codigo_rol(sesion, nuevo.id) != CODIGO_ROL_ADMINISTRADOR:
        raise AltaRechazada("No se pudo verificar la asignación del rol; se revierte el alta.")
    return nuevo.id


async def ejecutar(nombre: str, *, aplicar: bool = False, verificar: bool = False) -> dict:
    nombre = validar_nombre(nombre)
    motor = obtener_motor_base_datos()
    async with motor.connect() as conexion, conexion.begin():
        await conexion.execute(text("SET TRANSACTION READ ONLY"))
        async with AsyncSession(bind=conexion) as sesion:
            plan = await inspeccionar(sesion, nombre)
            if verificar:
                if not plan["usuario_existe"]:
                    raise AltaRechazada("No existe el usuario indicado.")
                usuario = await sesion.scalar(
                    select(Usuario).where(func.lower(Usuario.usuario) == nombre.lower())
                )
                clave = leer_contrasena(confirmar=False)
                try:
                    coincide = verificar_contrasena(clave, usuario.contrasena_hash or "")
                finally:
                    del clave
                return {
                    **plan,
                    "modo": "solo_lectura",
                    "contrasena_coincide": coincide,
                    "usuario_activo": usuario.activo,
                    "advertencia": "No prueba HTTP/JWT ni crea una sesión.",
                }
    if not aplicar:
        return {**plan, "modo": "plan_sin_inserciones"}
    exigir_alta_posible(plan)
    clave = leer_contrasena(confirmar=True)
    try:
        hash_contrasena = generar_hash_contrasena(clave)
        if not verificar_contrasena(clave, hash_contrasena):
            raise AltaRechazada("No se pudo comprobar el hash generado.")
    finally:
        del clave
    # Revalidar en otra transacción tras la entrada interactiva; no mantener bloqueos al escribir.
    async with motor.connect() as conexion:
        conexion = await conexion.execution_options(isolation_level="SERIALIZABLE")
        async with conexion.begin(), AsyncSession(bind=conexion) as sesion:
            identificador = await insertar(sesion, nombre, hash_contrasena)
    return {
        "modo": "creado",
        "base": "esart_db",
        "usuario": nombre,
        "id": str(identificador),
        "rol": CODIGO_ROL_ADMINISTRADOR,
        "activo": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usuario", required=True)
    modos = parser.add_mutually_exclusive_group()
    modos.add_argument("--aplicar", action="store_true", help="Solo tras aprobación explícita")
    modos.add_argument("--verificar-contrasena", action="store_true", help="Comparar sin escribir ni login")
    args = parser.parse_args()

    async def principal():
        try:
            return await ejecutar(args.usuario, aplicar=args.aplicar, verificar=args.verificar_contrasena)
        finally:
            await cerrar_motor_base_datos()

    try:
        resultado = asyncio.run(principal())
        print(json.dumps(resultado, ensure_ascii=True))
        return 1 if resultado.get("contrasena_coincide") is False else 0
    except AltaRechazada as error:
        print(str(error))
    except (EOFError, KeyboardInterrupt):
        print("Operación cancelada; no se confirmó el alta.")
    except Exception as error:
        # No imprimir SQL, parámetros, hashes ni detalles del controlador.
        print("Operación detenida: " + type(error).__name__ + "; no se confirmó el alta.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
