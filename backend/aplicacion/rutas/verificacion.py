"""
Rutas de verificación de habilitación: /api/verificar (contrato de API §3).

Cada ruta exige su permiso de la malla (HU-09). La cédula sale enmascarada a quien no
tenga VER_DOCUMENTO_COMPLETO. La lógica de la regla vive en servicios/habilitacion.py.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.verificacion import (
    ArtilleroVerificado,
    CriterioVerificacion,
    CursoVerificacion,
    ElementoHabilitacion,
    PaginaHabilitacion,
    ReentrenamientoVerificacion,
    RespuestaVerificacion,
    ResumenHabilitacion,
    UnidadResumida,
)
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente, tiene_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual
from aplicacion.servicios import auditoria, habilitacion
from aplicacion.servicios.autenticacion import UsuarioAutenticado

enrutador_verificacion = APIRouter(prefix="/verificar", tags=["Verificación"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]

# Tamaño de página por defecto y máximo (contrato §1.3).
TAMANO_PAGINA_POR_DEFECTO = 50
TAMANO_PAGINA_MAXIMO = 200

puede_verificar = requerir_permiso_componente(
    "PERSONAL_VERIFICAR", OperacionCRUD.READ, obtener_id_usuario_actual
)
puede_listar = requerir_permiso_componente(
    "PERSONAL_HABILITADOS", OperacionCRUD.READ, obtener_id_usuario_actual
)
puede_ver_panel = requerir_permiso_componente(
    "PERSONAL_MILITAR", OperacionCRUD.READ, obtener_id_usuario_actual
)


async def puede_ver_cedula_completa(sesion: AsyncSession, usuario_id: int) -> bool:
    return await tiene_permiso_componente(sesion, usuario_id, "VER_DOCUMENTO_COMPLETO", OperacionCRUD.READ)


def _estado_certificado(certificado, hoy, parametros) -> str:
    """Estado legible de un certificado de reentrenamiento individual."""
    if not certificado.vigente or (
        parametros.exige_apto_para_disparar and not certificado.apto_para_disparar
    ):
        return "ANULADO"
    if certificado.fecha_vencimiento < hoy:
        return habilitacion.ESTADO_REENTRENAMIENTO_VENCIDO
    if (certificado.fecha_vencimiento - hoy).days <= parametros.dias_alerta_vencimiento:
        return habilitacion.ESTADO_REENTRENAMIENTO_POR_VENCER
    return habilitacion.ESTADO_REENTRENAMIENTO_VIGENTE


@enrutador_verificacion.get("/artillero/{numero_documento}", response_model=RespuestaVerificacion)
async def verificar_artillero(
    numero_documento: str,
    request: Request,
    sesion: Sesion,
    usuario_id: int = Depends(puede_verificar),
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
) -> RespuestaVerificacion:
    """APTO / NO APTO de un militar por cédula, con el detalle de cada criterio. Queda auditado."""
    cedula = habilitacion.normalizar_cedula(numero_documento)
    try:
        fila, criterios, cursos, reentrenamientos, parametros = await habilitacion.verificar_artillero(
            sesion, cedula
        )
    except ErrorAplicacion as error:
        # También se audita la consulta de una cédula que no existe (quién la buscó y cuándo).
        if error.codigo == "ARTILLERO_NO_ENCONTRADO":
            await auditoria.registrar_evento(
                sesion,
                auditoria.CONSULTA_ARTILLERO,
                request,
                usuario_id=usuario.id,
                nombre_usuario=usuario.nombre_usuario,
                documento=cedula,
                resultado="NO_ENCONTRADO",
            )
        raise
    await auditoria.registrar_evento(
        sesion,
        auditoria.CONSULTA_ARTILLERO,
        request,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        documento=cedula,
        resultado=fila.resultado,
    )
    ver_completa = await puede_ver_cedula_completa(sesion, usuario_id)
    return RespuestaVerificacion(
        artillero=ArtilleroVerificado(
            numero_documento=habilitacion.enmascarar_cedula(fila.documento_identidad, ver_completa),
            nombre_completo=habilitacion.nombre_completo(fila),
            grado=fila.grado,
            categoria=fila.categoria,
            unidad_militar=UnidadResumida(sigla=fila.unidad_codigo, nombre=fila.unidad_nombre)
            if fila.unidad_actual_id
            else None,
            estado_servicio="ACTIVO" if fila.activo else "INACTIVO",
        ),
        resultado=fila.resultado,
        fecha_verificacion=datetime.now(UTC),
        criterios=[CriterioVerificacion(**criterio.__dict__) for criterio in criterios],
        motivos=habilitacion.motivos_no_apto(criterios),
        alerta=habilitacion.construir_alerta(fila),
        cursos=[
            CursoVerificacion(
                nombre=curso.nombre,
                codigo=curso.codigo,
                institucion=curso.institucion,
                fecha_inicio=curso.fecha_inicio,
                fecha_fin=curso.fecha_fin,
                estado="APROBADO" if curso.finalizado_aprobado else "EN_CURSO",
                habilitante=bool(curso.habilitante),
            )
            for curso in cursos
        ],
        reentrenamientos=[
            ReentrenamientoVerificacion(
                numero_certificado=certificado.numero_certificado,
                tipo=certificado.tipo,
                calibre=certificado.calibre,
                fecha_expedicion=certificado.fecha_expedicion,
                fecha_vencimiento=certificado.fecha_vencimiento,
                estado=_estado_certificado(certificado, fila.hoy, parametros),
            )
            for certificado in reentrenamientos
        ],
    )


async def _listar(
    sesion: AsyncSession,
    request: Request,
    usuario: UsuarioAutenticado,
    accion: str,
    estado: str | None,
    unidad_militar_id: int | None,
    grado: str | None,
    texto: str | None,
    pagina: int,
    tamano_pagina: int,
) -> PaginaHabilitacion:
    filas, total, parametros = await habilitacion.listar_habilitacion(
        sesion,
        estado=estado,
        unidad_id=unidad_militar_id,
        grado=grado,
        texto=texto,
        pagina=pagina,
        tamano_pagina=tamano_pagina,
    )
    await auditoria.registrar_evento(
        sesion,
        accion,
        request,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "filtros": {
                "estado": estado,
                "unidad_militar_id": unidad_militar_id,
                "grado": grado,
                "texto": texto,
            },
            "pagina": pagina,
            "total": total,
        },
    )
    ver_completa = await puede_ver_cedula_completa(sesion, usuario.id)
    elementos = []
    for fila in filas:
        criterios = habilitacion.construir_criterios(fila, parametros)
        elementos.append(
            ElementoHabilitacion(
                numero_documento=habilitacion.enmascarar_cedula(fila.documento_identidad, ver_completa),
                nombre_completo=habilitacion.nombre_completo(fila),
                grado=fila.grado,
                unidad_militar_sigla=fila.unidad_codigo,
                activo=fila.activo,
                resultado=fila.resultado,
                motivos=habilitacion.motivos_no_apto(criterios),
                curso_habilitante=fila.codigo_curso,
                reentrenamiento_vence=fila.reentrenamiento_vence,
                estado_reentrenamiento=habilitacion.estado_reentrenamiento(fila),
            )
        )
    return PaginaHabilitacion(
        elementos=elementos,
        pagina=pagina,
        tamano_pagina=tamano_pagina,
        total_elementos=total,
        total_paginas=habilitacion.total_paginas(total, tamano_pagina),
    )


@enrutador_verificacion.get("/habilitacion", response_model=PaginaHabilitacion)
async def listar_habilitacion(
    request: Request,
    sesion: Sesion,
    usuario_id: int = Depends(puede_listar),
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
    estado: Literal["APTO", "NO_APTO", "POR_VENCER"] | None = None,
    unidad_militar_id: int | None = Query(default=None, ge=1),
    grado: str | None = Query(default=None, max_length=20),
    texto: str | None = Query(default=None, max_length=100),
    pagina: int = Query(default=1, ge=1),
    tamano_pagina: int = Query(default=TAMANO_PAGINA_POR_DEFECTO, ge=1, le=TAMANO_PAGINA_MAXIMO),
) -> PaginaHabilitacion:
    """Listado de todos los militares con su estado; 'estado' filtra APTO, NO_APTO o POR_VENCER."""
    return await _listar(
        sesion,
        request,
        usuario,
        auditoria.CONSULTA_HABILITADOS,
        estado,
        unidad_militar_id,
        grado,
        texto,
        pagina,
        tamano_pagina,
    )


@enrutador_verificacion.get("/habilitados", response_model=PaginaHabilitacion)
async def listar_habilitados(
    request: Request,
    sesion: Sesion,
    usuario_id: int = Depends(puede_listar),
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
    unidad_militar_id: int | None = Query(default=None, ge=1),
    grado: str | None = Query(default=None, max_length=20),
    texto: str | None = Query(default=None, max_length=100),
    pagina: int = Query(default=1, ge=1),
    tamano_pagina: int = Query(default=TAMANO_PAGINA_POR_DEFECTO, ge=1, le=TAMANO_PAGINA_MAXIMO),
) -> PaginaHabilitacion:
    """Solo APTO (contrato §3)."""
    return await _listar(
        sesion,
        request,
        usuario,
        auditoria.CONSULTA_HABILITADOS,
        "APTO",
        unidad_militar_id,
        grado,
        texto,
        pagina,
        tamano_pagina,
    )


@enrutador_verificacion.get("/no-habilitados", response_model=PaginaHabilitacion)
async def listar_no_habilitados(
    request: Request,
    sesion: Sesion,
    usuario_id: int = Depends(puede_listar),
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
    unidad_militar_id: int | None = Query(default=None, ge=1),
    grado: str | None = Query(default=None, max_length=20),
    texto: str | None = Query(default=None, max_length=100),
    pagina: int = Query(default=1, ge=1),
    tamano_pagina: int = Query(default=TAMANO_PAGINA_POR_DEFECTO, ge=1, le=TAMANO_PAGINA_MAXIMO),
) -> PaginaHabilitacion:
    """Solo NO APTO, con sus motivos (contrato §3)."""
    return await _listar(
        sesion,
        request,
        usuario,
        auditoria.CONSULTA_NO_HABILITADOS,
        "NO_APTO",
        unidad_militar_id,
        grado,
        texto,
        pagina,
        tamano_pagina,
    )


@enrutador_verificacion.get(
    "/resumen", response_model=ResumenHabilitacion, dependencies=[Depends(puede_ver_panel)]
)
async def resumen_habilitacion(
    request: Request,
    sesion: Sesion,
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
) -> ResumenHabilitacion:
    """Indicadores del panel: total, APTO, NO APTO, por vencer, activos y unidades."""
    resumen = await habilitacion.resumir_habilitacion(sesion)
    await auditoria.registrar_evento(
        sesion,
        auditoria.CONSULTA_RESUMEN,
        request,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        resultado="EXITOSO",
    )
    return ResumenHabilitacion(**resumen)
