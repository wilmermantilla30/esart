"""
Firma desde el celular: piezas sin base de datos.

El flujo completo con PostgreSQL (solicitud, QR, TOTP real, PDF firmado, evidencias y auditoría)
está en herramientas/probar_firma_movil_aislada.py, que usa un clúster efímero.
"""

import base64
import io
from datetime import datetime

import pytest
from PIL import Image, ImageDraw

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.nucleo.registro import ocultar_datos_sensibles
from aplicacion.reportes.comun import FirmaDocumento, datos_a_json, datos_desde_json
from aplicacion.reportes.maestro import datos_de_ejemplo, generar_documento
from aplicacion.servicios.firma_movil import hash_token, validar_rubrica


def png(ancho=600, alto=200, trazo=True, formato="PNG", fondo=(0, 0, 0, 0)) -> bytes:
    imagen = Image.new("RGBA", (ancho, alto), fondo)
    if trazo:
        ImageDraw.Draw(imagen).line(
            [(20, alto - 20), (ancho // 2, 20), (ancho - 20, alto - 30)], fill=(0, 0, 80, 255), width=5
        )
    salida = io.BytesIO()
    imagen.convert("RGB" if formato == "JPEG" else "RGBA").save(salida, formato)
    return salida.getvalue()


def data_url(contenido: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(contenido).decode()


def test_rubrica_valida_se_recodifica_sin_metadatos():
    original = png()
    limpia = validar_rubrica(data_url(original))
    with Image.open(io.BytesIO(limpia)) as imagen:
        assert imagen.format == "PNG" and imagen.mode == "RGBA" and imagen.size == (600, 200)
        assert not imagen.info.get("exif")


@pytest.mark.parametrize(
    ("contenido", "codigo"),
    [
        (png(trazo=False), "RUBRICA_VACIA"),
        (png(trazo=False, fondo=(255, 255, 255, 255)), "RUBRICA_VACIA"),  # lienzo blanco sin trazo
        (png(formato="JPEG"), "RUBRICA_INVALIDA"),
        (png(ancho=40, alto=40), "RUBRICA_INVALIDA"),
        (b"no es una imagen", "RUBRICA_INVALIDA"),
    ],
)
def test_rubricas_rechazadas(contenido, codigo):
    with pytest.raises(ErrorAplicacion) as error:
        validar_rubrica(data_url(contenido))
    assert error.value.codigo == codigo


def test_rubrica_con_base64_corrupto():
    with pytest.raises(ErrorAplicacion) as error:
        validar_rubrica("data:image/png;base64,%%%no-base64%%%")
    assert error.value.codigo == "RUBRICA_INVALIDA"


def test_el_token_solo_se_guarda_como_sha256():
    assert len(hash_token("abc")) == 64 and hash_token("abc") != hash_token("abd")


def test_el_token_del_qr_no_queda_en_los_logs():
    token = "Zx9" + "a" * 40
    linea = f'127.0.0.1 - "GET /api/firma-movil/{token}/pdf HTTP/1.1" 200'
    assert token not in ocultar_datos_sensibles(linea)
    assert token not in ocultar_datos_sensibles(f"http://192.168.1.5:4200/firma/{token}")


def test_datos_del_documento_ida_y_vuelta_json():
    datos = datos_de_ejemplo()
    assert datos_desde_json(datos_a_json(datos)) == datos


@pytest.mark.parametrize("tipo", ["CERTIFICACION", "OFICIO_REMISORIO"])
def test_pdf_firmado_incluye_la_rubrica(tipo):
    sin_firma, _ = generar_documento(tipo, datos_de_ejemplo())
    firma = FirmaDocumento(png(), "CR Juan Pérez", "Director", datetime(2026, 11, 19, 9, 0), "F-ABC12345")
    firmado, _ = generar_documento(tipo, datos_desde_json(datos_a_json(datos_de_ejemplo()), firma))
    assert (
        firmado.startswith(b"%PDF-") and b"/Subtype /Image" in firmado and b"/Subtype /Image" not in sin_firma
    )
