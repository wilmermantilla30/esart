"""Contrato HTTP público del CAPTCHA; no abre conexiones PostgreSQL."""

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.principal import crear_aplicacion
from aplicacion.seguridad.imagen_captcha import generar_png, generar_texto
from aplicacion.servicios import captcha_local

pytestmark = pytest.mark.anyio


async def test_cabecera_obligatoria_y_png_sin_jwt(monkeypatch):
    api = crear_aplicacion()
    sesion = object()

    async def entregar():
        yield sesion

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    png = generar_png(generar_texto())
    emitir = AsyncMock(
        return_value={
            "captcha_id": "a" * 43,
            "imagen_png_base64": base64.b64encode(png).decode(),
            "expira_en": datetime.now(UTC) + timedelta(minutes=5),
            "longitud": 6,
        }
    )
    monkeypatch.setattr(captcha_local, "generar", emitir)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas") as c:
        ausente = await c.get("/api/auth/captcha")
        assert ausente.status_code == 422
        emitir.assert_not_awaited()
        assert ausente.headers["cache-control"] == "no-store"
        bien = await c.get(
            "/api/auth/captcha",
            headers={
                "X-ESART-Usuario": "cuenta.local",
                "X-ESART-Captcha-Anterior": "b" * 43,
            },
        )
        assert bien.status_code == 200 and bien.headers["cache-control"] == "no-store"
        assert base64.b64decode(bien.json()["imagen_png_base64"]).startswith(b"\x89PNG\r\n\x1a\n")
        assert bien.json()["longitud"] == 6
        assert "respuesta" not in bien.json() and not bien.cookies
        emitir.assert_awaited_once_with(sesion, "cuenta.local", "127.0.0.1", "b" * 43)


async def test_openapi_no_declara_autenticacion_para_captcha():
    operacion = crear_aplicacion().openapi()["paths"]["/api/auth/captcha"]["get"]
    assert not operacion.get("security")
    cabecera = next(p for p in operacion["parameters"] if p["name"] == "X-ESART-Usuario")
    assert cabecera["in"] == "header" and cabecera["required"]
