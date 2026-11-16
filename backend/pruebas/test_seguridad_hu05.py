"""Pruebas de contraseñas (bcrypt) y del JWT de sesión (HU-05)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from aplicacion.configuracion import obtener_configuracion
from aplicacion.seguridad.contrasenas import generar_hash_contrasena, verificar_contrasena
from aplicacion.seguridad.tokens import (
    ALGORITMO_JWT,
    TokenSesionInvalido,
    crear_token_sesion,
    decodificar_token_sesion,
)

CONTRASENA_DE_PRUEBA = "Clave-de-prueba-1"
HASH_DE_PRUEBA = generar_hash_contrasena(CONTRASENA_DE_PRUEBA)


# --- Contraseñas ---------------------------------------------------------------


def test_hash_bcrypt_verifica_la_contrasena_correcta():
    assert HASH_DE_PRUEBA.startswith("$2b$12$")
    assert verificar_contrasena(CONTRASENA_DE_PRUEBA, HASH_DE_PRUEBA) is True


def test_hash_bcrypt_rechaza_la_contrasena_incorrecta():
    assert verificar_contrasena("otra-clave", HASH_DE_PRUEBA) is False


def test_verificar_no_lanza_error_con_contrasena_demasiado_larga_ni_hash_danado():
    assert verificar_contrasena("x" * 73, HASH_DE_PRUEBA) is False
    assert verificar_contrasena(CONTRASENA_DE_PRUEBA, "no-es-un-hash") is False


def test_generar_hash_rechaza_mas_de_72_bytes():
    # "ñ" ocupa 2 bytes en UTF-8: 37 caracteres son 74 bytes.
    with pytest.raises(ValueError):
        generar_hash_contrasena("ñ" * 37)


# --- JWT -----------------------------------------------------------------------


def _clave_jwt() -> str:
    return obtener_configuracion().jwt_clave_secreta.get_secret_value()


def test_token_valido_devuelve_usuario_y_sesion():
    usuario_id, sesion_id = 42, uuid.uuid4()

    datos = decodificar_token_sesion(crear_token_sesion(usuario_id, sesion_id))

    assert datos.usuario_id == usuario_id
    assert datos.sesion_id == sesion_id


def test_token_alterado_es_rechazado():
    token = crear_token_sesion(7, uuid.uuid4())
    token_alterado = token[:-2] + ("AA" if not token.endswith("AA") else "BB")

    with pytest.raises(TokenSesionInvalido):
        decodificar_token_sesion(token_alterado)


def test_token_firmado_con_otra_clave_es_rechazado():
    ahora = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "7", "jti": str(uuid.uuid4()), "iat": ahora, "exp": ahora + timedelta(hours=1)},
        "otra-clave-que-tambien-tiene-mas-de-32-caracteres",
        algorithm=ALGORITMO_JWT,
    )
    with pytest.raises(TokenSesionInvalido):
        decodificar_token_sesion(token)


def test_token_vencido_es_rechazado():
    hace_dos_horas = datetime.now(UTC) - timedelta(hours=2)
    token = jwt.encode(
        {
            "sub": "7",
            "jti": str(uuid.uuid4()),
            "iat": hace_dos_horas,
            "exp": hace_dos_horas + timedelta(hours=1),
        },
        _clave_jwt(),
        algorithm=ALGORITMO_JWT,
    )
    with pytest.raises(TokenSesionInvalido):
        decodificar_token_sesion(token)


def test_token_sin_firma_algoritmo_none_es_rechazado():
    token = jwt.encode({"sub": "7", "jti": str(uuid.uuid4())}, key=None, algorithm="none")
    with pytest.raises(TokenSesionInvalido):
        decodificar_token_sesion(token)


def test_token_sin_reclamos_obligatorios_es_rechazado():
    token = jwt.encode({"sub": "7"}, _clave_jwt(), algorithm=ALGORITMO_JWT)
    with pytest.raises(TokenSesionInvalido):
        decodificar_token_sesion(token)


def test_token_con_usuario_no_numerico_o_no_positivo_es_rechazado():
    ahora = datetime.now(UTC)
    for sujeto in ("abc", "0", "-3"):
        token = jwt.encode(
            {"sub": sujeto, "jti": str(uuid.uuid4()), "iat": ahora, "exp": ahora + timedelta(hours=1)},
            _clave_jwt(),
            algorithm=ALGORITMO_JWT,
        )
        with pytest.raises(TokenSesionInvalido):
            decodificar_token_sesion(token)
