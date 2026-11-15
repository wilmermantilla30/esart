"""Alembic valida conexión sin exigir secretos de autenticación de la API."""

import pytest
from pydantic import ValidationError

from aplicacion.base_datos.configuracion import ConfiguracionConexion


def test_conexion_no_requiere_jwt_ni_administrador(monkeypatch):
    for nombre in ("JWT_CLAVE_SECRETA", "ADMIN_USUARIO", "ADMIN_HASH_CONTRASENA"):
        monkeypatch.delenv(nombre, raising=False)
    configuracion = ConfiguracionConexion(_env_file=None)
    assert configuracion.entorno == "pruebas"
    assert "clave_pruebas" not in repr(configuracion)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://postgres:clave@localhost/esart_pruebas",
        "postgresql://usuario:clave@localhost/esart_pruebas",
        "postgresql+asyncpg://usuario@localhost/esart_pruebas",
    ],
)
def test_conexion_rechaza_destinos_inseguros(url):
    with pytest.raises(ValidationError):
        ConfiguracionConexion(_env_file=None, url_base_datos=url)


def test_conexion_produccion_no_admite_base_de_pruebas():
    with pytest.raises(ValidationError, match="esart_db"):
        ConfiguracionConexion(_env_file=None, entorno="produccion")
