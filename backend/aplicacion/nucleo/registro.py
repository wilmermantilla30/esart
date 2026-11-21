"""
Configuración de los registros (logs) de la aplicación.

Regla de seguridad del proyecto: credenciales, contraseñas, tokens y cédulas
nunca deben quedar en los logs. Además de no escribirlos a propósito, aquí se
instala un filtro que los oculta como segunda barrera, por si algún mensaje
(nuestro, de uvicorn o de una librería) los incluye por error.
"""

import logging
import logging.config
import re

# Cada par es (patrón a buscar, texto de reemplazo).
PATRONES_DATOS_SENSIBLES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Pares clave=valor o "clave": "valor" con nombres sensibles.
    (
        re.compile(
            r'(?i)("?(?:contrasena|contraseña|password|clave|secret|secreto|token|'
            r'authorization|cookie|captcha_respuesta|hash_contrasena)\w*"?\s*[:=]\s*)'
            r'("[^"]*"|\'[^\']*\'|\S+)'
        ),
        r"\1[OCULTO]",
    ),
    # Contraseña dentro de una URL de base de datos: usuario:CONTRASENA@servidor.
    (re.compile(r"(\w+(?:\+\w+)?://[^:/\s@]+):[^@\s]+@"), r"\1:[OCULTO]@"),
    # Token tipo "Bearer xxxxx".
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-_.]+"), r"\1[OCULTO]"),
    # Cualquier JWT suelto (tres bloques base64url separados por puntos, empieza por eyJ).
    (re.compile(r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"), "[JWT_OCULTO]"),
    # Hash bcrypt.
    (re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}"), "[HASH_OCULTO]"),
    # Cédula en la ruta de verificación (aparece en los logs de acceso de uvicorn).
    # La trazabilidad de quién consultó qué cédula está en la tabla de auditoría,
    # que tiene acceso controlado; los logs de texto no la necesitan.
    (re.compile(r"(/artillero/)[^/?\s\"]+"), r"\1[CEDULA_OCULTA]"),
    # Token de un solo uso de la firma desde el celular (va en la ruta del QR): quien lo lea en
    # un log podría abrir la solicitud. El backend solo guarda su sha256.
    (re.compile(r"(/firma(?:-movil)?/)[A-Za-z0-9_\-]{20,}"), r"\1[TOKEN_FIRMA_OCULTO]"),
)


def ocultar_datos_sensibles(texto: str) -> str:
    """Devuelve el texto con credenciales, tokens y cédulas reemplazados por marcadores."""
    for patron, reemplazo in PATRONES_DATOS_SENSIBLES:
        texto = patron.sub(reemplazo, texto)
    return texto


def _ocultar_si_es_texto(valor: object) -> object:
    """Aplica ocultar_datos_sensibles solo a los valores de texto; el resto lo deja igual."""
    return ocultar_datos_sensibles(valor) if isinstance(valor, str) else valor


class FiltroDatosSensibles(logging.Filter):
    """
    Filtro de logging que limpia cada registro antes de escribirlo.

    Se limpian el mensaje y también sus argumentos por separado (en vez de
    unirlos) porque algunos formateadores, como el de acceso de uvicorn, leen
    los argumentos por posición.
    """

    def filter(self, registro: logging.LogRecord) -> bool:
        registro.msg = _ocultar_si_es_texto(registro.msg)
        if isinstance(registro.args, tuple):
            registro.args = tuple(_ocultar_si_es_texto(argumento) for argumento in registro.args)
        elif isinstance(registro.args, dict):
            registro.args = {clave: _ocultar_si_es_texto(valor) for clave, valor in registro.args.items()}
        # Siempre devuelve True: el filtro modifica el registro, no lo descarta.
        return True


def configurar_registro(nivel_registro: str) -> None:
    """
    Configura los logs de la aplicación, de uvicorn y de SQLAlchemy.

    Todos pasan por un único manejador de consola con el filtro de datos
    sensibles. Los logs de uvicorn se redefinen aquí para que también pasen
    por el filtro (por defecto uvicorn usa sus propios manejadores).
    """
    formato = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"datos_sensibles": {"()": FiltroDatosSensibles}},
            "formatters": {"estandar": {"format": formato}},
            "handlers": {
                "consola": {
                    "class": "logging.StreamHandler",
                    "formatter": "estandar",
                    "filters": ["datos_sensibles"],
                }
            },
            "root": {"level": nivel_registro, "handlers": ["consola"]},
            "loggers": {
                # propagate=False evita que cada línea se escriba dos veces.
                "uvicorn": {"level": nivel_registro, "handlers": ["consola"], "propagate": False},
                "uvicorn.error": {"level": nivel_registro, "handlers": ["consola"], "propagate": False},
                "uvicorn.access": {"level": nivel_registro, "handlers": ["consola"], "propagate": False},
                # SQLAlchemy en WARNING: en INFO escribiría cada consulta SQL.
                "sqlalchemy.engine": {"level": "WARNING", "handlers": ["consola"], "propagate": False},
            },
        }
    )
