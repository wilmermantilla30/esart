"""
S2-12: el instructor descarga la plantilla de notas de su materia y la sube.

- Lectura de notas y firma de la plantilla: sin base de datos.
- Flujo completo y validaciones: con PostgreSQL (ESART_URL_BD_INTEGRACION); se revierte al final.
"""

import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from aplicacion.servicios.notas import (
    COLUMNA_CEDULA,
    COLUMNA_NOTA,
    HOJA_CONTROL,
    HOJA_NOTAS,
    PRIMERA_FILA_ALUMNOS,
    firmar,
    leer_firma,
    leer_nota,
)
from pruebas.test_auditoria_y_malla import cabecera_csrf, conceder_por_excepcion, entrar
from pruebas.test_cursos_instructor_materia import preparar_curso
from pruebas.test_login_hu05 import crear_usuario, iniciar_sesion, requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_panel_parametros import ultimo_evento
from pruebas.test_permisos_notas import documento_civil, registrar_civil
from pruebas.test_verificacion_habilitacion import crear_militar

pytestmark = pytest.mark.anyio

RUTA = "/api/notas"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- Sin base de datos ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperada"),
    [
        (4, "4.00"),
        (3.5, "3.50"),
        (3.45, "3.45"),
        ("3,7", "3.70"),
        (" 2.05 ", "2.05"),
        (0, "0.00"),
        (5, "5.00"),
    ],
)
def test_lee_notas_validas(valor, esperada):
    assert leer_nota(valor) == Decimal(esperada)


@pytest.mark.parametrize(
    ("valor", "motivo"),
    [
        (None, "Falta la nota"),
        ("  ", "Falta la nota"),
        ("cuatro", "número"),
        (True, "número"),
        (5.5, "entre 0 y 5"),
        (-1, "entre 0 y 5"),
        (3.555, "2 decimales"),
        ("nan", "número"),
    ],
)
def test_rechaza_notas_invalidas(valor, motivo):
    with pytest.raises(ValueError, match=motivo):
        leer_nota(valor)


def test_la_firma_detecta_cambios():
    token = firmar(7, 42, [3, 1, 2])
    assert leer_firma(token) == {"c": 7, "m": 42, "a": [1, 2, 3]}
    version, datos, firma = token.split(".")
    otro = firmar(8, 42, [1, 2, 3]).split(".")[1]
    assert leer_firma(f"{version}.{otro}.{firma}") is None  # datos cambiados, firma vieja
    assert leer_firma(token[:-1] + ("0" if token[-1] != "0" else "1")) is None
    assert leer_firma(None) is None and leer_firma("basura") is None


# --- Con PostgreSQL -------------------------------------------------------------------


async def agregar_alumno(sesion, curso_id: int, numero: int) -> str:
    cedula = await crear_militar(sesion, "sacli", numero)
    await sesion.execute(
        text("""
            INSERT INTO esart.hoja_vida_artillero (artillero_id, grado, curso_id)
            SELECT id, grado, :curso FROM esart.personal_militar WHERE documento_identidad = :cedula
        """),
        {"curso": curso_id, "cedula": cedula},
    )
    return cedula


async def preparar(cliente_api, sesion, otros_instructores: int = 0):
    """Curso con malla, 2 alumnos y un instructor civil con usuario y NOTAS_CARGA por excepción.
    Deja la sesión abierta como ese instructor. Devuelve (curso, malla_id, cédulas, otros), donde
    otros son las cédulas de instructores civiles extra registrados sin materias (pocos inicios
    de sesión por prueba: el TOTP limita los intentos)."""
    administrador = await entrar(cliente_api, sesion, roles=("ADMINISTRADOR",))
    curso, _ = await preparar_curso(cliente_api, sesion, administrador.id, con_malla=True)
    cedulas = [await agregar_alumno(sesion, curso, 81), await agregar_alumno(sesion, curso, 82)]
    documento = documento_civil()
    instructor = await registrar_civil(cliente_api, documento)
    otros = [documento_civil() for _ in range(otros_instructores)]
    for otro in otros:
        await registrar_civil(cliente_api, otro)
    detalle = (await cliente_api.get(f"/api/cursos/{curso}")).json()
    malla_id = next(m["malla_id"] for m in detalle["materias"] if m["materia"] == "TOPOGRAFÍA S202")
    asignado = await cliente_api.put(
        f"/api/cursos/{curso}/materias/{malla_id}/instructor",
        json={"instructor_id": instructor},
        headers=cabecera_csrf(cliente_api),
    )
    assert asignado.status_code == 200, asignado.text

    usuario = await crear_usuario(sesion, roles=("USUARIO",), documento_identidad=documento)
    await conceder_por_excepcion(
        sesion, usuario, "NOTAS_CARGA", puede_acceder=True, puede_leer=True, puede_crear=True
    )
    await iniciar_sesion(cliente_api, usuario.usuario)
    return curso, malla_id, cedulas, otros


async def descargar(cliente_api, curso: int, malla_id: int) -> bytes:
    respuesta = await cliente_api.get(f"{RUTA}/plantilla/{curso}/{malla_id}")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == TIPO_XLSX
    return respuesta.content


def llenar(plantilla: bytes, notas: dict[str, object], *, cambiar=None) -> bytes:
    """Escribe la nota de cada cédula (como lo haría el instructor en Excel)."""
    libro = load_workbook(io.BytesIO(plantilla))
    hoja = libro[HOJA_NOTAS]
    for fila in range(PRIMERA_FILA_ALUMNOS, hoja.max_row + 1):
        cedula = hoja.cell(fila, COLUMNA_CEDULA).value
        if cedula in notas:
            hoja.cell(fila, COLUMNA_NOTA).value = notas[cedula]
    if cambiar:
        cambiar(libro)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


async def subir(cliente_api, curso: int, malla_id: int, contenido: bytes, nombre="notas.xlsx"):
    return await cliente_api.post(
        f"{RUTA}/entregas/{curso}/{malla_id}",
        files={"archivo": (nombre, contenido, TIPO_XLSX)},
        headers=cabecera_csrf(cliente_api),
    )


@requiere_postgresql
async def test_descargar_subir_y_reemplazar_la_planilla(cliente_api, sesion_bd):  # noqa: F811
    curso, malla_id, cedulas, _ = await preparar(cliente_api, sesion_bd)

    yo = (await cliente_api.get("/api/auth/yo")).json()
    assert "NOTAS_CARGA" in {elemento["codigo"] for elemento in yo["menu"]}
    mias = (await cliente_api.get(f"{RUTA}/mis-materias")).json()
    assert mias["es_instructor"] is True
    materia = next(m for m in mias["materias"] if m["curso_id"] == curso)
    assert (materia["malla_id"], materia["alumnos"], materia["estado_entrega"]) == (malla_id, 2, None)

    plantilla = await descargar(cliente_api, curso, malla_id)
    libro = load_workbook(io.BytesIO(plantilla))
    assert libro[HOJA_CONTROL].sheet_state == "veryHidden"
    assert sorted(libro[HOJA_NOTAS].cell(f, COLUMNA_CEDULA).value for f in (9, 10)) == sorted(cedulas)

    enviada = await subir(
        cliente_api, curso, malla_id, llenar(plantilla, {cedulas[0]: 4.25, cedulas[1]: "2,8"})
    )
    assert enviada.status_code == 200, enviada.text
    entrega = enviada.json()["entrega"]
    assert entrega["estado"] == "EN_REVISION"
    assert sorted(n["nota"] for n in entrega["notas"]) == [2.8, 4.25]
    evento = await ultimo_evento(sesion_bd, "NOTAS_ENTREGADAS")
    assert evento.detalle["alumnos"] == 2 and evento.detalle["reemplaza"] is None
    assert evento.detalle["por_debajo_de_la_minima"] == 1  # 2,80 < 3,00

    # Mientras está en revisión, otra carga la reemplaza.
    otra = await subir(cliente_api, curso, malla_id, llenar(plantilla, {cedulas[0]: 5, cedulas[1]: 3}))
    assert sorted(n["nota"] for n in otra.json()["entrega"]["notas"]) == [3.0, 5.0]
    assert (await ultimo_evento(sesion_bd, "NOTAS_ENTREGADAS")).detalle["reemplaza"] == "EN_REVISION"
    materia = next(
        m
        for m in (await cliente_api.get(f"{RUTA}/mis-materias")).json()["materias"]
        if m["curso_id"] == curso
    )
    assert (materia["estado_entrega"], materia["notas_entregadas"]) == ("EN_REVISION", 2)

    # Ya aprobada por el Inspector, no se puede volver a subir.
    await sesion_bd.execute(
        text("UPDATE esart.entregas_notas SET estado = 'APROBADA' WHERE curso_id = :c"), {"c": curso}
    )
    aprobada = await subir(cliente_api, curso, malla_id, llenar(plantilla, {cedulas[0]: 1, cedulas[1]: 1}))
    assert aprobada.status_code == 409 and aprobada.json()["error"]["codigo"] == "ENTREGA_APROBADA"


@requiere_postgresql
async def test_la_planilla_invalida_se_rechaza_completa(cliente_api, sesion_bd):  # noqa: F811
    curso, malla_id, cedulas, _ = await preparar(cliente_api, sesion_bd)
    plantilla = await descargar(cliente_api, curso, malla_id)

    def errores(respuesta) -> list[str]:
        assert respuesta.status_code == 422, respuesta.text
        assert respuesta.json()["error"]["codigo"] == "NOTAS_INVALIDAS"
        return [e["mensaje"] for e in respuesta.json()["error"]["detalle"]["errores"]]

    assert errores(await subir(cliente_api, curso, malla_id, llenar(plantilla, {cedulas[0]: 4}))) == [
        "Falta la nota."
    ]
    mensajes = errores(
        await subir(cliente_api, curso, malla_id, llenar(plantilla, {cedulas[0]: 5.5, cedulas[1]: 3.555}))
    )
    assert any("entre 0 y 5" in m for m in mensajes) and any("2 decimales" in m for m in mensajes)

    def alumno_ajeno(libro):
        libro[HOJA_NOTAS].cell(PRIMERA_FILA_ALUMNOS, COLUMNA_CEDULA).value = "1234567"

    mensajes = errores(
        await subir(
            cliente_api,
            curso,
            malla_id,
            llenar(plantilla, {cedulas[0]: 4, cedulas[1]: 4}, cambiar=alumno_ajeno),
        )
    )
    assert any("no corresponde a un alumno" in m for m in mensajes) and any(
        "Falta el alumno" in m for m in mensajes
    )
    # Nada se guardó.
    assert not await sesion_bd.scalar(
        text("SELECT 1 FROM esart.entregas_notas WHERE curso_id = :c"), {"c": curso}
    )

    def alterar_firma(libro):
        libro[HOJA_CONTROL]["A1"] = "v1.e30.firma-falsa"

    alterada = await subir(
        cliente_api, curso, malla_id, llenar(plantilla, {cedulas[0]: 4, cedulas[1]: 4}, cambiar=alterar_firma)
    )
    assert alterada.status_code == 422 and alterada.json()["error"]["codigo"] == "PLANTILLA_ALTERADA"

    no_excel = await subir(cliente_api, curso, malla_id, b"%PDF-1.4 hola", nombre="notas.pdf")
    assert no_excel.status_code == 422 and no_excel.json()["error"]["codigo"] == "ARCHIVO_INVALIDO"

    # Un alumno nuevo en el curso después de descargar: la plantilla quedó vieja.
    await agregar_alumno(sesion_bd, curso, 83)
    vieja = await subir(cliente_api, curso, malla_id, llenar(plantilla, {cedulas[0]: 4, cedulas[1]: 4}))
    assert vieja.status_code == 409 and vieja.json()["error"]["codigo"] == "PLANTILLA_DESACTUALIZADA"


@requiere_postgresql
async def test_solo_el_instructor_titular_ve_y_carga_la_materia(cliente_api, sesion_bd):  # noqa: F811
    curso, malla_id, _, (otro_documento,) = await preparar(cliente_api, sesion_bd, otros_instructores=1)

    # Otro instructor con el mismo permiso pero sin esa materia.
    otro = await crear_usuario(sesion_bd, roles=("USUARIO",), documento_identidad=otro_documento)
    await conceder_por_excepcion(
        sesion_bd, otro, "NOTAS_CARGA", puede_acceder=True, puede_leer=True, puede_crear=True
    )
    await iniciar_sesion(cliente_api, otro.usuario)
    assert (await cliente_api.get(f"{RUTA}/mis-materias")).json() == {"es_instructor": True, "materias": []}
    ajena = await cliente_api.get(f"{RUTA}/plantilla/{curso}/{malla_id}")
    assert ajena.status_code == 403 and ajena.json()["error"]["codigo"] == "MATERIA_NO_ASIGNADA"

    # Con el permiso pero sin ser instructor.
    sin_instructor = await crear_usuario(sesion_bd, roles=("USUARIO",))
    await conceder_por_excepcion(
        sesion_bd, sin_instructor, "NOTAS_CARGA", puede_acceder=True, puede_leer=True
    )
    await iniciar_sesion(cliente_api, sin_instructor.usuario)
    assert (await cliente_api.get(f"{RUTA}/mis-materias")).json() == {"es_instructor": False, "materias": []}
    respuesta = await cliente_api.get(f"{RUTA}/plantilla/{curso}/{malla_id}")
    assert respuesta.status_code == 403 and respuesta.json()["error"]["codigo"] == "NO_ES_INSTRUCTOR"
