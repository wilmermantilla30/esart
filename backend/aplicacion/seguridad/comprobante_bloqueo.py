"""Comprobante de contexto previo; nunca sustituye una sesión autenticada."""

import hashlib
import hmac
import math
from datetime import UTC, datetime

import jwt
from fastapi import Response

from aplicacion.configuracion import obtener_configuracion

COOKIE = "esart_contexto_bloqueo"
AUDIENCIA = "ESART/CONTEXTO-BLOQUEO/V1"


def clave() -> bytes:
    raiz = obtener_configuracion().jwt_clave_secreta.get_secret_value().encode()
    return hmac.new(raiz, AUDIENCIA.encode(), hashlib.sha256).digest()


def escribir(respuesta: Response, nombre: str, hasta: str, intento_actual: dict | None = None):
    fin = datetime.fromisoformat(hasta)
    token = jwt.encode(
        {
            "sub": nombre,
            "aud": AUDIENCIA,
            "exp": math.ceil(fin.timestamp()),
            "intento_actual": intento_actual,
        },
        clave(),
        algorithm="HS256",
    )
    respuesta.set_cookie(
        COOKIE,
        token,
        max_age=max(0, math.ceil((fin - datetime.now(UTC)).total_seconds())),
        httponly=True,
        secure=obtener_configuracion().cookie_segura,
        samesite="strict",
        path="/api/auth",
    )


def leer(token: str | None) -> str | None:
    datos = leer_datos(token)
    return datos["sub"] if datos else None


def leer_datos(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        datos = jwt.decode(
            token,
            clave(),
            algorithms=["HS256"],
            audience=AUDIENCIA,
            options={"require": ["sub", "aud", "exp"]},
        )
        nombre = datos["sub"]
        return datos if isinstance(nombre, str) and 3 <= len(nombre) <= 80 else None
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


def borrar(respuesta: Response):
    respuesta.delete_cookie(
        COOKIE,
        path="/api/auth",
        httponly=True,
        secure=obtener_configuracion().cookie_segura,
        samesite="strict",
    )
