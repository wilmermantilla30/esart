"""Pruebas del filtro que oculta datos sensibles en los logs."""

import logging

from aplicacion.nucleo.registro import FiltroDatosSensibles, ocultar_datos_sensibles


def test_oculta_contrasena_en_pares_clave_valor():
    texto = ocultar_datos_sensibles('login fallido contrasena=Secreta123 "password": "otra"')

    assert "Secreta123" not in texto
    assert "otra" not in texto


def test_oculta_contrasena_en_url_de_base_de_datos():
    texto = ocultar_datos_sensibles("conectando a postgresql+asyncpg://esart:ClaveBD@localhost/esart_db")

    assert "ClaveBD" not in texto
    assert "esart:[OCULTO]@localhost" in texto


def test_oculta_jwt_y_bearer():
    jwt_falso = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.firmaFalsa123"
    texto = ocultar_datos_sensibles(f"cabecera Authorization Bearer {jwt_falso}")

    assert jwt_falso not in texto


def test_oculta_hash_bcrypt():
    hash_falso = "$2b$12$" + "b" * 53

    assert hash_falso not in ocultar_datos_sensibles(f"hash leido {hash_falso}")


def test_oculta_cedula_en_ruta_de_verificacion():
    texto = ocultar_datos_sensibles('GET /api/verificar/artillero/1234567890 HTTP/1.1')

    assert "1234567890" not in texto
    assert "/artillero/[CEDULA_OCULTA]" in texto


def test_filtro_limpia_argumentos_por_posicion_como_los_de_uvicorn():
    # uvicorn escribe sus logs de acceso con argumentos por posición.
    registro = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1", "GET", "/api/verificar/artillero/1234567890", "1.1", 200),
        exc_info=None,
    )

    FiltroDatosSensibles().filter(registro)

    assert "1234567890" not in registro.getMessage()
    assert registro.args[4] == 200  # los valores que no son texto quedan intactos


def test_texto_sin_datos_sensibles_queda_igual():
    texto = "ESART iniciando en entorno desarrollo"

    assert ocultar_datos_sensibles(texto) == texto
