"""
HU-21: FastAPI sirve el dashboard compilado y agrega cabeceras de seguridad.

Se construye la aplicación con una carpeta de front falsa (tmp_path), sin base de datos.
"""

import httpx
import pytest

from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.front_estatico import CACHE_INMUTABLE, CACHE_REVALIDAR
from aplicacion.principal import crear_aplicacion

pytestmark = pytest.mark.anyio

INDICE = "<!doctype html><html><body><app-root></app-root></body></html>"


@pytest.fixture
def carpeta_front(tmp_path):
    (tmp_path / "index.html").write_text(INDICE, encoding="utf-8")
    (tmp_path / "main-V3DA5O76.js").write_text("console.log('esart')", encoding="utf-8")
    (tmp_path / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "fuente-ABCDEFGH.woff2").write_bytes(b"wOF2")
    # Un archivo fuera de la carpeta del front que nunca debe poder leerse.
    (tmp_path.parent / "secreto.env").write_text("CLAVE=no", encoding="utf-8")
    return tmp_path


@pytest.fixture
async def cliente_con_front(carpeta_front, monkeypatch):
    monkeypatch.setattr(obtener_configuracion(), "ruta_front", carpeta_front)
    aplicacion = crear_aplicacion()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=aplicacion), base_url="http://pruebas"
    ) as cliente:
        yield cliente


async def test_la_raiz_y_las_rutas_de_angular_devuelven_el_index(cliente_con_front):
    for ruta in ("/", "/dashboard", "/instructores", "/administracion/parametros?pestana=cursos"):
        respuesta = await cliente_con_front.get(ruta)
        assert respuesta.status_code == 200, ruta
        assert "<app-root>" in respuesta.text
        assert respuesta.headers["cache-control"] == CACHE_REVALIDAR


async def test_los_archivos_con_huella_se_guardan_un_anio_y_los_demas_se_revalidan(cliente_con_front):
    script = await cliente_con_front.get("/main-V3DA5O76.js")
    assert script.status_code == 200 and script.headers["cache-control"] == CACHE_INMUTABLE
    fuente = await cliente_con_front.get("/media/fuente-ABCDEFGH.woff2")
    assert fuente.status_code == 200 and fuente.headers["cache-control"] == CACHE_INMUTABLE
    icono = await cliente_con_front.get("/favicon.ico")
    assert icono.status_code == 200 and icono.headers["cache-control"] == CACHE_REVALIDAR


async def test_archivos_inexistentes_y_rutas_con_puntos_no_se_sirven(cliente_con_front):
    assert (await cliente_con_front.get("/no-existe.js")).status_code == 404
    assert (await cliente_con_front.get("/..%2Fsecreto.env")).status_code == 404
    assert (await cliente_con_front.get("/media/../../secreto.env")).status_code == 404


async def test_la_api_sigue_respondiendo_y_sus_404_son_json(cliente_con_front):
    salud = await cliente_con_front.get("/api/salud")
    assert salud.status_code in (200, 503)  # sin base de datos real puede estar degradada
    inexistente = await cliente_con_front.get("/api/no-existe")
    assert inexistente.status_code == 404
    assert inexistente.json()["error"]["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert inexistente.headers["cache-control"] == "no-store"


async def test_cabeceras_de_seguridad(cliente_con_front):
    pagina = await cliente_con_front.get("/instructores")
    politica = pagina.headers["content-security-policy"]
    assert "script-src 'self'" in politica and "frame-ancestors 'none'" in politica
    assert "cdn" not in politica.lower()
    assert pagina.headers["x-content-type-options"] == "nosniff"
    assert pagina.headers["x-frame-options"] == "DENY"
    api = await cliente_con_front.get("/api/no-existe")
    assert "content-security-policy" not in api.headers  # las respuestas JSON no la necesitan
    assert api.headers["x-content-type-options"] == "nosniff"


async def test_sin_front_compilado_solo_se_sirve_la_api(tmp_path, monkeypatch):
    monkeypatch.setattr(obtener_configuracion(), "ruta_front", tmp_path / "no-existe")
    aplicacion = crear_aplicacion()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=aplicacion), base_url="http://pruebas"
    ) as cliente:
        respuesta = await cliente.get("/dashboard")
        assert respuesta.status_code == 404
        assert respuesta.json()["error"]["codigo"] == "RECURSO_NO_ENCONTRADO"
