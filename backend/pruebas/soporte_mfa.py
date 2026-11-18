"""Recorrido HTTP real de vinculación para cuentas nuevas del laboratorio aislado."""

from urllib.parse import parse_qs, urlparse

import pyotp


async def completar_vinculacion(cliente, primer_factor):
    assert primer_factor.status_code == 202 and primer_factor.json()["configuracion_requerida"]
    datos = {"desafio_id": primer_factor.json()["desafio_id"]}
    qr = await cliente.post("/api/auth/totp/login/configurar", json=datos)
    assert qr.status_code == 200
    secreto = parse_qs(urlparse(qr.json()["uri"]).query)["secret"][0]
    fin = await cliente.post(
        "/api/auth/totp/login/vincular", json={**datos, "codigo": pyotp.TOTP(secreto).now()}
    )
    assert fin.status_code == 200
    return fin
