"""
Pruebas de las estadísticas del panel principal (cursos, alumnos, egresados y avance).

- Cálculos puros: sin base de datos.
- Endpoint: con PostgreSQL (ESART_URL_BD_INTEGRACION); todo se revierte al final.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from aplicacion.servicios.estadisticas import avance_del_curso, catalogo_grados
from pruebas.test_auditoria_y_malla import cabecera_csrf, entrar
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_verificacion_habilitacion import crear_militar

pytestmark = pytest.mark.anyio


# --- Sin base de datos ---------------------------------------------------------------


def test_avance_de_un_curso_por_fechas():
    inicio = date(2026, 1, 1)
    assert avance_del_curso(inicio, inicio + timedelta(days=100), date(2026, 1, 26)) == {
        "dias_totales": 100,
        "dias_transcurridos": 25,
        "porcentaje": 25,
        "dias_restantes": 75,
        "vencido": False,
    }
    vencido = avance_del_curso(inicio, inicio + timedelta(days=10), date(2026, 2, 1))
    assert vencido["porcentaje"] == 100 and vencido["vencido"] and vencido["dias_restantes"] == 0
    sin_empezar = avance_del_curso(date(2026, 3, 1), date(2026, 4, 1), date(2026, 2, 1))
    assert sin_empezar["porcentaje"] == 0 and not sin_empezar["vencido"]


def test_los_grados_salen_en_orden_jerarquico():
    siglas = [grado["sigla"] for grado in catalogo_grados()]
    assert (
        siglas.index("ST")
        < siglas.index("GR")
        < siglas.index("C3")
        < siglas.index("SMCC")
        < siglas.index("SLP")
    )


# --- Con PostgreSQL -------------------------------------------------------------------


async def crear_curso(
    sesion, *, comandante: int, creador: int, inicio: date, estado: str, alumnos: list[str]
) -> int:
    curso_id = await sesion.scalar(
        text("""
            INSERT INTO esart.cursos
              (tipo_curso_id, comandante_id, codigo, nombre, fecha_inicio, fecha_fin, estado, creado_por_id)
            SELECT tc.id, :comandante, :codigo, 'Curso de prueba', :inicio, :fin, :estado, :creador
            FROM esart.tipos_curso tc WHERE tc.codigo = 'SACLI'
            RETURNING id
        """),
        {
            "comandante": comandante,
            "codigo": f"PRUEBA-{uuid.uuid4().hex[:10]}",
            "inicio": inicio,
            "fin": inicio + timedelta(days=70),
            "estado": estado,
            "creador": creador,
        },
    )
    await sesion.execute(
        text("""
            INSERT INTO esart.hoja_vida_artillero (artillero_id, grado, curso_id)
            SELECT id, grado, :curso FROM esart.personal_militar WHERE documento_identidad = ANY(:cedulas)
        """),
        {"curso": curso_id, "cedulas": alumnos},
    )
    return curso_id


@requiere_postgresql
async def test_panel_cuenta_cursos_alumnos_egresados_y_filtra_por_periodo(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    comandante = (
        await cliente_api.post(
            "/api/instructores",
            json={
                "tipo": "CIVIL",
                "documento": f"7{uuid.uuid4().int % 10**9:09d}",
                "nombres": "Comandante",
                "apellidos": "De Prueba",
                "fecha_ingreso_escuela": "2020-01-01",
            },
            headers=cabecera_csrf(cliente_api),
        )
    ).json()["id"]
    alumnos = [await crear_militar(sesion_bd, "sacli", numero) for numero in (81, 82, 83)]

    antes = (await cliente_api.get("/api/estadisticas/panel", params={"anio": 2031})).json()
    # Un año sin cursos en la base: el período empieza vacío.
    assert antes["indicadores"]["cursos_periodo"] == 0

    culminado = await crear_curso(
        sesion_bd, comandante=comandante, creador=administrador.id, inicio=date(2031, 2, 1),
        estado="CULMINADO", alumnos=alumnos,
    )  # fmt: skip
    segundo_semestre = await crear_curso(
        sesion_bd, comandante=comandante, creador=administrador.id, inicio=date(2031, 8, 1),
        estado="APLAZADO", alumnos=alumnos[:1],
    )  # fmt: skip

    anio = (await cliente_api.get("/api/estadisticas/panel", params={"anio": 2031})).json()
    assert anio["indicadores"]["cursos_periodo"] == 2
    assert anio["indicadores"]["alumnos_periodo"] == 4
    assert anio["indicadores"]["egresados"] == 3 and anio["indicadores"]["cursos_culminados"] == 1
    assert {"anio": 2031, "semestre_1": 1, "semestre_2": 1} in anio["cursos_por_anio"]
    detalle = next(curso for curso in anio["cursos"] if curso["id"] == culminado)
    assert detalle["grados"] == {"SV": 3} and detalle["genero"] == {"M": 3, "F": 0}
    assert detalle["comandante"] == "Comandante De Prueba"
    assert [grado["sigla"] for grado in anio["grados"]] == ["SV"]

    primer = (await cliente_api.get("/api/estadisticas/panel", params={"anio": 2031, "semestre": 1})).json()
    assert [curso["id"] for curso in primer["cursos"]] == [culminado]
    segundo = (await cliente_api.get("/api/estadisticas/panel", params={"anio": 2031, "semestre": 2})).json()
    assert [curso["id"] for curso in segundo["cursos"]] == [segundo_semestre]
    assert (await cliente_api.get("/api/estadisticas/panel", params={"semestre": 3})).status_code == 422


@requiere_postgresql
async def test_seguimiento_de_cursos_en_curso_y_acceso_de_usuario(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    comandante = (
        await cliente_api.post(
            "/api/instructores",
            json={
                "tipo": "CIVIL",
                "documento": f"7{uuid.uuid4().int % 10**9:09d}",
                "nombres": "Otro",
                "apellidos": "Comandante",
                "fecha_ingreso_escuela": "2020-01-01",
            },
            headers=cabecera_csrf(cliente_api),
        )
    ).json()["id"]
    hoy = await sesion_bd.scalar(text("SELECT (now() AT TIME ZONE 'America/Bogota')::date"))
    en_curso = await crear_curso(
        sesion_bd, comandante=comandante, creador=administrador.id, inicio=hoy - timedelta(days=35),
        estado="EN_CURSO", alumnos=[],
    )  # fmt: skip

    datos = (await cliente_api.get("/api/estadisticas/panel")).json()
    seguimiento = next(curso for curso in datos["en_curso"] if curso["id"] == en_curso)
    assert seguimiento["porcentaje"] == 50 and seguimiento["dias_restantes"] == 35
    assert seguimiento["vencido"] is False
    assert datos["indicadores"]["cursos_en_curso"] >= 1

    # El panel es para todos: un USUARIO (el Comandante) también lo ve.
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    assert (await cliente_api.get("/api/estadisticas/panel")).status_code == 200
