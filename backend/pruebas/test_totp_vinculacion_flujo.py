"""Regresión del flujo de vinculación TOTP: QR/clave manual, verificación, vencimiento,
regeneración del secreto pendiente y múltiples intentos. Sin base de datos ni secretos reales."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, unquote, urlparse

import pyotp
import pytest

from aplicacion.modelos.totp import UsuarioTotp
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import totp

AHORA = datetime(2026, 11, 19, 2, 21, 50, tzinfo=UTC)


@pytest.fixture
def clave(monkeypatch):
    import base64
    import secrets

    from pydantic import SecretStr

    from aplicacion.configuracion import obtener_configuracion

    cfg = obtener_configuracion()
    monkeypatch.setattr(cfg, "totp_habilitado", True)
    monkeypatch.setattr(
        cfg, "totp_clave_cifrado", SecretStr(base64.b64encode(secrets.token_bytes(32)).decode())
    )


@pytest.fixture
def reloj(monkeypatch):
    estado = {"ahora": AHORA}
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(side_effect=lambda _s: estado["ahora"]))
    return estado


def servicio_con(registro, monkeypatch):
    sesion = SimpleNamespace(
        add=MagicMock(),
        commit=AsyncMock(),
        flush=AsyncMock(),
        execute=AsyncMock(),
        scalar=AsyncMock(return_value="admin.esart"),
    )
    servicio = totp.TotpService(sesion)
    monkeypatch.setattr(servicio, "registro", AsyncMock(return_value=registro))
    monkeypatch.setattr(servicio, "auditar", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(servicio, "respuesta_uniforme", AsyncMock())
    return servicio, sesion


def secreto_de_uri(uri):
    partes = urlparse(uri)
    return partes, parse_qs(partes.query)


def pendiente(secreto, expira):
    return UsuarioTotp(
        usuario_id=1,
        estado="PENDIENTE",
        secreto_cifrado=totp.TotpService.cifrar(1, secreto),
        expira_configuracion_en=expira,
        ultimo_intervalo_aceptado=None,
    )


@pytest.mark.anyio
async def test_qr_y_clave_manual_corresponden_al_secreto_almacenado(clave, reloj, monkeypatch):
    servicio, sesion = servicio_con(None, monkeypatch)
    salida = await servicio.configurar_verificado(1, "127.0.0.1")
    registro = sesion.add.call_args.args[0]
    partes, params = secreto_de_uri(salida["uri"])
    # Google Authenticator: otpauth://totp, SHA1, 6 dígitos y 30 s son los valores por defecto.
    assert partes.scheme == "otpauth" and partes.netloc == "totp"
    assert unquote(partes.path) == "/ESART:admin.esart (19-11 02h21 UTC)" and params["issuer"] == ["ESART"]
    assert set(params) == {"secret", "issuer"}
    assert params["secret"] == [totp.TotpService.descifrar(registro)]
    assert registro.estado == "PENDIENTE"
    assert registro.expira_configuracion_en == AHORA + timedelta(minutes=10)
    # La URI se interpreta igual que en un autenticador: mismo secreto, SHA1, 6 dígitos y 30 s.
    leido = pyotp.parse_uri(salida["uri"])
    assert (leido.secret, leido.digest, leido.digits, leido.interval) == (
        totp.TotpService.descifrar(registro),
        hashlib.sha1,
        6,
        30,
    )
    assert leido.issuer == "ESART" and leido.name == "admin.esart (19-11 02h21 UTC)"


@pytest.mark.anyio
async def test_etiqueta_recuperada_conserva_fecha_de_creacion_y_secreto(clave, reloj, monkeypatch):
    servicio, sesion = servicio_con(None, monkeypatch)
    primera = await servicio.configurar_verificado(1, "127.0.0.1")
    registro = sesion.add.call_args.args[0]
    cifrado = registro.secreto_cifrado
    # Siete minutos después el QR recuperado identifica el mismo secreto con la misma fecha.
    reloj["ahora"] = AHORA + timedelta(minutes=7)
    servicio2, _ = servicio_con(registro, monkeypatch)
    segunda = await servicio2.configurar_verificado(1, "127.0.0.1")
    assert segunda["uri"] == primera["uri"] and registro.secreto_cifrado == cifrado
    servicio2.auditar.assert_awaited_with(1, "TOTP_CONFIGURACION_RECUPERADA", "CORRECTO", "127.0.0.1")
    # Vencido, el secreto nuevo lleva otra fecha: el usuario distingue la entrada vigente.
    reloj["ahora"] = AHORA + timedelta(minutes=12)
    tercera = await servicio2.configurar_verificado(1, "127.0.0.1")
    nuevo = pyotp.parse_uri(tercera["uri"])
    assert nuevo.name == "admin.esart (19-11 02h33 UTC)"
    assert nuevo.secret == totp.TotpService.descifrar(registro) != pyotp.parse_uri(primera["uri"]).secret


def test_etiqueta_en_utc_sin_dos_puntos_en_la_hora():
    from datetime import timezone

    bogota = timezone(timedelta(hours=-5))
    expira = datetime(2026, 11, 18, 21, 55, 46, tzinfo=bogota)  # 02:55:46 UTC
    etiqueta = totp.TotpService.etiqueta_vinculacion("admin.esart", expira)
    assert etiqueta == "admin.esart (19-11 02h45 UTC)" and ":" not in etiqueta


@pytest.mark.anyio
async def test_codigo_de_la_uri_con_etiqueta_vincula(clave, reloj, monkeypatch):
    servicio, sesion = servicio_con(None, monkeypatch)
    salida = await servicio.configurar_verificado(1, "127.0.0.1")
    registro = sesion.add.call_args.args[0]
    servicio2, _ = servicio_con(registro, monkeypatch)
    codigo = pyotp.parse_uri(salida["uri"]).at(AHORA)
    resultado = await servicio2.confirmar(1, codigo, "127.0.0.1", identidad_verificada=True)
    assert resultado["activo"] and registro.estado == "ACTIVO"


@pytest.mark.anyio
async def test_vinculacion_correcta_con_codigo_del_qr(clave, reloj, monkeypatch):
    secreto = pyotp.random_base32()
    registro = pendiente(secreto, AHORA + timedelta(minutes=10))
    servicio, sesion = servicio_con(registro, monkeypatch)
    codigo = pyotp.TOTP(secreto, digits=6, interval=30, digest=hashlib.sha1).at(AHORA)
    salida = await servicio.confirmar(1, codigo, "127.0.0.1", identidad_verificada=True)
    assert salida["activo"] and registro.estado == "ACTIVO"
    assert registro.expira_configuracion_en is None
    assert registro.ultimo_intervalo_aceptado == int(AHORA.timestamp()) // 30
    sesion.commit.assert_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "desfase,aceptado", [(-30, True), (30, True), (-60, False), (60, False), (-300, False)]
)
async def test_tolerancia_de_reloj_es_un_paso(clave, reloj, monkeypatch, desfase, aceptado):
    secreto = pyotp.random_base32()
    registro = pendiente(secreto, AHORA + timedelta(minutes=10))
    servicio, _ = servicio_con(registro, monkeypatch)
    codigo = pyotp.TOTP(secreto).at(AHORA + timedelta(seconds=desfase))
    assert await servicio.verificar(registro, codigo) is aceptado


@pytest.mark.anyio
async def test_codigo_invalido_o_de_secreto_anterior_se_rechaza(clave, reloj, monkeypatch):
    anterior, actual = pyotp.random_base32(), pyotp.random_base32()
    registro = pendiente(actual, AHORA + timedelta(minutes=10))
    servicio, sesion = servicio_con(registro, monkeypatch)
    for codigo in (
        pyotp.TOTP(anterior).at(AHORA),
        "000000" if pyotp.TOTP(actual).at(AHORA) != "000000" else "111111",
    ):
        with pytest.raises(ErrorAplicacion) as error:
            await servicio.confirmar(1, codigo, "127.0.0.1", identidad_verificada=True)
        assert error.value.codigo == "VERIFICACION_INVALIDA"
    assert registro.estado == "PENDIENTE"
    servicio.auditar.assert_awaited_with(1, "TOTP_INVALIDO", "DENEGADO", "127.0.0.1")


@pytest.mark.anyio
async def test_pendiente_vencido_rechaza_incluso_codigo_correcto(clave, reloj, monkeypatch):
    secreto = pyotp.random_base32()
    registro = pendiente(secreto, AHORA)
    servicio, _ = servicio_con(registro, monkeypatch)
    with pytest.raises(ErrorAplicacion):
        await servicio.confirmar(1, pyotp.TOTP(secreto).at(AHORA), "127.0.0.1", identidad_verificada=True)
    assert registro.estado == "PENDIENTE"


@pytest.mark.anyio
async def test_pendiente_vigente_conserva_secreto_y_no_se_regenera(clave, reloj, monkeypatch):
    secreto = pyotp.random_base32()
    registro = pendiente(secreto, AHORA + timedelta(minutes=5))
    cifrado = registro.secreto_cifrado
    servicio, sesion = servicio_con(registro, monkeypatch)
    salida = await servicio.configurar_verificado(1, "127.0.0.1")
    assert secreto_de_uri(salida["uri"])[1]["secret"] == [secreto]
    assert registro.secreto_cifrado == cifrado
    servicio.auditar.assert_awaited_with(1, "TOTP_CONFIGURACION_RECUPERADA", "CORRECTO", "127.0.0.1")
    # Validar códigos (fallidos) tampoco cambia el secreto.
    with pytest.raises(ErrorAplicacion):
        await servicio.confirmar(1, "123456", "127.0.0.1", identidad_verificada=True)
    assert registro.secreto_cifrado == cifrado


@pytest.mark.anyio
async def test_pendiente_vencido_regenera_secreto_e_invalida_el_anterior(clave, reloj, monkeypatch):
    anterior = pyotp.random_base32()
    registro = pendiente(anterior, AHORA - timedelta(seconds=1))
    servicio, _ = servicio_con(registro, monkeypatch)
    salida = await servicio.configurar_verificado(1, "127.0.0.1")
    nuevo = secreto_de_uri(salida["uri"])[1]["secret"][0]
    assert nuevo != anterior and totp.TotpService.descifrar(registro) == nuevo
    servicio.auditar.assert_awaited_with(1, "TOTP_CONFIGURACION_PENDIENTE", "CORRECTO", "127.0.0.1")
    with pytest.raises(ErrorAplicacion):
        await servicio.confirmar(1, pyotp.TOTP(anterior).at(AHORA), "127.0.0.1", identidad_verificada=True)
    assert await servicio.verificar(registro, pyotp.TOTP(nuevo).at(AHORA))


@pytest.mark.anyio
async def test_multiples_intentos_cuentan_y_cancelan_al_quinto(clave, reloj, monkeypatch):
    secreto = pyotp.random_base32()
    registro = pendiente(secreto, AHORA + timedelta(minutes=10))
    servicio, _ = servicio_con(registro, monkeypatch)
    desafio = SimpleNamespace(intentos=0, estado="PENDIENTE", correlacion_id=uuid.uuid4())
    monkeypatch.setattr(
        servicio, "contexto_vinculacion", AsyncMock(return_value=(SimpleNamespace(id=1), desafio))
    )
    malo = "000000" if pyotp.TOTP(secreto).at(AHORA) != "000000" else "111111"
    for intento in range(1, 6):
        with pytest.raises(ErrorAplicacion):
            await servicio.vincular_login(uuid.uuid4(), "nonce", malo, "127.0.0.1")
        assert desafio.intentos == intento
    assert desafio.estado == "CANCELADO" and registro.estado == "PENDIENTE"
