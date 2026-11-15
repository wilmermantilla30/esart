"""Configuración de conexión compartida por API, Alembic y herramientas."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

RUTA_ARCHIVO_ENV = Path(__file__).resolve().parents[3] / ".env"


def validar_url_base_datos(valor: str, entorno: str) -> None:
    """Valida la conexión sin incluir credenciales en los errores."""
    if any(marcador in valor for marcador in ("CAMBIAR", "REEMPLAZAR")):
        raise ValueError("URL_BASE_DATOS todavía tiene un valor de ejemplo. Reemplácelo.")
    if not valor.startswith("postgresql+asyncpg://"):
        raise ValueError("URL_BASE_DATOS debe empezar por 'postgresql+asyncpg://'.")
    try:
        url = make_url(valor)
        puerto = url.port
    except (ArgumentError, ValueError):
        raise ValueError("URL_BASE_DATOS no es una URL válida de PostgreSQL.") from None
    if not url.host or not url.username or not url.password or (puerto is not None and puerto < 1):
        raise ValueError("URL_BASE_DATOS requiere servidor, usuario, contraseña y puerto válido.")
    if url.username.lower() == "postgres":
        raise ValueError("La API no puede utilizar el superusuario postgres.")
    if entorno != "pruebas" and (url.username != "esart_aplicacion" or url.database != "esart_db"):
        raise ValueError("La API debe utilizar el usuario esart_aplicacion y la base esart_db.")


class ConfiguracionConexion(BaseSettings):
    """Las migraciones no requieren secretos JWT ni credenciales de administrador."""

    model_config = SettingsConfigDict(
        env_file=RUTA_ARCHIVO_ENV,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )
    entorno: Literal["desarrollo", "pruebas", "produccion"] = "desarrollo"
    url_base_datos: SecretStr
    segundos_espera_conexion: int = Field(default=5, ge=1, le=60)
    nivel_registro: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def validar_conexion(self) -> "ConfiguracionConexion":
        validar_url_base_datos(self.url_base_datos.get_secret_value(), self.entorno)
        return self


@lru_cache
def obtener_configuracion_conexion() -> ConfiguracionConexion:
    """Lee la misma URL y archivo raíz que la API."""
    return ConfiguracionConexion()
