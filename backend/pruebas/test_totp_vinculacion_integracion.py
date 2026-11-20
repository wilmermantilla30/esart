"""
Integración real de la vinculación TOTP: endpoints FastAPI + servicio + PostgreSQL.

Recorre lo mismo que el navegador: login -> desafío VINCULACION (cookie esart_totp_login) ->
/totp/login/configurar (URI otpauth que dibuja Angular) -> código calculado con una
implementación RFC 6238 INDEPENDIENTE (hmac/struct, sin pyotp) -> /totp/login/vincular.

Solo corre con ESART_URL_BD_INTEGRACION. Todo ocurre dentro de una transacción externa que se
revierte (savepoints): la base queda exactamente igual. conftest usa una clave de cifrado de
prueba, así que ningún secreto real interviene.

    $env:ESART_URL_BD_INTEGRACION = "postgresql+asyncpg://esart_aplicacion:...@localhost:5432/esart_db"
"""

import base64
import hashlib
import hmac
import secrets
import struct
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from sqlalchemy import func, select

from aplicacion.modelos.totp import AuditoriaSeguridad, DesafioTotp, UsuarioTotp
from aplicacion.servicios.totp import TotpService
from pruebas.test_login_hu05 import CONTRASENA_CORRECTA, crear_usuario, requiere_postgresql, sesion_bd  # noqa: F401

pytestmark = [pytest.mark.anyio, requiere_postgresql]


def totp_independiente(secreto_base32: str, instante: datetime, digitos=6, periodo=30) -> str:
    """RFC 6238 / RFC 4226 con HMAC-SHA1, como Google Authenticator. Sin pyotp."""
    relleno = "=" * (-len(secreto_base32) % 8)
    clave = base64.b32decode(secreto_base32.upper() + relleno)
    contador = int(instante.timestamp()) // periodo
    resumen = hmac.new(clave, struct.pack(">Q", contador), hashlib.sha1).digest()
    desplazamiento = resumen[-1] & 0x0F
    valor = struct.unpack(">I", resumen[desplazamiento : desplazamiento + 4])[0] & 0x7FFFFFFF
    return str(valor % 10**digitos).zfill(digitos)


def test_implementacion_independiente_cumple_rfc6238():
    # Vectores oficiales SHA1 (RFC 6238, apéndice B), clave ASCII "12345678901234567890".
    secreto = base64.b32encode(b"12345678901234567890").decode()
    for segundos, esperado in ((59, "94287082"), (1111111109, "07081804"), (2000000000, "69279037")):
        assert totp_independiente(secreto, datetime.fromtimestamp(segundos, UTC), digitos=8) == esperado


def secreto_como_angular(uri: str) -> str:
    """Igual que totp.ts: new URL(uri).searchParams.get('secret')."""
    partes = urlparse(uri)
    assert partes.scheme == "otpauth" and partes.netloc == "totp"
    return parse_qs(partes.query)["secret"][0]


async def test_vinculacion_real_extremo_a_extremo(cliente_api, sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd)
    usuario_id, nombre = usuario.id, usuario.usuario
    cliente_api.headers["user-agent"] = "navegador-de-prueba"

    # 1. Contraseña correcta: 202 con desafío de VINCULACION y cookie ligada al navegador.
    acceso = await cliente_api.post(
        "/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CONTRASENA_CORRECTA}
    )
    assert acceso.status_code == 202, acceso.text
    assert acceso.json()["configuracion_requerida"] and "esart_totp_login" in cliente_api.cookies
    assert "esart_sesion" not in cliente_api.cookies
    datos = {"desafio_id": acceso.json()["desafio_id"]}

    # 2. URI que recibe Angular; una segunda petición devuelve la misma (no se regenera).
    qr = await cliente_api.post("/api/auth/totp/login/configurar", json=datos)
    assert qr.status_code == 200, qr.text
    uri = qr.json()["uri"]
    assert (await cliente_api.post("/api/auth/totp/login/configurar", json=datos)).json()["uri"] == uri
    assert unquote(urlparse(uri).path).startswith(f"/ESART:{nombre} (")
    assert set(parse_qs(urlparse(uri).query)) == {"secret", "issuer"}  # SHA1/6/30 por defecto

    # 3. Secreto de la URI == secreto pendiente persistido (descifrado), sin transformación.
    secreto = secreto_como_angular(uri)
    registro = await sesion_bd.scalar(select(UsuarioTotp).where(UsuarioTotp.usuario_id == usuario_id))
    assert registro.estado == "PENDIENTE" and secreto not in registro.secreto_cifrado
    assert TotpService.descifrar(registro) == secreto
    cifrado_antes = registro.secreto_cifrado

    # 4. Código independiente con el reloj UTC de PostgreSQL (el mismo que usa el servidor).
    ahora = await sesion_bd.scalar(select(func.clock_timestamp()))
    codigo = totp_independiente(secreto, ahora)

    # 5-6. Endpoint real de vinculación: 200, sesión emitida, códigos de recuperación.
    fin = await cliente_api.post("/api/auth/totp/login/vincular", json={**datos, "codigo": codigo})
    assert fin.status_code == 200, fin.text
    cuerpo = fin.json()
    assert cuerpo["activo"] and len(cuerpo["codigos_recuperacion"]) == 10
    assert "esart_sesion" in cliente_api.cookies
    assert (await cliente_api.get("/api/auth/yo")).status_code == 200

    # 7. Estado persistido (visible tras el commit/savepoint del endpoint).
    registro = await sesion_bd.scalar(
        select(UsuarioTotp)
        .where(UsuarioTotp.usuario_id == usuario_id)
        .execution_options(populate_existing=True)
    )
    assert registro.estado == "ACTIVO" and registro.activado_en is not None
    assert registro.expira_configuracion_en is None and registro.secreto_cifrado == cifrado_antes
    assert registro.ultimo_intervalo_aceptado is not None
    desafio = await sesion_bd.get(DesafioTotp, uuid.UUID(datos["desafio_id"]), populate_existing=True)
    assert desafio.estado == "CONSUMIDO" and desafio.usuario_id == usuario_id
    acciones = set(
        await sesion_bd.scalars(
            select(AuditoriaSeguridad.accion).where(AuditoriaSeguridad.usuario_id == usuario_id)
        )
    )
    assert {"TOTP_CONFIGURACION_PENDIENTE", "TOTP_ACTIVADO", "TOTP_VINCULACION_LOGIN"} <= acciones
    assert "TOTP_INVALIDO" not in acciones  # 8. Ningún 401 inesperado.

    # El mismo código no puede reutilizarse (antirepetición).
    repetido = await cliente_api.post("/api/auth/totp/login/vincular", json={**datos, "codigo": codigo})
    assert repetido.status_code == 401


async def test_codigo_de_otro_secreto_responde_401_sin_activar(cliente_api, sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd)
    usuario_id, nombre = usuario.id, usuario.usuario
    acceso = await cliente_api.post(
        "/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CONTRASENA_CORRECTA}
    )
    datos = {"desafio_id": acceso.json()["desafio_id"]}
    secreto = secreto_como_angular(
        (await cliente_api.post("/api/auth/totp/login/configurar", json=datos)).json()["uri"]
    )
    ahora = await sesion_bd.scalar(select(func.clock_timestamp()))
    otro = base64.b32encode(secrets.token_bytes(20)).decode()  # secreto ajeno al pendiente
    malo = totp_independiente(otro, ahora)
    if malo == totp_independiente(secreto, ahora):
        pytest.skip("Coincidencia casual de códigos")
    respuesta = await cliente_api.post("/api/auth/totp/login/vincular", json={**datos, "codigo": malo})
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "VERIFICACION_INVALIDA"
    registro = await sesion_bd.scalar(
        select(UsuarioTotp)
        .where(UsuarioTotp.usuario_id == usuario_id)
        .execution_options(populate_existing=True)
    )
    assert registro.estado == "PENDIENTE" and "esart_sesion" not in cliente_api.cookies
