"""
S2-11: permisos nuevos (malla curricular y notas) y usuario para el instructor civil.

Todo con PostgreSQL (ESART_URL_BD_INTEGRACION); se revierte al final.
"""

import uuid

import pytest
from sqlalchemy import select, text

from aplicacion.modelos import AuditoriaEvento
from aplicacion.seguridad.permisos import obtener_permisos_efectivos
from aplicacion.servicios.instructores import instructor_del_usuario
from pruebas.test_auditoria_y_malla import cabecera_csrf, conceder_por_excepcion, entrar
from pruebas.test_login_hu05 import crear_usuario, requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_verificacion_habilitacion import crear_militar

pytestmark = pytest.mark.anyio

COMPONENTES_NUEVOS = {"MALLAS_CURRICULARES", "NOTAS_CARGA", "NOTAS_REVISION", "CONSEJO_ACADEMICO"}
CONTRASENA_TEMPORAL = "Temporal-Civil-2026"


async def registrar_civil(cliente_api, documento: str) -> int:
    respuesta = await cliente_api.post(
        "/api/instructores",
        json={
            "tipo": "CIVIL",
            "documento": documento,
            "nombres": "María Fernanda",
            "apellidos": "López Ruiz",
            "profesion": "Ingeniera de sistemas",
            "fecha_ingreso_escuela": "2025-06-15",
            "especialidades": ["CDT"],
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def documento_civil() -> str:
    return f"7{uuid.uuid4().int % 10**9:09d}"


@requiere_postgresql
async def test_componentes_nuevos_son_permisos_especiales_activos(sesion_bd):  # noqa: F811
    filas = (
        await sesion_bd.execute(
            text("SELECT codigo, ruta_angular, activo FROM esart.componentes WHERE codigo = ANY(:codigos)"),
            {"codigos": list(COMPONENTES_NUEVOS)},
        )
    ).all()
    assert {fila.codigo for fila in filas} == COMPONENTES_NUEVOS
    assert all(fila.activo for fila in filas)
    # Sin ruta: se asignan en la malla pero no aparecen en el menú hasta que existan sus pantallas.
    # S2-12 (p0022) le dio pantalla a NOTAS_CARGA y S2-13 (p0023) a NOTAS_REVISION.
    rutas = {fila.codigo: fila.ruta_angular for fila in filas}
    assert rutas.pop("NOTAS_CARGA") == "/notas/mis-materias"
    assert rutas.pop("NOTAS_REVISION") == "/notas/revision"
    assert set(rutas.values()) == {None}


@requiere_postgresql
async def test_administrador_los_tiene_y_usuario_no_por_defecto(sesion_bd):  # noqa: F811
    administrador = await crear_usuario(sesion_bd, roles=("ADMINISTRADOR",))
    usuario = await crear_usuario(sesion_bd, roles=("USUARIO",))
    del_administrador = {p.codigo: p for p in await obtener_permisos_efectivos(sesion_bd, administrador.id)}
    for codigo in COMPONENTES_NUEVOS:
        permiso = del_administrador[codigo]
        assert (
            permiso.puede_acceder and permiso.puede_crear and permiso.puede_leer and permiso.puede_actualizar
        )
    del_usuario = {
        p.codigo for p in await obtener_permisos_efectivos(sesion_bd, usuario.id) if p.puede_acceder
    }
    assert not COMPONENTES_NUEVOS & del_usuario


@requiere_postgresql
async def test_un_usuario_recibe_carga_de_notas_por_excepcion(cliente_api, sesion_bd):  # noqa: F811
    usuario = await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    await conceder_por_excepcion(
        sesion_bd, usuario, "NOTAS_CARGA", puede_acceder=True, puede_crear=True, puede_leer=True
    )
    yo = (await cliente_api.get("/api/auth/yo")).json()
    assert "NOTAS_CARGA" in yo["permisos"]
    # Desde S2-12 la carga de notas tiene pantalla y sale en el menú; la revisión todavía no.
    assert "NOTAS_CARGA" in {elemento["codigo"] for elemento in yo["menu"]}
    assert "NOTAS_REVISION" not in yo["permisos"]


@requiere_postgresql
async def test_usuario_para_un_instructor_civil(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    documento = documento_civil()
    instructor_id = await registrar_civil(cliente_api, documento)

    persona = await cliente_api.get(f"/api/administracion/usuarios/militar/{documento}")
    assert persona.status_code == 200, persona.text
    datos = persona.json()
    assert (datos["tipo_persona"], datos["grado"], datos["unidad"]) == ("CIVIL", "Civil", None)
    assert datos["nombre_usuario_sugerido"].startswith("mlopez")

    creado = await cliente_api.post(
        "/api/administracion/usuarios",
        json={
            "documento_identidad": documento,
            "nombre_usuario": datos["nombre_usuario_sugerido"],
            "rol": "USUARIO",
            "contrasena_temporal": CONTRASENA_TEMPORAL,
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert creado.status_code == 201, creado.text
    assert creado.json()["nombre_completo"] == "María Fernanda López Ruiz"
    evento = await sesion_bd.scalar(
        select(AuditoriaEvento)
        .where(AuditoriaEvento.accion == "USUARIO_CREADO")
        .order_by(AuditoriaEvento.id.desc())
    )
    assert evento.detalle["tipo_persona"] == "CIVIL"

    # El civil no entra a Personal militar (no cuenta como artillero).
    assert not await sesion_bd.scalar(
        text("SELECT 1 FROM esart.personal_militar WHERE documento_identidad = :d"), {"d": documento}
    )
    # El panel de instructores muestra su usuario y el servicio lo reconoce como instructor.
    listado = (await cliente_api.get("/api/instructores", params={"texto": documento})).json()
    tarjeta = next(item for item in listado if item["id"] == instructor_id)
    assert tarjeta["nombre_usuario"] == datos["nombre_usuario_sugerido"]
    assert await instructor_del_usuario(sesion_bd, documento) == instructor_id

    repetido = await cliente_api.get(f"/api/administracion/usuarios/militar/{documento}")
    assert repetido.json()["usuario_existente"] == datos["nombre_usuario_sugerido"]


@requiere_postgresql
async def test_no_se_crea_usuario_a_un_civil_inactivo_ni_a_cedulas_desconocidas(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    documento = documento_civil()
    instructor_id = await registrar_civil(cliente_api, documento)
    desactivado = await cliente_api.post(
        f"/api/instructores/{instructor_id}/desactivar", headers=cabecera_csrf(cliente_api)
    )
    assert desactivado.status_code == 200, desactivado.text

    creado = await cliente_api.post(
        "/api/administracion/usuarios",
        json={
            "documento_identidad": documento,
            "nombre_usuario": f"civil.{uuid.uuid4().hex[:6]}",
            "rol": "USUARIO",
            "contrasena_temporal": CONTRASENA_TEMPORAL,
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert creado.status_code == 422 and "inactiva" in creado.json()["error"]["mensaje"]
    assert await instructor_del_usuario(sesion_bd, documento) is None

    desconocida = await cliente_api.get(f"/api/administracion/usuarios/militar/{documento_civil()}")
    assert desconocida.status_code == 404
    assert "instructor civil" in desconocida.json()["error"]["mensaje"]


@requiere_postgresql
async def test_instructor_militar_se_reconoce_por_su_cedula(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    cedula = await crear_militar(sesion_bd, "sacli", 71)
    assert await instructor_del_usuario(sesion_bd, cedula) is None  # todavía no es instructor
    registrado = await cliente_api.post(
        "/api/instructores",
        json={"tipo": "MILITAR", "documento": cedula, "fecha_ingreso_escuela": "2024-02-01"},
        headers=cabecera_csrf(cliente_api),
    )
    assert registrado.status_code == 201, registrado.text
    assert await instructor_del_usuario(sesion_bd, cedula) == registrado.json()["id"]
    assert await instructor_del_usuario(sesion_bd, None) is None
