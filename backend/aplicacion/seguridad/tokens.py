"""
Emisión y validación del JWT de sesión (HS256).

El token viaja SOLO dentro de la cookie httpOnly 'esart_sesion'; nunca en el
cuerpo de una respuesta ni en los registros. Su 'jti' es el id de la fila de
sesiones_usuario, lo que permite revocar la sesión desde el servidor.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from aplicacion.configuracion import obtener_configuracion

ALGORITMO_JWT = "HS256"

# Vida máxima absoluta del token. El cierre por 30 minutos de inactividad lo
# controla aparte la tabla sesiones_usuario (HU-08); este límite evita que una
# sesión con actividad constante dure indefinidamente.
HORAS_VIGENCIA_MAXIMA_TOKEN = 12

# Reclamos que todo token válido debe traer; si falta alguno se rechaza.
RECLAMOS_OBLIGATORIOS = ("sub", "jti", "iat", "exp")


@dataclass(frozen=True)
class DatosTokenSesion:
    """Lo que el servidor obtiene de un token ya validado."""

    # BIGINT de esart_ref.usuarios.id.
    usuario_id: int
    sesion_id: UUID


class TokenSesionInvalido(Exception):
    """El token no existe, está alterado, venció o no tiene la forma esperada."""


def crear_token_sesion(usuario_id: int, sesion_id: UUID) -> str:
    """Firma un JWT para la sesión indicada."""
    clave_secreta = obtener_configuracion().jwt_clave_secreta.get_secret_value()
    ahora = datetime.now(UTC)
    reclamos = {
        "sub": str(usuario_id),
        "jti": str(sesion_id),
        "iat": ahora,
        "exp": ahora + timedelta(hours=HORAS_VIGENCIA_MAXIMA_TOKEN),
    }
    return jwt.encode(reclamos, clave_secreta, algorithm=ALGORITMO_JWT)


def decodificar_token_sesion(token: str) -> DatosTokenSesion:
    """
    Valida firma, vencimiento y forma del token y devuelve sus datos.

    Lanza TokenSesionInvalido sin dar detalles: quien llama responde siempre con
    el mismo error 401, sin explicar al cliente qué falló.
    """
    clave_secreta = obtener_configuracion().jwt_clave_secreta.get_secret_value()
    try:
        # algorithms fijo: impide el ataque de cambiar el algoritmo a 'none' u otro.
        reclamos = jwt.decode(
            token,
            clave_secreta,
            algorithms=[ALGORITMO_JWT],
            options={"require": list(RECLAMOS_OBLIGATORIOS)},
        )
        usuario_id = int(reclamos["sub"])
        if usuario_id <= 0:
            raise ValueError("usuario_id inválido")
        return DatosTokenSesion(usuario_id=usuario_id, sesion_id=UUID(reclamos["jti"]))
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise TokenSesionInvalido from error
