"""Endpoint del contrato §5. Revalida el libro y resuelve las unidades en PostgreSQL."""

import asyncio
import logging
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.importaciones import DatosFormularioCurso, RespuestaImportacionPersonal
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import (
    obtener_id_usuario_actual,
    obtener_usuario_actual,
    verificar_csrf,
)
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp
from aplicacion.servicios.importacion_personal import (
    MAX_ARCHIVO,
    DatosCurso,
    datos_formulario_curso,
    guardar_personal,
    leer_excel,
)

registrador = logging.getLogger(__name__)

puede_importar = requerir_permiso_componente(
    "PERSONAL_CARGUE_EXCEL", OperacionCRUD.CREATE, obtener_id_usuario_actual
)
enrutador = APIRouter(
    prefix="/importaciones",
    tags=["Importación de personal"],
    dependencies=[Depends(verificar_csrf), Depends(puede_importar)],
)


async def autorizar_importacion(sesion, actor, codigo, request):
    """Reutiliza política, límites y verificación TOTP existentes, si están habilitados."""
    await exigir_codigo_totp(
        sesion,
        actor.id,
        "PERSONAL_CARGUE_EXCEL",
        codigo,
        request,
        prefijo_auditoria="IMPORTACION",
        mensaje_requerido="Ingrese el código del autenticador para confirmar esta importación.",
    )


@enrutador.get("/datos-curso", response_model=DatosFormularioCurso)
async def obtener_datos_curso(sesion: Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]):
    """Tipos de curso, instructores activos y número que tendrá el próximo curso."""
    return await datos_formulario_curso(sesion)


@enrutador.post("/excel", status_code=201, response_model=RespuestaImportacionPersonal)
async def importar_excel(
    request: Request,
    archivo: UploadFile,
    sesion: Annotated[AsyncSession, Depends(obtener_sesion_base_datos)],
    actor: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
    hoja: Annotated[str, Form(min_length=1, max_length=31)],
    tipo_curso_id: Annotated[int, Form(gt=0)],
    nombre_curso: Annotated[str, Form(min_length=1, max_length=200)],
    comandante_id: Annotated[int, Form(gt=0)],
    fecha_inicio: Annotated[date, Form()],
    fecha_fin: Annotated[date, Form()],
    estado_curso: Annotated[Literal["EN_CURSO", "CULMINADO", "CANCELADO", "APLAZADO"], Form()],
    observacion_curso: Annotated[str, Form(max_length=2000)] = "",
    codigo_totp: Annotated[str, Form(max_length=6)] = "",
):
    """Recibe el original y la hoja explícita; nunca importa las demás hojas del libro."""
    try:
        registrador.info("IMPORTACION_RECIBIDA etapa=recepcion")
        if not (archivo.filename or "").lower().endswith((".xlsx", ".xls")):
            raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Solo se permiten archivos .xlsx y .xls.")
        contenido = await archivo.read(MAX_ARCHIVO + 1)
        registrador.info("IMPORTACION_ETAPA etapa=lectura bytes=%d", len(contenido))
        nombre_hoja, filas = await asyncio.to_thread(leer_excel, contenido, hoja, archivo.filename)

        async def autorizar():
            await autorizar_importacion(sesion, actor, codigo_totp, request)

        curso = DatosCurso(
            tipo_curso_id,
            nombre_curso,
            comandante_id,
            fecha_inicio,
            fecha_fin,
            estado_curso,
            observacion_curso,
        )
        return await guardar_personal(sesion, nombre_hoja, filas, actor, curso, request, autorizar)
    finally:
        await archivo.close()
