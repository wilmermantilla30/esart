"""
S2-15: nota final, puesto y cierre del curso.

- Cálculo de la nota final y del puesto (empates y casos límite): sin base de datos.
- Resultados provisionales y cierre con PostgreSQL (ESART_URL_BD_INTEGRACION); se revierte al
  final. Las notas oficiales, habilitaciones y decisiones del Consejo se cargan directamente en la
  base: su flujo ya se prueba en test_carga_notas, test_revision_notas y test_habilitacion_consejo.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

from aplicacion.servicios.resultados_curso import (
    APROBADO,
    REPROBADO,
    AlumnoEnCalculo,
    NotaDeMateria,
    calcular_resultados,
    es_area_especifica,
)
from pruebas.test_auditoria_y_malla import cabecera_csrf, entrar
from pruebas.test_carga_notas import agregar_alumno
from pruebas.test_cursos_instructor_materia import preparar_curso
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_nota_minima import fijar_nota_inicial
from pruebas.test_panel_parametros import codigo_siguiente, ultimo_evento
from pruebas.test_revision_notas import codigo_error

pytestmark = pytest.mark.anyio

MINIMA = Decimal("3.00")


# --- Cálculo (sin base de datos) ------------------------------------------------------------------


def alumno(nombre: str, notas: list[str], *, habilitadas=0, especificas=(), **otros) -> AlumnoEnCalculo:
    """Alumno con esas notas; las primeras `habilitadas` pasaron por habilitación."""
    return AlumnoEnCalculo(
        personal_id=hash(nombre),
        cedula=nombre,
        grado="SV",
        apellidos=nombre,
        nombres="",
        notas=[
            NotaDeMateria(
                Decimal(nota), habilitada=posicion < habilitadas, especifica=posicion in especificas
            )
            for posicion, nota in enumerate(notas)
        ],
        **otros,
    )


def puestos(filas: list[dict]) -> dict[str, int | None]:
    return {fila["cedula"]: fila["puesto"] for fila in filas}


def test_quien_habilito_queda_despues_aunque_tenga_mejor_nota():
    filas = calcular_resultados(
        [alumno("A", ["4.0", "4.0"]), alumno("B", ["5.0", "4.8"], habilitadas=1)], MINIMA
    )
    assert [fila["cedula"] for fila in filas] == ["A", "B"]
    assert puestos(filas) == {"A": 1, "B": 2}


def test_desempatan_los_decimales_luego_las_habilitadas_y_el_area_especifica():
    filas = calcular_resultados(
        [
            # 13/3 = 4.3333… y 4.33: misma nota final con 2 decimales, gana la de más decimales.
            alumno("decimales_menor", ["4.33", "4.33", "4.33"]),
            alumno("decimales_mayor", ["4.33", "4.33", "4.34"]),
            # Habilitaron los dos con el mismo promedio: gana quien habilitó menos materias.
            alumno("dos_habilitadas", ["4.0", "4.0"], habilitadas=2),
            alumno("una_habilitada", ["4.0", "4.0"], habilitadas=1),
            # Mismo promedio: desempata el área profesional específica.
            alumno("especifica_baja", ["3.5", "4.5"], especificas=(0,)),
            alumno("especifica_alta", ["3.5", "4.5"], especificas=(1,)),
        ],
        MINIMA,
    )
    orden = [fila["cedula"] for fila in filas]
    assert orden.index("decimales_mayor") < orden.index("decimales_menor")
    assert orden.index("especifica_alta") < orden.index("especifica_baja")
    assert orden[-2:] == ["una_habilitada", "dos_habilitadas"]
    assert {fila["cedula"]: fila["nota_final"] for fila in filas}["decimales_mayor"] == Decimal("4.33")


def test_empate_total_comparte_el_puesto_y_salta_el_siguiente():
    filas = calcular_resultados(
        [alumno("A", ["4.5"]), alumno("B", ["4.0"]), alumno("C", ["4.0"]), alumno("D", ["3.5"])], MINIMA
    )
    assert puestos(filas) == {"A": 1, "B": 2, "C": 2, "D": 4}


def test_reprobados_sin_puesto_y_pendientes_sin_resultado():
    filas = calcular_resultados(
        [
            alumno("justo", ["3.00", "3.00"]),
            alumno("por_debajo", ["2.99", "3.00"]),  # 2.995 -> 3.00 con 2 decimales: aprueba
            alumno("bajo", ["2.0", "3.0"]),
            alumno("consejo", ["4.8", "4.9"], habilitadas=1, reprobado_por_consejo="Repite el curso"),
            alumno("incompleto", ["4.0"], pendientes=["Balística: falta la nota aprobada."]),
        ],
        MINIMA,
    )
    por_cedula = {fila["cedula"]: fila for fila in filas}
    assert por_cedula["justo"]["resultado"] == APROBADO
    assert (por_cedula["por_debajo"]["nota_final"], por_cedula["por_debajo"]["resultado"]) == (
        Decimal("3.00"),
        APROBADO,
    )
    assert (por_cedula["bajo"]["resultado"], por_cedula["bajo"]["puesto"]) == (REPROBADO, None)
    assert "mínima" in por_cedula["bajo"]["motivo"]
    assert por_cedula["consejo"]["resultado"] == REPROBADO and "Repite" in por_cedula["consejo"]["motivo"]
    assert (por_cedula["incompleto"]["resultado"], por_cedula["incompleto"]["puesto"]) == (None, None)
    # Orden: aprobados por puesto, reprobados por nota y al final los incompletos.
    assert [fila["cedula"] for fila in filas][-1] == "incompleto"


@pytest.mark.parametrize(
    ("area", "esperado"),
    [
        ("Profesional Específica", True),
        ("PROFESIONAL ESPECIFICA", True),
        ("  profesional   específica ", True),
        ("Profesional General", False),
        (None, False),
    ],
)
def test_reconoce_el_area_profesional_especifica(area, esperado):
    assert es_area_especifica(area) is esperado


# --- Con PostgreSQL -------------------------------------------------------------------------------


async def materias_evaluables(sesion, curso_id: int) -> list[int]:
    filas = await sesion.execute(
        text("""
            SELECT m.id FROM esart.malla_curricular m
            JOIN esart.cursos c ON c.malla_version_id = m.version_id
            WHERE c.id = :curso AND m.evaluable ORDER BY m.orden
        """),
        {"curso": curso_id},
    )
    return [fila.id for fila in filas]


async def entrega(sesion, curso_id: int, malla_id: int, tipo="ORDINARIA", estado="APROBADA") -> int:
    """Entrega ya aprobada (la exige la llave de las notas oficiales)."""
    return await sesion.scalar(
        text("""
            INSERT INTO esart.entregas_notas
              (curso_id, malla_id, tipo, instructor_id, estado, nombre_archivo, sha256)
            SELECT :curso, :malla, :tipo, c.comandante_id, :estado, 'prueba.xlsx', repeat('0', 64)
            FROM esart.cursos c WHERE c.id = :curso
            RETURNING id
        """),
        {"curso": curso_id, "malla": malla_id, "tipo": tipo, "estado": estado},
    )


async def personal_id(sesion, cedula: str) -> int:
    return await sesion.scalar(
        text("SELECT id FROM esart.personal_militar WHERE documento_identidad = :c"), {"c": cedula}
    )


async def nota_oficial(
    sesion, curso_id, malla_id, entrega_id, cedula, nota, origen="ORDINARIA", ordinaria=None
):
    await sesion.execute(
        text("""
            INSERT INTO esart.notas_oficiales
              (curso_id, malla_id, personal_id, nota, nota_ordinaria, origen, entrega_id)
            VALUES (:curso, :malla, :persona, :nota, :ordinaria, :origen, :entrega)
        """),
        {
            "curso": curso_id,
            "malla": malla_id,
            "persona": await personal_id(sesion, cedula),
            "nota": nota,
            "ordinaria": ordinaria if ordinaria is not None else nota,
            "origen": origen,
            "entrega": entrega_id,
        },
    )


async def habilitacion(sesion, curso_id, malla_id, entrega_id, cedula, nota, resultado) -> int:
    return await sesion.scalar(
        text("""
            INSERT INTO esart.habilitaciones_materia
              (curso_id, malla_id, personal_id, entrega_id, nota, resultado)
            VALUES (:curso, :malla, :persona, :entrega, :nota, :resultado) RETURNING id
        """),
        {
            "curso": curso_id,
            "malla": malla_id,
            "persona": await personal_id(sesion, cedula),
            "entrega": entrega_id,
            "nota": nota,
            "resultado": resultado,
        },
    )


async def curso_en_historial(sesion, curso_id: int, cedula: str) -> None:
    """Lo que deja el cargue por Excel: el curso en el historial del artillero, sin aprobar."""
    await sesion.execute(
        text("""
            INSERT INTO esart.artillero_cursos
              (hoja_vida_id, tipo_curso_id, nombre, institucion, fecha_inicio, aprobado)
            SELECT hv.id, c.tipo_curso_id, c.nombre, 'Escuela de Artillería', c.fecha_inicio, false
            FROM esart.hoja_vida_artillero hv JOIN esart.cursos c ON c.id = hv.curso_id
            JOIN esart.personal_militar p ON p.id = hv.artillero_id
            WHERE c.id = :curso AND p.documento_identidad = :cedula
        """),
        {"curso": curso_id, "cedula": cedula},
    )


async def aprobado_en_historial(sesion, curso_id: int, cedula: str) -> bool:
    return await sesion.scalar(
        text("""
            SELECT ac.aprobado FROM esart.artillero_cursos ac
            JOIN esart.hoja_vida_artillero hv ON hv.id = ac.hoja_vida_id
            JOIN esart.personal_militar p ON p.id = hv.artillero_id
            WHERE hv.curso_id = :curso AND p.documento_identidad = :cedula
        """),
        {"curso": curso_id, "cedula": cedula},
    )


@requiere_postgresql
async def test_resultados_provisionales_y_cierre_del_curso(cliente_api, sesion_bd):  # noqa: F811
    await fijar_nota_inicial(sesion_bd)
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    curso, _ = await preparar_curso(cliente_api, sesion_bd, administrador.id, con_malla=True)
    primero, habilito, consejo = [await agregar_alumno(sesion_bd, curso, numero) for numero in (91, 92, 93)]
    for cedula in (primero, habilito, consejo):
        await curso_en_historial(sesion_bd, curso, cedula)
    ruta = f"/api/cursos/{curso}/resultados"

    # Sin notas: provisional, con lo que falta por alumno.
    provisional = (await cliente_api.get(ruta)).json()
    assert (provisional["cerrado"], provisional["completo"], provisional["puede_cerrar"]) == (
        False,
        False,
        False,
    )
    assert provisional["materias_evaluables"] == 2
    assert all(len(a["pendientes"]) == 2 and a["resultado"] is None for a in provisional["alumnos"])
    incompleto = await cliente_api.post(
        f"/api/cursos/{curso}/cerrar", json={}, headers=cabecera_csrf(cliente_api)
    )
    assert incompleto.status_code == 409 and codigo_error(incompleto) == "RESULTADOS_INCOMPLETOS"
    assert incompleto.json()["error"]["detalle"]["pendientes"]

    topografia, balistica = await materias_evaluables(sesion_bd, curso)
    entrega_topografia = await entrega(sesion_bd, curso, topografia)
    entrega_balistica = await entrega(sesion_bd, curso, balistica)
    for cedula, notas in (
        (primero, ("4.20", "4.00")),
        (habilito, ("4.50", "4.80")),
        (consejo, ("4.90", "4.90")),
    ):
        await nota_oficial(sesion_bd, curso, topografia, entrega_topografia, cedula, notas[0])
    await nota_oficial(sesion_bd, curso, balistica, entrega_balistica, primero, "4.00")
    # Habilitó Balística (2,00 -> 3,50): cuenta 3,50 y queda después aunque su promedio sea mayor.
    await nota_oficial(
        sesion_bd,
        curso,
        balistica,
        entrega_balistica,
        habilito,
        "3.50",
        origen="HABILITACION",
        ordinaria="2.00",
    )
    # Perdió la habilitación de Balística y el Consejo decidió que repite el curso.
    await nota_oficial(sesion_bd, curso, balistica, entrega_balistica, consejo, "1.00")

    # Sin habilitación ni decisión del Consejo, sigue pendiente; con una entrega abierta, también.
    abierta = await entrega(sesion_bd, curso, balistica, tipo="HABILITACION", estado="EN_REVISION")
    pendiente = (await cliente_api.get(ruta)).json()
    assert not pendiente["completo"] and any("en revisión" in p for p in pendiente["pendientes"])
    await sesion_bd.execute(
        text("UPDATE esart.entregas_notas SET estado = 'APROBADA' WHERE id = :id"), {"id": abierta}
    )
    await habilitacion(sesion_bd, curso, balistica, abierta, habilito, "3.50", "APROBADA")
    perdida = await habilitacion(sesion_bd, curso, balistica, abierta, consejo, "2.00", "REPROBADA")
    falta_consejo = (await cliente_api.get(ruta)).json()
    assert any("Consejo" in p for a in falta_consejo["alumnos"] for p in a["pendientes"])
    await sesion_bd.execute(
        text("""
            INSERT INTO esart.decisiones_consejo (habilitacion_id, decision, numero_acta, fecha_acta)
            VALUES (:id, 'REPITE_CURSO', 'Acta 1', current_date)
        """),
        {"id": perdida},
    )

    completo = (await cliente_api.get(ruta)).json()
    assert (completo["completo"], completo["puede_cerrar"]) == (True, True)
    por_cedula = {a["cedula"]: a for a in completo["alumnos"]}
    assert (por_cedula[primero]["nota_final"], por_cedula[primero]["puesto"]) == (4.1, 1)
    assert (por_cedula[habilito]["nota_final"], por_cedula[habilito]["puesto"]) == (4.0, 2)
    assert por_cedula[habilito]["materias_habilitadas"] == 1
    # Cuenta la nota de habilitación perdida (2,00), no la ordinaria; reprobado por el Consejo.
    assert (por_cedula[consejo]["nota_final"], por_cedula[consejo]["resultado"]) == (3.45, "REPROBADO")
    assert por_cedula[consejo]["puesto"] is None

    # Cierre con TOTP.
    sin_codigo = await cliente_api.post(
        f"/api/cursos/{curso}/cerrar", json={}, headers=cabecera_csrf(cliente_api)
    )
    assert sin_codigo.status_code == 409 and codigo_error(sin_codigo) == "TOTP_REQUERIDO"
    cerrado = await cliente_api.post(
        f"/api/cursos/{curso}/cerrar",
        json={"codigo_totp": codigo_siguiente(cliente_api)},
        headers=cabecera_csrf(cliente_api),
    )
    assert cerrado.status_code == 200, cerrado.text
    assert (cerrado.json()["cerrado"], cerrado.json()["estado_curso"]) == (True, "CULMINADO")
    assert [a["puesto"] for a in cerrado.json()["alumnos"]] == [1, 2, None]
    assert await sesion_bd.scalar(text("SELECT estado FROM esart.cursos WHERE id = :id"), {"id": curso}) == (
        "CULMINADO"
    )
    # El historial que alimenta APTO / NO APTO: aprobado solo para los aprobados.
    assert await aprobado_en_historial(sesion_bd, curso, primero) is True
    assert await aprobado_en_historial(sesion_bd, curso, habilito) is True
    assert await aprobado_en_historial(sesion_bd, curso, consejo) is False
    evento = await ultimo_evento(sesion_bd, "CURSO_CERRADO")
    assert (evento.detalle["aprobados"], evento.detalle["reprobados"]) == (2, 1)
    assert (evento.detalle["primer_puesto"], evento.detalle["historial_actualizado"]) == ([primero], 2)

    # Cerrado: los resultados quedan guardados y no se vuelve a cerrar.
    guardado = (await cliente_api.get(ruta)).json()
    assert guardado["cerrado"] is True and guardado["cerrado_por"] == administrador.usuario
    otra_vez = await cliente_api.post(
        f"/api/cursos/{curso}/cerrar", json={}, headers=cabecera_csrf(cliente_api)
    )
    assert otra_vez.status_code == 409 and codigo_error(otra_vez) == "CURSO_NO_EDITABLE"


@requiere_postgresql
async def test_curso_sin_malla_no_tiene_nota_final(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    curso, _ = await preparar_curso(cliente_api, sesion_bd, administrador.id)
    respuesta = await cliente_api.get(f"/api/cursos/{curso}/resultados")
    assert respuesta.status_code == 409 and codigo_error(respuesta) == "CURSO_SIN_MALLA"
    assert (await cliente_api.get("/api/cursos/999999999/resultados")).status_code == 404
