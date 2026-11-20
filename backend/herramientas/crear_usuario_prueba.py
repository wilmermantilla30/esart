"""
Crea, de forma idempotente, una cuenta de PRUEBA con rol USUARIO (sin permisos administrativos).

Uso, desde backend/:
    python -m herramientas.crear_usuario_prueba                       # solo comprueba (no escribe)
    python -m herramientas.crear_usuario_prueba --ejecutar            # crea la cuenta

- Solo desarrollo local (ENTORNO=desarrollo, base esart_db, rol esart_aplicacion).
- Si el usuario ya existe (sin distinguir mayúsculas) no modifica nada.
- La contraseña temporal se genera con `secrets`, cumple la política (>=10, letras y números),
  se guarda SOLO como hash bcrypt (generar_hash_contrasena) y se muestra UNA vez en esta terminal.
  No se escribe en archivos ni en la auditoría.
- requiere_cambio_contrasena=TRUE: el primer ingreso pide cambiarla y luego vincular TOTP.
- documento_identidad queda NULL: no hay militares activos sin usuario y la cuenta de prueba no
  debe apropiarse de la cédula de una persona real.
- Una sola transacción: usuario + esart.usuario_roles + auditoría USUARIO_CREADO; si algo falla,
  no queda nada.
"""

import argparse
import asyncio
import secrets
import string

from sqlalchemy import func, select, text

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import Rol, Usuario, UsuarioRoles
from aplicacion.seguridad.contrasenas import generar_hash_contrasena, verificar_contrasena
from aplicacion.servicios import administracion_usuarios as servicio
from herramientas.administrar_usuarios import operador_del_sistema

ROL_PRUEBA = "USUARIO"


def generar_contrasena(longitud: int = 16) -> str:
    alfabeto = string.ascii_letters + string.digits
    while True:
        valor = "".join(secrets.choice(alfabeto) for _ in range(longitud))
        if any(c.isalpha() for c in valor) and any(c.isdigit() for c in valor):
            servicio.validar_contrasena_nueva(valor)
            return valor


async def crear(nombre: str, ejecutar: bool) -> int:
    if obtener_configuracion().entorno != "desarrollo":
        print("Rechazado: solo se admite ENTORNO=desarrollo.")
        return 1
    try:
        async with obtener_fabrica_sesiones()() as sesion:
            base, rol_bd = (await sesion.execute(text("SELECT current_database(), current_user"))).one()
            if (base, rol_bd) != ("esart_db", "esart_aplicacion"):
                print("Rechazado: la conexión no apunta a esart_db como esart_aplicacion.")
                return 1
            existente = await sesion.scalar(
                select(Usuario).where(func.lower(Usuario.usuario) == nombre.lower())
            )
            if existente is not None:
                print(f"Sin cambios: el usuario {existente.usuario} ya existe (id {existente.id}).")
                return 0
            rol = await sesion.scalar(select(Rol).where(Rol.codigo == ROL_PRUEBA, Rol.activo.is_(True)))
            if rol is None:
                print(f"Rechazado: el rol {ROL_PRUEBA} no existe o está inactivo.")
                return 1
            if not ejecutar:
                await sesion.rollback()
                print(f"Comprobación correcta: se crearía {nombre} con rol {ROL_PRUEBA}. Use --ejecutar.")
                return 0

            contrasena = generar_contrasena()
            hash_ = await asyncio.to_thread(generar_hash_contrasena, contrasena)
            if not await asyncio.to_thread(verificar_contrasena, contrasena, hash_):
                raise RuntimeError("El hash generado no verifica; no se crea la cuenta.")
            usuario = Usuario(
                usuario=nombre,
                contrasena_hash=hash_,
                documento_identidad=None,
                activo=True,
                requiere_cambio_contrasena=True,
            )
            sesion.add(usuario)
            await sesion.flush()
            sesion.add(UsuarioRoles(usuario_id=usuario.id, rol_id=rol.id))
            # _auditar confirma la transacción completa (usuario + rol + evento).
            await servicio._auditar(
                sesion,
                servicio.auditoria.USUARIO_CREADO,
                servicio.Actor.consola(operador_del_sistema()),
                {"usuario_creado": nombre, "rol": ROL_PRUEBA, "cuenta_de_prueba": True},
            )
            usuario_id = usuario.id
        # Comprobación independiente: otra conexión solo ve datos confirmados (COMMIT efectivo).
        async with obtener_fabrica_sesiones()() as verificacion:
            await verificacion.execute(text("SET TRANSACTION READ ONLY"))
            fila = (
                await verificacion.execute(
                    text(
                        "SELECT u.activo, u.requiere_cambio_contrasena, u.contrasena_hash LIKE '$2%',"
                        " array_agg(r.codigo ORDER BY r.codigo),"
                        " (SELECT count(*) FROM esart.auditoria_eventos e"
                        "   WHERE e.accion = 'USUARIO_CREADO' AND e.detalle->>'usuario_creado' = :n)"
                        " FROM esart_ref.usuarios u"
                        " JOIN esart.usuario_roles ur ON ur.usuario_id = u.id"
                        " JOIN esart.roles r ON r.id = ur.rol_id"
                        " WHERE u.id = :id GROUP BY u.id"
                    ),
                    {"id": usuario_id, "n": nombre},
                )
            ).one_or_none()
            await verificacion.rollback()
        if fila is None or not (fila[0] and fila[1] and fila[2]) or fila[3] != [ROL_PRUEBA] or fila[4] < 1:
            print("ERROR: la verificación posterior no encontró la cuenta confirmada como se esperaba.")
            return 1
        print(f"Confirmado en PostgreSQL: {nombre} (id {usuario_id}), rol {ROL_PRUEBA}, activo,")
        print("hash bcrypt, cambio de contraseña obligatorio y auditoría USUARIO_CREADO.")
        print("Contraseña temporal (se muestra solo esta vez; cámbiela al entrar):")
        print(f"    {contrasena}")
        return 0
    finally:
        await cerrar_motor_base_datos()


def main() -> None:
    analizador = argparse.ArgumentParser(prog="python -m herramientas.crear_usuario_prueba")
    analizador.add_argument("--usuario", default="prueba.esar")
    analizador.add_argument(
        "--ejecutar", action="store_true", help="Crea la cuenta (sin esto, solo comprueba)."
    )
    argumentos = analizador.parse_args()
    raise SystemExit(asyncio.run(crear(argumentos.usuario.strip(), argumentos.ejecutar)))


if __name__ == "__main__":
    main()
