"""Contrato interno para validación y consumo del CAPTCHA local."""

from typing import Protocol

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos


class VerificadorCaptcha(Protocol):
    fallo_contabilizable: bool

    async def verificar(self, identificador: str | None, respuesta: str | None, contexto: str) -> bool:
        """Validar desafío no expirado, ligado al contexto y de un solo uso, atómicamente."""
        ...


class CaptchaNoDisponible:
    fallo_contabilizable = False

    async def verificar(self, identificador: str | None, respuesta: str | None, contexto: str) -> bool:
        return False


def obtener_verificador_captcha(
    sesion: AsyncSession = Depends(obtener_sesion_base_datos),
) -> VerificadorCaptcha:
    from aplicacion.servicios.captcha_local import CaptchaPostgres

    return CaptchaPostgres(sesion)
