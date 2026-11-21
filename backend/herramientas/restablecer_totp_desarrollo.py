"""Inspecciona o restablece un factor TOTP únicamente en PostgreSQL local de desarrollo."""

import argparse
import asyncio
import getpass
import ipaddress
import json

import pyotp
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import make_url

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import Rol, Usuario, UsuarioRoles
from aplicacion.modelos.seguridad import SesionUsuario
from aplicacion.modelos.totp import (
    AuditoriaSeguridad,
    CambioSeguridad,
    DesafioTotp,
    RecuperacionTotp,
    UsuarioTotp,
)
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.seguridad_login import reloj_servidor
from aplicacion.servicios.totp import TotpService


def argumentos_cli():
    parser = argparse.ArgumentParser(description="Recuperación TOTP local de ESART (solo desarrollo).")
    subparsers = parser.add_subparsers(dest="comando", required=True)
    for comando in ("inspeccionar", "restablecer"):
        sub = subparsers.add_parser(comando)
        sub.add_argument("--usuario-id", required=True, type=int)
        if comando == "restablecer":
            sub.add_argument("--confirmar-id", required=True, type=int)
            sub.add_argument("--justificacion", required=True)
    return parser.parse_args()


def validar_destino(cfg):
    """Falla cerrado antes de abrir una sesión si configuración no apunta a dev local."""
    url = make_url(cfg.url_base_datos.get_secret_value())
    if not (
        cfg.entorno == "desarrollo"
        and url.host in {"localhost", "127.0.0.1", "::1"}
        and url.database == "esart_db"
        and url.username == "esart_aplicacion"
    ):
        raise ValueError("Recuperación cancelada: solo se permite desarrollo local en esart_db.")
    return url


async def comprobar_conexion(sesion):
    fila = (
        await sesion.execute(
            text(
                "SELECT current_database() AS base, current_user AS rol, "
                "inet_server_addr()::text AS servidor, inet_server_port() AS puerto"
            )
        )
    ).mappings().one()
    servidor = str(ipaddress.ip_interface(fila["servidor"]).ip) if fila["servidor"] else None
    if (
        fila["base"] != "esart_db"
        or fila["rol"] != "esart_aplicacion"
        or servidor not in {"127.0.0.1", "::1"}
    ):
        raise ValueError("Recuperación cancelada: PostgreSQL no confirma el destino local de desarrollo.")
    return {"base": fila["base"], "rol": fila["rol"], "servidor": servidor, "puerto": fila["puerto"]}


async def inspeccionar(sesion, usuario_id):
    cfg = obtener_configuracion()
    usuario = await sesion.scalar(select(Usuario).where(Usuario.id == usuario_id))
    if usuario is None:
        raise ValueError(f"No existe el usuario id={usuario_id}.")
    if usuario.usuario.lower() != cfg.admin_usuario.lower():
        raise ValueError("El ID indicado no coincide con ADMIN_USUARIO del entorno de desarrollo.")
    roles = list(
        (
            await sesion.execute(
                select(Rol.codigo)
                .join(UsuarioRoles, UsuarioRoles.rol_id == Rol.id)
                .where(UsuarioRoles.usuario_id == usuario_id, Rol.activo.is_(True))
                .order_by(Rol.codigo)
            )
        ).scalars()
    )
    if "ADMINISTRADOR" not in roles:
        raise ValueError("El usuario configurado no tiene el rol ADMINISTRADOR activo.")
    factor = await sesion.scalar(select(UsuarioTotp).where(UsuarioTotp.usuario_id == usuario_id))
    recuperaciones = (
        await sesion.execute(
            select(RecuperacionTotp.id, RecuperacionTotp.usado_en, RecuperacionTotp.revocado_en)
            .where(RecuperacionTotp.usuario_id == usuario_id)
            .order_by(RecuperacionTotp.id)
        )
    ).mappings().all()
    desafios = (
        await sesion.execute(
            select(DesafioTotp.id, DesafioTotp.estado, DesafioTotp.expira_en)
            .where(DesafioTotp.usuario_id == usuario_id, DesafioTotp.estado.in_(["PENDIENTE", "VERIFICADO"]))
            .order_by(DesafioTotp.creado_en)
        )
    ).mappings().all()
    sesiones = (
        await sesion.execute(
            select(SesionUsuario.id, SesionUsuario.fecha_inicio, SesionUsuario.fecha_ultima_actividad)
            .where(SesionUsuario.usuario_id == usuario_id, SesionUsuario.revocada.is_(False))
            .order_by(SesionUsuario.fecha_inicio)
        )
    ).mappings().all()
    total_auditoria = await sesion.scalar(
        select(func.count())
        .select_from(AuditoriaSeguridad)
        .where(AuditoriaSeguridad.usuario_id == usuario_id)
    )
    evento_recuperacion = (
        await sesion.execute(
            select(
                AuditoriaSeguridad.accion,
                AuditoriaSeguridad.actor_tipo,
                AuditoriaSeguridad.resultado,
                AuditoriaSeguridad.motivo,
                AuditoriaSeguridad.fecha_evento,
            )
            .where(
                AuditoriaSeguridad.usuario_id == usuario_id,
                AuditoriaSeguridad.accion == "TOTP_RECUPERADO_DESARROLLO",
            )
            .order_by(AuditoriaSeguridad.fecha_evento.desc())
            .limit(1)
        )
    ).mappings().first()
    return {
        "usuario": {
            "id": usuario.id,
            "nombre": usuario.usuario,
            "activo": usuario.activo,
            "contrasena_configurada": bool(usuario.contrasena_hash),
            "requiere_cambio_contrasena": usuario.requiere_cambio_contrasena,
            "roles_activos": roles,
        },
        "seguridad.usuario_totp": {
            "registro_id": factor.id if factor else None,
            "estado": factor.estado if factor else "SIN_FILA",
            "activado_en": factor.activado_en if factor else None,
            "expira_configuracion_en": factor.expira_configuracion_en if factor else None,
            "revocado_en": factor.revocado_en if factor else None,
        },
        "seguridad.totp_recuperacion": {
            "registros": [
                {"id": r["id"], "usado": r["usado_en"] is not None, "revocado": r["revocado_en"] is not None}
                for r in recuperaciones
            ]
        },
        "seguridad.desafios": {
            "registros_afectables": [
                {"estado": r["estado"], "expira_en": r["expira_en"]} for r in desafios
            ]
        },
        "esart.sesiones_usuario": {"registros_abiertos": len(sesiones)},
        "seguridad.auditoria": {
            "eventos_historial_conservados": total_auditoria,
            "ultimo_evento_recuperacion": dict(evento_recuperacion) if evento_recuperacion else None,
        },
    }


async def ejecutar(args):
    cfg = obtener_configuracion()
    url = validar_destino(cfg)
    if args.comando == "restablecer" and args.confirmar_id != args.usuario_id:
        raise ValueError("La confirmación debe repetir exactamente el ID del usuario.")
    razon = args.justificacion.strip() if args.comando == "restablecer" else None
    if razon is not None and (len(razon) < 12 or len(razon) > 1000):
        raise ValueError("La justificación debe tener entre 12 y 1000 caracteres no blancos.")

    async with obtener_fabrica_sesiones()() as sesion:
        await sesion.execute(text("SET TRANSACTION READ ONLY"))
        conexion = await comprobar_conexion(sesion)
        actual = await inspeccionar(sesion, args.usuario_id)
        if not cfg.totp_habilitado or not cfg.totp_clave_cifrado:
            raise ValueError(
                "TOTP no está habilitado o falta su clave de cifrado; "
                "no se puede garantizar el reingreso."
            )
        preflight = TotpService(sesion)
        await preflight.preparar()
        await preflight.politica("LOGIN_TOTP")
        await preflight.politica("DESBLOQUEO_TOTP")
        await sesion.rollback()

        salida = {
            "entorno": cfg.entorno,
            "conexion": {"base": url.database, "rol": url.username, **conexion},
            "totp_habilitado": cfg.totp_habilitado,
            "politicas_login_y_desbloqueo": "activas y consultables",
            "estado_actual": actual,
        }
        if args.comando == "inspeccionar":
            salida["operacion"] = "solo_lectura"
            print(json.dumps(salida, ensure_ascii=False, default=str, indent=2))
            return

        # Segunda conexión/transacción con nuevas verificaciones; ninguna escritura empieza
        # hasta confirmar otra vez configuración, servidor, usuario y estado TOTP.
        if not cfg.totp_habilitado or not cfg.totp_clave_cifrado:
            raise ValueError("TOTP no está habilitado o falta la clave de cifrado; se cancela sin cambios.")
        conexion = await comprobar_conexion(sesion)
        servicio = TotpService(sesion)
        await servicio.preparar()
        await servicio.politica("LOGIN_TOTP")
        await servicio.politica("DESBLOQUEO_TOTP")
        usuario = await servicio.usuario(args.usuario_id)
        if usuario.usuario.lower() != cfg.admin_usuario.lower():
            raise ValueError("El usuario ya no coincide con ADMIN_USUARIO; se cancela.")
        rol_admin = await sesion.scalar(
            select(Rol.id)
            .join(UsuarioRoles, UsuarioRoles.rol_id == Rol.id)
            .where(
                UsuarioRoles.usuario_id == args.usuario_id,
                Rol.codigo == "ADMINISTRADOR",
                Rol.activo.is_(True),
            )
            .limit(1)
        )
        if rol_admin is None:
            raise ValueError("El usuario ya no tiene rol ADMINISTRADOR activo; se cancela.")
        factor = await servicio.registro(args.usuario_id)
        if not factor or factor.estado != "ACTIVO":
            raise ErrorAplicacion(
                409,
                "TOTP_NO_ACTIVO",
                "El factor ya no está activo; se cancela sin cambios.",
            )

        ahora = await reloj_servidor(sesion)
        estado_anterior = factor.estado
        # Sobrescribe el cifrado anterior; este secreto aleatorio nunca se devuelve ni se imprime.
        factor.secreto_cifrado = servicio.cifrar(args.usuario_id, pyotp.random_base32())
        factor.estado = "PENDIENTE"
        factor.activado_en = None
        factor.expira_configuracion_en = None
        factor.revocado_en = ahora
        factor.ultimo_intervalo_aceptado = None
        factor.actualizado_en = ahora
        await sesion.execute(
            update(RecuperacionTotp)
            .where(RecuperacionTotp.usuario_id == args.usuario_id, RecuperacionTotp.revocado_en.is_(None))
            .values(revocado_en=ahora)
        )
        await sesion.execute(
            update(DesafioTotp)
            .where(
                DesafioTotp.usuario_id == args.usuario_id,
                DesafioTotp.estado.in_(["PENDIENTE", "VERIFICADO"]),
            )
            .values(estado="CANCELADO")
        )
        await sesion.execute(
            update(SesionUsuario)
            .where(SesionUsuario.usuario_id == args.usuario_id, SesionUsuario.revocada.is_(False))
            .values(revocada=True, fecha_revocacion=ahora)
        )
        evento = await servicio.auditar(
            args.usuario_id, "TOTP_RECUPERADO_DESARROLLO", "CORRECTO", "127.0.0.1"
        )
        evento.actor_tipo = "ADMIN_DESARROLLO"
        evento.recurso_tipo = "USUARIO"
        evento.recurso_id = str(args.usuario_id)
        evento.motivo = razon
        evento.datos = {
            "operador_sistema": getpass.getuser(),
            "entorno": cfg.entorno,
            "base_datos": url.database,
        }
        await sesion.flush()
        sesion.add(
            CambioSeguridad(
                auditoria_id=evento.id,
                campo="estado_totp",
                valor_anterior=estado_anterior,
                valor_nuevo="PENDIENTE",
            )
        )
        await sesion.commit()
        salida["resultado"] = {
            "usuario_id": args.usuario_id,
            "estado_totp": "PENDIENTE (PENDIENTE_CONFIGURACION)",
            "password_roles_permisos_academia": "sin cambios",
            "auditoria": "evento y cambio append-only registrados; historial conservado",
        }
        print(json.dumps(salida, ensure_ascii=False, default=str, indent=2))


async def principal(args):
    try:
        await ejecutar(args)
        return 0
    except (ValueError, ErrorAplicacion) as error:
        mensaje = error.mensaje if isinstance(error, ErrorAplicacion) else str(error)
        print(json.dumps({"operacion": "cancelada_sin_confirmar", "motivo": mensaje}, ensure_ascii=False))
        return 1
    finally:
        await cerrar_motor_base_datos()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal(argumentos_cli())))
