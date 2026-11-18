"""
Pruebas del panel de Parámetros: regla de habilitación, plantillas y seguridad (solo consulta).

- Validación de archivos y de la regla: sin base de datos.
- Endpoints: con PostgreSQL (ESART_URL_BD_INTEGRACION); todo se revierte al final.
"""

import io
import time
import uuid
import zipfile

import pyotp
import pytest
from openpyxl import Workbook
from sqlalchemy import select

from aplicacion.modelos import AuditoriaEvento
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import plantillas
from aplicacion.servicios.parametros_habilitacion import CursoDisponible, validar_propuesta
from pruebas.test_auditoria_y_malla import cabecera_csrf, entrar
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_verificacion_habilitacion import crear_militar

pytestmark = pytest.mark.anyio

CURSOS = [
    CursoDisponible("SACLI", "Liviana"),
    CursoDisponible("SACME", "Mediana"),
    CursoDisponible("OA", "Obs"),
]


def libro_xlsx() -> bytes:
    libro = Workbook()
    libro.active.append(["Cédula", "Nombres"])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def zip_office(partes: dict[str, bytes]) -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as archivo:
        for nombre, contenido in partes.items():
            archivo.writestr(nombre, contenido)
    return salida.getvalue()


# --- Validación de archivos (sin base de datos) ---------------------------------------


def test_acepta_los_cuatro_formatos_por_su_contenido_real():
    docx = zip_office({"[Content_Types].xml": b"<x/>", "word/document.xml": b"<w/>"})
    casos = {
        "plantilla.xlsx": (libro_xlsx(), "XLSX"),
        "acta.docx": (docx, "DOCX"),
        "manual.pdf": (b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF", "PDF"),
        "viejo.xls": (bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 512, "XLS"),
    }
    for nombre, (contenido, formato) in casos.items():
        validado = plantillas.validar_archivo(nombre, contenido)
        assert validado.formato == formato and len(validado.sha256) == 64


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("programa.exe", b"MZ\x90\x00"),  # extensión no admitida
        ("con_macros.xlsm", b"PK\x03\x04"),  # formato con macros
        ("falso.xlsx", b"%PDF-1.4"),  # la extensión no corresponde al contenido
        ("falso.pdf", b"PK\x03\x04resto"),
        ("vacio.pdf", b""),
        ("roto.docx", b"PK\x03\x04no-es-un-zip"),
        ("pdf_activo.pdf", b"%PDF-1.4\n<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>"),
        ("lanza.pdf", b"%PDF-1.4\n<< /S /Launch /F (cmd.exe) >>"),
        ("macro.xls", bytes.fromhex("D0CF11E0A1B11AE1") + "_VBA_PROJECT".encode("utf-16-le")),
    ],
)
def test_rechaza_archivos_peligrosos_o_falsos(nombre, contenido):
    with pytest.raises(ErrorAplicacion) as error:
        plantillas.validar_archivo(nombre, contenido)
    assert error.value.estado_http == 422


def test_rechaza_office_con_proyecto_de_macros_aunque_la_extension_sea_xlsx():
    con_macros = zip_office(
        {"[Content_Types].xml": b"<x/>", "xl/workbook.xml": b"<w/>", "xl/vbaProject.bin": b"\x00"}
    )
    with pytest.raises(ErrorAplicacion):
        plantillas.validar_archivo("parece_normal.xlsx", con_macros)


def test_rechaza_archivos_de_mas_de_25_mb():
    with pytest.raises(ErrorAplicacion):
        plantillas.validar_archivo("grande.pdf", b"%PDF-" + b"0" * plantillas.TAMANO_MAXIMO_BYTES)


def test_el_nombre_del_archivo_nunca_es_una_ruta_ni_trae_caracteres_peligrosos():
    assert plantillas.limpiar_nombre_archivo("..\\..\\windows\\evil.pdf") == "evil.pdf"
    assert plantillas.limpiar_nombre_archivo("../../etc/passwd") == "passwd"
    assert plantillas.limpiar_nombre_archivo('Acta "Tiro"\r\nX: 1.docx') == "Acta _Tiro___X_ 1.docx"
    assert plantillas.limpiar_nombre_archivo("Plantilla Cédula ñ.xlsx") == "Plantilla Cedula n.xlsx"


# --- Validación de la regla (sin base de datos) ---------------------------------------


def test_la_propuesta_se_normaliza():
    regla = validar_propuesta([" sacme", "SACLI", "SACLI"], 12, 60, True, CURSOS)
    assert regla.cursos_habilitantes == ["SACLI", "SACME"]


@pytest.mark.parametrize(
    ("cursos", "meses", "dias"),
    [
        (["INVENTADO"], 12, 60),  # curso inexistente o inactivo
        (["SACLI"], 0, 30),  # vigencia fuera de rango
        (["SACLI"], 61, 30),
        (["SACLI"], 12, 0),  # alerta fuera de rango
        (["SACLI"], 2, 60),  # la alerta empezaría después de vencer
    ],
)
def test_la_propuesta_invalida_se_rechaza(cursos, meses, dias):
    with pytest.raises(ErrorAplicacion) as error:
        validar_propuesta(cursos, meses, dias, True, CURSOS)
    assert error.value.estado_http == 422


# --- Con PostgreSQL -------------------------------------------------------------------


async def ultimo_evento(sesion, accion: str) -> AuditoriaEvento:
    return await sesion.scalar(
        select(AuditoriaEvento).where(AuditoriaEvento.accion == accion).order_by(AuditoriaEvento.id.desc())
    )


def codigo_siguiente(cliente_api) -> str:
    """Código del siguiente intervalo: el actual ya se usó para vincular el autenticador."""
    return pyotp.TOTP(cliente_api.secreto_totp).at(time.time() + 30)


@requiere_postgresql
async def test_solo_quien_tiene_el_componente_ve_el_panel(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    for ruta in ("/api/parametros/habilitacion", "/api/parametros/plantillas", "/api/parametros/seguridad"):
        assert (await cliente_api.get(ruta)).status_code == 403


@requiere_postgresql
async def test_simular_y_guardar_la_regla_con_totp_y_auditoria(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    # Un militar APTO solo por SACLI: si SACLI deja de ser habilitante, pasa a NO APTO.
    await crear_militar(sesion_bd, "sacli", 41)

    regla = (await cliente_api.get("/api/parametros/habilitacion")).json()
    valores = regla["valores"]
    assert {"SACLI", "SACME"} <= {curso["codigo"] for curso in regla["cursos_disponibles"]}
    propuesta = {**valores, "cursos_habilitantes": ["SACME"]}

    simulacion = await cliente_api.post(
        "/api/parametros/habilitacion/simular", json=propuesta, headers=cabecera_csrf(cliente_api)
    )
    assert simulacion.status_code == 200, simulacion.text
    datos = simulacion.json()
    assert datos["pasan_a_no_apto"] >= 1
    assert datos["propuesto"]["total"] == datos["actual"]["total"]
    # Simular no guarda nada.
    assert (await cliente_api.get("/api/parametros/habilitacion")).json()["valores"] == valores

    guardar = {**propuesta, "version": regla["actualizado_en"]}
    sin_codigo = await cliente_api.put(
        "/api/parametros/habilitacion", json=guardar, headers=cabecera_csrf(cliente_api)
    )
    assert sin_codigo.status_code == 409 and sin_codigo.json()["error"]["codigo"] == "TOTP_REQUERIDO"
    errado = await cliente_api.put(
        "/api/parametros/habilitacion",
        json={**guardar, "codigo_totp": "000000"},
        headers=cabecera_csrf(cliente_api),
    )
    assert errado.status_code == 422 and errado.json()["error"]["codigo"] == "TOTP_INVALIDO"

    correcto = await cliente_api.put(
        "/api/parametros/habilitacion",
        json={**guardar, "codigo_totp": codigo_siguiente(cliente_api)},
        headers=cabecera_csrf(cliente_api),
    )
    assert correcto.status_code == 200, correcto.text
    assert correcto.json()["valores"]["cursos_habilitantes"] == ["SACME"]
    evento = await ultimo_evento(sesion_bd, "PARAMETROS_ACTUALIZADOS")
    assert evento.detalle["cambios"]["CURSOS_HABILITANTES"] == {
        "anterior": valores["cursos_habilitantes"],
        "nuevo": ["SACME"],
    }

    # Con la versión vieja (otro administrador ya guardó) no se sobrescribe.
    viejo = await cliente_api.put(
        "/api/parametros/habilitacion",
        json={**guardar, "cursos_habilitantes": ["SACLI"], "codigo_totp": "123456"},
        headers=cabecera_csrf(cliente_api),
    )
    assert viejo.status_code == 409 and viejo.json()["error"]["codigo"] == "PARAMETROS_DESACTUALIZADOS"


@requiere_postgresql
async def test_guardar_exige_csrf(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    regla = (await cliente_api.get("/api/parametros/habilitacion")).json()
    respuesta = await cliente_api.put(
        "/api/parametros/habilitacion", json={**regla["valores"], "version": regla["actualizado_en"]}
    )
    assert respuesta.status_code == 403


@requiere_postgresql
async def test_publicar_descargar_y_retirar_una_plantilla(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    contenido = libro_xlsx()
    nombre = f"Plantilla de prueba {uuid.uuid4().hex[:6]}"
    formulario = {"nombre_oficial": nombre, "version": "v1.0", "descripcion": "Para el cargue."}

    publicada = await cliente_api.post(
        "/api/parametros/plantillas",
        data=formulario,
        files={"archivo": ("Plantilla_Cargue.xlsx", contenido)},
        headers=cabecera_csrf(cliente_api),
    )
    assert publicada.status_code == 201, publicada.text
    plantilla = publicada.json()
    assert plantilla["formato"] == "XLSX" and plantilla["tamano_bytes"] == len(contenido)
    assert "contenido" not in plantilla

    repetida = await cliente_api.post(
        "/api/parametros/plantillas",
        data=formulario,
        files={"archivo": ("otra.xlsx", contenido)},
        headers=cabecera_csrf(cliente_api),
    )
    assert repetida.status_code == 409

    falsa = await cliente_api.post(
        "/api/parametros/plantillas",
        data={**formulario, "version": "v2"},
        files={"archivo": ("falsa.pdf", contenido)},
        headers=cabecera_csrf(cliente_api),
    )
    assert falsa.status_code == 422 and falsa.json()["error"]["codigo"] == "ARCHIVO_INVALIDO"

    listado = (await cliente_api.get("/api/parametros/plantillas", params={"formato": "XLSX"})).json()
    assert plantilla["id"] in {p["id"] for p in listado}
    solo_pdf = (await cliente_api.get("/api/parametros/plantillas", params={"formato": "PDF"})).json()
    assert all(p["formato"] == "PDF" for p in solo_pdf)

    descarga = await cliente_api.get(f"/api/parametros/plantillas/{plantilla['id']}/descarga")
    assert descarga.status_code == 200 and descarga.content == contenido
    assert descarga.headers["content-disposition"].startswith("attachment;")
    assert descarga.headers["x-content-type-options"] == "nosniff"
    assert (await ultimo_evento(sesion_bd, "PLANTILLA_DESCARGADA")).detalle["plantilla_id"] == plantilla["id"]

    retirada = await cliente_api.post(
        f"/api/parametros/plantillas/{plantilla['id']}/retirar", headers=cabecera_csrf(cliente_api)
    )
    assert retirada.status_code == 204
    assert plantilla["id"] not in {
        p["id"] for p in (await cliente_api.get("/api/parametros/plantillas")).json()
    }
    assert (
        await cliente_api.get(f"/api/parametros/plantillas/{plantilla['id']}/descarga")
    ).status_code == 404
    assert (await ultimo_evento(sesion_bd, "PLANTILLA_RETIRADA")).detalle["plantilla_id"] == plantilla["id"]


@requiere_postgresql
async def test_parametros_de_seguridad_solo_consulta(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    datos = (await cliente_api.get("/api/parametros/seguridad")).json()
    assert datos["intento_captcha"] == 4 and datos["intento_bloqueo"] == 7
    assert datos["usuarios_con_autenticador"] >= 1  # quien acaba de entrar ya vinculó su autenticador
    assert "PARAMETROS_MODIFICAR" in {politica["codigo"] for politica in datos["politicas"]}
