"""
Pruebas del registro manual de personal militar (POST /api/personal).

- Validación y catálogo de grados: sin base de datos.
- Endpoint: con PostgreSQL (ESART_URL_BD_INTEGRACION, con p0015 aplicada); todo se revierte.
"""

import uuid

import pytest
from sqlalchemy import select, text

from aplicacion.modelos import AuditoriaEvento
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.registro_personal import (
    GRADOS_POR_CATEGORIA,
    DatosPersonal,
    normalizar,
    opciones_categorias,
)
from pruebas.test_auditoria_y_malla import cabecera_csrf, entrar
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401

pytestmark = pytest.mark.anyio


def datos(**cambios) -> DatosPersonal:
    base = {
        "documento_identidad": "1.024.589.632",
        "nombres": "  Carlos   Andrés ",
        "apellidos": "Colorado Gil",
        "grado": "my",
        "genero": "M",
        "categoria": "oficial",
        "unidad_actual_id": None,
        "especialidad_actual": "  ",
        "activo": True,
    }
    return DatosPersonal(**{**base, **cambios})


# --- Sin base de datos ----------------------------------------------------------------


def test_normaliza_cedula_espacios_y_mayusculas():
    valores = normalizar(datos())
    assert valores["documento_identidad"] == "1024589632"
    assert valores["nombres"] == "Carlos Andrés"
    assert (valores["grado"], valores["categoria"]) == ("MY", "OFICIAL")
    assert valores["especialidad_actual"] is None


@pytest.mark.parametrize(
    ("cambios", "fragmento"),
    [
        ({"categoria": "CIVIL"}, "categoría"),
        ({"grado": "SS"}, "no corresponde"),  # suboficial con categoría oficial
        ({"genero": "X"}, "género"),
        ({"nombres": "   "}, "nombres"),
        ({"apellidos": "A" * 151}, "máximo 150"),
        ({"especialidad_actual": "E" * 101}, "máximo 100"),
        ({"documento_identidad": "12AB"}, "cédula"),
    ],
)
def test_rechaza_datos_invalidos(cambios, fragmento):
    with pytest.raises(ErrorAplicacion) as error:
        normalizar(datos(**cambios))
    assert error.value.estado_http == 422
    assert fragmento in error.value.mensaje


def test_opciones_incluyen_todas_las_categorias_con_sus_grados():
    opciones = opciones_categorias()
    assert [o["codigo"] for o in opciones] == list(GRADOS_POR_CATEGORIA)
    oficial = next(o for o in opciones if o["codigo"] == "OFICIAL")
    assert {"codigo": "MY", "nombre": "Mayor"} in oficial["grados"]
    # Las siglas caben en personal_militar.grado (VARCHAR 20) y no se repiten entre categorías.
    siglas = [g["codigo"] for o in opciones for g in o["grados"]]
    assert len(siglas) == len(set(siglas)) and max(map(len, siglas)) <= 20


# --- Con PostgreSQL -------------------------------------------------------------------


def cedula_nueva() -> str:
    return f"97{uuid.uuid4().int % 10**8:08d}"


def cuerpo(cedula: str, **cambios) -> dict:
    return {
        "documento_identidad": cedula,
        "nombres": "Carlos Andrés",
        "apellidos": "Colorado Gil",
        "grado": "MY",
        "genero": "M",
        "categoria": "OFICIAL",
        "especialidad_actual": "Artillería de Campaña",
        "activo": True,
        **cambios,
    }


@requiere_postgresql
async def test_administrador_registra_y_queda_auditado(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    csrf = cabecera_csrf(cliente_api)
    opciones = (await cliente_api.get("/api/personal/opciones-registro")).json()
    unidad = opciones["unidades"][0]["id"] if opciones["unidades"] else None
    cedula = cedula_nueva()

    respuesta = await cliente_api.post(
        "/api/personal", json=cuerpo(cedula, unidad_actual_id=unidad), headers=csrf
    )
    assert respuesta.status_code == 201, respuesta.text
    creado = respuesta.json()
    assert creado["nombre_completo"] == "MY Carlos Andrés Colorado Gil"
    fila = (
        await sesion_bd.execute(
            text("SELECT grado, categoria, unidad_actual_id FROM esart.personal_militar WHERE id = :id"),
            {"id": creado["id"]},
        )
    ).one()
    assert (fila.grado, fila.categoria, fila.unidad_actual_id) == ("MY", "OFICIAL", unidad)
    evento = await sesion_bd.scalar(
        select(AuditoriaEvento)
        .where(AuditoriaEvento.accion == "PERSONAL_REGISTRADO")
        .order_by(AuditoriaEvento.id.desc())
    )
    assert evento.detalle["personal_id"] == creado["id"]
    assert evento.numero_documento_consultado == cedula

    repetido = await cliente_api.post("/api/personal", json=cuerpo(cedula), headers=csrf)
    assert repetido.status_code == 409
    assert repetido.json()["error"]["codigo"] == "DOCUMENTO_EXISTENTE"


@requiere_postgresql
async def test_rechaza_unidad_inexistente_y_sin_csrf(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    sin_unidad = await cliente_api.post(
        "/api/personal",
        json=cuerpo(cedula_nueva(), unidad_actual_id=999_999_999),
        headers=cabecera_csrf(cliente_api),
    )
    assert sin_unidad.status_code == 422
    sin_csrf = await cliente_api.post("/api/personal", json=cuerpo(cedula_nueva()))
    assert sin_csrf.status_code == 403


@requiere_postgresql
async def test_usuario_sin_permiso_no_registra(cliente_api, sesion_bd):  # noqa: F811
    # El rol USUARIO no tiene PERSONAL_CARGUE_MANUAL en la malla por defecto.
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    respuesta = await cliente_api.post(
        "/api/personal", json=cuerpo(cedula_nueva()), headers=cabecera_csrf(cliente_api)
    )
    assert respuesta.status_code == 403
    assert (await cliente_api.get("/api/personal/opciones-registro")).status_code == 403
