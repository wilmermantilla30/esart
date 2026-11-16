"""Desafíos locales, TTL 5 minutos, HMAC y consumo bajo bloqueo PostgreSQL."""

import asyncio
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos.seguridad import AuditoriaAcceso, DesafioCaptcha, LimiteInicioIP
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.imagen_captcha import ALFABETO, generar_png, generar_texto
from aplicacion.servicios.seguridad_login import ip_canonica, reloj_servidor, seudonimo


def proteger_respuesta(identificador: str, contexto: str, respuesta: str) -> str:
    raiz = obtener_configuracion().jwt_clave_secreta.get_secret_value().encode()
    clave = hmac.new(raiz, b"ESART/CAPTCHA/RESPUESTA/V1", hashlib.sha256).digest()
    dato = f"{identificador}:{contexto}:{respuesta.strip().upper()}".encode()
    return hmac.new(clave, dato, hashlib.sha256).hexdigest()


async def comprobar_estructura(sesion: AsyncSession) -> None:
    lista = await sesion.scalar(
        text("""
      SELECT to_regclass('esart.desafios_captcha') IS NOT NULL
         AND EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass('esart.auditoria_acceso')
                    AND attname='captcha_id' AND NOT attisdropped)
    """)
    )
    if not lista:
        raise ErrorAplicacion(503, "CAPTCHA_NO_DISPONIBLE", "Verificación temporalmente no disponible.")


def auditar(sesion: AsyncSession, evento: str, ahora, *, identificador=None, origen=None):
    sesion.add(AuditoriaAcceso(evento=evento, fecha=ahora, captcha_id=identificador, origen_hmac=origen))


async def generar(sesion: AsyncSession, nombre: str, ip: str | None, anterior: str | None) -> dict:
    await comprobar_estructura(sesion)
    nombre = nombre.strip()
    if not 3 <= len(nombre) <= 80 or not nombre.isprintable():
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Indique un nombre de usuario válido.")
    normalizado = await sesion.scalar(select(func.lower(nombre)))
    contexto = seudonimo("usuario", normalizado)
    origen = seudonimo("captcha_ip", ip_canonica(ip) or "origen_no_verificable")
    cfg = obtener_configuracion()
    await sesion.execute(
        insert(LimiteInicioIP)
        .values(clave=origen, inicio=func.clock_timestamp(), intentos=0)
        .on_conflict_do_nothing(index_elements=["clave"])
    )
    limite = await sesion.scalar(
        select(LimiteInicioIP)
        .where(LimiteInicioIP.clave == origen)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ahora = await reloj_servidor(sesion)
    if ahora >= limite.inicio + timedelta(seconds=cfg.ventana_generacion_captcha_segundos):
        limite.inicio, limite.intentos = ahora, 0
    if limite.intentos >= cfg.limite_generacion_captcha_ip:
        auditar(sesion, "CAPTCHA_IP_LIMITADA", ahora, origen=origen)
        await sesion.commit()
        raise ErrorAplicacion(429, "INTENTOS_LIMITADOS", "Demasiadas solicitudes. Inténtelo más tarde.")
    limite.intentos += 1
    if anterior:
        previo = await sesion.scalar(
            select(DesafioCaptcha)
            .where(DesafioCaptcha.id == anterior)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if previo is None or previo.contexto != contexto or previo.consumido_en is not None:
            auditar(sesion, "CAPTCHA_REGEN_RECHAZADA", ahora, origen=origen)
            await sesion.commit()
            raise ErrorAplicacion(409, "CAPTCHA_NO_DISPONIBLE", "Solicite un nuevo desafío.")
        previo.consumido_en = await reloj_servidor(sesion)
        auditar(sesion, "CAPTCHA_REGENERADO", previo.consumido_en, identificador=previo.id)
    identificador = secrets.token_urlsafe(32)
    codigo = generar_texto()
    try:
        imagen = await asyncio.wait_for(asyncio.to_thread(generar_png, codigo), timeout=2)
        huella = proteger_respuesta(identificador, contexto, codigo)
    finally:
        del codigo
    creado = await reloj_servidor(sesion)
    vence = creado + timedelta(minutes=5)
    sesion.add(
        DesafioCaptcha(
            id=identificador, contexto=contexto, respuesta_hmac=huella, creado_en=creado, expira_en=vence
        )
    )
    await sesion.flush()
    auditar(sesion, "CAPTCHA_EMITIDO", creado, identificador=identificador, origen=origen)
    await sesion.commit()
    return {
        "captcha_id": identificador,
        "imagen_png_base64": base64.b64encode(imagen).decode("ascii"),
        "expira_en": vence,
        "longitud": 6,
    }


class CaptchaPostgres:
    def __init__(self, sesion: AsyncSession):
        self.sesion = sesion
        self.fallo_contabilizable = False

    async def verificar(self, identificador: str | None, respuesta: str | None, contexto: str) -> bool:
        self.fallo_contabilizable = False
        await comprobar_estructura(self.sesion)
        if not identificador or not respuesta or len(identificador) != 43:
            return False
        desafio = await self.sesion.scalar(
            select(DesafioCaptcha)
            .where(DesafioCaptcha.id == identificador)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if desafio is None or not hmac.compare_digest(desafio.contexto, contexto):
            return False
        if desafio.consumido_en is not None:
            auditar(
                self.sesion,
                "CAPTCHA_REUTILIZADO",
                await reloj_servidor(self.sesion),
                identificador=identificador,
            )
            return False
        ahora = await reloj_servidor(self.sesion)
        # Se consume también la respuesta errónea: un solo intento por desafío.
        desafio.consumido_en = ahora
        # Solo el primer envío de un desafío del contexto puede contar como fallo.
        # La fila permanece bloqueada hasta confirmar también el intento de login.
        self.fallo_contabilizable = True
        normalizada = respuesta.strip().upper()
        valida_forma = len(normalizada) == 6 and all(c in ALFABETO for c in normalizada)
        coincide = valida_forma and hmac.compare_digest(
            proteger_respuesta(identificador, contexto, normalizada), desafio.respuesta_hmac
        )
        valido = ahora < desafio.expira_en and valida_forma and coincide
        evento = (
            "CAPTCHA_VALIDADO"
            if valido
            else ("CAPTCHA_VENCIDO" if ahora >= desafio.expira_en else "CAPTCHA_RECHAZADO")
        )
        auditar(self.sesion, evento, ahora, identificador=identificador)
        # No commit: el login confirma el consumo y su resultado en la misma transacción.
        return valido
