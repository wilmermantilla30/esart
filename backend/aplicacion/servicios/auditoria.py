"""
Auditoría de acciones (HU-11): quién, qué, cuándo y desde dónde, en esart.auditoria_eventos.

- La tabla es inmutable (trigger) y la cuenta de la API solo puede insertar y leer.
- Nunca se guardan contraseñas ni tokens: el detalle se revisa antes de insertar y, si trae una
  clave sospechosa, se rechaza (es un error de programación, no un dato del usuario).
- Si la auditoría no se puede escribir, la acción falla: una consulta sin registro no debe
  quedar respondida (cumplimiento de la Ley 1581).
"""

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos import AuditoriaEvento
from aplicacion.seguridad.sesion_http import obtener_ip_cliente

# Acciones registrables (deben coincidir con el CHECK de la migración p0007).
LOGIN_EXITOSO = "LOGIN_EXITOSO"
LOGIN_FALLIDO = "LOGIN_FALLIDO"
USUARIO_BLOQUEADO = "USUARIO_BLOQUEADO"
CIERRE_SESION = "CIERRE_SESION"
CONSULTA_ARTILLERO = "CONSULTA_ARTILLERO"
CONSULTA_HABILITADOS = "CONSULTA_HABILITADOS"
CONSULTA_NO_HABILITADOS = "CONSULTA_NO_HABILITADOS"
CONSULTA_RESUMEN = "CONSULTA_RESUMEN"
ACCESO_DENEGADO = "ACCESO_DENEGADO"
PERMISOS_ROL_MODIFICADOS = "PERMISOS_ROL_MODIFICADOS"
PERMISOS_USUARIO_MODIFICADOS = "PERMISOS_USUARIO_MODIFICADOS"

# Fragmentos de clave que jamás pueden aparecer en el detalle de un evento.
FRAGMENTOS_PROHIBIDOS = ("contrasena", "password", "token", "hash", "secreto", "clave", "captcha_respuesta")

LONGITUD_MAXIMA_AGENTE_USUARIO = 300
LONGITUD_MAXIMA_NOMBRE_USUARIO = 80


def _validar_detalle(detalle: Any, ruta: str = "detalle") -> None:
    """Recorre el detalle y rechaza claves que parezcan credenciales."""
    if isinstance(detalle, Mapping):
        for clave, valor in detalle.items():
            if any(fragmento in str(clave).lower() for fragmento in FRAGMENTOS_PROHIBIDOS):
                raise ValueError(f"La auditoría no admite la clave '{ruta}.{clave}' (posible credencial).")
            _validar_detalle(valor, f"{ruta}.{clave}")
    elif isinstance(detalle, list | tuple):
        for posicion, valor in enumerate(detalle):
            _validar_detalle(valor, f"{ruta}[{posicion}]")


async def registrar_evento(
    sesion: AsyncSession,
    accion: str,
    request: Request | None = None,
    *,
    usuario_id: int | None = None,
    nombre_usuario: str | None = None,
    documento: str | None = None,
    resultado: str | None = None,
    detalle: dict | None = None,
) -> None:
    """Inserta un evento y lo confirma en la base (commit)."""
    _validar_detalle(detalle)
    agente = request.headers.get("user-agent") if request else None
    sesion.add(
        AuditoriaEvento(
            accion=accion,
            usuario_id=usuario_id,
            nombre_usuario=(nombre_usuario or None) and nombre_usuario[:LONGITUD_MAXIMA_NOMBRE_USUARIO],
            numero_documento_consultado=documento,
            resultado=resultado,
            direccion_ip=obtener_ip_cliente(request) if request else None,
            agente_usuario=(agente or None) and agente[:LONGITUD_MAXIMA_AGENTE_USUARIO],
            detalle=detalle,
        )
    )
    await sesion.commit()
