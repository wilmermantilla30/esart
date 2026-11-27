"""
Rutas de verificación de habilitación: /api/verificar (contrato de API §3).

Cada ruta exige su permiso de la malla (HU-09). La cédula sale enmascarada a quien no
tenga VER_DOCUMENTO_COMPLETO. La lógica de la regla vive en servicios/habilitacion.py.
"""

import secrets
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.esquemas.verificacion import (
    ArtilleroVerificado,
    CriterioVerificacion,
    CursoAcademico,
    CursoVerificacion,
    ElementoHabilitacion,
    OpcionDocumentoArtillero,
    PaginaHabilitacion,
    ReentrenamientoVerificacion,
    RespuestaVerificacion,
    ResumenHabilitacion,
    UnidadResumida,
)
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.reportes.comun import (
    CriterioDocumento,
    CursoDocumento,
    DatosDocumento,
    DocumentoNoDisponible,
    HistorialCursoDocumento,
    MateriaDocumento,
    ReentrenamientoDocumento,
)
from aplicacion.reportes.maestro import REPORTES, generar_documento
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente, tiene_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual
from aplicacion.servicios import auditoria, habilitacion, historial_academico
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
        historial_academico=[
            CursoAcademico(**curso) for curso in await historial_academico.historial(sesion, fila.id)
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


# --- Documentos PDF del artillero (diploma, oficio remisorio, certificación) ----------------
# El script maestro (aplicacion/reportes/maestro.py) decide qué script genera cada opción; aquí
# solo se arma DatosDocumento con la misma verificación de /artillero/{cedula}, con el mismo
# permiso (PERSONAL_VERIFICAR, leer), la misma regla de cédula enmascarada y queda auditado.
OpcionDocumento = Literal["DIPLOMA", "OFICIO_REMISORIO", "CERTIFICACION"]


@enrutador_verificacion.get(
    "/documentos", response_model=list[OpcionDocumentoArtillero], dependencies=[Depends(puede_verificar)]
)
async def opciones_documento() -> list[OpcionDocumentoArtillero]:
    """Documentos que se pueden generar (para el selector del front)."""
    return [OpcionDocumentoArtillero(codigo=codigo, nombre=r.nombre) for codigo, r in REPORTES.items()]


@enrutador_verificacion.get("/artillero/{numero_documento}/documento")
async def generar_documento_artillero(
    numero_documento: str,
    request: Request,
    sesion: Sesion,
    tipo: OpcionDocumento = Query(..., description="DIPLOMA, OFICIO_REMISORIO o CERTIFICACION"),
    usuario_id: int = Depends(puede_verificar),
    usuario: UsuarioAutenticado = Depends(obtener_usuario_actual),
) -> Response:
    """PDF del documento elegido. 404 si la cédula no existe; 409 si el documento no aplica
    (diploma sin curso aprobado)."""
    cedula = habilitacion.normalizar_cedula(numero_documento)
    fila, criterios, cursos, reentrenamientos, parametros = await habilitacion.verificar_artillero(
        sesion, cedula
    )
    # Número del documento: fecha + sufijo aleatorio; queda en la auditoría para rastrearlo.
    numero = f"ESART-{fila.hoy:%Y%m%d}-{secrets.token_hex(3).upper()}"
    datos = DatosDocumento(
        cedula=habilitacion.enmascarar_cedula(
            fila.documento_identidad, await puede_ver_cedula_completa(sesion, usuario_id)
        ),
        grado=fila.grado,
        nombres=fila.nombres,
        apellidos=fila.apellidos,
        categoria=fila.categoria,
        unidad=fila.unidad_nombre if fila.unidad_actual_id else None,
        activo=fila.activo,
        resultado=fila.resultado,
        fecha_expedicion=fila.hoy,
        numero=numero,
        expedido_por=usuario.nombre_usuario,
        motivos=habilitacion.motivos_no_apto(criterios),
        criterios=[CriterioDocumento(c.descripcion, c.tipo, c.cumple, c.detalle) for c in criterios],
        cursos=[
            CursoDocumento(
                nombre=curso.nombre,
                codigo=curso.codigo,
                institucion=curso.institucion,
                fecha_inicio=curso.fecha_inicio,
                fecha_fin=curso.fecha_fin,
                aprobado=bool(curso.finalizado_aprobado),
            )
            for curso in cursos
        ],
        reentrenamientos=[
            ReentrenamientoDocumento(
                numero_certificado=c.numero_certificado,
                tipo=c.tipo,
                calibre=c.calibre,
                fecha_expedicion=c.fecha_expedicion,
                fecha_vencimiento=c.fecha_vencimiento,
                estado=_estado_certificado(c, fila.hoy, parametros),
            )
            for c in reentrenamientos
        ],
        historial=[
            HistorialCursoDocumento(
                nombre=curso["nombre"],
                codigo=curso["codigo"],
                fecha_inicio=curso["fecha_inicio"],
                fecha_fin=curso["fecha_fin"],
                cerrado=curso["cerrado"],
                nota_final=curso["nota_final"],
                resultado=curso["resultado"],
                puesto=curso["puesto"],
                aprobados_del_curso=curso["aprobados_del_curso"],
                materias=[
                    MateriaDocumento(m["materia"], m["nota"], m["estado"], m["instructor"])
                    for m in curso["materias"]
                ],
            )
            for curso in await historial_academico.historial(sesion, fila.id)
        ],
    )
    try:
        pdf, nombre = generar_documento(tipo, datos)
    except DocumentoNoDisponible as error:
        raise ErrorAplicacion(409, "DOCUMENTO_NO_DISPONIBLE", str(error)) from None
    await auditoria.registrar_evento(
        sesion,
        auditoria.CONSULTA_ARTILLERO,
        request,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        documento=cedula,
        resultado=f"DOC_{tipo}"[:20],
        detalle={"documento_generado": tipo, "numero": numero},
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
