"""Puente transaccional: solo adaptadores de recursos reales registrados por backend."""

import hashlib
import hmac
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select

from aplicacion.modelos.seguridad import SesionUsuario
from aplicacion.modelos.totp import AutorizacionTotp, CambioSeguridad, DesafioTotp, PoliticaAccion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.seguridad_login import ip_canonica, reloj_servidor
from aplicacion.servicios.totp import TotpService


@dataclass(frozen=True)
class AdaptadorAccion:
    tipo_recurso: str
    permiso_requerido: str
    permitir: Callable  # async(sesion, identidad) -> bool, consulta permisos reales
    preparar: Callable  # async(sesion, recurso_id, datos) -> instantánea canónica bloqueada/validada
    ejecutar: Callable  # async(sesion, recurso_id, datos) -> {resultado, cambios}; NO hace commit
    campos_auditables: frozenset[str] = frozenset()

    def __post_init__(self):
        if any(
            any(
                secreto in campo.lower() for secreto in ("contrasena", "password", "secreto", "token", "hash")
            )
            for campo in self.campos_auditables
        ):
            raise ValueError("La auditoría no puede registrar credenciales o secretos")


ADAPTADORES: dict[str, AdaptadorAccion] = {}


def hash_operacion(identidad, politica, recurso_id, datos, instantanea, tipo_recurso):
    contenido = json.dumps(
        {
            "usuario": identidad.id,
            "sesion": str(identidad.sesion_id),
            "politica": politica,
            "recurso": recurso_id,
            "tipo_recurso": tipo_recurso,
            "datos": datos,
            "estado": instantanea,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    if len(contenido) > 65536:
        raise ErrorAplicacion(413, "OPERACION_EXCESIVA", "La operación excede el tamaño permitido.")
    return hashlib.sha256(contenido).hexdigest()


class AutorizacionAccionesService(TotpService):
    async def preparar(self):
        if self._preparado:
            return
        await super().preparar()
        try:
            await self.verificar_integridad_acciones()
        except Exception:
            self._preparado = False
            raise

    async def preparar_operacion(self, identidad, politica, recurso_id, datos, ip=None):
        adaptador = ADAPTADORES.get(politica.codigo)
        if adaptador is None:
            raise ErrorAplicacion(
                501, "OPERACION_NO_INTEGRADA", "La operación aún no dispone de integración segura."
            )
        if (
            not politica.activa
            or not politica.requiere_totp
            or not politica.permiso_requerido
            or politica.permiso_requerido != adaptador.permiso_requerido
            or not await adaptador.permitir(self.sesion, identidad)
        ):
            await self.auditar(identidad.id, "AUTORIZACION_DENEGADA", "DENEGADO", ip)
            await self.sesion.commit()
            raise ErrorAplicacion(403, "SIN_PERMISO", "No tiene permiso para esta operación.")
        sesion = await self.sesion.scalar(
            select(SesionUsuario)
            .where(SesionUsuario.id == identidad.sesion_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not sesion or sesion.revocada or sesion.usuario_id != identidad.id:
            raise ErrorAplicacion(401, "NO_AUTENTICADO", "Debe iniciar sesión.")
        instantanea = await adaptador.preparar(self.sesion, recurso_id, datos)
        if not isinstance(instantanea, dict) or instantanea.get("version") is None:
            raise ErrorAplicacion(
                503, "RECURSO_NO_VERSIONADO", "El recurso requiere una versión verificable."
            )
        return adaptador, hash_operacion(
            identidad, politica.codigo, recurso_id, datos, instantanea, adaptador.tipo_recurso
        )

    async def crear(self, identidad, codigo, recurso_id, datos, ip):
        await self.limitar(ip, identidad.id)
        await self.usuario(identidad.id)
        politica = await self.politica(codigo)
        adaptador, huella = await self.preparar_operacion(identidad, politica, recurso_id, datos, ip)
        ahora = await reloj_servidor(self.sesion)
        desafio = DesafioTotp(
            id=uuid.uuid4(),
            usuario_id=identidad.id,
            politica_id=politica.id,
            recurso_tipo=adaptador.tipo_recurso,
            recurso_id=recurso_id,
            operacion_hash=huella,
            expira_en=ahora + timedelta(seconds=politica.vigencia_segundos),
            correlacion_id=uuid.uuid4(),
            ip_origen=ip_canonica(ip),
        )
        self.sesion.add(desafio)
        await self.auditar(identidad.id, "DESAFIO_ACCION_GENERADO", "CORRECTO", ip, desafio.correlacion_id)
        await self.sesion.commit()
        return {
            "desafio_id": desafio.id,
            "expira_en": desafio.expira_en,
            "politica": politica.codigo,
            "recurso_id": recurso_id,
        }

    async def verificar_accion(
        self, identidad, identificador, recurso_id, datos, codigo, ip, politica_solicitada=None
    ):
        await self.limitar(ip, identidad.id)
        await self.usuario(identidad.id)
        registro = await self.registro(identidad.id)
        desafio = await self.sesion.scalar(
            select(DesafioTotp)
            .where(DesafioTotp.id == identificador)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        ahora = await reloj_servidor(self.sesion)
        if (
            not desafio
            or desafio.usuario_id != identidad.id
            or desafio.estado != "PENDIENTE"
            or ahora >= desafio.expira_en
            or desafio.intentos >= 5
            or desafio.recurso_id != recurso_id
        ):
            await self.rechazar(identidad.id, ip)
        politica = await self.sesion.get(PoliticaAccion, desafio.politica_id)
        if politica_solicitada is not None and politica_solicitada != politica.codigo:
            raise ErrorAplicacion(
                409, "OPERACION_CAMBIO", "La política solicitada no corresponde al desafío."
            )
        adaptador, huella = await self.preparar_operacion(identidad, politica, recurso_id, datos, ip)
        if desafio.recurso_tipo != adaptador.tipo_recurso:
            raise ErrorAplicacion(409, "OPERACION_CAMBIO", "El tipo de recurso cambió.")
        if not hmac.compare_digest(huella, desafio.operacion_hash):
            raise ErrorAplicacion(409, "OPERACION_CAMBIO", "La operación cambió; solicite otra autorización.")
        desafio.intentos += 1
        if not registro or registro.estado != "ACTIVO" or not await self.verificar(registro, codigo):
            if desafio.intentos >= 5:
                desafio.estado = "CANCELADO"
            await self.rechazar(identidad.id, ip)
        desafio.estado, desafio.verificado_en = "VERIFICADO", ahora
        autorizacion = AutorizacionTotp(
            id=uuid.uuid4(),
            desafio_id=desafio.id,
            usuario_id=identidad.id,
            politica_id=politica.id,
            operacion_hash=huella,
            expira_en=desafio.expira_en,
        )
        self.sesion.add(autorizacion)
        await self.auditar(identidad.id, "AUTORIZACION_CONCEDIDA", "CORRECTO", ip, desafio.correlacion_id)
        await self.sesion.commit()
        return {"autorizacion_id": autorizacion.id, "expira_en": autorizacion.expira_en}

    async def ejecutar_autorizada(
        self, identidad, identificador, recurso_id, datos, ip, politica_solicitada=None
    ):
        await self.preparar()
        await self.usuario(identidad.id)
        factor = await self.registro(identidad.id)
        if not factor or factor.estado != "ACTIVO":
            raise ErrorAplicacion(403, "SIN_PERMISO", "Autenticador no disponible para esta operación.")
        inicial = await self.sesion.get(AutorizacionTotp, identificador)
        if not inicial or inicial.usuario_id != identidad.id:
            raise ErrorAplicacion(403, "SIN_PERMISO", "Autorización no disponible.")
        desafio = await self.sesion.scalar(
            select(DesafioTotp)
            .where(DesafioTotp.id == inicial.desafio_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        autorizacion = await self.sesion.scalar(
            select(AutorizacionTotp)
            .where(AutorizacionTotp.id == identificador)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        ahora = await reloj_servidor(self.sesion)
        if (
            autorizacion.resultado != "AUTORIZADA"
            or autorizacion.consumida_en is not None
            or ahora >= autorizacion.expira_en
            or desafio.estado != "VERIFICADO"
            or desafio.recurso_id != recurso_id
        ):
            raise ErrorAplicacion(409, "AUTORIZACION_INVALIDA", "Autorización vencida o utilizada.")
        politica = await self.sesion.get(PoliticaAccion, autorizacion.politica_id)
        if politica_solicitada is not None and politica_solicitada != politica.codigo:
            raise ErrorAplicacion(
                409, "OPERACION_CAMBIO", "La política solicitada no corresponde a la autorización."
            )
        adaptador, huella = await self.preparar_operacion(identidad, politica, recurso_id, datos, ip)
        if not hmac.compare_digest(huella, autorizacion.operacion_hash):
            raise ErrorAplicacion(409, "OPERACION_CAMBIO", "La operación cambió; solicite otra autorización.")
        resultado = await adaptador.ejecutar(self.sesion, recurso_id, datos)
        autorizacion.resultado, autorizacion.consumida_en = "CONSUMIDA", ahora
        desafio.estado, desafio.consumido_en = "CONSUMIDO", ahora
        auditoria = await self.auditar(identidad.id, politica.codigo, "CORRECTO", ip, desafio.correlacion_id)
        auditoria.autorizacion_id = autorizacion.id
        await self.sesion.flush()
        for campo, valores in resultado.get("cambios", {}).items():
            if campo in adaptador.campos_auditables:
                self.sesion.add(
                    CambioSeguridad(
                        auditoria_id=auditoria.id,
                        campo=campo,
                        valor_anterior=valores[0],
                        valor_nuevo=valores[1],
                    )
                )
        await self.sesion.commit()
        return resultado.get("resultado")
