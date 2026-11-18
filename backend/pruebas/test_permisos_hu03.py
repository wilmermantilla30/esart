"""La dependencia FastAPI aplica controles CRUD y códigos sin confiar en Angular."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI, Request

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.nucleo.errores import registrar_manejadores_errores
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente


@pytest.mark.anyio
@pytest.mark.parametrize("operacion", list(OperacionCRUD))
@pytest.mark.parametrize("permitido", [True, False])
async def test_control_crud_en_fastapi(operacion, permitido):
    usuario_id = uuid4()

    async def identidad_confiable():
        return usuario_id

    sesion = AsyncMock()
    sesion.add = MagicMock()
    sesion.scalar.return_value = permitido

    async def sesion_falsa():
        yield sesion

    app = FastAPI()
    registrar_manejadores_errores(app)
    app.dependency_overrides[obtener_sesion_base_datos] = sesion_falsa
    dependencia = requerir_permiso_componente("PERSONAL_MILITAR", operacion, identidad_confiable)

    @app.get("/protegido", dependencies=[Depends(dependencia)])
    async def protegido():
        return {"permitido": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://pruebas"
    ) as cliente:
        respuesta = await cliente.get("/protegido")
    assert respuesta.status_code == (200 if permitido else 403)
    if not permitido:
        assert respuesta.json()["error"]["codigo"] == "SIN_PERMISO"
    consulta = str(sesion.scalar.call_args.args[0])
    assert operacion.value in consulta
    assert "coalesce" in consulta


@pytest.mark.anyio
async def test_codigo_api_adicional_es_obligatorio():
    async def identidad_confiable():
        return uuid4()

    sesion = AsyncMock()
    sesion.add = MagicMock()
    sesion.scalar.side_effect = [True, None]
    dependencia = requerir_permiso_componente(
        "PERSONAL_MILITAR",
        OperacionCRUD.READ,
        identidad_confiable,
        codigo_permiso="VER_DOCUMENTO_COMPLETO",
    )
    from aplicacion.nucleo.errores import ErrorAplicacion

    with pytest.raises(ErrorAplicacion) as error:
        # Petición mínima: la verificación la usa para auditar el 403 (HU-11).
        peticion = Request(
            {"type": "http", "method": "GET", "path": "/protegido", "headers": [], "client": None}
        )
        await dependencia(request=peticion, usuario_id=uuid4(), sesion=sesion)
    assert error.value.estado_http == 403
    # No consultar una tabla granular inexistente ni inferir concesiones CRUD: solo la
    # consulta del componente y la de pertenencia a ADMINISTRADOR (único dueño de los códigos).
    assert sesion.scalar.await_count == 2
