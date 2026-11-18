"""TOTP local: cifrado autenticado, reloj PostgreSQL, consumo y auditoría transaccionales."""

import asyncio
import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import pyotp
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import Usuario
from aplicacion.modelos.seguridad import LimiteInicioIP, SesionUsuario
from aplicacion.modelos.totp import (
    AuditoriaSeguridad,
    CambioSeguridad,
    DesafioTotp,
    PoliticaAccion,
    RecuperacionTotp,
    UsuarioTotp,
)
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.contrasenas import verificar_contrasena
from aplicacion.servicios.seguridad_login import ip_canonica, reloj_servidor, seudonimo

registrador = logging.getLogger(__name__)


@dataclass
class DesafioLoginTotp:
    id: uuid.UUID
    expira_en: object
    nonce: str = field(repr=False)
    configuracion_requerida: bool = False
    cambio_contrasena_requerido: bool = False


class TotpService:
    def __init__(self, sesion):
        self.sesion = sesion
        self._preparado = False
        self.inicio = time.monotonic()

    async def respuesta_uniforme(self):
        await asyncio.sleep(max(0, 0.05 - (time.monotonic() - self.inicio)))

    @classmethod
    def nonce_contexto(cls, nombre, identificador, proposito):
        aleatorio = secrets.token_urlsafe(32)
        contexto = seudonimo("totp_contexto", nombre)
        cuerpo = f"{identificador}/{proposito}/{aleatorio}/{contexto}".encode()
        clave = hmac.new(cls.clave(), b"ESART/TOTP/NONCE/V1", hashlib.sha256).digest()
        return f"{aleatorio}.{contexto}." + hmac.new(clave, cuerpo, hashlib.sha256).hexdigest()

    @classmethod
    def contexto_nonce(cls, nonce, identificador, proposito):
        if not nonce:
            return None
        partes = nonce.split(".")
        if len(partes) != 3 or len(partes[0]) != 43 or len(partes[1]) != 64 or len(partes[2]) != 64:
            return None
        cuerpo = f"{identificador}/{proposito}/{partes[0]}/{partes[1]}".encode()
        clave = hmac.new(cls.clave(), b"ESART/TOTP/NONCE/V1", hashlib.sha256).digest()
        esperado = hmac.new(clave, cuerpo, hashlib.sha256).hexdigest()
        return partes[1] if hmac.compare_digest(esperado, partes[2]) else None

    async def preparar(self):
        self.clave()
        if self._preparado:
            return
        from aplicacion.servicios.requisitos_totp import permisos_faltantes

        faltantes = await permisos_faltantes(self.sesion)
        if faltantes:
            registrador.error("TOTP_PERMISOS_FALTANTES: %s", ", ".join(faltantes))
            raise ErrorAplicacion(
                503, "TOTP_PERMISOS_FALTANTES", "El autenticador requiere permisos de base de datos."
            )
        self._preparado = True

    async def verificar_integridad_acciones(self):
        acceso = await self.sesion.scalar(
            text("""SELECT
                (SELECT count(*)=5 FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace
                  WHERE n.nspname='seguridad' AND k.convalidated AND k.conname IN
                  ('fk_usuario_totp_usuario_esart','fk_totp_recuperacion_usuario_esart',
                   'fk_desafios_usuario_esart','fk_autorizaciones_usuario_esart','fk_auditoria_usuario_esart'))
                AND EXISTS(SELECT 1 FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace
                  WHERE n.nspname='seguridad' AND k.conname='fk_autorizacion_contexto' AND k.convalidated)
                AND (SELECT count(*)=4 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                  JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='seguridad'
                  AND c.relname IN ('auditoria','auditoria_cambios') AND t.tgenabled='O'
                  AND t.tgname IN ('seguridad_auditoria_inmutable','seguridad_auditoria_no_truncate'))
                AND COALESCE(has_table_privilege(to_regclass('seguridad.autorizaciones'),'SELECT'),false)
                AND COALESCE(has_table_privilege(to_regclass('seguridad.autorizaciones'),'INSERT'),false)
                AND COALESCE(has_column_privilege(to_regclass('seguridad.autorizaciones'),
                  'resultado','UPDATE'),false)
                AND COALESCE(has_column_privilege(to_regclass('seguridad.autorizaciones'),
                  'consumida_en','UPDATE'),false)
            """)
        )
        if not acceso:
            raise ErrorAplicacion(
                503, "TOTP_INTEGRIDAD_ACCIONES", "Las operaciones requieren configuración administrativa."
            )

    @staticmethod
    def clave():
        cfg = obtener_configuracion()
        if not cfg.totp_habilitado or not cfg.totp_clave_cifrado:
            raise ErrorAplicacion(503, "TOTP_NO_DISPONIBLE", "Servicio de autenticador no disponible.")
        try:
            valor = base64.b64decode(cfg.totp_clave_cifrado.get_secret_value(), validate=True)
            if len(valor) != 32:
                raise ValueError
            return valor
        except (ValueError, TypeError):
            raise ErrorAplicacion(
                503, "TOTP_NO_DISPONIBLE", "Configuración de autenticador no disponible."
            ) from None

    @classmethod
    def cifrar(cls, usuario_id, secreto):
        nonce = secrets.token_bytes(12)
        dato = AESGCM(cls.clave()).encrypt(nonce, secreto.encode(), f"ESART/TOTP/V1/{usuario_id}".encode())
        return "v1." + base64.b64encode(nonce + dato).decode()

    @classmethod
    def descifrar(cls, registro):
        try:
            if not registro.secreto_cifrado.startswith("v1."):
                raise ValueError
            datos = base64.b64decode(registro.secreto_cifrado[3:], validate=True)
            return (
                AESGCM(cls.clave())
                .decrypt(datos[:12], datos[12:], f"ESART/TOTP/V1/{registro.usuario_id}".encode())
                .decode()
            )
        except (InvalidTag, ValueError, UnicodeError):
            raise ErrorAplicacion(
                503, "TOTP_NO_DISPONIBLE", "Autenticador temporalmente no disponible."
            ) from None

    async def auditar(self, usuario_id, accion, resultado, ip=None, correlacion=None):
        registro = AuditoriaSeguridad(
            evento_id=uuid.uuid4(),
            usuario_id=usuario_id,
            actor_tipo="USUARIO" if usuario_id else "ANONIMO",
            modulo="SEGURIDAD",
            accion=accion,
            resultado=resultado,
            ip_origen=ip_canonica(ip),
            correlacion_id=correlacion,
            datos={},
        )
        self.sesion.add(registro)
        return registro

    async def limitar(self, ip, contexto):
        await self.preparar()
        for dominio, valor in (
            ("totp_ip", ip_canonica(ip) or "origen_no_verificable"),
            ("totp_usuario", str(contexto)),
        ):
            clave = seudonimo(dominio, valor)
            await self.sesion.execute(
                insert(LimiteInicioIP)
                .values(clave=clave, inicio=func.clock_timestamp(), intentos=0)
                .on_conflict_do_nothing()
            )
            fila = await self.sesion.scalar(
                select(LimiteInicioIP)
                .where(LimiteInicioIP.clave == clave)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            ahora = await reloj_servidor(self.sesion)
            if ahora >= fila.inicio + timedelta(minutes=10):
                fila.inicio, fila.intentos = ahora, 0
            if fila.intentos >= 10:
                await self.auditar(None, "TOTP_LIMITE", "DENEGADO", ip)
                await self.sesion.commit()
                raise ErrorAplicacion(429, "INTENTOS_LIMITADOS", "Demasiadas solicitudes. Intente más tarde.")
            fila.intentos += 1

    async def usuario(self, usuario_id, permitir_bloqueado=False):
        usuario = await self.sesion.scalar(
            select(Usuario)
            .where(Usuario.id == usuario_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        ahora = await reloj_servidor(self.sesion)
        if (
            not usuario
            or not usuario.activo
            or (not permitir_bloqueado and usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora)
        ):
            raise ErrorAplicacion(401, "VERIFICACION_INVALIDA", "No fue posible completar la verificación.")
        return usuario

    async def registro(self, usuario_id):
        return await self.sesion.scalar(
            select(UsuarioTotp)
            .where(UsuarioTotp.usuario_id == usuario_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def verificar(self, registro, codigo):
        if not registro or not re.fullmatch(r"[0-9]{6}", codigo):
            return False
        secreto = self.descifrar(registro)
        intervalo = int((await reloj_servidor(self.sesion)).timestamp()) // 30
        generador = pyotp.TOTP(secreto, digits=6, interval=30, digest=hashlib.sha1)
        for paso in (intervalo - 1, intervalo, intervalo + 1):
            if hmac.compare_digest(generador.at(paso * 30), codigo):
                if (
                    registro.ultimo_intervalo_aceptado is not None
                    and paso <= registro.ultimo_intervalo_aceptado
                ):
                    return False
                registro.ultimo_intervalo_aceptado = paso
                registro.actualizado_en = await reloj_servidor(self.sesion)
                return True
        return False

    async def rechazar(self, usuario_id, ip, accion="TOTP_INVALIDO"):
        await self.auditar(usuario_id, accion, "DENEGADO", ip)
        await self.sesion.commit()
        await self.respuesta_uniforme()
        raise ErrorAplicacion(401, "VERIFICACION_INVALIDA", "No fue posible completar la verificación.")

    async def configurar(self, usuario_id, contrasena, ip):
        await self.limitar(ip, usuario_id)
        usuario = await self.usuario(usuario_id)
        if not await asyncio.to_thread(verificar_contrasena, contrasena, usuario.contrasena_hash):
            await self.rechazar(usuario_id, ip, "TOTP_REAUTENTICACION_INVALIDA")
        return await self.configurar_verificado(usuario_id, ip)

    async def configurar_verificado(self, usuario_id, ip):
        """Uso interno: el llamador ya bloqueó y verificó la identidad del titular."""
        registro = await self.registro(usuario_id)
        if registro and registro.estado == "ACTIVO":
            raise ErrorAplicacion(409, "TOTP_YA_ACTIVO", "Ya existe un autenticador activo.")
        ahora = await reloj_servidor(self.sesion)
        if (
            registro
            and registro.estado == "PENDIENTE"
            and registro.expira_configuracion_en
            and registro.expira_configuracion_en > ahora
        ):
            secreto = self.descifrar(registro)
            await self.auditar(usuario_id, "TOTP_CONFIGURACION_RECUPERADA", "CORRECTO", ip)
            await self.sesion.commit()
            return {
                "uri": pyotp.TOTP(secreto, digits=6, interval=30, digest=hashlib.sha1).provisioning_uri(
                    name=await self.sesion.scalar(select(Usuario.usuario).where(Usuario.id == usuario_id)),
                    issuer_name="ESART",
                ),
                "expira_en": registro.expira_configuracion_en,
            }
        secreto = pyotp.random_base32()
        if registro is None:
            registro = UsuarioTotp(usuario_id=usuario_id)
            self.sesion.add(registro)
        registro.secreto_cifrado = self.cifrar(usuario_id, secreto)
        registro.estado = "PENDIENTE"
        registro.expira_configuracion_en = ahora + timedelta(minutes=10)
        registro.activado_en = registro.revocado_en = registro.ultimo_intervalo_aceptado = None
        registro.actualizado_en = ahora
        await self.auditar(usuario_id, "TOTP_CONFIGURACION_PENDIENTE", "CORRECTO", ip)
        await self.sesion.commit()
        return {
            "uri": pyotp.TOTP(secreto, digits=6, interval=30, digest=hashlib.sha1).provisioning_uri(
                name=await self.sesion.scalar(select(Usuario.usuario).where(Usuario.id == usuario_id)),
                issuer_name="ESART",
            ),
            "expira_en": registro.expira_configuracion_en,
        }

    async def confirmar(self, usuario_id, codigo, ip, confirmar_transaccion=True, identidad_verificada=False):
        if not identidad_verificada:
            await self.limitar(ip, usuario_id)
            await self.usuario(usuario_id)
        registro = await self.registro(usuario_id)
        ahora = await reloj_servidor(self.sesion)
        if (
            not registro
            or registro.estado != "PENDIENTE"
            or not registro.expira_configuracion_en
            or ahora >= registro.expira_configuracion_en
            or not await self.verificar(registro, codigo)
        ):
            await self.rechazar(usuario_id, ip)
        registro.estado, registro.activado_en = "ACTIVO", ahora
        registro.expira_configuracion_en = None
        evento = await self.auditar(usuario_id, "TOTP_ACTIVADO", "CORRECTO", ip)
        await self.sesion.flush()
        self.sesion.add(
            CambioSeguridad(
                auditoria_id=evento.id, campo="estado_totp", valor_anterior="PENDIENTE", valor_nuevo="ACTIVO"
            )
        )
        codigos = await self.generar_recuperacion(usuario_id)
        if confirmar_transaccion:
            await self.sesion.commit()
        return {
            "configurado": True,
            "activo": True,
            "fecha_activacion": ahora,
            "codigos_recuperacion": codigos,
        }

    @classmethod
    def hash_recuperacion(cls, usuario_id, codigo):
        clave = hmac.new(cls.clave(), b"ESART/RECUPERACION/V1", hashlib.sha256).digest()
        return hmac.new(clave, f"{usuario_id}/{codigo}".encode(), hashlib.sha256).hexdigest()

    async def generar_recuperacion(self, usuario_id):
        ahora = await reloj_servidor(self.sesion)
        await self.sesion.execute(
            update(RecuperacionTotp)
            .where(RecuperacionTotp.usuario_id == usuario_id, RecuperacionTotp.revocado_en.is_(None))
            .values(revocado_en=ahora)
        )
        codigos = [secrets.token_hex(16) for _ in range(10)]
        for codigo in codigos:
            self.sesion.add(
                RecuperacionTotp(
                    usuario_id=usuario_id, codigo_hash=self.hash_recuperacion(usuario_id, codigo)
                )
            )
        return codigos

    async def verificar_recuperacion(self, usuario_id, codigo):
        if not re.fullmatch(r"[0-9a-f]{32}", codigo):
            return False
        fila = await self.sesion.scalar(
            select(RecuperacionTotp)
            .where(
                RecuperacionTotp.usuario_id == usuario_id,
                RecuperacionTotp.codigo_hash == self.hash_recuperacion(usuario_id, codigo),
                RecuperacionTotp.usado_en.is_(None),
                RecuperacionTotp.revocado_en.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if fila is None:
            return False
        fila.usado_en = await reloj_servidor(self.sesion)
        return True

    async def renovar_recuperacion(self, usuario_id, contrasena, codigo, ip):
        await self.limitar(ip, usuario_id)
        usuario = await self.usuario(usuario_id)
        registro = await self.registro(usuario_id)
        correcta = await asyncio.to_thread(verificar_contrasena, contrasena, usuario.contrasena_hash)
        if (
            not correcta
            or not registro
            or registro.estado != "ACTIVO"
            or not await self.verificar(registro, codigo)
        ):
            await self.rechazar(usuario_id, ip)
        codigos = await self.generar_recuperacion(usuario_id)
        await self.auditar(usuario_id, "TOTP_RECUPERACION_RENOVADA", "CORRECTO", ip)
        await self.sesion.commit()
        return {"codigos_recuperacion": codigos}

    async def desactivar(self, usuario_id, contrasena, codigo, ip, recuperacion=False):
        await self.limitar(ip, usuario_id)
        usuario = await self.usuario(usuario_id)
        registro = await self.registro(usuario_id)
        correcta = await asyncio.to_thread(verificar_contrasena, contrasena, usuario.contrasena_hash)
        if (
            not correcta
            or not registro
            or registro.estado != "ACTIVO"
            or not (
                await self.verificar_recuperacion(usuario_id, codigo)
                if recuperacion
                else await self.verificar(registro, codigo)
            )
        ):
            await self.rechazar(usuario_id, ip)
        registro.estado, registro.revocado_en = "REVOCADO", await reloj_servidor(self.sesion)
        await self.sesion.execute(
            update(SesionUsuario)
            .where(SesionUsuario.usuario_id == usuario_id, SesionUsuario.revocada.is_(False))
            .values(revocada=True, fecha_revocacion=registro.revocado_en)
        )
        await self.sesion.execute(
            update(RecuperacionTotp)
            .where(RecuperacionTotp.usuario_id == usuario_id, RecuperacionTotp.revocado_en.is_(None))
            .values(revocado_en=registro.revocado_en)
        )
        await self.sesion.execute(
            update(DesafioTotp)
            .where(DesafioTotp.usuario_id == usuario_id, DesafioTotp.estado.in_(["PENDIENTE", "VERIFICADO"]))
            .values(estado="CANCELADO")
        )
        evento = await self.auditar(usuario_id, "TOTP_REVOCADO", "CORRECTO", ip)
        await self.sesion.flush()
        self.sesion.add(
            CambioSeguridad(
                auditoria_id=evento.id, campo="estado_totp", valor_anterior="ACTIVO", valor_nuevo="REVOCADO"
            )
        )
        await self.sesion.commit()
        return {"configurado": True, "activo": False, "fecha_activacion": None}

    async def politica(self, codigo):
        self.clave()
        politica = await self.sesion.scalar(
            select(PoliticaAccion).where(PoliticaAccion.codigo == codigo, PoliticaAccion.activa.is_(True))
        )
        if not politica or not politica.requiere_totp:
            raise ErrorAplicacion(503, "POLITICA_NO_DISPONIBLE", "Política de seguridad no disponible.")
        return politica

    @staticmethod
    def vinculo(usuario_id, proposito, nonce):
        return hashlib.sha256(f"ESART/TOTP/{usuario_id}/{proposito}/{nonce}".encode()).hexdigest()

    async def crear_desafio(self, usuario_id, proposito, ip):
        politica = await self.politica("DESBLOQUEO_TOTP" if proposito == "DESBLOQUEO" else "LOGIN_TOTP")
        ahora = await reloj_servidor(self.sesion)
        identificador = uuid.uuid4()
        nombre = await self.sesion.scalar(select(func.lower(Usuario.usuario)).where(Usuario.id == usuario_id))
        nonce = self.nonce_contexto(nombre, identificador, proposito)
        desafio = DesafioTotp(
            id=identificador,
            usuario_id=usuario_id,
            politica_id=politica.id,
            recurso_tipo=proposito,
            operacion_hash=self.vinculo(usuario_id, proposito, nonce),
            expira_en=ahora + timedelta(seconds=politica.vigencia_segundos),
            ip_origen=ip_canonica(ip),
            correlacion_id=uuid.uuid4(),
        )
        self.sesion.add(desafio)
        await self.auditar(usuario_id, "TOTP_DESAFIO_" + proposito, "CORRECTO", ip, desafio.correlacion_id)
        await self.sesion.flush()
        return DesafioLoginTotp(
            desafio.id, desafio.expira_en, nonce, proposito == "VINCULACION", proposito == "CAMBIO_CONTRASENA"
        )

    async def contexto_vinculacion(self, identificador, nonce, ip, proposito="VINCULACION"):
        """Prueba reciente de contraseña, ligada al navegador y sin acceso de negocio."""
        await self.preparar()
        contexto = self.contexto_nonce(nonce, identificador, proposito)
        await self.limitar(ip, contexto or ("sin_contexto:" + str(ip_canonica(ip))))
        if contexto is None:
            await self.rechazar(None, ip)
        inicial = await self.sesion.get(DesafioTotp, identificador)
        if inicial is None:
            await self.rechazar(None, ip)
        usuario = await self.usuario(inicial.usuario_id)
        desafio = await self.sesion.scalar(
            select(DesafioTotp)
            .where(DesafioTotp.id == identificador)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        ahora = await reloj_servidor(self.sesion)
        if (
            desafio.recurso_tipo != proposito
            or desafio.estado != "PENDIENTE"
            or ahora >= desafio.expira_en
            or desafio.intentos >= 5
            or not hmac.compare_digest(desafio.operacion_hash, self.vinculo(usuario.id, proposito, nonce))
        ):
            await self.rechazar(usuario.id, ip)
        registro = await self.registro(usuario.id)
        if proposito == "VINCULACION" and (
            (registro and registro.estado == "ACTIVO") or usuario.requiere_cambio_contrasena
        ):
            await self.rechazar(usuario.id, ip)
        if proposito == "CAMBIO_CONTRASENA" and not usuario.requiere_cambio_contrasena:
            await self.rechazar(usuario.id, ip)
        return usuario, desafio

    async def cambiar_contrasena_inicial(self, identificador, nonce, actual, nueva, ip, request=None):
        from aplicacion.servicios.administracion_usuarios import cambiar_contrasena_comprobada

        usuario, desafio = await self.contexto_vinculacion(
            identificador, nonce, ip, proposito="CAMBIO_CONTRASENA"
        )
        desafio.intentos += 1
        if desafio.intentos >= 5:
            desafio.estado = "CANCELADO"
        await cambiar_contrasena_comprobada(
            self.sesion,
            usuario_id=usuario.id,
            nombre_usuario=usuario.usuario,
            contrasena_actual=actual,
            contrasena_nueva=nueva,
            request=request,
            confirmar=False,
        )
        ahora = await reloj_servidor(self.sesion)
        desafio.estado = "CONSUMIDO"
        desafio.consumido_en = desafio.verificado_en = ahora
        registro = await self.registro(usuario.id)
        siguiente = await self.crear_desafio(
            usuario.id, "LOGIN" if registro and registro.estado == "ACTIVO" else "VINCULACION", ip
        )
        await self.sesion.commit()
        return siguiente

    async def configurar_login(self, identificador, nonce, ip):
        usuario, desafio = await self.contexto_vinculacion(identificador, nonce, ip)
        # configurar_verificado confirma la transacción; conservar el plazo del desafío.
        expira = desafio.expira_en
        salida = await self.configurar_verificado(usuario.id, ip)
        salida["expira_en"] = min(salida["expira_en"], expira)
        return salida

    async def vincular_login(self, identificador, nonce, codigo, ip):
        usuario, desafio = await self.contexto_vinculacion(identificador, nonce, ip)
        desafio.intentos += 1
        if desafio.intentos >= 5:
            desafio.estado = "CANCELADO"
        salida = await self.confirmar(
            usuario.id, codigo, ip, confirmar_transaccion=False, identidad_verificada=True
        )
        ahora = await reloj_servidor(self.sesion)
        desafio.estado = "CONSUMIDO"
        desafio.consumido_en = desafio.verificado_en = ahora
        await self.auditar(usuario.id, "TOTP_VINCULACION_LOGIN", "CORRECTO", ip, desafio.correlacion_id)
        return usuario, salida

    async def validar_desafio(self, identificador, proposito, nonce, codigo, ip, recuperacion=False):
        await self.preparar()
        contexto = self.contexto_nonce(nonce, identificador, proposito)
        await self.limitar(ip, contexto or ("sin_contexto:" + str(ip_canonica(ip))))
        if contexto is None:
            await self.rechazar(None, ip)
        inicial = await self.sesion.get(DesafioTotp, identificador)
        if inicial is None:
            await self.rechazar(None, ip)
        usuario = await self.usuario(inicial.usuario_id, permitir_bloqueado=proposito == "DESBLOQUEO")
        registro = await self.registro(usuario.id)
        desafio = await self.sesion.scalar(
            select(DesafioTotp)
            .where(DesafioTotp.id == identificador)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        ahora = await reloj_servidor(self.sesion)
        if ahora >= desafio.expira_en and desafio.estado == "PENDIENTE":
            desafio.estado = "EXPIRADO"
        if (
            desafio.recurso_tipo != proposito
            or desafio.estado != "PENDIENTE"
            or ahora >= desafio.expira_en
            or desafio.intentos >= 5
            or not nonce
            or not hmac.compare_digest(desafio.operacion_hash, self.vinculo(usuario.id, proposito, nonce))
        ):
            await self.rechazar(usuario.id, ip)
        desafio.intentos += 1
        valido = False
        if registro and registro.estado == "ACTIVO":
            if recuperacion and proposito == "LOGIN":
                valido = await self.verificar_recuperacion(usuario.id, codigo)
            elif not recuperacion:
                valido = await self.verificar(registro, codigo)
        if not valido:
            if desafio.intentos >= 5:
                desafio.estado = "CANCELADO"
            await self.rechazar(usuario.id, ip)
        desafio.estado, desafio.consumido_en, desafio.verificado_en = "CONSUMIDO", ahora, ahora
        if recuperacion:
            await self.auditar(usuario.id, "TOTP_RECUPERACION_USADA", "CORRECTO", ip, desafio.correlacion_id)
        await self.auditar(usuario.id, "TOTP_VALIDADO_" + proposito, "CORRECTO", ip, desafio.correlacion_id)
        return usuario
