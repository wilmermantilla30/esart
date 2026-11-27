"""
S2-16: fase de campaña del CAPINTE calificada por ítems.

- Cálculo de la nota, lectura de la marca y validación de los ítems: sin base de datos.
- Plantilla del comandante, carga, Cursos y Parámetros con PostgreSQL (ESART_URL_BD_INTEGRACION);
  todo se revierte al final.
"""

import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.campana import leer_marca, nota_de_items, validar_items
from aplicacion.servicios.notas import (
    COLUMNA_CEDULA,
    COLUMNA_PRIMER_ITEM,
    FILA_ENCABEZADO,
    HOJA_CONTROL,
    HOJA_NOTAS,
    PRIMERA_FILA_ALUMNOS,
    leer_firma,
)
from pruebas.test_auditoria_y_malla import cabecera_csrf, conceder_por_excepcion, entrar
from pruebas.test_carga_notas import agregar_alumno, descargar, subir
from pruebas.test_cursos_instructor_materia import preparar_curso
from pruebas.test_login_hu05 import crear_usuario, iniciar_sesion, requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_panel_parametros import codigo_siguiente, ultimo_evento
from pruebas.test_permisos_notas import documento_civil, registrar_civil
from pruebas.test_revision_notas import codigo_error

pytestmark = pytest.mark.anyio

PUNTAJE_IGUAL = Decimal("0.2632")


# --- Sin base de datos ----------------------------------------------------------------------------


def test_la_nota_es_la_suma_de_los_aprobados_con_tope_de_cinco():
    assert nota_de_items([PUNTAJE_IGUAL] * 17) == Decimal("4.47")
    assert nota_de_items([PUNTAJE_IGUAL] * 19) == Decimal("5.00")  # 5,0008 -> tope 5,00
    assert nota_de_items([]) == Decimal("0.00")


@pytest.mark.parametrize(("valor", "aprobado"), [("X", True), (" x ", True), (None, False), ("", False)])
def test_lee_la_marca_de_aprobado(valor, aprobado):
    assert leer_marca(valor) is aprobado


@pytest.mark.parametrize("valor", ["si", "1", "✓", 1])
def test_rechaza_otras_marcas(valor):
    with pytest.raises(ValueError, match="Escriba X"):
        leer_marca(valor)


def test_valida_los_items_de_parametros():
    items = [{"nombre": f"Ítem {numero}", "puntaje": PUNTAJE_IGUAL} for numero in range(19)]
    assert [item["orden"] for item in validar_items(items)][:3] == [1, 2, 3]
    casos = [
        [],  # sin ítems
        [{"nombre": "Tiro", "puntaje": "4"}],  # no suma 5,00
        [{"nombre": "Tiro", "puntaje": "2.5"}, {"nombre": " tiro ", "puntaje": "2.5"}],  # repetido
        [{"nombre": "Tiro", "puntaje": "2.50001"}, {"nombre": "Trote", "puntaje": "2.5"}],  # 5 decimales
        [{"nombre": "Tiro", "puntaje": "5"}, {"nombre": "Trote", "puntaje": "0"}],  # puntaje 0
        [{"nombre": "TR", "puntaje": "5"}],  # nombre corto
    ]
    for caso in casos:
        with pytest.raises(ErrorAplicacion) as error:
            validar_items(caso)
        assert error.value.codigo == "DATOS_INVALIDOS"


# --- Con PostgreSQL -------------------------------------------------------------------------------


async def items_de_balistica(sesion, curso_id: int) -> tuple[int, list[int]]:
    """Convierte 'Balística' del curso de prueba en fase de campaña con 3 ítems (2 + 2 + 1)."""
    malla_id, materia_id = (
        await sesion.execute(
            text("""
                SELECT m.id, m.materia_id FROM esart.malla_curricular m
                JOIN esart.cursos c ON c.malla_version_id = m.version_id
                JOIN esart.materias mt ON mt.id = m.materia_id
                WHERE c.id = :curso AND mt.nombre = 'BALÍSTICA S202'
            """),
            {"curso": curso_id},
        )
    ).one()
    ids = []
    for orden, (nombre, puntaje) in enumerate((("Tiro", "2"), ("Trote", "2"), ("Helipuerto", "1")), start=1):
        ids.append(
            await sesion.scalar(
                text("""
                    INSERT INTO esart.items_campana (materia_id, orden, nombre, puntaje)
                    VALUES (:materia, :orden, :nombre, CAST(:puntaje AS numeric)) RETURNING id
                """),
                {"materia": materia_id, "orden": orden, "nombre": nombre, "puntaje": puntaje},
            )
        )
    return malla_id, ids


def marcar(plantilla: bytes, marcas: dict[str, list[object]]) -> bytes:
    """Escribe las marcas de cada cédula en las columnas de ítems."""
    libro = load_workbook(io.BytesIO(plantilla))
    hoja = libro[HOJA_NOTAS]
    for fila in range(PRIMERA_FILA_ALUMNOS, hoja.max_row + 1):
        cedula = hoja.cell(fila, COLUMNA_CEDULA).value
        for posicion, marca in enumerate(marcas.get(cedula, [])):
            hoja.cell(fila, COLUMNA_PRIMER_ITEM + posicion).value = marca
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


@requiere_postgresql
async def test_el_comandante_registra_la_fase_de_campana_por_items(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    curso, _ = await preparar_curso(cliente_api, sesion_bd, administrador.id, con_malla=True)
    primera, segunda = [await agregar_alumno(sesion_bd, curso, numero) for numero in (84, 85)]
    malla_id, items = await items_de_balistica(sesion_bd, curso)
    documento = documento_civil()
    comandante = await registrar_civil(cliente_api, documento)
    await sesion_bd.execute(
        text("UPDATE esart.cursos SET comandante_id = :comandante WHERE id = :curso"),
        {"comandante": comandante, "curso": curso},
    )

    # En Cursos la fase de campaña no lleva instructor: es del comandante.
    detalle = (await cliente_api.get(f"/api/cursos/{curso}")).json()
    fase = next(m for m in detalle["materias"] if m["malla_id"] == malla_id)
    assert fase["por_items"] is True
    asignar = await cliente_api.put(
        f"/api/cursos/{curso}/materias/{malla_id}/instructor",
        json={"instructor_id": comandante},
        headers=cabecera_csrf(cliente_api),
    )
    assert asignar.status_code == 422 and codigo_error(asignar) == "MATERIA_POR_ITEMS"

    usuario = await crear_usuario(sesion_bd, roles=("USUARIO",), documento_identidad=documento)
    await conceder_por_excepcion(
        sesion_bd, usuario, "NOTAS_CARGA", puede_acceder=True, puede_leer=True, puede_crear=True
    )
    await iniciar_sesion(cliente_api, usuario.usuario)
    materias = [
        m
        for m in (await cliente_api.get("/api/notas/mis-materias")).json()["materias"]
        if m["curso_id"] == curso
    ]
    # Solo la fase de campaña: las demás materias no las tiene asignadas.
    assert [(m["malla_id"], m["por_items"]) for m in materias] == [(malla_id, True)]

    plantilla = await descargar(cliente_api, curso, malla_id)
    libro = load_workbook(io.BytesIO(plantilla))
    encabezados = [libro[HOJA_NOTAS].cell(FILA_ENCABEZADO, COLUMNA_PRIMER_ITEM + n).value for n in range(4)]
    assert encabezados[0].startswith("1. Tiro (2.0000)") and encabezados[3] == "Nota (calculada)"
    firmado = leer_firma(libro[HOJA_CONTROL]["A1"].value)
    assert [item[0] for item in firmado["i"]] == items

    # Una marca que no es X: se rechaza todo con la fila y el ítem.
    mala = await subir(
        cliente_api, curso, malla_id, marcar(plantilla, {primera: ["X", "X"], segunda: ["si"]})
    )
    assert mala.status_code == 422 and codigo_error(mala) == "NOTAS_INVALIDAS"
    assert any("Ítem 1" in e["mensaje"] for e in mala.json()["error"]["detalle"]["errores"])

    enviada = await subir(
        cliente_api, curso, malla_id, marcar(plantilla, {primera: ["X", "x", None], segunda: [None, "", "X"]})
    )
    assert enviada.status_code == 200, enviada.text
    assert enviada.json()["entrega"]["estado"] == "EN_REVISION"
    assert sorted(n["nota"] for n in enviada.json()["entrega"]["notas"]) == [1.0, 4.0]
    marcados = await sesion_bd.scalar(
        text("""
            SELECT count(*) FILTER (WHERE ie.aprobado) FROM esart.items_entrega ie
            JOIN esart.entregas_notas e ON e.id = ie.entrega_id WHERE e.curso_id = :curso
        """),
        {"curso": curso},
    )
    assert marcados == 3
    evento = await ultimo_evento(sesion_bd, "NOTAS_ENTREGADAS")
    assert evento.detalle["por_items"] is True and evento.detalle["alumnos"] == 2

    # Si cambian los puntajes en Parámetros, la plantilla descargada antes queda vieja.
    await sesion_bd.execute(
        text("UPDATE esart.items_campana SET puntaje = 1.5 WHERE id = :id"), {"id": items[0]}
    )
    vieja = await subir(cliente_api, curso, malla_id, marcar(plantilla, {primera: ["X"], segunda: ["X"]}))
    assert vieja.status_code == 409 and codigo_error(vieja) == "PLANTILLA_DESACTUALIZADA"


@requiere_postgresql
async def test_editar_los_items_en_parametros_con_totp(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    ruta = "/api/parametros/campana"
    vigente = (await cliente_api.get(ruta)).json()
    assert vigente["codigo_materia"] == "MAT-074" and len(vigente["items"]) == 19
    assert round(vigente["total"], 2) == 5.0

    # Se retira el último ítem y se reparten 5,00 entre los 18 restantes.
    items = [
        {"id": item["id"], "nombre": item["nombre"], "puntaje": "0.2778"} for item in vigente["items"][:18]
    ]
    items[-1]["puntaje"] = "0.2774"
    solicitud = {"items": items, "version": vigente["actualizado_en"]}
    no_suma = await cliente_api.put(
        ruta, json={**solicitud, "items": items[:-1]}, headers=cabecera_csrf(cliente_api)
    )
    assert no_suma.status_code == 422 and codigo_error(no_suma) == "DATOS_INVALIDOS"
    sin_codigo = await cliente_api.put(ruta, json=solicitud, headers=cabecera_csrf(cliente_api))
    assert sin_codigo.status_code == 409 and codigo_error(sin_codigo) == "TOTP_REQUERIDO"
    guardado = await cliente_api.put(
        ruta,
        json={**solicitud, "codigo_totp": codigo_siguiente(cliente_api)},
        headers=cabecera_csrf(cliente_api),
    )
    assert guardado.status_code == 200, guardado.text
    assert len(guardado.json()["items"]) == 18 and round(guardado.json()["total"], 2) == 5.0
    retirado = vigente["items"][-1]["id"]
    assert (
        await sesion_bd.scalar(
            text("SELECT activo FROM esart.items_campana WHERE id = :id"), {"id": retirado}
        )
        is False
    )
    evento = await ultimo_evento(sesion_bd, "PARAMETROS_ACTUALIZADOS")
    cambio = evento.detalle["cambios"]["FASE_CAMPANA_CAPINTE"]
    assert len(cambio["anterior"]) == 19 and len(cambio["nuevo"]) == 18

    # Con la versión vieja (otro usuario ya guardó) no se sobrescribe.
    vieja = await cliente_api.put(
        ruta, json={**solicitud, "codigo_totp": "123456"}, headers=cabecera_csrf(cliente_api)
    )
    assert vieja.status_code == 409 and codigo_error(vieja) == "PARAMETROS_DESACTUALIZADOS"
