"""
S2-10: nota mínima de aprobación configurable en Parámetros (solo para cursos nuevos).

- Validación de la propuesta: sin base de datos.
- Endpoints y trigger de cursos: con PostgreSQL (ESART_URL_BD_INTEGRACION); todo se revierte.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.nota_minima import validar_propuesta
from pruebas.test_auditoria_y_malla import cabecera_csrf, entrar
from pruebas.test_estadisticas_panel import crear_curso
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_panel_parametros import codigo_siguiente, ultimo_evento

pytestmark = pytest.mark.anyio

RUTA = "/api/parametros/nota-minima"


# --- Validación (sin base de datos) ---------------------------------------------------


def test_la_propuesta_valida_se_normaliza_a_dos_decimales():
    assert validar_propuesta(Decimal("3.5")) == Decimal("3.50")
    assert validar_propuesta(Decimal("1")) == Decimal("1.00")
    assert validar_propuesta(Decimal("5.00")) == Decimal("5.00")


@pytest.mark.parametrize("valor", ["0.99", "5.01", "0", "3.555", "-1"])
def test_la_propuesta_fuera_de_rango_o_con_mas_decimales_se_rechaza(valor):
    with pytest.raises(ErrorAplicacion) as error:
        validar_propuesta(Decimal(valor))
    assert error.value.codigo == "DATOS_INVALIDOS"


# --- Con PostgreSQL -------------------------------------------------------------------


async def registrar_comandante(cliente_api) -> int:
    """Instructor civil que sirve de comandante de los cursos de prueba."""
    respuesta = await cliente_api.post(
        "/api/instructores",
        json={
            "tipo": "CIVIL",
            "documento": "7123456789",
            "nombres": "Ana",
            "apellidos": "Prueba Nota",
            "profesion": "Docente",
            "fecha_ingreso_escuela": "2025-01-10",
            "especialidades": [],
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


async def fijar_nota_inicial(sesion) -> None:
    """Deja la nota en 3,00 sin importar lo que tenga la base (la sesión se revierte al final)."""
    await sesion.execute(
        text("""
            UPDATE esart.parametros_habilitacion SET valor = '3.00'::jsonb
            WHERE codigo = 'NOTA_MINIMA_APROBACION'
        """)
    )


async def nota_del_curso(sesion, curso_id: int) -> Decimal | None:
    return await sesion.scalar(
        text("SELECT nota_minima_aprobacion FROM esart.cursos WHERE id = :id"), {"id": curso_id}
    )


@requiere_postgresql
async def test_valor_inicial_y_solo_lectura_para_quien_no_tiene_el_componente(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    assert (await cliente_api.get(RUTA)).status_code == 403

    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    await fijar_nota_inicial(sesion_bd)
    respuesta = await cliente_api.get(RUTA)
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["valor"] == 3.0 and datos["actualizado_en"]


@requiere_postgresql
async def test_cambiar_la_nota_con_totp_solo_afecta_a_los_cursos_nuevos(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    await fijar_nota_inicial(sesion_bd)
    comandante = await registrar_comandante(cliente_api)
    curso_anterior = await crear_curso(
        sesion_bd,
        comandante=comandante,
        creador=administrador.id,
        inicio=date(2026, 2, 1),
        estado="EN_CURSO",
        alumnos=[],
    )
    # El trigger copia la nota vigente al crear el curso.
    assert await nota_del_curso(sesion_bd, curso_anterior) == Decimal("3.00")

    vigente = (await cliente_api.get(RUTA)).json()
    assert vigente["cursos_en_curso"] >= 1
    solicitud = {"valor": 3.5, "version": vigente["actualizado_en"]}

    sin_codigo = await cliente_api.put(RUTA, json=solicitud, headers=cabecera_csrf(cliente_api))
    assert sin_codigo.status_code == 409 and sin_codigo.json()["error"]["codigo"] == "TOTP_REQUERIDO"
    errado = await cliente_api.put(
        RUTA, json={**solicitud, "codigo_totp": "000000"}, headers=cabecera_csrf(cliente_api)
    )
    assert errado.status_code == 422 and errado.json()["error"]["codigo"] == "TOTP_INVALIDO"

    correcto = await cliente_api.put(
        RUTA,
        json={**solicitud, "codigo_totp": codigo_siguiente(cliente_api)},
        headers=cabecera_csrf(cliente_api),
    )
    assert correcto.status_code == 200, correcto.text
    assert correcto.json()["valor"] == 3.5
    evento = await ultimo_evento(sesion_bd, "PARAMETROS_ACTUALIZADOS")
    assert evento.detalle["cambios"] == {"NOTA_MINIMA_APROBACION": {"anterior": "3.00", "nuevo": "3.50"}}

    # El curso que ya existía conserva su nota; el nuevo toma la vigente.
    assert await nota_del_curso(sesion_bd, curso_anterior) == Decimal("3.00")
    curso_nuevo = await crear_curso(
        sesion_bd,
        comandante=comandante,
        creador=administrador.id,
        inicio=date(2026, 6, 1),
        estado="EN_CURSO",
        alumnos=[],
    )
    assert await nota_del_curso(sesion_bd, curso_nuevo) == Decimal("3.50")

    # Con la versión vieja (otro administrador ya guardó) no se sobrescribe.
    viejo = await cliente_api.put(
        RUTA, json={**solicitud, "valor": 4, "codigo_totp": "123456"}, headers=cabecera_csrf(cliente_api)
    )
    assert viejo.status_code == 409 and viejo.json()["error"]["codigo"] == "PARAMETROS_DESACTUALIZADOS"


@requiere_postgresql
async def test_rechaza_valores_invalidos_iguales_y_sin_csrf(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    await fijar_nota_inicial(sesion_bd)
    version = (await cliente_api.get(RUTA)).json()["actualizado_en"]

    sin_csrf = await cliente_api.put(RUTA, json={"valor": 3.5, "version": version})
    assert sin_csrf.status_code == 403
    for valor in (0.5, 5.5):
        fuera = await cliente_api.put(
            RUTA, json={"valor": valor, "version": version}, headers=cabecera_csrf(cliente_api)
        )
        assert fuera.status_code == 422 and fuera.json()["error"]["codigo"] == "DATOS_INVALIDOS"
    igual = await cliente_api.put(
        RUTA, json={"valor": 3, "version": version}, headers=cabecera_csrf(cliente_api)
    )
    assert igual.status_code == 422 and igual.json()["error"]["codigo"] == "SIN_CAMBIOS"


@requiere_postgresql
async def test_cambiar_la_nota_no_invalida_el_formulario_de_la_regla(cliente_api, sesion_bd):  # noqa: F811
    """Son parámetros distintos: cada uno tiene su propia versión para la concurrencia."""
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    regla = (await cliente_api.get("/api/parametros/habilitacion")).json()
    nota = (await cliente_api.get(RUTA)).json()
    guardada = await cliente_api.put(
        RUTA,
        json={"valor": 4, "version": nota["actualizado_en"], "codigo_totp": codigo_siguiente(cliente_api)},
        headers=cabecera_csrf(cliente_api),
    )
    assert guardada.status_code == 200, guardada.text
    assert (await cliente_api.get("/api/parametros/habilitacion")).json()["actualizado_en"] == regla[
        "actualizado_en"
    ]
