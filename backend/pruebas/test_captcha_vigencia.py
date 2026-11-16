"""Límite exacto de vigencia, sin cambiar el reloj ni filas de PostgreSQL operativo."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from aplicacion.modelos.seguridad import DesafioCaptcha
from aplicacion.servicios import captcha_local


@pytest.mark.anyio
@pytest.mark.parametrize("desplazamiento,aceptado", [(-1, True), (0, False), (1, False)])
async def test_plazo_cinco_minutos_no_inclusivo(monkeypatch, desplazamiento, aceptado):
    creado = datetime(2026, 11, 16, tzinfo=UTC)
    vence = creado + timedelta(minutes=5)
    identificador, contexto, respuesta = "a" * 43, "b" * 64, "ACD346"
    desafio = DesafioCaptcha(
        id=identificador,
        contexto=contexto,
        respuesta_hmac=captcha_local.proteger_respuesta(identificador, contexto, respuesta),
        creado_en=creado,
        expira_en=vence,
        consumido_en=None,
    )
    sesion = MagicMock()
    sesion.scalar = AsyncMock(return_value=desafio)
    monkeypatch.setattr(captcha_local, "comprobar_estructura", AsyncMock())
    ahora = vence + timedelta(microseconds=desplazamiento)
    monkeypatch.setattr(captcha_local, "reloj_servidor", AsyncMock(return_value=ahora))
    resultado = await captcha_local.CaptchaPostgres(sesion).verificar(identificador, respuesta, contexto)
    assert resultado is aceptado
    assert desafio.consumido_en == ahora
    evento = sesion.add.call_args.args[0].evento
    assert evento == ("CAPTCHA_VALIDADO" if aceptado else "CAPTCHA_VENCIDO")


@pytest.mark.anyio
async def test_respuesta_unicode_invalida_es_fallo_no_averia(monkeypatch):
    ahora = datetime(2026, 11, 16, tzinfo=UTC)
    desafio = DesafioCaptcha(
        id="a" * 43,
        contexto="b" * 64,
        respuesta_hmac="c" * 64,
        creado_en=ahora,
        expira_en=ahora + timedelta(minutes=5),
        consumido_en=None,
    )
    sesion = MagicMock(scalar=AsyncMock(return_value=desafio))
    monkeypatch.setattr(captcha_local, "comprobar_estructura", AsyncMock())
    monkeypatch.setattr(captcha_local, "reloj_servidor", AsyncMock(return_value=ahora))
    proveedor = captcha_local.CaptchaPostgres(sesion)
    assert not await proveedor.verificar(desafio.id, chr(0xD800) * 6, desafio.contexto)
    assert proveedor.fallo_contabilizable is True and desafio.consumido_en == ahora
    assert not await proveedor.verificar(desafio.id, "ACD346", desafio.contexto)
    assert proveedor.fallo_contabilizable is False
