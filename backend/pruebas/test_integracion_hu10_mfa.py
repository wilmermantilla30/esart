"""Contratos HU-10/MFA: el paso de contraseña temporal nunca equivale a una sesión."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.principal import crear_aplicacion
from aplicacion.servicios import auditoria, autenticacion
from aplicacion.servicios.totp import DesafioLoginTotp, TotpService


@pytest.mark.anyio
async def test_login_temporal_no_emite_jwt_ni_registra_exito(monkeypatch):
    from aplicacion.rutas import autenticacion as rutas

    api = crear_aplicacion()
    desafio = DesafioLoginTotp(
        uuid.uuid4(), datetime.now(UTC), "nonce-de-prueba", cambio_contrasena_requerido=True
    )
    monkeypatch.setattr(rutas, "iniciar_sesion", AsyncMock(return_value=desafio))
    registrar = AsyncMock()
    monkeypatch.setattr(auditoria, "registrar_evento", registrar)

    async def entregar():
        yield SimpleNamespace()

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas") as c:
        r = await c.post("/api/auth/login", json={"nombre_usuario": "cuenta.local", "contrasena": "temporal"})
        assert r.status_code == 202 and r.json()["cambio_contrasena_requerido"]
        assert "esart_sesion" not in c.cookies and "usuario" not in r.json()
        assert (await c.get("/api/catalogos/unidades")).status_code == 401
        registrar.assert_not_awaited()


@pytest.mark.anyio
async def test_finalizar_mfa_conserva_auditoria_hu11_en_el_mismo_commit(monkeypatch):
    cfg = autenticacion.obtener_configuracion()
    monkeypatch.setattr(cfg, "totp_habilitado", True)
    usuario = SimpleNamespace(
        id=73, usuario="cuenta.local", activo=True, requiere_cambio_contrasena=False, documento_identidad=None
    )
    sesion = SimpleNamespace(add=MagicMock(), commit=AsyncMock())
    monkeypatch.setattr(autenticacion, "obtener_codigo_rol", AsyncMock(return_value="USUARIO"))
    monkeypatch.setattr(autenticacion, "obtener_nombre_completo", AsyncMock(return_value="Cuenta"))
    monkeypatch.setattr(autenticacion, "crear_token_sesion", MagicMock(return_value="jwt-solo-prueba"))
    monkeypatch.setattr(
        autenticacion.seguridad_login, "reloj_servidor", AsyncMock(return_value=datetime.now(UTC))
    )
    monkeypatch.setattr(autenticacion.seguridad_login, "registrar", AsyncMock())
    local = AsyncMock()
    monkeypatch.setattr(TotpService, "auditar", local)
    remoto = AsyncMock()
    monkeypatch.setattr(auditoria, "registrar_evento", remoto)

    async def confirmar():
        local.assert_awaited_once()
        remoto.assert_awaited_once()
        assert remoto.call_args.kwargs["confirmar"] is False

    sesion.commit.side_effect = confirmar
    resultado = await autenticacion.finalizar_login(sesion, usuario, "127.0.0.1", "prueba", None)
    assert resultado.usuario_id == 73 and not resultado.requiere_cambio_contrasena
    assert remoto.call_args.args[1] == auditoria.LOGIN_EXITOSO
    sesion.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_reglas_hu10_cambio_previo_a_mfa_no_confirman_transaccion(monkeypatch):
    from aplicacion.servicios import administracion_usuarios as usuarios

    sesion = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    monkeypatch.setattr(
        usuarios, "_obtener_usuario", AsyncMock(return_value=SimpleNamespace(contrasena_hash="hash"))
    )
    monkeypatch.setattr(usuarios, "verificar_contrasena", lambda *_: True)
    monkeypatch.setattr(usuarios, "generar_hash_contrasena", lambda *_: "hash-nuevo-solo-prueba")
    revocar, registrar = AsyncMock(), AsyncMock()
    monkeypatch.setattr(usuarios, "_revocar_sesiones", revocar)
    monkeypatch.setattr(usuarios, "_auditar", registrar)
    await usuarios.cambiar_contrasena_comprobada(
        sesion,
        usuario_id=73,
        nombre_usuario="cuenta.local",
        contrasena_actual="Temporal-123",
        contrasena_nueva="Nueva-local-2026",
        confirmar=False,
    )
    revocar.assert_awaited_once_with(sesion, 73, excepto=None)
    assert registrar.call_args.kwargs["confirmar"] is False
    parametros = sesion.execute.call_args_list[0].args[0].compile().params
    assert parametros["requiere_cambio_contrasena"] is False
    assert parametros["contrasena_hash"] == "hash-nuevo-solo-prueba"
    sesion.commit.assert_not_awaited()
