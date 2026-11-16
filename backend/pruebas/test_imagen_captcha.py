"""Imagen y HMAC offline: sin PostgreSQL, red ni respuestas de producción."""

import io
import socket

import pytest
from PIL import Image

from aplicacion.seguridad.imagen_captcha import ALFABETO, generar_png, generar_texto
from aplicacion.servicios.captcha_local import proteger_respuesta


def test_png_real_sin_internet(monkeypatch):
    def prohibido(*args, **kwargs):
        raise AssertionError("La generación no debe abrir conexiones")

    monkeypatch.setattr(socket, "create_connection", prohibido)
    monkeypatch.setattr(socket, "socket", prohibido)
    texto = generar_texto()
    png = generar_png(texto)
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) <= 65536
    with Image.open(io.BytesIO(png)) as imagen:
        assert imagen.size == (312, 96) and imagen.format == "PNG"
        assert not imagen.info


def test_aleatoriedad_y_alfabeto():
    codigos = [generar_texto() for _ in range(30)]
    assert len(set(codigos)) > 1
    assert all(len(c) == 6 and set(c) <= set(ALFABETO) for c in codigos)
    assert not set("01OIL25SZ8B") & set(ALFABETO)


def test_respuesta_protegida_sensible_id_contexto_no_mayusculas():
    codigo = generar_texto()
    huella = proteger_respuesta("id-unico", "contexto", codigo)
    assert len(huella) == 64 and codigo not in huella
    assert huella == proteger_respuesta("id-unico", "contexto", codigo.lower())
    assert huella != proteger_respuesta("otro-id", "contexto", codigo)
    assert huella != proteger_respuesta("id-unico", "otro-contexto", codigo)


@pytest.mark.parametrize("valor", ["", "ABCD", "A" * 500])
def test_imagen_no_acepta_entrada_arbitraria(valor):
    with pytest.raises(ValueError):
        generar_png(valor)
