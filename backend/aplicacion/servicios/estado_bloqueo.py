"""Lectura sin incrementar intentos ni desbloquear mediante escrituras."""

import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos import Usuario
from aplicacion.modelos.seguridad import EstadoAccesoAnonimo
from aplicacion.servicios.seguridad_login import reloj_servidor, seudonimo


async def consultar(sesion: AsyncSession, nombre: str | None) -> dict:
    ahora = await reloj_servidor(sesion)
    estado = None
    if nombre:
        estado = (
            await sesion.execute(
                select(Usuario.id, Usuario.bloqueado_hasta).where(func.lower(Usuario.usuario) == nombre)
            )
        ).one_or_none()
        if estado is None:
            estado = await sesion.get(EstadoAccesoAnonimo, seudonimo("usuario", nombre))
    vigente = bool(estado and estado.bloqueado_hasta and estado.bloqueado_hasta > ahora)
    return {
        "bloqueado": vigente,
        "usuario_intentado": nombre,
        "bloqueado_hasta": estado.bloqueado_hasta.isoformat() if vigente else None,
        "ahora_servidor": ahora.isoformat(),
        "segundos_restantes": math.ceil((estado.bloqueado_hasta - ahora).total_seconds()) if vigente else 0,
        # La firma protege el contexto, pero no prueba identidad ni autoría de los fallos.
        "detalles_autorizados": False,
        "intentos_fallidos_consecutivos": None,
        "direccion_ip": None,
    }
