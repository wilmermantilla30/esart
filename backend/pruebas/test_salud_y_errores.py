"""Pruebas de la ruta de salud y del formato único de errores."""

import pytest

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.principal import aplicacion

pytestmark = pytest.mark.anyio


class SesionBaseDatosQueResponde:
    """Sesión falsa que simula una base de datos disponible."""

    async def execute(self, *_argumentos, **_argumentos_nombrados):
        return None


class SesionBaseDatosCaida:
    """Sesión falsa que simula una base de datos que no responde."""

    async def execute(self, *_argumentos, **_argumentos_nombrados):
        raise OSError("conexión rechazada")


def reemplazar_sesion_base_datos(clase_sesion_falsa) -> None:
    """Hace que la aplicación use una sesión falsa en lugar de PostgreSQL."""

    async def entregar_sesion_falsa():
        yield clase_sesion_falsa()

    aplicacion.dependency_overrides[obtener_sesion_base_datos] = entregar_sesion_falsa


async def test_salud_responde_ok_cuando_la_base_de_datos_responde(cliente_api):
    reemplazar_sesion_base_datos(SesionBaseDatosQueResponde)

    respuesta = await cliente_api.get("/api/salud")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "base_datos": "ok"}


async def test_salud_responde_503_sin_detalles_cuando_la_base_de_datos_no_responde(cliente_api):
    reemplazar_sesion_base_datos(SesionBaseDatosCaida)

    respuesta = await cliente_api.get("/api/salud")

    assert respuesta.status_code == 503
    assert respuesta.json() == {"estado": "degradado", "base_datos": "error"}
    # El mensaje técnico del error nunca llega al cliente.
    assert "rechazada" not in respuesta.text


async def test_ruta_inexistente_usa_el_formato_unico_de_error(cliente_api):
    respuesta = await cliente_api.get("/api/no-existe")

    assert respuesta.status_code == 404
    assert respuesta.json() == {
        "error": {
            "codigo": "RECURSO_NO_ENCONTRADO",
            "mensaje": "El recurso solicitado no existe.",
            "detalle": None,
        }
    }


async def test_metodo_no_permitido_usa_el_formato_unico_de_error(cliente_api):
    reemplazar_sesion_base_datos(SesionBaseDatosQueResponde)

    respuesta = await cliente_api.post("/api/salud")

    assert respuesta.status_code == 405
    assert respuesta.json()["error"]["codigo"] == "METODO_NO_PERMITIDO"


async def test_documentacion_visible_fuera_de_produccion(cliente_api):
    respuesta = await cliente_api.get("/api/documentacion")

    assert respuesta.status_code == 200
