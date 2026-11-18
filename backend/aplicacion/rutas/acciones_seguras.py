import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.rutas.autenticacion import obtener_ip_cliente
from aplicacion.rutas.totp import Codigo
from aplicacion.seguridad.sesion_http import obtener_usuario_actual, verificar_csrf
from aplicacion.servicios.autorizacion_acciones import AutorizacionAccionesService

enrutador = APIRouter(
    prefix="/seguridad", tags=["Autorizaciones TOTP"], dependencies=[Depends(verificar_csrf)]
)


class Operacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo_politica: str = Field(min_length=1, max_length=100)
    recurso_id: str = Field(min_length=1, max_length=150)
    datos: dict = Field(default_factory=dict, max_length=100)


class VerificarOperacion(Operacion, Codigo):
    pass


@enrutador.post("/desafios")
async def crear(
    datos: Operacion,
    request: Request,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    return await AutorizacionAccionesService(sesion).crear(
        identidad, datos.codigo_politica, datos.recurso_id, datos.datos, obtener_ip_cliente(request)
    )


@enrutador.post("/desafios/{identificador}/verificar")
async def verificar(
    identificador: uuid.UUID,
    datos: VerificarOperacion,
    request: Request,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    return await AutorizacionAccionesService(sesion).verificar_accion(
        identidad,
        identificador,
        datos.recurso_id,
        datos.datos,
        datos.codigo,
        obtener_ip_cliente(request),
        datos.codigo_politica,
    )


@enrutador.post("/autorizaciones/{identificador}/ejecutar")
async def ejecutar(
    identificador: uuid.UUID,
    datos: Operacion,
    request: Request,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    return await AutorizacionAccionesService(sesion).ejecutar_autorizada(
        identidad,
        identificador,
        datos.recurso_id,
        datos.datos,
        obtener_ip_cliente(request),
        datos.codigo_politica,
    )
