"""
S2-02: módulo Cursos e instructor titular de cada materia con nota.

Todo con PostgreSQL (ESART_URL_BD_INTEGRACION); se revierte al final.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.malla_curricular import FilaMalla, crear_version, tipo_curso_por_codigo
from pruebas.test_auditoria_y_malla import cabecera_csrf, conceder_por_excepcion, entrar
from pruebas.test_estadisticas_panel import crear_curso
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_mallas_parametros import insertar_tipo
from pruebas.test_panel_parametros import ultimo_evento
from pruebas.test_permisos_notas import documento_civil, registrar_civil

pytestmark = pytest.mark.anyio

RUTA = "/api/cursos"


async def preparar_curso(cliente_api, sesion, creador_id: int, *, estado: str = "EN_CURSO", con_malla=False):
    """Tipo de curso propio con malla v1 (2 materias con nota y 1 sin nota) y un curso de ese tipo."""
    codigo = f"PRB{uuid.uuid4().hex[:6].upper()}"
    await insertar_tipo(sesion, codigo)
    tipo = await tipo_curso_por_codigo(sesion, codigo)
    version = await crear_version(
        sesion,
        tipo,
        2026,
        [
            FilaMalla(1, "Topografía S202", True),
            FilaMalla(2, "Balística S202", True),
            FilaMalla(3, "Tiempo del comandante", False),
        ],
        Actor.consola("pruebas"),
    )
    comandante = await registrar_civil(cliente_api, documento_civil())
    curso = await crear_curso(
        sesion, comandante=comandante, creador=creador_id, inicio=date(2026, 9, 1), estado=estado, alumnos=[]
    )
    # El curso de prueba se crea como SACLI: se pasa al tipo propio, con o sin malla.
    await sesion.execute(
        text("UPDATE esart.cursos SET tipo_curso_id = :tipo, malla_version_id = :version WHERE id = :curso"),
        {"tipo": tipo.id, "version": version.id if con_malla else None, "curso": curso},
    )
    return curso, codigo


def materia(detalle: dict, nombre: str) -> dict:
    return next(m for m in detalle["materias"] if m["materia"] == nombre)


@requiere_postgresql
async def test_sin_el_permiso_cursos_no_se_ve_el_modulo(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    assert (await cliente_api.get(RUTA)).status_code == 403
    yo = (await cliente_api.get("/api/auth/yo")).json()
    assert "CURSOS" not in {elemento["codigo"] for elemento in yo["menu"]}


@requiere_postgresql
async def test_asignar_malla_vigente_y_el_instructor_de_cada_materia(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    curso, codigo_tipo = await preparar_curso(cliente_api, sesion_bd, administrador.id)

    # El módulo aparece en el menú del administrador y el curso en la lista, sin malla.
    yo = (await cliente_api.get("/api/auth/yo")).json()
    assert "CURSOS" in {elemento["codigo"] for elemento in yo["menu"]}
    fila = next(
        c for c in (await cliente_api.get(RUTA, params={"tipo": codigo_tipo})).json() if c["id"] == curso
    )
    assert fila["version_malla"] is None and fila["materias_con_nota"] == 0

    sin_malla = (await cliente_api.get(f"{RUTA}/{curso}")).json()
    assert sin_malla["materias"] == [] and sin_malla["version_vigente_disponible"] == 1

    con_malla = await cliente_api.post(f"{RUTA}/{curso}/malla", headers=cabecera_csrf(cliente_api))
    assert con_malla.status_code == 200, con_malla.text
    detalle = con_malla.json()
    assert detalle["version_malla"] == 1 and detalle["nota_minima_aprobacion"] is not None
    assert len(detalle["materias"]) == 3
    assert (await ultimo_evento(sesion_bd, "CURSO_MALLA_ASIGNADA")).detalle["version"] == 1
    repetida = await cliente_api.post(f"{RUTA}/{curso}/malla", headers=cabecera_csrf(cliente_api))
    assert repetida.status_code == 409 and repetida.json()["error"]["codigo"] == "CURSO_CON_MALLA"

    primero = await registrar_civil(cliente_api, documento_civil())
    segundo = await registrar_civil(cliente_api, documento_civil())
    disponibles = {i["id"] for i in (await cliente_api.get(f"{RUTA}/instructores-disponibles")).json()}
    assert {primero, segundo} <= disponibles

    topografia = materia(detalle, "TOPOGRAFÍA S202")["malla_id"]
    ruta_materia = f"{RUTA}/{curso}/materias/{topografia}/instructor"
    asignado = await cliente_api.put(
        ruta_materia, json={"instructor_id": primero}, headers=cabecera_csrf(cliente_api)
    )
    assert asignado.status_code == 200, asignado.text
    assert materia(asignado.json(), "TOPOGRAFÍA S202")["instructor_id"] == primero
    evento = await ultimo_evento(sesion_bd, "INSTRUCTOR_MATERIA_ASIGNADO")
    assert evento.detalle["anterior"] is None and evento.detalle["nuevo"]["id"] == primero

    # "Ver cursos" del instructor muestra la materia que dicta.
    cursos_instructor = (await cliente_api.get(f"/api/instructores/{primero}/cursos")).json()
    assert [m["materia"] for m in cursos_instructor["materias"]] == ["TOPOGRAFÍA S202"]

    cambiado = await cliente_api.put(
        ruta_materia, json={"instructor_id": segundo}, headers=cabecera_csrf(cliente_api)
    )
    assert materia(cambiado.json(), "TOPOGRAFÍA S202")["instructor_id"] == segundo
    evento = await ultimo_evento(sesion_bd, "INSTRUCTOR_MATERIA_ASIGNADO")
    assert evento.detalle["anterior"]["id"] == primero and evento.detalle["nuevo"]["id"] == segundo
    igual = await cliente_api.put(
        ruta_materia, json={"instructor_id": segundo}, headers=cabecera_csrf(cliente_api)
    )
    assert igual.status_code == 422 and igual.json()["error"]["codigo"] == "SIN_CAMBIOS"

    sin_nota = materia(detalle, "TIEMPO DEL COMANDANTE")["malla_id"]
    rechazado = await cliente_api.put(
        f"{RUTA}/{curso}/materias/{sin_nota}/instructor",
        json={"instructor_id": primero},
        headers=cabecera_csrf(cliente_api),
    )
    assert rechazado.status_code == 422 and rechazado.json()["error"]["codigo"] == "MATERIA_SIN_NOTA"

    quitado = await cliente_api.put(
        ruta_materia, json={"instructor_id": None}, headers=cabecera_csrf(cliente_api)
    )
    assert materia(quitado.json(), "TOPOGRAFÍA S202")["instructor_id"] is None
    assert (await ultimo_evento(sesion_bd, "INSTRUCTOR_MATERIA_ASIGNADO")).detalle["nuevo"] is None


@requiere_postgresql
async def test_reglas_de_la_asignacion(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    curso, _ = await preparar_curso(cliente_api, sesion_bd, administrador.id, con_malla=True)
    detalle = (await cliente_api.get(f"{RUTA}/{curso}")).json()
    balistica = materia(detalle, "BALÍSTICA S202")["malla_id"]
    ruta_materia = f"{RUTA}/{curso}/materias/{balistica}/instructor"

    inactivo = await registrar_civil(cliente_api, documento_civil())
    await cliente_api.post(f"/api/instructores/{inactivo}/desactivar", headers=cabecera_csrf(cliente_api))
    respuesta = await cliente_api.put(
        ruta_materia, json={"instructor_id": inactivo}, headers=cabecera_csrf(cliente_api)
    )
    assert respuesta.status_code == 422 and respuesta.json()["error"]["codigo"] == "INSTRUCTOR_NO_DISPONIBLE"

    # Una materia de otra malla no pertenece a este curso.
    otro, _ = await preparar_curso(cliente_api, sesion_bd, administrador.id, con_malla=True)
    ajena = (await cliente_api.get(f"{RUTA}/{otro}")).json()["materias"][0]["malla_id"]
    respuesta = await cliente_api.put(
        f"{RUTA}/{curso}/materias/{ajena}/instructor",
        json={"instructor_id": None},
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 404 and respuesta.json()["error"]["codigo"] == "MATERIA_NO_ENCONTRADA"

    # Un curso culminado ya no se modifica.
    await sesion_bd.execute(
        text("UPDATE esart.cursos SET estado = 'CULMINADO' WHERE id = :id"), {"id": curso}
    )
    activo = await registrar_civil(cliente_api, documento_civil())
    respuesta = await cliente_api.put(
        ruta_materia, json={"instructor_id": activo}, headers=cabecera_csrf(cliente_api)
    )
    assert respuesta.status_code == 409 and respuesta.json()["error"]["codigo"] == "CURSO_NO_EDITABLE"
    assert (await cliente_api.get(f"{RUTA}/999999999")).status_code == 404


@requiere_postgresql
async def test_con_solo_leer_se_ve_el_curso_pero_no_se_asigna(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    curso, _ = await preparar_curso(cliente_api, sesion_bd, administrador.id, con_malla=True)
    instructor = await registrar_civil(cliente_api, documento_civil())

    usuario = await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    await conceder_por_excepcion(sesion_bd, usuario, "CURSOS", puede_acceder=True, puede_leer=True)
    detalle = await cliente_api.get(f"{RUTA}/{curso}")
    assert detalle.status_code == 200
    malla_id = detalle.json()["materias"][0]["malla_id"]
    respuesta = await cliente_api.put(
        f"{RUTA}/{curso}/materias/{malla_id}/instructor",
        json={"instructor_id": instructor},
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 403
    assert (await cliente_api.get(f"{RUTA}/instructores-disponibles")).status_code == 403
