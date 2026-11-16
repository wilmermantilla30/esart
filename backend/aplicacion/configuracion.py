"""
Configuración central de ESART.

Lee las variables de entorno (en desarrollo, desde el archivo .env) y las valida
al arrancar. Si falta una variable obligatoria o tiene un valor inseguro, la
aplicación NO arranca: es preferible fallar al inicio que funcionar en producción
con una configuración insegura.

Los valores secretos se guardan como SecretStr: si alguien imprime la
configuración o aparece en un error, se muestran como '**********'.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aplicacion.base_datos.configuracion import validar_url_base_datos

# Longitud mínima de la clave del JWT. HS256 usa una clave de 256 bits;
# 32 caracteres aleatorios es el mínimo razonable.
LONGITUD_MINIMA_CLAVE_JWT = 32

# Forma de un hash bcrypt: $2a$, $2b$ o $2y$, costo de dos dígitos y 53 caracteres.
PATRON_HASH_BCRYPT = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")

# Ruta operativa única: backend/.env, independiente del directorio de ejecución.
# Se calcula desde la ubicación de este archivo para que funcione sin importar
# desde qué carpeta se ejecute uvicorn o pytest.
# backend/aplicacion/configuracion.py -> parents[1]=backend.
RUTA_ARCHIVO_ENV = Path(__file__).resolve().parents[1] / ".env"

# Textos de los valores de ejemplo de .env.ejemplo. Si siguen presentes,
# significa que alguien copió el archivo sin reemplazar los secretos.
MARCADORES_VALOR_DE_EJEMPLO = ("CAMBIAR", "REEMPLAZAR")


class Configuracion(BaseSettings):
    """Variables de entorno de la aplicación, ya validadas y tipadas."""

    # Cada atributo se lee de la variable de entorno con el mismo nombre en
    # mayúsculas (ej. url_base_datos <- URL_BASE_DATOS).
    model_config = SettingsConfigDict(
        env_file=RUTA_ARCHIVO_ENV,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # --- Generales ---
    entorno: Literal["desarrollo", "pruebas", "produccion"] = "desarrollo"
    nombre_aplicacion: str = "ESART"
    nivel_registro: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Base de datos ---
    url_base_datos: SecretStr
    tamano_pool_conexiones: int = Field(default=10, ge=1, le=100)
    segundos_espera_conexion: int = Field(default=5, ge=1, le=60)

    # --- Sesión ---
    jwt_clave_secreta: SecretStr
    minutos_inactividad_sesion: int = Field(default=30, ge=1, le=480)
    limite_intentos_ip: int = Field(default=30, ge=1, le=1000)
    ventana_intentos_ip_segundos: int = Field(default=900, ge=60, le=86400)
    limite_generacion_captcha_ip: int = Field(default=20, ge=1, le=100)
    ventana_generacion_captcha_segundos: int = Field(default=300, ge=60, le=3600)
    cookie_segura: bool = True

    # --- Administrador inicial ---
    admin_usuario: str = Field(min_length=3, max_length=60)
    admin_hash_contrasena: SecretStr

    @property
    def es_produccion(self) -> bool:
        """Indica si la aplicación corre en producción."""
        return self.entorno == "produccion"

    @model_validator(mode="after")
    def validar_configuracion_segura(self) -> "Configuracion":
        """
        Rechaza configuraciones inseguras o incompletas.

        Los mensajes de error nunca incluyen el valor del secreto, solo
        explican qué está mal y cómo corregirlo.
        """
        clave_jwt = self.jwt_clave_secreta.get_secret_value()
        hash_admin = self.admin_hash_contrasena.get_secret_value()
        url_base_datos = self.url_base_datos.get_secret_value()

        # Primero se descarta que sigan los valores de ejemplo de .env.ejemplo,
        # porque es el error más común y su mensaje es el más claro.
        for nombre_variable, valor in (
            ("JWT_CLAVE_SECRETA", clave_jwt),
            ("ADMIN_HASH_CONTRASENA", hash_admin),
            ("URL_BASE_DATOS", url_base_datos),
        ):
            if any(marcador in valor for marcador in MARCADORES_VALOR_DE_EJEMPLO):
                raise ValueError(
                    f"{nombre_variable} todavía tiene el valor de ejemplo de .env.ejemplo. Reemplácelo."
                )

        if len(clave_jwt) < LONGITUD_MINIMA_CLAVE_JWT:
            raise ValueError(f"JWT_CLAVE_SECRETA debe tener al menos {LONGITUD_MINIMA_CLAVE_JWT} caracteres.")

        # El administrador se configura con el HASH, nunca con la contraseña
        # en texto plano. Si el valor no tiene forma de hash bcrypt, se rechaza.
        if not PATRON_HASH_BCRYPT.match(hash_admin):
            raise ValueError(
                "ADMIN_HASH_CONTRASENA debe ser un hash bcrypt, no la contraseña en texto plano. "
                "Vea .env.ejemplo para generarlo."
            )

        # En producción la cookie de sesión solo puede viajar por HTTPS.
        if self.es_produccion and not self.cookie_segura:
            raise ValueError("En producción COOKIE_SEGURA debe ser true.")

        validar_url_base_datos(url_base_datos, self.entorno)

        return self


@lru_cache
def obtener_configuracion() -> Configuracion:
    """
    Devuelve la configuración de la aplicación.

    Se lee una sola vez y se reutiliza (lru_cache): leer y validar el .env en
    cada petición sería un gasto innecesario. Todo el código debe obtener la
    configuración por esta función, nunca creando Configuracion() directamente.
    """
    return Configuracion()
