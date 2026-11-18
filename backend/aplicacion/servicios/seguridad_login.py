"""Estado persistente 3/7/3h. Todos los rechazos se confirman antes de devolver el error público."""

import hashlib
import hmac
import ipaddress
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy import insert as insertar
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import IntentoInicioSesion, Usuario
from aplicacion.modelos.seguridad import AuditoriaAcceso, EstadoAccesoAnonimo, LimiteInicioIP
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.captcha import VerificadorCaptcha

HORAS_BLOQUEO = 3
registrador = logging.getLogger(__name__)


async def reloj_servidor(sesion: AsyncSession) -> datetime:
    return await sesion.scalar(select(func.clock_timestamp()))


def seudonimo(dominio: str, valor: str) -> str:
    raiz = obtener_configuracion().jwt_clave_secreta.get_secret_value().encode()
    secreto = hmac.new(raiz, b"ESART/SEGURIDAD/SEUDONIMOS/V1", hashlib.sha256).digest()
    return hmac.new(secreto, (dominio + ":" + valor).encode(), hashlib.sha256).hexdigest()


def ip_canonica(valor: str | None) -> str | None:
    try:
        direccion = ipaddress.ip_address(valor) if valor else None
        if isinstance(direccion, ipaddress.IPv6Address) and direccion.ipv4_mapped:
            direccion = direccion.ipv4_mapped
        return str(direccion) if direccion else None
    except ValueError:
        return None


@dataclass
class ContextoIntento:
    clave: str
    ip: str | None
    ahora: datetime | None
    usuario: Usuario | None = None
    estado: object = None
    captcha_requerido: bool = False
    captcha_validado: bool | None = None
    expirado: bool = False
    intento_registrado: IntentoInicioSesion | None = None


async def registrar(
    sesion: AsyncSession, c: ContextoIntento, *, exito: bool, motivo: str | None, evento: str
) -> None:
    intento = IntentoInicioSesion(
        nombre_usuario_intentado=c.clave,
        usuario_id=c.usuario.id if c.usuario else None,
        direccion_ip=c.ip,
        exitoso=exito,
        motivo_fallo=motivo,
        fecha=c.ahora,
        captcha_requerido=c.captcha_requerido,
        captcha_validado=c.captcha_validado,
    )
    sesion.add(intento)
    await sesion.flush()
    c.intento_registrado = intento
    # Campos p0003 explícitos: no enviar columnas nuevas de CAPTCHA antes de aprobar p0004.
    await sesion.execute(
        insertar(AuditoriaAcceso.__table__)
        .inline()
        .values(intento_id=intento.id, evento=evento, fecha=c.ahora)
    )
    if c.expirado:
        await sesion.execute(
            insertar(AuditoriaAcceso.__table__)
            .inline()
            .values(intento_id=intento.id, evento="BLOQUEO_VENCIDO", fecha=c.ahora)
        )


async def rechazar(sesion: AsyncSession, c: ContextoIntento, motivo: str, *, contar: bool = True) -> None:
    estado = c.estado
    if contar:
        estado.intentos_fallidos_consecutivos = min(7, estado.intentos_fallidos_consecutivos + 1)
        if estado.intentos_fallidos_consecutivos == 7:
            estado.bloqueado_hasta = c.ahora + timedelta(hours=HORAS_BLOQUEO)
    bloqueado = estado.bloqueado_hasta is not None and estado.bloqueado_hasta > c.ahora
    await registrar(
        sesion,
        c,
        exito=False,
        motivo=motivo,
        evento="CUENTA_BLOQUEADA" if contar and bloqueado else "LOGIN_RECHAZADO",
    )
    if obtener_configuracion().totp_habilitado:
        from aplicacion.servicios.totp import TotpService

        try:
            # La auditoría principal ya se escribió arriba y sigue siendo obligatoria.
            # La copia adicional TOTP no puede revertir contador/bloqueo si su esquema falla.
            async with sesion.begin_nested():
                await TotpService(sesion).auditar(
                    c.usuario.id if c.usuario else None,
                    "CUENTA_BLOQUEADA" if contar and bloqueado else "LOGIN_FALLIDO",
                    "DENEGADO",
                    c.ip,
                )
                await sesion.flush()
        except DBAPIError:
            registrador.error(
                "No se pudo escribir la auditoría adicional TOTP; "
                "se conserva auditoría de acceso y control persistente del login."
            )
    detalle = {
        "captcha_requerido": not bloqueado and estado.intentos_fallidos_consecutivos >= 3,
        "acceso_temporalmente_restringido": bloqueado,
        "captcha_validado": c.captcha_validado,
    }
    if bloqueado:
        detalle.update(
            bloqueado_hasta=estado.bloqueado_hasta.isoformat(),
            ahora_servidor=c.ahora.isoformat(),
            detalles_autorizados=False,
            intentos_fallidos_consecutivos=None,
            direccion_ip=None,
            segundos_restantes=math.ceil((estado.bloqueado_hasta - c.ahora).total_seconds()),
        )
        # Solo este envío: nunca el contador acumulado ni la IP de otro intento.
        intento = c.intento_registrado
        if intento is not None:
            detalle["intento_actual"] = {
                "alcance": "ENVIO_ACTUAL",
                "envios_registrados": 1,
                "fecha": intento.fecha.isoformat(),
                "direccion_ip_observada": str(intento.direccion_ip) if intento.direccion_ip else None,
                "observacion_ip": "Peer observado por el backend; puede ser un proxy o una dirección local, "
                "no una terminal remota verificada.",
            }
    await sesion.commit()
    if bloqueado:
        # Mismo contrato para estados de usuarios existentes y nombres inexistentes.
        raise ErrorAplicacion(
            423,
            "CUENTA_BLOQUEADA",
            "Su cuenta se encuentra bloqueada temporalmente "
            "por múltiples intentos fallidos de inicio de sesión.",
            detalle,
        )
    raise ErrorAplicacion(
        401,
        "CAPTCHA_INVALIDO" if motivo == "CAPTCHA_INVALIDO" else "CREDENCIALES_INVALIDAS",
        "El CAPTCHA no es válido o ha expirado. La contraseña no se comprobó. Solicite un código nuevo."
        if motivo == "CAPTCHA_INVALIDO"
        else "No fue posible iniciar sesión. Compruebe los datos o inténtelo más tarde.",
        detalle,
    )


async def preparar(
    sesion: AsyncSession,
    nombre: str,
    ip: str | None,
    captcha_id: str | None,
    captcha_respuesta: str | None,
    verificador: VerificadorCaptcha | None,
) -> ContextoIntento:
    listo = await sesion.scalar(
        text("""
      SELECT to_regclass('esart.limites_inicio_ip') IS NOT NULL
         AND to_regclass('esart.estados_acceso_anonimos') IS NOT NULL
         AND to_regclass('esart.auditoria_acceso') IS NOT NULL
         AND EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass('esart.intentos_inicio_sesion')
                    AND attname='captcha_validado' AND NOT attisdropped)
    """)
    )
    if not listo:
        raise ErrorAplicacion(503, "SEGURIDAD_NO_DISPONIBLE", "Inicio de sesión temporalmente no disponible.")
    cfg = obtener_configuracion()
    # lower de PostgreSQL: misma normalización del índice único de nombres.
    normalizado = await sesion.scalar(select(func.lower(nombre.strip())))
    c = ContextoIntento(seudonimo("usuario", normalizado), ip_canonica(ip), None)
    clave_ip = seudonimo("ip", c.ip or "origen_no_verificable")
    # INSERT DO NOTHING + FOR UPDATE evita creación concurrente perdida en varios workers.
    await sesion.execute(
        insert(LimiteInicioIP)
        .values(clave=clave_ip, inicio=func.clock_timestamp(), intentos=0)
        .on_conflict_do_nothing(index_elements=["clave"])
    )
    limite = await sesion.scalar(
        select(LimiteInicioIP)
        .where(LimiteInicioIP.clave == clave_ip)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ahora = await reloj_servidor(sesion)
    c.ahora = ahora
    if ahora >= limite.inicio + timedelta(seconds=cfg.ventana_intentos_ip_segundos):
        limite.inicio, limite.intentos = ahora, 0
    if limite.intentos >= cfg.limite_intentos_ip:
        await registrar(sesion, c, exito=False, motivo="LIMITE_IP", evento="IP_LIMITADA")
        await sesion.commit()
        raise ErrorAplicacion(429, "INTENTOS_LIMITADOS", "Demasiados intentos. Inténtelo más tarde.")
    limite.intentos += 1
    c.usuario = await sesion.scalar(
        select(Usuario)
        .where(func.lower(Usuario.usuario) == normalizado)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if c.usuario:
        c.estado = c.usuario
    else:
        await sesion.execute(
            insert(EstadoAccesoAnonimo).values(clave=c.clave).on_conflict_do_nothing(index_elements=["clave"])
        )
        c.estado = await sesion.scalar(
            select(EstadoAccesoAnonimo)
            .where(EstadoAccesoAnonimo.clave == c.clave)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    # Leer reloj después de esperar la fila: frontera exacta y sin extender bloqueos activos.
    c.ahora = await reloj_servidor(sesion)
    if c.estado.bloqueado_hasta is not None:
        if c.ahora < c.estado.bloqueado_hasta:
            await rechazar(sesion, c, "BLOQUEO_VIGENTE", contar=False)
        c.estado.bloqueado_hasta = None
        c.estado.intentos_fallidos_consecutivos = 0
        c.expirado = True
    c.captcha_requerido = c.estado.intentos_fallidos_consecutivos >= 3
    if c.captcha_requerido:
        from aplicacion.servicios.captcha_local import CaptchaPostgres

        proveedor = verificador or CaptchaPostgres(sesion)
        try:
            c.captcha_validado = bool(
                captcha_id
                and captcha_respuesta
                and await proveedor.verificar(captcha_id, captcha_respuesta, c.clave)
            )
        except ErrorAplicacion as error:
            if error.estado_http >= 500:
                await sesion.rollback()
            raise
        except Exception:
            # Una avería no equivale a credenciales/CAPTCHA incorrectos.
            await sesion.rollback()
            raise ErrorAplicacion(
                503, "CAPTCHA_NO_DISPONIBLE", "Verificación temporalmente no disponible."
            ) from None
        if not c.captcha_validado:
            # Política TOTP: CAPTCHA rechazado no equivale a contraseña comprobada incorrecta.
            # Se conserva cuota IP, consumo del desafío, registro y auditoría, sin sumar credenciales.
            await rechazar(
                sesion,
                c,
                "CAPTCHA_INVALIDO",
                contar=False,
            )
    return c
