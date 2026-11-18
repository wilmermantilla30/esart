from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import Response

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.principal import crear_aplicacion
from aplicacion.seguridad import comprobante_bloqueo as comprobante
from aplicacion.seguridad.tokens import TokenSesionInvalido, decodificar_token_sesion


def test_comprobante_no_es_sesion_y_detecta_alteracion():
    respuesta = Response()
    comprobante.escribir(respuesta, "cuenta.pruebas", (datetime.now(UTC) + timedelta(hours=3)).isoformat())
    cookie = respuesta.headers["set-cookie"]
    token = cookie.split(";", 1)[0].split("=", 1)[1]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert comprobante.leer(token) == "cuenta.pruebas"
    assert comprobante.leer(token + "alterado") is None
    with pytest.raises(TokenSesionInvalido):
        decodificar_token_sesion(token)


def test_comprobante_vencido_no_permite_recuperar_contexto():
    respuesta = Response()
    comprobante.escribir(respuesta, "cuenta.pruebas", (datetime.now(UTC) - timedelta(seconds=5)).isoformat())
    token = respuesta.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    assert comprobante.leer(token) is None


@pytest.mark.anyio
async def test_sin_comprobante_no_hay_consulta_por_nombre():
    api = crear_aplicacion()
    sesion = AsyncMock()

    async def entregar():
        yield sesion

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas") as c:
        r = await c.get(
            "/api/auth/bloqueo?nombre_usuario=admin.esart", headers={"X-ESART-Usuario": "admin.esart"}
        )
        assert r.status_code == 200 and r.json() == {"bloqueado": False}
        assert r.headers["cache-control"] == "no-store"
    sesion.scalar.assert_not_awaited()
    sesion.get.assert_not_awaited()


@pytest.mark.anyio
async def test_cliente_no_puede_inyectar_instantanea_publica(cliente_api):
    respuesta = await cliente_api.post(
        "/api/auth/login",
        json={
            "nombre_usuario": "cuenta.pruebas",
            "contrasena": "entrada-solo-prueba",
            "intento_actual": {"envios_registrados": 7, "direccion_ip_observada": "192.0.2.4"},
        },
    )
    assert respuesta.status_code == 422


@pytest.mark.anyio
async def test_un_423_con_nombre_no_autoriza_contador_ni_ip(monkeypatch):
    from aplicacion.rutas import autenticacion

    api = crear_aplicacion()
    ahora = datetime.now(UTC)
    fin = ahora + timedelta(hours=3)
    sesion = AsyncMock()
    sesion.add = MagicMock()
    sesion.scalar.side_effect = ["cuenta.original", ahora]
    filas = MagicMock()
    filas.one_or_none.return_value = SimpleNamespace(
        id=44, bloqueado_hasta=fin, intentos_fallidos_consecutivos=7
    )
    sesion.execute.return_value = filas

    async def entregar():
        yield sesion

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    monkeypatch.setattr(
        autenticacion,
        "iniciar_sesion",
        AsyncMock(
            side_effect=ErrorAplicacion(
                423, "CUENTA_BLOQUEADA", "Acceso bloqueado.", {"bloqueado_hasta": fin.isoformat()}
            )
        ),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas") as c:
        bloqueo = await c.post(
            "/api/auth/login", json={"nombre_usuario": "cuenta.original", "contrasena": "entrada-solo-prueba"}
        )
        assert bloqueo.status_code == 423 and comprobante.COOKIE in c.cookies
        estado = await c.get(
            "/api/auth/bloqueo?nombre_usuario=otra.cuenta", headers={"X-ESART-Usuario": "otra.cuenta"}
        )
        datos = estado.json()
        assert datos["usuario_intentado"] == "cuenta.original"
        assert datos["segundos_restantes"] == 10800
        assert datos["detalles_autorizados"] is False
        assert datos["intentos_fallidos_consecutivos"] is None and datos["direccion_ip"] is None
        parametros = sesion.execute.call_args.args[0].compile().params.values()
        assert "cuenta.original" in parametros and "otra.cuenta" not in parametros
        protegido = await c.get("/api/auth/administracion/bloqueos/44")
        assert protegido.status_code == 401
    # HU-11: el único guardado es el evento de auditoría del bloqueo; consultar el estado no escribe.
    assert sesion.commit.await_count == 1
    evento = sesion.add.call_args.args[0]
    assert evento.accion == "USUARIO_BLOQUEADO" and evento.nombre_usuario == "cuenta.original"
    assert "entrada-solo-prueba" not in str(evento.detalle)
