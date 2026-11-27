"""
Rutas del panel de Parámetros: /api/parametros (contrato de API §6).

Tres pestañas, todas bajo el componente PARAMETROS_HABILITACION de la malla:
- Cursos y Capacitaciones: la regla APTO / NO APTO (leer, simular y guardar con TOTP) y la nota
  mínima de aprobación (S2-10, leer y guardar con TOTP).
- Mallas curriculares (S2-09): bajo su propio componente MALLAS_CURRICULARES, para darlo por
  excepción a quien no administra el resto de Parámetros.
- Plantillas y Formatos: repositorio de documentos (listar, publicar, descargar y retirar).
- Parámetros de Seguridad: solo consulta.
"""

from dataclasses import asdict
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, Response, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.esquemas.parametros import (
    ConfiguracionCampana,
    DetalleMalla,
    MateriaCatalogo,
    NotaMinima,
    ParametrosSeguridad,
    Plantilla,
    PoliticaSeguridad,
    ReglaHabilitacion,
    SimulacionRegla,
    SolicitudCrearTipoCurso,
    SolicitudGuardarCampana,
    SolicitudGuardarMalla,
    SolicitudGuardarNotaMinima,
    SolicitudGuardarRegla,
    TipoCursoMalla,
    ValoresRegla,
)
from aplicacion.seguridad.permisos import OperacionCRUD, requerir_permiso_componente
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual, obtener_usuario_actual, verificar_csrf
from aplicacion.servicios import campana, mallas_parametros, nota_minima, parametros_habilitacion, plantillas
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.malla_curricular import FilaMalla
from aplicacion.servicios.seguridad_login import HORAS_BLOQUEO

COMPONENTE = "PARAMETROS_HABILITACION"
# Umbrales del login acordados en HU-06 (captcha desde el 4.º intento, bloqueo en el 7.º).
INTENTO_CAPTCHA = 4
INTENTO_BLOQUEO = 7

enrutador_parametros = APIRouter(prefix="/parametros", tags=["Parámetros"])

Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]
UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]

puede_leer = requerir_permiso_componente(COMPONENTE, OperacionCRUD.READ, obtener_id_usuario_actual)
puede_actualizar = requerir_permiso_componente(COMPONENTE, OperacionCRUD.UPDATE, obtener_id_usuario_actual)
puede_crear = requerir_permiso_componente(COMPONENTE, OperacionCRUD.CREATE, obtener_id_usuario_actual)
puede_eliminar = requerir_permiso_componente(COMPONENTE, OperacionCRUD.DELETE, obtener_id_usuario_actual)

COMPONENTE_MALLAS = "MALLAS_CURRICULARES"
mallas_leer = requerir_permiso_componente(COMPONENTE_MALLAS, OperacionCRUD.READ, obtener_id_usuario_actual)
mallas_crear = requerir_permiso_componente(COMPONENTE_MALLAS, OperacionCRUD.CREATE, obtener_id_usuario_actual)
mallas_actualizar = requerir_permiso_componente(
    COMPONENTE_MALLAS, OperacionCRUD.UPDATE, obtener_id_usuario_actual
)


def _regla(datos: dict) -> ReglaHabilitacion:
    return ReglaHabilitacion(
        valores=ValoresRegla(**asdict(datos["parametros"])),
        actualizado_en=datos["actualizado_en"],
        actualizado_por=datos["actualizado_por"],
        cursos_disponibles=[asdict(curso) for curso in datos["cursos_disponibles"]],
        resumen=datos["resumen"],
    )


async def _propuesta(sesion: AsyncSession, valores: ValoresRegla):
    """Valida la propuesta contra los tipos de curso activos."""
    return parametros_habilitacion.validar_propuesta(
        valores.cursos_habilitantes,
        valores.meses_vigencia_reentrenamiento,
        valores.dias_alerta_vencimiento,
        valores.exige_apto_para_disparar,
        await parametros_habilitacion.cursos_disponibles(sesion),
    )


# --- Cursos y Capacitaciones: regla de habilitación ---------------------------------------


@enrutador_parametros.get(
    "/habilitacion", response_model=ReglaHabilitacion, dependencies=[Depends(puede_leer)]
)
async def obtener_regla(sesion: Sesion) -> ReglaHabilitacion:
    """Valores vigentes, último cambio, cursos posibles y el resumen APTO / NO APTO actual."""
    return _regla(await parametros_habilitacion.obtener_regla(sesion))


@enrutador_parametros.post(
    "/habilitacion/simular",
    response_model=SimulacionRegla,
    dependencies=[Depends(verificar_csrf), Depends(puede_leer)],
)
async def simular_regla(datos: ValoresRegla, sesion: Sesion) -> SimulacionRegla:
    """Qué pasaría con la propuesta, sin guardar nada."""
    return SimulacionRegla(**await parametros_habilitacion.simular(sesion, await _propuesta(sesion, datos)))


@enrutador_parametros.put(
    "/habilitacion",
    response_model=ReglaHabilitacion,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def guardar_regla(
    datos: SolicitudGuardarRegla, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> ReglaHabilitacion:
    """Aplica la regla nueva (con TOTP) y devuelve el estado guardado."""
    propuesta = await _propuesta(sesion, datos)
    resultado = await parametros_habilitacion.guardar(
        sesion,
        propuesta,
        datos.version,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        codigo_totp=datos.codigo_totp,
        request=request,
    )
    return _regla(resultado)


# --- Cursos y Capacitaciones: nota mínima de aprobación (S2-10) ---------------------------


def _nota_minima(estado: nota_minima.EstadoNotaMinima) -> NotaMinima:
    return NotaMinima(
        valor=float(estado.valor),
        actualizado_en=estado.actualizado_en,
        actualizado_por=estado.actualizado_por,
        cursos_en_curso=estado.cursos_en_curso,
    )


@enrutador_parametros.get("/nota-minima", response_model=NotaMinima, dependencies=[Depends(puede_leer)])
async def obtener_nota_minima(sesion: Sesion) -> NotaMinima:
    """Nota mínima vigente para los cursos nuevos y su último cambio."""
    return _nota_minima(await nota_minima.obtener(sesion))


@enrutador_parametros.put(
    "/nota-minima",
    response_model=NotaMinima,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def guardar_nota_minima(
    datos: SolicitudGuardarNotaMinima, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> NotaMinima:
    """Cambia la nota mínima (con TOTP). Solo aplica a los cursos que se creen desde ahora."""
    estado = await nota_minima.guardar(
        sesion,
        datos.valor,
        datos.version,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        codigo_totp=datos.codigo_totp,
        request=request,
    )
    return _nota_minima(estado)


# --- Cursos y Capacitaciones: ítems de la fase de campaña del CAPINTE (S2-16) ----------------------


@enrutador_parametros.get("/campana", response_model=ConfiguracionCampana, dependencies=[Depends(puede_leer)])
async def obtener_campana(sesion: Sesion) -> ConfiguracionCampana:
    """Ítems de la fase de campaña del CAPINTE con su puntaje (suman 5,00)."""
    return ConfiguracionCampana(**await campana.obtener(sesion))


@enrutador_parametros.put(
    "/campana",
    response_model=ConfiguracionCampana,
    dependencies=[Depends(verificar_csrf), Depends(puede_actualizar)],
)
async def guardar_campana(
    datos: SolicitudGuardarCampana, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> ConfiguracionCampana:
    """Reemplaza los ítems y puntajes (con TOTP). Solo afecta a las plantillas que se descarguen después."""
    resultado = await campana.guardar(
        sesion,
        [item.model_dump() for item in datos.items],
        datos.version,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        codigo_totp=datos.codigo_totp,
        request=request,
    )
    return ConfiguracionCampana(**resultado)


# --- Mallas curriculares (S2-09) -------------------------------------------------------------


@enrutador_parametros.get("/mallas", response_model=list[TipoCursoMalla], dependencies=[Depends(mallas_leer)])
async def listar_mallas(sesion: Sesion) -> list[TipoCursoMalla]:
    """Tipos de curso con su versión vigente (o sin malla todavía)."""
    return [TipoCursoMalla(**fila) for fila in await mallas_parametros.listar_tipos(sesion)]


@enrutador_parametros.get(
    "/mallas/materias", response_model=list[MateriaCatalogo], dependencies=[Depends(mallas_leer)]
)
async def listar_materias(sesion: Sesion) -> list[MateriaCatalogo]:
    """Catálogo de materias para sugerir nombres en el editor."""
    return [MateriaCatalogo(**fila) for fila in await mallas_parametros.catalogo_materias(sesion)]


@enrutador_parametros.post(
    "/mallas",
    status_code=201,
    response_model=DetalleMalla,
    dependencies=[Depends(verificar_csrf), Depends(mallas_crear)],
)
async def crear_tipo_curso(
    datos: SolicitudCrearTipoCurso, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> DetalleMalla:
    """Crea un tipo de curso sin malla (con TOTP)."""
    nuevo = mallas_parametros.NuevoTipoCurso(
        codigo=datos.codigo,
        nombre=datos.nombre,
        tipo=datos.tipo,
        modalidad=datos.modalidad,
        duracion_semanas=datos.duracion_semanas,
    )
    resultado = await mallas_parametros.crear_tipo(
        sesion, nuevo, actor=Actor.web(usuario, request), codigo_totp=datos.codigo_totp
    )
    return DetalleMalla(**resultado)


@enrutador_parametros.get(
    "/mallas/{codigo_tipo}", response_model=DetalleMalla, dependencies=[Depends(mallas_leer)]
)
async def obtener_malla(sesion: Sesion, codigo_tipo: str, version: int | None = None) -> DetalleMalla:
    """Malla vigente (o la versión pedida) de un tipo de curso, con su historial de versiones."""
    return DetalleMalla(**await mallas_parametros.detalle(sesion, codigo_tipo.upper(), version))


@enrutador_parametros.put(
    "/mallas/{codigo_tipo}",
    response_model=DetalleMalla,
    dependencies=[Depends(verificar_csrf), Depends(mallas_actualizar)],
)
async def guardar_malla(
    codigo_tipo: str, datos: SolicitudGuardarMalla, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> DetalleMalla:
    """Guarda la malla editada como versión nueva (con TOTP). Los cursos ya creados no cambian."""
    filas = [
        FilaMalla(
            orden=fila.orden,
            materia=fila.materia,
            evaluable=fila.evaluable,
            area=(fila.area or "").strip() or None,
            modulo=(fila.modulo or "").strip() or None,
        )
        for fila in datos.filas
    ]
    resultado = await mallas_parametros.guardar_version(
        sesion,
        codigo_tipo.upper(),
        datos.anio,
        filas,
        datos.observacion,
        datos.version,
        actor=Actor.web(usuario, request),
        codigo_totp=datos.codigo_totp,
    )
    return DetalleMalla(**resultado)


# --- Plantillas y Formatos ------------------------------------------------------------------


@enrutador_parametros.get("/plantillas", response_model=list[Plantilla], dependencies=[Depends(puede_leer)])
async def listar_plantillas(
    sesion: Sesion, formato: Literal["XLSX", "XLS", "PDF", "DOCX"] | None = None
) -> list[Plantilla]:
    """Plantillas vigentes, opcionalmente de un solo formato."""
    return [Plantilla(**fila._mapping) for fila in await plantillas.listar(sesion, formato)]


@enrutador_parametros.post(
    "/plantillas",
    status_code=201,
    response_model=Plantilla,
    dependencies=[Depends(verificar_csrf), Depends(puede_crear)],
)
async def publicar_plantilla(
    request: Request,
    sesion: Sesion,
    usuario: UsuarioActual,
    archivo: UploadFile,
    nombre_oficial: Annotated[str, Form(min_length=3, max_length=200)],
    version: Annotated[str, Form(min_length=1, max_length=30, pattern=r"^[\w .\-]+$")],
    descripcion: Annotated[str, Form(max_length=2000)] = "",
) -> Plantilla:
    """Publica un documento nuevo. Se valida el contenido real del archivo, no solo su extensión."""
    try:
        # Se lee como máximo un byte más del límite: suficiente para saber que lo supera.
        contenido = await archivo.read(plantillas.TAMANO_MAXIMO_BYTES + 1)
    finally:
        await archivo.close()
    validado = plantillas.validar_archivo(archivo.filename, contenido)
    fila = await plantillas.publicar(
        sesion,
        validado,
        nombre_oficial=nombre_oficial.strip(),
        version=version.strip(),
        descripcion=descripcion.strip(),
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        request=request,
    )
    return Plantilla(**fila._mapping)


@enrutador_parametros.get("/plantillas/{plantilla_id}/descarga", dependencies=[Depends(puede_leer)])
async def descargar_plantilla(
    plantilla_id: int, request: Request, sesion: Sesion, usuario: UsuarioActual
) -> Response:
    """Entrega el archivo como adjunto (nunca para abrirlo dentro de la página)."""
    nombre, tipo, contenido = await plantillas.descargar(
        sesion, plantilla_id, usuario_id=usuario.id, nombre_usuario=usuario.nombre_usuario, request=request
    )
    return Response(
        content=contenido,
        media_type=tipo,
        headers={
            # filename* (RFC 5987) admite cualquier nombre sin riesgo de inyectar cabeceras.
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@enrutador_parametros.post(
    "/plantillas/{plantilla_id}/retirar",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(verificar_csrf), Depends(puede_eliminar)],
)
async def retirar_plantilla(plantilla_id: int, request: Request, sesion: Sesion, usuario: UsuarioActual):
    """La plantilla deja de ofrecerse; queda guardada para consulta histórica."""
    await plantillas.retirar(
        sesion, plantilla_id, usuario_id=usuario.id, nombre_usuario=usuario.nombre_usuario, request=request
    )


# --- Parámetros de Seguridad (solo consulta) ------------------------------------------------


@enrutador_parametros.get(
    "/seguridad", response_model=ParametrosSeguridad, dependencies=[Depends(puede_leer)]
)
async def obtener_parametros_seguridad(sesion: Sesion) -> ParametrosSeguridad:
    """Estado de la doble autenticación, políticas que exigen TOTP y reglas del login."""
    configuracion = obtener_configuracion()
    usuarios = (
        await sesion.execute(
            text("""
                SELECT count(*) FILTER (WHERE u.activo) AS activos,
                       count(t.id) FILTER (WHERE u.activo AND t.estado = 'ACTIVO') AS con_autenticador
                FROM esart_ref.usuarios u
                LEFT JOIN seguridad.usuario_totp t ON t.usuario_id = u.id
            """)
        )
    ).one()
    politicas = await sesion.execute(
        text("""
            SELECT codigo, nombre, modulo, requiere_totp, activa
            FROM seguridad.politicas_accion ORDER BY modulo, codigo
        """)
    )
    return ParametrosSeguridad(
        totp_habilitado=configuracion.totp_habilitado,
        usuarios_activos=usuarios.activos,
        usuarios_con_autenticador=usuarios.con_autenticador,
        minutos_inactividad_sesion=configuracion.minutos_inactividad_sesion,
        intento_captcha=INTENTO_CAPTCHA,
        intento_bloqueo=INTENTO_BLOQUEO,
        horas_bloqueo=HORAS_BLOQUEO,
        politicas=[PoliticaSeguridad(**fila._mapping) for fila in politicas],
    )
