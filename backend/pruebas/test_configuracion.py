"""Pruebas de la validación de la configuración (la aplicación no debe arrancar insegura)."""

import pytest
from pydantic import ValidationError

from aplicacion.configuracion import Configuracion
from pruebas.conftest import VARIABLES_ENTORNO_PRUEBAS


def crear_configuracion_con(monkeypatch, **variables_cambiadas: str) -> Configuracion:
    """Crea una Configuracion con las variables de prueba, cambiando solo las indicadas."""
    for nombre, valor in {**VARIABLES_ENTORNO_PRUEBAS, **variables_cambiadas}.items():
        monkeypatch.setenv(nombre, valor)
    # _env_file=None: la prueba no debe leer el .env del desarrollador.
    return Configuracion(_env_file=None)


def test_configuracion_valida_se_acepta(monkeypatch):
    configuracion = crear_configuracion_con(monkeypatch)

    assert configuracion.entorno == "pruebas"
    assert configuracion.minutos_inactividad_sesion == 30


def test_rechaza_clave_jwt_corta(monkeypatch):
    with pytest.raises(ValidationError, match="JWT_CLAVE_SECRETA"):
        crear_configuracion_con(monkeypatch, JWT_CLAVE_SECRETA="corta")


def test_rechaza_contrasena_de_admin_en_texto_plano(monkeypatch):
    with pytest.raises(ValidationError, match="hash bcrypt"):
        crear_configuracion_con(monkeypatch, ADMIN_HASH_CONTRASENA="MiContrasena123")


def test_rechaza_valores_de_ejemplo_sin_reemplazar(monkeypatch):
    with pytest.raises(ValidationError, match="valor de ejemplo"):
        crear_configuracion_con(
            monkeypatch, JWT_CLAVE_SECRETA="CAMBIAR_POR_UNA_CLAVE_ALEATORIA_DE_MINIMO_32_CARACTERES"
        )


def test_rechaza_url_sin_controlador_asincrono(monkeypatch):
    with pytest.raises(ValidationError, match="asyncpg"):
        crear_configuracion_con(monkeypatch, URL_BASE_DATOS="postgresql://usuario:clave@localhost/esart_db")


def test_produccion_exige_cookie_segura(monkeypatch):
    with pytest.raises(ValidationError, match="COOKIE_SEGURA"):
        crear_configuracion_con(monkeypatch, ENTORNO="produccion", COOKIE_SEGURA="false")


def test_error_de_configuracion_no_revela_el_secreto(monkeypatch):
    secreto_corto = "secreto-que-no-debe-aparecer"
    with pytest.raises(ValidationError) as error:
        crear_configuracion_con(monkeypatch, JWT_CLAVE_SECRETA=secreto_corto)

    assert secreto_corto not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://postgres:clave@localhost/esart_db",
        "postgresql+asyncpg://otro:clave@localhost/esart_db",
        "postgresql+asyncpg://esart_aplicacion:clave@localhost/otra_db",
        "postgresql+asyncpg://esart_aplicacion:clave@localhost:invalido/esart_db",
        "postgresql+asyncpg://esart_aplicacion@localhost/esart_db",
    ],
)
def test_rechaza_conexion_insegura_o_incorrecta(monkeypatch, url):
    with pytest.raises(ValidationError):
        crear_configuracion_con(monkeypatch, ENTORNO="desarrollo", URL_BASE_DATOS=url)


def test_acepta_cuenta_aplicacion_en_desarrollo(monkeypatch):
    configuracion = crear_configuracion_con(
        monkeypatch,
        ENTORNO="desarrollo",
        URL_BASE_DATOS="postgresql+asyncpg://esart_aplicacion:clave@localhost:5432/esart_db",
    )
    assert configuracion.entorno == "desarrollo"


def test_error_de_campo_no_revela_entradas(monkeypatch):
    valor_invalido = "valor-privado-no-valido"
    with pytest.raises(ValidationError) as error:
        crear_configuracion_con(monkeypatch, COOKIE_SEGURA=valor_invalido)
    assert valor_invalido not in str(error.value)
