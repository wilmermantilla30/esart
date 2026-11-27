"""
S2-17: historial académico en la verificación del artillero y en la Certificación.

- Reglas de la materia y bloque del PDF: sin base de datos.
- Verificación con un curso en curso (parcial) y cerrado, con PostgreSQL (ESART_URL_BD_INTEGRACION);
  se revierte al final. Las notas oficiales se cargan en la base (su flujo se prueba en S2-12..S2-15).
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from aplicacion.reportes.certificacion import historial_academico as bloque_historial
from aplicacion.reportes.comun import DatosDocumento, HistorialCursoDocumento, MateriaDocumento, estilos
from aplicacion.servicios.historial_academico import (
    APROBADA_POR_CONSEJO,
    HABILITACION_PERDIDA,
    HABILITADA,
    estado_materia,
    nota_que_cuenta,
)
from pruebas.test_auditoria_y_malla import entrar
from pruebas.test_carga_notas import agregar_alumno
from pruebas.test_cursos_instructor_materia import preparar_curso
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_resultados_curso import entrega, habilitacion, materias_evaluables, nota_oficial

pytestmark = pytest.mark.anyio


# --- Sin base de datos ----------------------------------------------------------------------------


def test_como_termino_cada_materia():
    assert estado_materia("ORDINARIA", None) is None
    assert estado_materia("HABILITACION", "APROBADA") == HABILITADA
    assert estado_materia("CONSEJO", "REPROBADA") == APROBADA_POR_CONSEJO
    assert estado_materia("ORDINARIA", "REPROBADA") == HABILITACION_PERDIDA


def test_la_nota_que_cuenta_es_la_misma_de_la_nota_final():
    fila = SimpleNamespace(nota=Decimal("2.00"), origen="ORDINARIA", resultado_habilitacion="REPROBADA")
    # Perdió la habilitación y el Consejo no aprobó: cuenta la de habilitación.
    assert nota_que_cuenta(SimpleNamespace(**vars(fila), nota_habilitacion=Decimal("2.40"))) == Decimal(
        "2.40"
    )
    assert nota_que_cuenta(
        SimpleNamespace(
            nota=Decimal("3.00"),
            origen="CONSEJO",
            resultado_habilitacion="REPROBADA",
            nota_habilitacion=Decimal("2.40"),
        )
    ) == Decimal("3.00")
    assert (
        nota_que_cuenta(
            SimpleNamespace(nota=None, origen=None, resultado_habilitacion=None, nota_habilitacion=None)
        )
        is None
    )


def test_la_certificacion_trae_el_historial_con_el_puesto():
    datos = DatosDocumento(
        cedula="1012345678",
        grado="SV",
        nombres="Juan",
        apellidos="Pérez",
        categoria="SUBOFICIAL",
        unidad=None,
        activo=True,
        resultado="APTO",
        fecha_expedicion=date(2026, 11, 27),
        numero="ESART-1",
        expedido_por="admin",
        historial=[
            HistorialCursoDocumento(
                nombre="SACLI 2026-2",
                codigo="SACLI 03",
                fecha_inicio=date(2026, 8, 3),
                fecha_fin=date(2026, 11, 20),
                cerrado=True,
                nota_final=4.1,
                resultado="APROBADO",
                puesto=3,
                aprobados_del_curso=25,
                materias=[MateriaDocumento("Topografía", 4.2, HABILITADA, "SV Gómez")],
            ),
            HistorialCursoDocumento(
                nombre="CAPINTE 2027",
                codigo="CAPINTE 01",
                fecha_inicio=None,
                fecha_fin=None,
                cerrado=False,
                nota_final=None,
                resultado=None,
                puesto=None,
                aprobados_del_curso=None,
            ),
        ],
    )
    textos = " ".join(getattr(bloque, "text", "") for bloque in bloque_historial(datos, estilos()))
    assert "Historial académico" in textos
    assert "4,10" in textos and "puesto 3 de 25" in textos
    assert "notas parciales" in textos


# --- Con PostgreSQL -------------------------------------------------------------------------------


@requiere_postgresql
async def test_la_verificacion_muestra_el_historial_parcial_y_el_cerrado(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    curso, _ = await preparar_curso(cliente_api, sesion_bd, administrador.id, con_malla=True)
    cedula = await agregar_alumno(sesion_bd, curso, 86)
    topografia, balistica = await materias_evaluables(sesion_bd, curso)
    await sesion_bd.execute(
        text("""
            INSERT INTO esart.cursos_materias_instructor (curso_id, malla_id, instructor_id, asignado_por_id)
            SELECT c.id, :malla, c.comandante_id, :usuario FROM esart.cursos c WHERE c.id = :curso
        """),
        {"curso": curso, "malla": topografia, "usuario": administrador.id},
    )
    entrega_topografia = await entrega(sesion_bd, curso, topografia)
    await nota_oficial(sesion_bd, curso, topografia, entrega_topografia, cedula, "4.20")
    ruta = f"/api/verificar/artillero/{cedula}"

    # En curso: solo Topografía tiene nota aprobada (parcial, sin nota final ni puesto).
    parcial = (await cliente_api.get(ruta)).json()["historial_academico"]
    assert len(parcial) == 1 and parcial[0]["cerrado"] is False
    assert (parcial[0]["nota_final"], parcial[0]["puesto"], parcial[0]["materias_con_nota"]) == (
        None,
        None,
        1,
    )
    por_materia = {m["materia"]: m for m in parcial[0]["materias"]}
    assert por_materia["TOPOGRAFÍA S202"]["nota"] == 4.2 and por_materia["TOPOGRAFÍA S202"]["instructor"]
    assert por_materia["BALÍSTICA S202"]["nota"] is None

    # Habilitó Balística (2,00 -> 3,50) y el curso se cerró con su resultado.
    entrega_balistica = await entrega(sesion_bd, curso, balistica)
    await nota_oficial(
        sesion_bd,
        curso,
        balistica,
        entrega_balistica,
        cedula,
        "3.50",
        origen="HABILITACION",
        ordinaria="2.00",
    )
    entrega_habilitacion = await entrega(sesion_bd, curso, balistica, tipo="HABILITACION")
    await habilitacion(sesion_bd, curso, balistica, entrega_habilitacion, cedula, "3.50", "APROBADA")
    await sesion_bd.execute(
        text("""
            INSERT INTO esart.resultados_curso
              (curso_id, personal_id, nota_final, nota_exacta, materias_evaluadas, materias_habilitadas,
               resultado, puesto)
            SELECT :curso, id, 3.85, 3.85, 2, 1, 'APROBADO', 1 FROM esart.personal_militar
            WHERE documento_identidad = :cedula
        """),
        {"curso": curso, "cedula": cedula},
    )
    await sesion_bd.execute(
        text("UPDATE esart.cursos SET estado = 'CULMINADO' WHERE id = :id"), {"id": curso}
    )
    cerrado = (await cliente_api.get(ruta)).json()["historial_academico"][0]
    assert (cerrado["cerrado"], cerrado["nota_final"], cerrado["resultado"]) == (True, 3.85, "APROBADO")
    assert (cerrado["puesto"], cerrado["aprobados_del_curso"]) == (1, 1)
    por_materia = {m["materia"]: m for m in cerrado["materias"]}
    assert (por_materia["BALÍSTICA S202"]["nota"], por_materia["BALÍSTICA S202"]["estado"]) == (
        3.5,
        HABILITADA,
    )

    # La Certificación sale con el historial.
    pdf = await cliente_api.get(f"{ruta}/documento", params={"tipo": "CERTIFICACION"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
