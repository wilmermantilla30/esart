"""
S2-09: mallas curriculares y tipos de curso editables desde el panel de Parámetros.

- Comparación de mallas y validación del tipo de curso: sin base de datos.
- Endpoints: con PostgreSQL (ESART_URL_BD_INTEGRACION); todo se revierte al final.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.malla_curricular import FilaMalla, crear_version, tipo_curso_por_codigo
from aplicacion.servicios.mallas_parametros import NuevoTipoCurso, comparar, validar_tipo
from pruebas.test_auditoria_y_malla import cabecera_csrf, conceder_por_excepcion, entrar
from pruebas.test_estadisticas_panel import crear_curso
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_nota_minima import registrar_comandante
from pruebas.test_panel_parametros import codigo_siguiente, ultimo_evento

pytestmark = pytest.mark.anyio

RUTA = "/api/parametros/mallas"


def fila(orden: int, materia: str, evaluable: bool = True) -> FilaMalla:
    return FilaMalla(orden=orden, materia=materia, evaluable=evaluable)


# --- Sin base de datos ----------------------------------------------------------------


def test_comparar_resume_agregadas_quitadas_y_cambios_de_nota():
    antes = [fila(1, "Topografía"), fila(2, "Balística"), fila(3, "Tiempo del comandante", False)]
    despues = [fila(1, "Balística", False), fila(2, "Topografía"), fila(3, "Ciberdefensa")]
    cambios = comparar(antes, despues)
    assert cambios["agregadas"] == ["CIBERDEFENSA"]
    assert cambios["quitadas"] == ["TIEMPO DEL COMANDANTE"]
    assert cambios["cambian_evaluable"] == ["BALÍSTICA"]
    assert cambios["orden_cambiado"] is True
    assert comparar(antes, antes)["orden_cambiado"] is False


def test_el_tipo_de_curso_se_normaliza_y_valida():
    nuevo = validar_tipo(
        NuevoTipoCurso(" capfu_2 ", "  Curso   de fuegos ", "ESPECIALIZACION", "PRESENCIAL", 6)
    )
    assert (nuevo.codigo, nuevo.nombre) == ("CAPFU_2", "Curso de fuegos")
    for invalido in (
        NuevoTipoCurso("C", "Curso", "ESPECIALIZACION", "PRESENCIAL", 6),  # código muy corto
        NuevoTipoCurso("CON ESPACIO", "Curso", "ESPECIALIZACION", "PRESENCIAL", 6),
        NuevoTipoCurso("CAPFU", "Curso", "OTRO", "PRESENCIAL", 6),  # tipo fuera del catálogo
        NuevoTipoCurso("CAPFU", "Curso", "ESPECIALIZACION", "PRESENCIAL", 0),  # sin duración
    ):
        with pytest.raises(ErrorAplicacion):
            validar_tipo(invalido)


# --- Con PostgreSQL -------------------------------------------------------------------


def codigo_tipo() -> str:
    return f"PRB{uuid.uuid4().hex[:6].upper()}"


async def insertar_tipo(sesion, codigo: str) -> None:
    """Tipo de curso de prueba creado directo en la base (sin gastar un código TOTP)."""
    await sesion.execute(
        text("""
            INSERT INTO esart.tipos_curso (codigo, nombre, tipo, modalidad, duracion_semanas)
            VALUES (:codigo, 'Curso de prueba S2-09', 'ESPECIALIZACION', 'PRESENCIAL', 4)
        """),
        {"codigo": codigo},
    )


def filas_json(*filas: tuple[str, bool]) -> list[dict]:
    return [{"orden": i, "materia": nombre, "evaluable": nota} for i, (nombre, nota) in enumerate(filas, 1)]


@requiere_postgresql
async def test_sin_el_permiso_no_se_ven_ni_se_editan_las_mallas(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    assert (await cliente_api.get(RUTA)).status_code == 403
    respuesta = await cliente_api.put(
        f"{RUTA}/SACLI",
        json={"anio": 2026, "filas": filas_json(("Topografía", True)), "version": None},
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 403


@requiere_postgresql
async def test_crear_tipo_de_curso_con_totp_y_auditoria(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    codigo = codigo_tipo()
    datos = {
        "codigo": codigo.lower(),
        "nombre": "Curso de coordinación de fuegos",
        "tipo": "ESPECIALIZACION",
        "modalidad": "PRESENCIAL",
        "duracion_semanas": 6,
    }
    sin_codigo = await cliente_api.post(RUTA, json=datos, headers=cabecera_csrf(cliente_api))
    assert sin_codigo.status_code == 409 and sin_codigo.json()["error"]["codigo"] == "TOTP_REQUERIDO"

    creado = await cliente_api.post(
        RUTA, json={**datos, "codigo_totp": codigo_siguiente(cliente_api)}, headers=cabecera_csrf(cliente_api)
    )
    assert creado.status_code == 201, creado.text
    cuerpo = creado.json()
    assert cuerpo["tipo_curso"]["codigo"] == codigo  # queda en mayúsculas
    assert cuerpo["version"] is None and cuerpo["filas"] == [] and cuerpo["versiones"] == []
    evento = await ultimo_evento(sesion_bd, "TIPO_CURSO_CREADO")
    assert evento.detalle["codigo"] == codigo

    listado = (await cliente_api.get(RUTA)).json()
    assert next(t for t in listado if t["codigo"] == codigo)["version"] is None

    repetido = await cliente_api.post(
        RUTA, json={**datos, "codigo_totp": "000000"}, headers=cabecera_csrf(cliente_api)
    )
    assert repetido.status_code == 409 and repetido.json()["error"]["codigo"] == "TIPO_CURSO_DUPLICADO"


@requiere_postgresql
async def test_guardar_crea_version_nueva_y_los_cursos_conservan_la_suya(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    codigo = codigo_tipo()
    await insertar_tipo(sesion_bd, codigo)
    tipo = await tipo_curso_por_codigo(sesion_bd, codigo)
    actor = Actor.consola("pruebas")
    await crear_version(
        sesion_bd, tipo, 2026, [fila(1, "Topografía S209"), fila(2, "Tiempo del comandante", False)], actor
    )
    # Un curso creado con la versión 1.
    comandante = await registrar_comandante(cliente_api)
    curso = await crear_curso(
        sesion_bd,
        comandante=comandante,
        creador=administrador.id,
        inicio=date(2026, 3, 1),
        estado="EN_CURSO",
        alumnos=[],
    )
    await sesion_bd.execute(
        text("""
            UPDATE esart.cursos SET tipo_curso_id = :tipo,
              malla_version_id = (
                SELECT id FROM esart.versiones_malla WHERE tipo_curso_id = :tipo AND numero = 1
              )
            WHERE id = :curso
        """),
        {"tipo": tipo.id, "curso": curso},
    )

    vigente = (await cliente_api.get(f"{RUTA}/{codigo}")).json()
    assert vigente["version"]["numero"] == 1 and vigente["version"]["cursos"] == 1
    assert [f["materia"] for f in vigente["filas"]] == ["TOPOGRAFÍA S209", "TIEMPO DEL COMANDANTE"]

    nueva = {
        "anio": 2027,
        "filas": filas_json(
            ("Ciberdefensa S209", True), ("Topografía S209", True), ("Tiempo del comandante", False)
        ),
        "observacion": "Se agrega Ciberdefensa",
        "version": 1,
    }
    sin_codigo = await cliente_api.put(f"{RUTA}/{codigo}", json=nueva, headers=cabecera_csrf(cliente_api))
    assert sin_codigo.status_code == 409 and sin_codigo.json()["error"]["codigo"] == "TOTP_REQUERIDO"
    guardada = await cliente_api.put(
        f"{RUTA}/{codigo}",
        json={**nueva, "codigo_totp": codigo_siguiente(cliente_api)},
        headers=cabecera_csrf(cliente_api),
    )
    assert guardada.status_code == 200, guardada.text
    cuerpo = guardada.json()
    assert cuerpo["version"]["numero"] == 2 and cuerpo["version"]["anio"] == 2027
    assert [v["estado"] for v in cuerpo["versiones"]] == ["VIGENTE", "HISTORICA"]
    assert cuerpo["filas"][0]["materia"] == "CIBERDEFENSA S209"

    # El curso sigue con la versión 1 y la versión 1 se puede consultar.
    assert (
        await sesion_bd.scalar(
            text("""
                SELECT v.numero FROM esart.cursos c
                JOIN esart.versiones_malla v ON v.id = c.malla_version_id
                WHERE c.id = :c
            """),
            {"c": curso},
        )
        == 1
    )
    historica = (await cliente_api.get(f"{RUTA}/{codigo}", params={"version": 1})).json()
    assert len(historica["filas"]) == 2 and historica["version"]["estado"] == "HISTORICA"

    evento = await ultimo_evento(sesion_bd, "MALLA_CURRICULAR_CARGADA")
    assert evento.detalle["origen"] == "PARAMETROS" and evento.detalle["version_anterior"] == 1
    assert evento.detalle["cambios"]["agregadas"] == ["CIBERDEFENSA S209"]
    assert len(evento.detalle["antes"]) == 2 and len(evento.detalle["despues"]) == 3

    # Con la versión vieja (otro usuario ya guardó) no se sobrescribe.
    vieja = await cliente_api.put(
        f"{RUTA}/{codigo}", json={**nueva, "codigo_totp": "123456"}, headers=cabecera_csrf(cliente_api)
    )
    assert vieja.status_code == 409 and vieja.json()["error"]["codigo"] == "MALLA_DESACTUALIZADA"


@requiere_postgresql
async def test_rechaza_malla_invalida_o_sin_cambios_antes_de_pedir_el_codigo(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    codigo = codigo_tipo()
    await insertar_tipo(sesion_bd, codigo)
    tipo = await tipo_curso_por_codigo(sesion_bd, codigo)
    await crear_version(sesion_bd, tipo, 2026, [fila(1, "Topografía S209")], Actor.consola("pruebas"))

    def solicitud(*filas):
        return {"anio": 2026, "filas": filas_json(*filas), "version": 1}

    casos = {
        "MALLA_INVALIDA": solicitud(("Topografía S209", True), ("topografía  s209", True)),  # repetida
        "SIN_CAMBIOS": solicitud(("topografía s209", True)),
    }
    for codigo_error, cuerpo in casos.items():
        respuesta = await cliente_api.put(f"{RUTA}/{codigo}", json=cuerpo, headers=cabecera_csrf(cliente_api))
        assert respuesta.status_code == 422, respuesta.text
        assert respuesta.json()["error"]["codigo"] == codigo_error
    sin_nota = await cliente_api.put(
        f"{RUTA}/{codigo}",
        json=solicitud(("Tiempo del comandante", False)),
        headers=cabecera_csrf(cliente_api),
    )
    assert sin_nota.json()["error"]["codigo"] == "MALLA_INVALIDA"
    assert (await cliente_api.get(f"{RUTA}/NO_EXISTE")).status_code == 404


@requiere_postgresql
async def test_permiso_por_excepcion_da_entrada_a_parametros_solo_para_mallas(cliente_api, sesion_bd):  # noqa: F811
    usuario = await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    await conceder_por_excepcion(
        sesion_bd, usuario, "MALLAS_CURRICULARES", puede_acceder=True, puede_leer=True, puede_actualizar=True
    )
    yo = (await cliente_api.get("/api/auth/yo")).json()
    assert "MALLAS_CURRICULARES" in yo["permisos"] and "PARAMETROS_HABILITACION" not in yo["permisos"]
    # Las operaciones del permiso especial llegan aunque no sea menú (el front muestra los botones).
    assert yo["operaciones"]["MALLAS_CURRICULARES"] == ["leer", "actualizar"]
    # El menú muestra Parámetros (por el permiso especial hijo), sin pestañas de menú.
    parametros = next(e for e in yo["menu"] if e["codigo"] == "PARAMETROS_HABILITACION")
    assert parametros["hijos"] == []

    assert (await cliente_api.get(RUTA)).status_code == 200
    assert (await cliente_api.get("/api/parametros/mallas/materias")).status_code == 200
    # El resto de Parámetros sigue cerrado.
    assert (await cliente_api.get("/api/parametros/habilitacion")).status_code == 403
    # Sin la operación "crear" no puede registrar tipos de curso.
    sin_crear = await cliente_api.post(
        RUTA,
        json={
            "codigo": codigo_tipo(),
            "nombre": "Curso",
            "tipo": "ESPECIALIZACION",
            "modalidad": "PRESENCIAL",
            "duracion_semanas": 2,
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert sin_crear.status_code == 403
