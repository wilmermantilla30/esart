"""Captura efímera del CAPTCHA solo para automatización aislada, jamás importada por producción."""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

from aplicacion.principal import aplicacion  # noqa: F401
from aplicacion.servicios import captcha_local

carpeta = Path(os.environ["ESART_EVIDENCIA_PUBLICA"]).resolve()
url = make_url(os.environ["URL_BASE_DATOS"])
raiz = Path(__file__).resolve().parents[1] / "respaldos"
if (
    os.environ.get("ENTORNO") != "pruebas"
    or url.host != "127.0.0.1"
    or url.port == 5432
    or not carpeta.is_relative_to(raiz)
    or not (carpeta.parent / "ESART_SOLO_PRUEBAS").is_file()
):
    raise RuntimeError("Aplicación de pruebas solo permitida en clúster aislado marcado")

original = captcha_local.generar_texto


def capturar():
    codigo = original()
    (carpeta / "captcha_efimero.txt").write_text(codigo, encoding="ascii")
    return codigo


captcha_local.generar_texto = capturar
