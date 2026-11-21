"""
Firma electrónica desde el celular (servicios/firma_movil.py; docs/ESART_FIRMA_MOVIL.md).

/api/firma (PC, con sesión y CSRF):
  GET  /firmantes?tipo=           firmantes autorizados vigentes            (PERSONAL_VERIFICAR leer)
  POST /solicitudes               borrador + QR de un solo uso              (PERSONAL_VERIFICAR leer)
  GET  /solicitudes/{id}          estado (el PC consulta hasta que se firme) (creador o FIRMA_DOCUMENTOS)
  GET  /autorizaciones            firmantes vigentes de ambos tipos          (FIRMA_DOCUMENTOS leer)
  GET  /candidatos                usuarios que se pueden autorizar           (FIRMA_DOCUMENTOS crear)
  POST /autorizaciones            autorizar a un usuario como firmante       (FIRMA_DOCUMENTOS crear)

/api/firma-movil/{token} (celular, SIN sesión): el token de 256 bits del QR (solo se guarda su sha256,
vence en 15 minutos y se usa una vez) más el código TOTP del firmante reemplazan la sesión. No hay
cookies, así que no aplica CSRF; los logs ocultan el token (nucleo/registro.py).
  GET  /{token}          resumen del documento
  GET  /{token}/pdf      borrador a firmar (verificado por sha256)
  POST /{token}/firmar   rúbrica + TOTP + aceptación → PDF firmado
"""

# Firmas de dependencias y mensajes en una línea para leerlos completos.
# ruff: noqa: E501

import logging
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente, tiene_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import firma_movil, habilitacion
from aplicacion.servicios.autenticacion import UsuarioAutenticado

registrador = logging.getLogger(__name__)
Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
TipoFirmable = Literal["CERTIFICACION", "OFICIO_REMISORIO"]

puede_verificar = requerir_permiso_componente(
    "PERSONAL_VERIFICAR", OperacionCRUD.READ, obtener_id_usuario_actual
)
puede_ver_firmas = requerir_permiso_componente(
    "FIRMA_DOCUMENTOS", OperacionCRUD.READ, obtener_id_usuario_actual
)
puede_autorizar = requerir_permiso_componente(
    "FIRMA_DOCUMENTOS", OperacionCRUD.CREATE, obtener_id_usuario_actual
)


async def exigir_estructura_firma(sesion: Sesion) -> None:
    """Sin p0018/p0019 en la base: 503 FIRMA_NO_DISPONIBLE con un mensaje claro (no un error interno)."""
    await firma_movil.verificar_estructura_firma(sesion)


enrutador_firma = APIRouter(
    prefix="/firma",
    tags=["Firma desde el celular"],
    dependencies=[Depends(verificar_csrf), Depends(exigir_estructura_firma)],
)
enrutador_firma_movil = APIRouter(
    prefix="/firma-movil",
    tags=["Firma desde el celular (público)"],
    dependencies=[Depends(exigir_estructura_firma)],
)


def _persistencia():
    configuracion = obtener_configuracion()
    if not configuracion.documentos_persistencia_habilitada:
        raise ErrorAplicacion(
            503,
            "ALMACENAMIENTO_NO_DISPONIBLE",
            "La firma requiere el almacenamiento documental: active DOCUMENTOS_PERSISTENCIA_HABILITADA=true en backend/.env y reinicie el backend.",
        )
    return configuracion


def _sin_acceso_al_almacen(configuracion) -> ErrorAplicacion:
    """El proceso del backend no puede escribir en la carpeta privada de documentos (permisos de Windows)."""
    registrador.error("FIRMA_ALMACEN_SIN_PERMISO directorio=%s", configuracion.directorio_documentos_privados)
    return ErrorAplicacion(
        503,
        "ALMACENAMIENTO_SIN_PERMISO",
        "El backend no tiene permiso para escribir en la carpeta de documentos privados "
        "(DIRECTORIO_DOCUMENTOS_PRIVADOS). Revise los permisos de esa carpeta o configure otra.",
    )


# --- Esquemas ------------------------------------------------------------------------------


class Firmante(BaseModel):
    autorizacion_id: UUID
    usuario_id: int
    nombre: str
    cargo: str
    tipo: str


class SolicitudNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cedula: str = Field(min_length=5, max_length=20)
    tipo: TipoFirmable
    autorizacion_id: UUID


class SolicitudCreada(BaseModel):
    solicitud_id: UUID
    documento_id: UUID
    url_firma: str  # lo que codifica el QR
    url_publica_configurada: bool  # False: el front debe armar la dirección (y avisar si es localhost)
    expira_en: str
    firmante: str
    cargo: str


class EstadoSolicitud(BaseModel):
    solicitud_id: UUID
    documento_id: UUID
    estado: str
    estado_documento: str
    expira_en: str
    firmante: str
    cargo: str


class CandidatoFirmante(BaseModel):
    usuario_id: int
    usuario: str | None
    nombre: str
    totp_activo: bool


class AutorizacionNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usuario_id: int = Field(gt=0)
    tipo: TipoFirmable
    cargo: str = Field(min_length=3, max_length=150)
    grado: str | None = Field(default=None, max_length=20)


class ResumenMovil(BaseModel):
    estado: str
    tipo: str
    numero: str
    artillero: str
    firmante: str
    cargo: str
    expira_en: str
    texto_consentimiento: str


class FirmaMovil(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubrica_png: str = Field(min_length=20, max_length=600_000)
    codigo_totp: str = Field(pattern=r"^[0-9]{6}$")
    acepto: bool


class FirmaRealizada(BaseModel):
    estado: str
    codigo_verificacion: str


# --- PC ------------------------------------------------------------------------------------


@enrutador_firma.get("/firmantes", response_model=list[Firmante], dependencies=[Depends(puede_verificar)])
async def firmantes(sesion: Sesion, tipo: TipoFirmable) -> list[Firmante]:
    return [Firmante(**f) for f in await firma_movil.listar_firmantes(sesion, tipo)]


@enrutador_firma.post("/solicitudes", status_code=201, response_model=SolicitudCreada)
async def solicitar(
    solicitud: SolicitudNueva,
    request: Request,
    sesion: Sesion,
    usuario_id: int = Depends(puede_verificar),
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
) -> SolicitudCreada:
    """Genera el borrador del documento y la solicitud de firma con su QR."""
    from aplicacion.rutas.verificacion import armar_datos_documento

    configuracion = _persistencia()
    cedula = habilitacion.normalizar_cedula(solicitud.cedula)
    fila, datos = await armar_datos_documento(sesion, cedula, usuario_id, usuario.nombre_usuario)
    destino = None
    try:
        respuesta, destino = await firma_movil.solicitar_firma(
            sesion, datos=datos, tipo=solicitud.tipo, personal_id=fila.id, autorizacion_id=solicitud.autorizacion_id,
            usuario_id=usuario_id, directorio=configuracion.directorio_documentos_privados, request=request,
        )  # fmt: skip
        await sesion.commit()
    except PermissionError:
        await sesion.rollback()
        raise _sin_acceso_al_almacen(configuracion) from None
    except Exception:
        await sesion.rollback()
        if destino is not None:
            destino.unlink(missing_ok=True)
        raise
    base = (configuracion.url_base_firma_movil or "").rstrip("/")
    return SolicitudCreada(
        solicitud_id=respuesta["solicitud_id"],
        documento_id=respuesta["documento_id"],
        url_firma=f"{base}/firma/{respuesta['token']}",
        url_publica_configurada=bool(base),
        expira_en=respuesta["expira_en"].isoformat(),
        firmante=respuesta["firmante"],
        cargo=respuesta["cargo"],
    )


@enrutador_firma.get("/solicitudes/{solicitud_id}", response_model=EstadoSolicitud)
async def estado(
    solicitud_id: UUID, sesion: Sesion, usuario_id: int = Depends(puede_verificar)
) -> EstadoSolicitud:
    ver_todas = await tiene_permiso_componente(sesion, usuario_id, "FIRMA_DOCUMENTOS", OperacionCRUD.READ)
    datos = await firma_movil.estado_solicitud(sesion, solicitud_id, usuario_id, ver_todas)
    return EstadoSolicitud(**{**datos, "expira_en": datos["expira_en"].isoformat()})


@enrutador_firma.get(
    "/autorizaciones", response_model=list[Firmante], dependencies=[Depends(puede_ver_firmas)]
)
async def autorizaciones(sesion: Sesion) -> list[Firmante]:
    filas = []
    for tipo in firma_movil.TIPOS_FIRMABLES:
        filas += await firma_movil.listar_firmantes(sesion, tipo)
    return [Firmante(**f) for f in filas]


@enrutador_firma.get(
    "/candidatos", response_model=list[CandidatoFirmante], dependencies=[Depends(puede_autorizar)]
)
async def candidatos(sesion: Sesion) -> list[CandidatoFirmante]:
    """Usuarios que FIRMA_DOCUMENTOS (crear) puede autorizar como firmantes."""
    return [CandidatoFirmante(**c) for c in await firma_movil.listar_candidatos(sesion)]


@enrutador_firma.post("/autorizaciones", status_code=201)
async def autorizar(
    datos: AutorizacionNueva, request: Request, sesion: Sesion, usuario_id: int = Depends(puede_autorizar)
) -> dict:
    resultado = await firma_movil.autorizar_firmante(
        sesion, usuario_id=datos.usuario_id, tipo=datos.tipo, cargo=datos.cargo, grado=datos.grado,
        concedido_por=usuario_id, request=request,
    )  # fmt: skip
    await sesion.commit()
    return {**resultado, "autorizacion_id": str(resultado["autorizacion_id"])}


# --- Celular (público, por token) ------------------------------------------------------------


@enrutador_firma_movil.get("/{token}", response_model=ResumenMovil)
async def abrir(token: str, sesion: Sesion) -> ResumenMovil:
    _persistencia()
    resumen = await firma_movil.abrir_solicitud(sesion, token)
    await sesion.commit()
    return ResumenMovil(**{**resumen, "expira_en": resumen["expira_en"].isoformat()})


@enrutador_firma_movil.get("/{token}/pdf")
async def borrador(token: str, sesion: Sesion) -> Response:
    configuracion = _persistencia()
    contenido, numero = await firma_movil.pdf_borrador(
        sesion, token, configuracion.directorio_documentos_privados
    )
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(f'borrador_{numero}.pdf')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@enrutador_firma_movil.post("/{token}/firmar", response_model=FirmaRealizada)
async def firmar(token: str, datos: FirmaMovil, request: Request, sesion: Sesion) -> FirmaRealizada:
    configuracion = _persistencia()
    archivos = []
    try:
        resultado, archivos = await firma_movil.firmar(
            sesion, token=token, rubrica_png=datos.rubrica_png, codigo_totp=datos.codigo_totp, acepto=datos.acepto,
            directorio=configuracion.directorio_documentos_privados, request=request,
        )  # fmt: skip
        await sesion.commit()
    except PermissionError:
        await sesion.rollback()
        raise _sin_acceso_al_almacen(configuracion) from None
    except Exception:
        await sesion.rollback()
        for archivo in archivos:
            archivo.unlink(missing_ok=True)
        raise
    return FirmaRealizada(estado=resultado["estado"], codigo_verificacion=resultado["codigo_verificacion"])
