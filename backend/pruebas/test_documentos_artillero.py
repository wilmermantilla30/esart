"""
Pruebas de los documentos PDF del artillero (ReportLab).

- Scripts y maestro (aplicacion/reportes): sin base de datos.
- Endpoint GET /api/verificar/artillero/{cedula}/documento: con PostgreSQL (ESART_URL_BD_INTEGRACION).
"""

import dataclasses
import re
from datetime import date

import pytest
from sqlalchemy import select

from aplicacion.modelos import AuditoriaEvento
from aplicacion.reportes import maestro
from aplicacion.reportes.comun import DocumentoNoDisponible, fecha_larga
from aplicacion.reportes.diploma import curso_del_diploma
from aplicacion.reportes.maestro import REPORTES, ReporteDesconocido, datos_de_ejemplo, generar_documento
from pruebas.test_auditoria_y_malla import entrar
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_verificacion_habilitacion import crear_militar


def paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf))


# --- Scripts y maestro (sin base de datos) ----------------------------------------------------


@pytest.mark.parametrize("opcion", list(REPORTES))
def test_cada_opcion_genera_un_pdf_de_una_pagina(opcion):
    pdf, nombre = generar_documento(opcion, datos_de_ejemplo())
    assert pdf.startswith(b"%PDF-")
    assert paginas(pdf) == 1
    assert nombre == f"{REPORTES[opcion].archivo}_1024589632.pdf"


def test_el_maestro_acepta_minusculas_y_rechaza_opciones_desconocidas():
    assert generar_documento("  certificacion ", datos_de_ejemplo())[0].startswith(b"%PDF-")
    with pytest.raises(ReporteDesconocido):
        generar_documento("ACTA", datos_de_ejemplo())


def test_diploma_usa_el_curso_aprobado_mas_reciente_y_exige_uno():
    datos = datos_de_ejemplo()
    reciente = dataclasses.replace(datos.cursos[0], nombre="SACLI", fecha_fin=date(2026, 3, 1))
    no_aprobado = dataclasses.replace(
        datos.cursos[0], nombre="SACME", fecha_fin=date(2026, 9, 1), aprobado=False
    )
    con_varios = dataclasses.replace(datos, cursos=[datos.cursos[0], reciente, no_aprobado])
    assert curso_del_diploma(con_varios).nombre == "SACLI"

    sin_aprobados = dataclasses.replace(datos, cursos=[no_aprobado])
    with pytest.raises(DocumentoNoDisponible):
        generar_documento("DIPLOMA", sin_aprobados)
    # Los otros dos documentos no exigen curso aprobado.
    for opcion in ("OFICIO_REMISORIO", "CERTIFICACION"):
        assert generar_documento(opcion, sin_aprobados)[0].startswith(b"%PDF-")


def test_textos_con_marcas_xml_no_rompen_el_pdf():
    datos = dataclasses.replace(datos_de_ejemplo(), nombres="Ana <b> & Co", unidad="Unidad <1>")
    for opcion in REPORTES:
        assert generar_documento(opcion, datos)[0].startswith(b"%PDF-")


def test_cedula_enmascarada_da_un_nombre_de_archivo_seguro():
    datos = dataclasses.replace(datos_de_ejemplo(), cedula="******9632")
    assert generar_documento("CERTIFICACION", datos)[1] == "certificacion_9632.pdf"


def test_certificacion_larga_ocupa_varias_paginas_sin_error():
    datos = datos_de_ejemplo()
    muchos = dataclasses.replace(datos, reentrenamientos=datos.reentrenamientos * 60)
    assert paginas(generar_documento("CERTIFICACION", muchos)[0]) > 1


def test_fecha_larga_en_espanol():
    assert fecha_larga(date(2026, 11, 18)) == "18 de noviembre de 2026"


def test_linea_de_comandos_genera_el_archivo(tmp_path, capsys):
    salida = tmp_path / "oficio.pdf"
    assert maestro.main(["oficio_remisorio", str(salida)]) == 0
    assert salida.read_bytes().startswith(b"%PDF-")
    assert maestro.main(["ACTA", str(tmp_path / "x.pdf")]) == 1
    assert maestro.main([]) == 2


# --- Endpoint (con PostgreSQL) ----------------------------------------------------------------


@requiere_postgresql
@pytest.mark.anyio
async def test_endpoint_entrega_pdf_y_queda_auditado(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    cedula = await crear_militar(sesion_bd, "sacli", 71)

    opciones = await cliente_api.get("/api/verificar/documentos")
    assert [o["codigo"] for o in opciones.json()] == list(REPORTES)

    for opcion in REPORTES:
        respuesta = await cliente_api.get(
            f"/api/verificar/artillero/{cedula}/documento", params={"tipo": opcion}
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.headers["content-type"] == "application/pdf"
        assert respuesta.headers["content-disposition"].endswith(f"{REPORTES[opcion].archivo}_{cedula}.pdf")
        assert respuesta.content.startswith(b"%PDF-")

    evento = await sesion_bd.scalar(
        select(AuditoriaEvento)
        .where(AuditoriaEvento.resultado == "DOC_CERTIFICACION")
        .order_by(AuditoriaEvento.id.desc())
    )
    assert evento.numero_documento_consultado == cedula
    assert evento.detalle["numero"].startswith("ESART-")


@requiere_postgresql
@pytest.mark.anyio
async def test_endpoint_diploma_sin_curso_y_opcion_invalida(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    cedula = await crear_militar(sesion_bd, "vencido", 72)  # sin cursos
    diploma = await cliente_api.get(
        f"/api/verificar/artillero/{cedula}/documento", params={"tipo": "DIPLOMA"}
    )
    assert diploma.status_code == 409
    assert diploma.json()["error"]["codigo"] == "DOCUMENTO_NO_DISPONIBLE"
    invalida = await cliente_api.get(f"/api/verificar/artillero/{cedula}/documento", params={"tipo": "ACTA"})
    assert invalida.status_code == 422
    inexistente = await cliente_api.get(
        "/api/verificar/artillero/1234567/documento", params={"tipo": "CERTIFICACION"}
    )
    assert inexistente.status_code == 404


# --- Endpoint con dependencias simuladas (sin base de datos) ----------------------------------


@pytest.fixture
def endpoint_simulado(monkeypatch):
    """Reemplaza identidad, permiso, sesión, verificación y auditoría para probar solo la ruta."""
    import types
    import uuid

    from aplicacion.base_datos.sesion import obtener_sesion_base_datos
    from aplicacion.principal import aplicacion
    from aplicacion.rutas import verificacion
    from aplicacion.seguridad.sesion_http import obtener_usuario_actual
    from aplicacion.servicios.autenticacion import UsuarioAutenticado
    from aplicacion.servicios.habilitacion import Criterio

    hoy = date(2026, 11, 18)
    fila = types.SimpleNamespace(
        id=1, documento_identidad="9950000021", nombres="Paula Isabella", apellidos="Acosta Galindo",
        grado="SS", categoria="SUB", activo=True, unidad_actual_id=5,
        unidad_nombre="Batallón de Artillería de Campaña N°5", resultado="NO_APTO", hoy=hoy,
    )  # fmt: skip
    curso = types.SimpleNamespace(
        nombre="Curso básico", codigo="CBA", institucion="ESART",
        fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 6, 1), finalizado_aprobado=True,
    )  # fmt: skip
    criterio = Criterio("Servicio activo", "OBLIGATORIO", True, "Activo", None)
    eventos = []

    async def verificar(_sesion, _cedula):
        return fila, [criterio], [curso], [], types.SimpleNamespace()

    async def registrar(_sesion, accion, _request=None, **datos):
        eventos.append((accion, datos))

    async def sin_cedula_completa(_sesion, _usuario_id):
        return False

    monkeypatch.setattr(verificacion.habilitacion, "verificar_artillero", verificar)
    monkeypatch.setattr(verificacion.auditoria, "registrar_evento", registrar)
    monkeypatch.setattr(verificacion, "puede_ver_cedula_completa", sin_cedula_completa)

    async def sin_historial(_sesion, _personal_id):
        # S2-17: sin base de datos no hay historial académico.
        return []

    monkeypatch.setattr(verificacion.historial_academico, "historial", sin_historial)
    aplicacion.dependency_overrides[verificacion.puede_verificar] = lambda: 7
    aplicacion.dependency_overrides[obtener_sesion_base_datos] = lambda: None
    aplicacion.dependency_overrides[obtener_usuario_actual] = lambda: UsuarioAutenticado(
        id=7,
        nombre_usuario="admin.esart",
        rol="ADMINISTRADOR",
        documento_identidad=None,
        sesion_id=uuid.uuid4(),
    )
    return eventos


@pytest.mark.anyio
async def test_ruta_entrega_pdf_con_cedula_enmascarada_y_audita(cliente_api, endpoint_simulado):
    respuesta = await cliente_api.get(
        "/api/verificar/artillero/9950000021/documento", params={"tipo": "OFICIO_REMISORIO"}
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.headers["cache-control"] == "no-store"
    # Sin VER_DOCUMENTO_COMPLETO la cédula sale enmascarada (también en el nombre del archivo).
    assert respuesta.headers["content-disposition"].endswith("oficio_remisorio_0021.pdf")
    assert respuesta.content.startswith(b"%PDF-")
    accion, datos = endpoint_simulado[-1]
    assert accion == "CONSULTA_ARTILLERO" and datos["resultado"] == "DOC_OFICIO_REMISORIO"
    assert datos["detalle"]["numero"].startswith("ESART-20261118-")


@pytest.mark.anyio
async def test_ruta_valida_la_opcion_y_lista_los_documentos(cliente_api, endpoint_simulado):
    invalida = await cliente_api.get("/api/verificar/artillero/9950000021/documento", params={"tipo": "ACTA"})
    assert invalida.status_code == 422
    opciones = (await cliente_api.get("/api/verificar/documentos")).json()
    assert opciones == [{"codigo": c, "nombre": r.nombre} for c, r in REPORTES.items()]
    assert endpoint_simulado == []  # nada se audita si no se generó documento
