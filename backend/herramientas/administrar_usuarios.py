"""
Administración de usuarios por consola (HU-10). Lo mismo se hace desde la web, en
Administración > Gestión de usuarios; la consola sirve cuando no hay nadie que pueda entrar.

Uso, desde backend/:
    python -m herramientas.administrar_usuarios listar [--buscar texto]
    python -m herramientas.administrar_usuarios crear --usuario nombre.apellido --rol USUARIO
        --cedula 1234567890
    python -m herramientas.administrar_usuarios desbloquear --usuario nombre.apellido
    python -m herramientas.administrar_usuarios desbloquear-ip --ip 10.1.2.3

- La cédula es obligatoria: el militar debe estar en Personal militar.
- La contraseña es temporal: el usuario debe cambiarla la primera vez que entre.
- La contraseña se pide con entrada OCULTA dos veces (nunca como argumento: quedaría en el
  historial de la terminal). Si no hay terminal, se rechaza.
- Usa la conexión de la API (.env, cuenta esart_aplicacion) y queda en la auditoría como
  "consola", con el usuario del sistema operativo que lo ejecutó.
"""

import argparse
import asyncio
import getpass
import sys

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import administracion_usuarios as servicio
from herramientas.crear_administrador_inicial import AltaRechazada, leer_contrasena

ROLES = ("USUARIO", "ADMINISTRADOR")


def operador_del_sistema() -> str:
    """Usuario del sistema operativo que ejecuta el comando (para la auditoría)."""
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return "desconocido"


def construir_argumentos() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="python -m herramientas.administrar_usuarios", description="Administración de usuarios de ESART."
    )
    comandos = analizador.add_subparsers(dest="comando", required=True)

    listar = comandos.add_parser("listar", help="Usuarios con su rol y estado de bloqueo.")
    listar.add_argument("--buscar", help="Parte del nombre de usuario.")

    crear = comandos.add_parser("crear", help="Crea un usuario con un rol (la contraseña se pide oculta).")
    crear.add_argument("--usuario", required=True, help="Nombre de usuario, por ejemplo jperez.esart")
    crear.add_argument("--rol", required=True, choices=ROLES)
    crear.add_argument("--cedula", required=True, help="Cédula del militar (debe estar en Personal militar).")

    desbloquear = comandos.add_parser(
        "desbloquear", help="Quita el bloqueo por intentos fallidos de una cuenta."
    )
    desbloquear.add_argument("--usuario", required=True)

    desbloquear_ip = comandos.add_parser(
        "desbloquear-ip", help="Pone en cero los intentos fallidos de una IP."
    )
    desbloquear_ip.add_argument("--ip", required=True)
    return analizador


def imprimir_usuarios(usuarios: list[servicio.EstadoUsuario]) -> None:
    if not usuarios:
        print("No hay usuarios.")
        return
    print(f"{'USUARIO':24} {'ROL':14} {'ACTIVO':7} {'INTENTOS':9} ESTADO")
    for u in usuarios:
        estado = f"BLOQUEADO hasta {u.bloqueado_hasta:%Y-%m-%d %H:%M}" if u.bloqueado else "normal"
        print(
            f"{u.usuario:24} {u.rol or 'sin rol':14} {'sí' if u.activo else 'no':7} "
            f"{u.intentos_fallidos:<9} {estado}"
        )


async def ejecutar(argumentos: argparse.Namespace) -> None:
    actor = servicio.Actor.consola(operador_del_sistema())
    async with obtener_fabrica_sesiones()() as sesion:
        if argumentos.comando == "listar":
            imprimir_usuarios(await servicio.listar_usuarios(sesion, argumentos.buscar))

        elif argumentos.comando == "crear":
            if argumentos.rol == "ADMINISTRADOR":
                respuesta = input(
                    f"Va a crear '{argumentos.usuario}' con rol ADMINISTRADOR (todos los permisos). "
                    "¿Continuar? (s/N): "
                )
                if respuesta.strip().lower() not in ("s", "si", "sí"):
                    print("Cancelado. No se creó nada.")
                    return
            contrasena = leer_contrasena(confirmar=True)
            usuario_id = await servicio.crear_usuario(
                sesion,
                nombre_usuario=argumentos.usuario,
                codigo_rol=argumentos.rol,
                contrasena=contrasena,
                documento_identidad=argumentos.cedula,
                actor=actor,
            )
            print(
                f"Usuario '{argumentos.usuario}' creado (id {usuario_id}) con rol {argumentos.rol}. "
                "Deberá cambiar la contraseña al entrar."
            )

        elif argumentos.comando == "desbloquear":
            estado = await servicio.desbloquear_usuario(
                sesion, nombre_usuario=argumentos.usuario, actor=actor
            )
            print(f"Usuario '{estado.usuario}' desbloqueado. Intentos fallidos: {estado.intentos_fallidos}.")

        elif argumentos.comando == "desbloquear-ip":
            anteriores = await servicio.desbloquear_ip(sesion, ip=argumentos.ip, actor=actor)
            print(f"IP {argumentos.ip}: contador puesto en cero (tenía {anteriores} intento(s)).")


async def principal(argumentos: argparse.Namespace) -> int:
    try:
        await ejecutar(argumentos)
        return 0
    except ErrorAplicacion as error:
        print(f"No se pudo: {error.mensaje}", file=sys.stderr)
        return 1
    except AltaRechazada as error:
        print(f"No se pudo: {error}", file=sys.stderr)
        return 1
    finally:
        await cerrar_motor_base_datos()


if __name__ == "__main__":
    sys.exit(asyncio.run(principal(construir_argumentos().parse_args())))
