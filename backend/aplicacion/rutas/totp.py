"""TOTP integrado con sesión existente; ningún secreto en consultas de estado."""

import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.esquemas.autenticacion import SolicitudCambioContrasena
from aplicacion.modelos import Usuario
from aplicacion.modelos.totp import UsuarioTotp
from aplicacion.rutas.autenticacion import obtener_ip_cliente
from aplicacion.seguridad.comprobante_bloqueo import borrar as borrar_contexto
from aplicacion.seguridad.sesion_http import escribir_cookies_sesion, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import seguridad_login
from aplicacion.servicios.autenticacion import finalizar_login
from aplicacion.servicios.totp import TotpService

enrutador = APIRouter(prefix="/auth", tags=["TOTP"])


class Codigo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(pattern=r"^[0-9]{6}$", repr=False)


class Configurar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contrasena: str = Field(min_length=1, max_length=72, repr=False)

    @field_validator("contrasena")
    @classmethod
    def validar_bytes(cls, valor):
        if len(valor.encode("utf-8")) > 72:
            raise ValueError("La contraseña excede el límite permitido.")
        return valor


class Desactivar(Configurar, Codigo):
    pass


class ConfirmarDesafio(Codigo):
    desafio_id: uuid.UUID


class SolicitarVinculacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desafio_id: uuid.UUID


class CambioContrasenaInicial(SolicitudCambioContrasena):
    desafio_id: uuid.UUID


class ConfirmarLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desafio_id: uuid.UUID
    codigo: str = Field(pattern=r"^(?:[0-9]{6}|[0-9a-f]{32})$", repr=False)
    recuperacion: bool = False


class RevocarRecuperacion(Configurar):
    codigo: str = Field(pattern=r"^[0-9a-f]{32}$", repr=False)


class SolicitarDesbloqueo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre_usuario: str = Field(min_length=3, max_length=80)


def cookie_desafio(respuesta, nonce, proposito):
    respuesta.set_cookie(
        "esart_totp_" + proposito.lower(),
        nonce,
        max_age=600,
        httponly=True,
        samesite="strict",
        secure=obtener_configuracion().cookie_segura,
        path="/api",
    )


def respuesta_desafio(desafio, proposito):
    salida = JSONResponse(
        jsonable_encoder(
            {
                "totp_requerido": True,
                "configuracion_requerida": desafio.configuracion_requerida,
                "cambio_contrasena_requerido": desafio.cambio_contrasena_requerido,
                "desafio_id": desafio.id,
                "expira_en": desafio.expira_en,
                "metodos": (
                    ["CAMBIO_CONTRASENA"]
                    if desafio.cambio_contrasena_requerido
                    else ["VINCULACION_TOTP"]
                    if desafio.configuracion_requerida
                    else ["TOTP", "RECUPERACION"]
                    if proposito == "LOGIN"
                    else ["TOTP"]
                ),
            }
        ),
        status_code=202,
    )
    cookie_desafio(salida, desafio.nonce, proposito)
    return salida


@enrutador.post("/cambiar-contrasena-inicial")
async def cambiar_contrasena_inicial(
    datos: CambioContrasenaInicial,
    request: Request,
    sesion=Depends(obtener_sesion_base_datos),
):
    desafio = await TotpService(sesion).cambiar_contrasena_inicial(
        datos.desafio_id,
        request.cookies.get("esart_totp_login"),
        datos.contrasena_actual,
        datos.contrasena_nueva,
        obtener_ip_cliente(request),
        request,
    )
    return respuesta_desafio(desafio, "LOGIN")


@enrutador.post("/totp/login/configurar")
async def configurar_login(
    datos: SolicitarVinculacion,
    request: Request,
    respuesta: Response,
    sesion=Depends(obtener_sesion_base_datos),
):
    respuesta.headers["Cache-Control"] = "no-store"
    return await TotpService(sesion).configurar_login(
        datos.desafio_id, request.cookies.get("esart_totp_login"), obtener_ip_cliente(request)
    )


@enrutador.post("/totp/login/vincular")
async def vincular_login(
    datos: ConfirmarDesafio,
    request: Request,
    respuesta: Response,
    sesion=Depends(obtener_sesion_base_datos),
):
    usuario, vinculacion = await TotpService(sesion).vincular_login(
        datos.desafio_id, request.cookies.get("esart_totp_login"), datos.codigo, obtener_ip_cliente(request)
    )
    salida = await completar_login(sesion, usuario, request, respuesta)
    respuesta.headers["Cache-Control"] = "no-store"
    return {**salida, **vinculacion}


@enrutador.get("/totp/estado")
async def estado(identidad=Depends(obtener_usuario_actual), sesion=Depends(obtener_sesion_base_datos)):
    await TotpService(sesion).preparar()
    fila = await sesion.scalar(select(UsuarioTotp).where(UsuarioTotp.usuario_id == identidad.id))
    return {
        "configurado": fila is not None,
        "activo": bool(fila and fila.estado == "ACTIVO"),
        "estado": fila.estado if fila else "NO_CONFIGURADO",
        "fecha_activacion": fila.activado_en if fila and fila.estado == "ACTIVO" else None,
    }


@enrutador.post("/totp/configurar", dependencies=[Depends(verificar_csrf)])
async def configurar(
    datos: Configurar,
    request: Request,
    respuesta: Response,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    respuesta.headers["Cache-Control"] = "no-store"
    return await TotpService(sesion).configurar(identidad.id, datos.contrasena, obtener_ip_cliente(request))


@enrutador.post("/totp/confirmar", dependencies=[Depends(verificar_csrf)])
async def confirmar(
    datos: Codigo,
    request: Request,
    respuesta: Response,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    respuesta.headers["Cache-Control"] = "no-store"
    return await TotpService(sesion).confirmar(identidad.id, datos.codigo, obtener_ip_cliente(request))


@enrutador.post("/totp/recuperacion/revocar", dependencies=[Depends(verificar_csrf)])
async def revocar_con_recuperacion(
    datos: RevocarRecuperacion,
    request: Request,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    return await TotpService(sesion).desactivar(
        identidad.id, datos.contrasena, datos.codigo, obtener_ip_cliente(request), recuperacion=True
    )


@enrutador.post("/totp/desactivar", dependencies=[Depends(verificar_csrf)])
async def desactivar(
    datos: Desactivar,
    request: Request,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    return await TotpService(sesion).desactivar(
        identidad.id, datos.contrasena, datos.codigo, obtener_ip_cliente(request)
    )


@enrutador.post("/totp/login/confirmar")
async def confirmar_login(
    datos: ConfirmarLogin, request: Request, respuesta: Response, sesion=Depends(obtener_sesion_base_datos)
):
    servicio = TotpService(sesion)
    usuario = await servicio.validar_desafio(
        datos.desafio_id,
        "LOGIN",
        request.cookies.get("esart_totp_login"),
        datos.codigo,
        obtener_ip_cliente(request),
        recuperacion=datos.recuperacion,
    )
    return await completar_login(sesion, usuario, request, respuesta)


async def completar_login(sesion, usuario, request, respuesta):
    """La activación/consumo y la sesión se confirman en finalizar_login, juntos."""
    ahora = await seguridad_login.reloj_servidor(sesion)
    contexto = seguridad_login.ContextoIntento(
        seguridad_login.seudonimo("usuario", usuario.usuario.lower()),
        obtener_ip_cliente(request),
        ahora,
        usuario=usuario,
        estado=usuario,
    )
    resultado = await finalizar_login(
        sesion,
        usuario,
        obtener_ip_cliente(request),
        request.headers.get("user-agent"),
        contexto,
        request=request,
    )
    escribir_cookies_sesion(respuesta, resultado.token_sesion)
    respuesta.delete_cookie("esart_totp_login", path="/api")
    borrar_contexto(respuesta)
    return {
        "usuario": {
            "nombre_usuario": resultado.nombre_usuario,
            "nombre_completo": resultado.nombre_completo,
            "rol": resultado.rol,
            "requiere_cambio_contrasena": resultado.requiere_cambio_contrasena,
        },
        "expira_por_inactividad_segundos": obtener_configuracion().minutos_inactividad_sesion * 60,
    }


@enrutador.post("/totp/recuperacion/renovar", dependencies=[Depends(verificar_csrf)])
async def renovar_recuperacion(
    datos: Desactivar,
    request: Request,
    respuesta: Response,
    identidad=Depends(obtener_usuario_actual),
    sesion=Depends(obtener_sesion_base_datos),
):
    respuesta.headers["Cache-Control"] = "no-store"
    return await TotpService(sesion).renovar_recuperacion(
        identidad.id, datos.contrasena, datos.codigo, obtener_ip_cliente(request)
    )


@enrutador.post("/desbloqueo/solicitar")
async def solicitar(datos: SolicitarDesbloqueo, request: Request, sesion=Depends(obtener_sesion_base_datos)):
    servicio = TotpService(sesion)
    nombre = await sesion.scalar(select(func.lower(datos.nombre_usuario.strip())))
    await servicio.limitar(obtener_ip_cliente(request), seguridad_login.seudonimo("totp_contexto", nombre))
    politica = await servicio.politica("DESBLOQUEO_TOTP")
    usuario = await sesion.scalar(
        select(Usuario).where(func.lower(Usuario.usuario) == nombre).with_for_update()
    )
    registro = await servicio.registro(usuario.id) if usuario else None
    ahora = await seguridad_login.reloj_servidor(sesion)
    if (
        usuario
        and usuario.activo
        and usuario.bloqueado_hasta
        and usuario.bloqueado_hasta > ahora
        and registro
        and registro.estado == "ACTIVO"
    ):
        desafio = await servicio.crear_desafio(usuario.id, "DESBLOQUEO", obtener_ip_cliente(request))
    else:
        from datetime import timedelta

        from aplicacion.servicios.totp import DesafioLoginTotp

        identificador = uuid.uuid4()
        desafio = DesafioLoginTotp(
            identificador,
            ahora + timedelta(seconds=politica.vigencia_segundos),
            servicio.nonce_contexto(nombre, identificador, "DESBLOQUEO"),
        )
        await servicio.auditar(None, "TOTP_SOLICITUD_DESBLOQUEO", "RECIBIDO", obtener_ip_cliente(request))
    await sesion.commit()
    await servicio.respuesta_uniforme()
    return respuesta_desafio(desafio, "DESBLOQUEO")


@enrutador.post("/desbloqueo/confirmar")
async def desbloquear(
    datos: ConfirmarDesafio, request: Request, respuesta: Response, sesion=Depends(obtener_sesion_base_datos)
):
    servicio = TotpService(sesion)
    usuario = await servicio.validar_desafio(
        datos.desafio_id,
        "DESBLOQUEO",
        request.cookies.get("esart_totp_desbloqueo"),
        datos.codigo,
        obtener_ip_cliente(request),
    )
    usuario.intentos_fallidos_consecutivos, usuario.bloqueado_hasta = 0, None
    await servicio.auditar(usuario.id, "CUENTA_DESBLOQUEADA_TOTP", "CORRECTO", obtener_ip_cliente(request))
    await sesion.commit()
    respuesta.delete_cookie("esart_totp_desbloqueo", path="/api")
    borrar_contexto(respuesta)
    return {"procesado": True}
