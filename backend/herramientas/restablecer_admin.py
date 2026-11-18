"""Restablecimiento local explícito de admin.esart/id=1; sin endpoint ni migraciones."""

import argparse
import asyncio
import logging
import os

from sqlalchemy import select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from aplicacion.base_datos.configuracion import opciones_tls_local
from aplicacion.modelos import Rol, Usuario, UsuarioRoles
from aplicacion.seguridad.contrasenas import generar_hash_contrasena, verificar_contrasena
from herramientas.crear_administrador_inicial import AltaRechazada, leer_contrasena

USUARIO = "admin.esart"
ID_USUARIO = 1
CONFIRMACION = "RESTABLECER admin.esart ID 1 EN esart_db"


class RestablecimientoRechazado(ValueError):
    """Mensaje operativo sin credenciales ni contenido del controlador."""


def validar_url_administrativa(url: str) -> None:
    try:
        destino = make_url(url)
        valido = (
            destino.drivername == "postgresql+asyncpg"
            and destino.database == "esart_db"
            and destino.username
            and destino.username != "esart_aplicacion"
            and destino.host
        )
    except Exception:
        valido = False
    if not valido:
        raise RestablecimientoRechazado("Se requiere una URL administrativa asyncpg de esart_db.")


async def comprobar_operador(sesion: AsyncSession) -> None:
    operador = (
        (
            await sesion.execute(
                text("""
      SELECT current_database() base,current_user operador,session_user autenticado,
             r.rolsuper superusuario,pg_get_userbyid(t.relowner) propietario
      FROM pg_roles r CROSS JOIN pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
      WHERE r.rolname=current_user AND n.nspname='esart_ref' AND t.relname='usuarios'
    """)
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        operador is None
        or operador["base"] != "esart_db"
        or operador["operador"] == "esart_aplicacion"
        or operador["autenticado"] != operador["operador"]
        or not (operador["superusuario"] or operador["propietario"] == operador["operador"])
    ):
        raise RestablecimientoRechazado(
            "Se exige sesión directa del propietario o superusuario; no SET ROLE."
        )


async def inspeccionar(sesion: AsyncSession, *, bloquear: bool = False) -> dict:
    await comprobar_operador(sesion)
    automatismos = await sesion.scalar(
        text("""
      SELECT EXISTS(SELECT 1 FROM pg_trigger
                    WHERE tgrelid='esart_ref.usuarios'::regclass AND NOT tgisinternal AND tgenabled<>'D')
          OR EXISTS(SELECT 1 FROM pg_rewrite WHERE ev_class='esart_ref.usuarios'::regclass)
    """)
    )
    if automatismos:
        raise RestablecimientoRechazado(
            "Hay triggers/reglas en usuarios que requieren revisión; no se deshabilitan."
        )
    tabla = Usuario.__table__
    consulta = select(tabla).where(tabla.c.id == ID_USUARIO)
    if bloquear:
        consulta = consulta.with_for_update()
    fila = (await sesion.execute(consulta)).mappings().one_or_none()
    if fila is None or fila["usuario"] != USUARIO or not fila["activo"]:
        raise RestablecimientoRechazado("La identidad id=1/admin.esart no existe o no está activa.")
    consulta_roles = (
        select(Rol.id, Rol.codigo, Rol.activo)
        .join(UsuarioRoles, UsuarioRoles.rol_id == Rol.id)
        .where(UsuarioRoles.usuario_id == ID_USUARIO)
    )
    if bloquear:
        consulta_roles = consulta_roles.with_for_update(read=True)
    roles = (await sesion.execute(consulta_roles)).mappings().all()
    if not any(r["codigo"] == "ADMINISTRADOR" and r["activo"] for r in roles):
        raise RestablecimientoRechazado("El usuario no tiene asignado ADMINISTRADOR activo.")
    return dict(fila)


def confirmar_operacion() -> None:
    if input(f"Para autorizar la actualización escriba exactamente {CONFIRMACION}: ") != CONFIRMACION:
        raise RestablecimientoRechazado("Confirmación incorrecta; no se modifica PostgreSQL.")


async def actualizar(sesion: AsyncSession, nueva: str) -> None:
    antes = await inspeccionar(sesion, bloquear=True)
    hash_nuevo = generar_hash_contrasena(nueva)
    # Core evita enviar otras columnas del ORM: solo una columna y una identidad fija.
    tabla = Usuario.__table__
    resultado = await sesion.execute(
        update(tabla)
        .where(tabla.c.id == ID_USUARIO, tabla.c.usuario == USUARIO, tabla.c.activo.is_(True))
        .values(contrasena_hash=hash_nuevo)
    )
    if resultado.rowcount != 1:
        raise RestablecimientoRechazado("No se actualizó exactamente una fila; se revierte.")
    despues = (await sesion.execute(select(tabla).where(tabla.c.id == ID_USUARIO))).mappings().one()
    if any(despues[c] != antes[c] for c in antes if c != "contrasena_hash"):
        raise RestablecimientoRechazado("Cambió otro campo, posiblemente por un trigger; se revierte.")
    if despues["contrasena_hash"] != hash_nuevo or not verificar_contrasena(
        nueva, despues["contrasena_hash"]
    ):
        raise RestablecimientoRechazado("La contraseña no coincide con el hash releído; se revierte.")
    # El contexto externo confirma solo tras superar la relectura. No abre sesiones JWT.


async def ejecutar(url: str, *, aplicar: bool = False) -> None:
    validar_url_administrativa(url)
    motor = create_async_engine(
        url, poolclass=NullPool, echo=False, hide_parameters=True, connect_args=opciones_tls_local(url)
    )
    try:
        async with motor.connect() as conexion, conexion.begin():
            await conexion.execute(text("SET TRANSACTION READ ONLY"))
            async with AsyncSession(bind=conexion) as sesion:
                await inspeccionar(sesion)
        print("Plan verificado: esart_db / esart_ref.usuarios / id=1 / admin.esart / ADMINISTRADOR activo.")
        if not aplicar:
            print("Solo lectura. No se solicitó contraseña ni se actualizó ningún registro.")
            return
        nueva = leer_contrasena(confirmar=True)
        try:
            confirmar_operacion()
            async with motor.connect() as conexion, conexion.begin(), AsyncSession(bind=conexion) as sesion:
                await actualizar(sesion, nueva)
            print("COMMIT confirmado: contraseña restablecida y comprobada; los demás campos se conservaron.")
        finally:
            del nueva
    finally:
        await motor.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aplicar", action="store_true", help="Requiere aprobación previa y confirmación escrita"
    )
    args = parser.parse_args()
    # Comando de terminal independiente: impedir trazas SQL/debug de filas con hashes.
    logging.disable(logging.CRITICAL)
    url = os.environ.get("ESART_ADMIN_URL")
    if not url:
        print("Falta ESART_ADMIN_URL en esta sesión administrativa; no se utiliza backend/.env.")
        return 1
    try:
        asyncio.run(ejecutar(url, aplicar=args.aplicar))
        return 0
    except (RestablecimientoRechazado, AltaRechazada) as error:
        print(str(error))
    except (EOFError, KeyboardInterrupt):
        print("Operación cancelada; no se confirmó la actualización.")
    except Exception as error:
        print("Operación detenida: " + type(error).__name__ + "; no se confirmó la actualización.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
