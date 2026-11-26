"""
S2-13: el Inspector de Estudios aprueba, devuelve o reabre las entregas de notas.

- Validación de la observación: sin base de datos.
- Flujo completo y permisos: con PostgreSQL (ESART_URL_BD_INTEGRACION); se revierte al final.
  Para no pasar del límite de inicios de sesión por prueba (TOTP), la nueva carga del instructor
  tras una devolución se simula en la base: la subida ya se prueba en test_carga_notas.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import confirmacion_totp
from aplicacion.servicios.revision_notas import validar_observacion
from pruebas.test_auditoria_y_malla import cabecera_csrf, conceder_por_excepcion
from pruebas.test_carga_notas import descargar, llenar, preparar, subir
from pruebas.test_login_hu05 import crear_usuario, iniciar_sesion, requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_panel_parametros import codigo_siguiente, ultimo_evento

pytestmark = pytest.mark.anyio

RUTA = "/api/notas/revision/entregas"


# --- Sin base de datos ----------------------------------------------------------------


def test_la_observacion_es_obligatoria_y_se_normaliza():
    assert validar_observacion("  Revise   la nota\n de Pérez ") == "Revise la nota de Pérez"
    for invalida in (None, "", "   ", "ok"):
        with pytest.raises(ErrorAplicacion) as error:
            validar_observacion(invalida)
        assert error.value.codigo == "DATOS_INVALIDOS"
    with pytest.raises(ErrorAplicacion):
        validar_observacion("x" * 1001)


# --- Con PostgreSQL -------------------------------------------------------------------


async def entrar_como_inspector(cliente_api, sesion, *, puede_actualizar=True):
    inspector = await crear_usuario(sesion, roles=("USUARIO",))
    await conceder_por_excepcion(
        sesion,
        inspector,
        "NOTAS_REVISION",
        puede_acceder=True,
        puede_leer=True,
        puede_actualizar=puede_actualizar,
    )
    await iniciar_sesion(cliente_api, inspector.usuario)
    return inspector


async def simular_nueva_carga(sesion, entrega_id: int, notas: dict[str, float]) -> None:
    """Lo que hace la subida del instructor sobre una entrega devuelta (sin iniciar su sesión)."""
    for cedula, nota in notas.items():
        await sesion.execute(
            text("""
                UPDATE esart.notas_entrega SET nota = :nota
                WHERE entrega_id = :entrega
                  AND personal_id = (
                      SELECT id FROM esart.personal_militar WHERE documento_identidad = :cedula
                  )
            """),
            {"nota": nota, "entrega": entrega_id, "cedula": cedula},
        )
    # clock_timestamp: dentro de la misma transacción now() no avanzaría y la versión no cambiaría.
    await sesion.execute(
        text("""
            UPDATE esart.entregas_notas
            SET estado = 'EN_REVISION', subido_en = clock_timestamp(),
                revisado_por_id = NULL, revisado_en = NULL, observacion_revision = NULL
            WHERE id = :id
        """),
        {"id": entrega_id},
    )


async def notas_oficiales(sesion, curso_id: int) -> dict[str, str]:
    filas = await sesion.execute(
        text("""
            SELECT p.documento_identidad, o.nota FROM esart.notas_oficiales o
            JOIN esart.personal_militar p ON p.id = o.personal_id
            WHERE o.curso_id = :curso
        """),
        {"curso": curso_id},
    )
    return {fila.documento_identidad: str(fila.nota) for fila in filas}


async def accion(cliente_api, entrega_id: int, nombre: str, datos: dict):
    return await cliente_api.post(
        f"{RUTA}/{entrega_id}/{nombre}", json=datos, headers=cabecera_csrf(cliente_api)
    )


def codigo_error(respuesta) -> str:
    return respuesta.json()["error"]["codigo"]


@requiere_postgresql
async def test_devolver_aprobar_y_corregir_una_nota_oficial(cliente_api, sesion_bd, monkeypatch):  # noqa: F811
    curso, malla_id, (primera, segunda), _ = await preparar(cliente_api, sesion_bd)
    plantilla = await descargar(cliente_api, curso, malla_id)
    enviada = await subir(cliente_api, curso, malla_id, llenar(plantilla, {primera: 4.25, segunda: 2.8}))
    assert enviada.status_code == 200, enviada.text

    await entrar_como_inspector(cliente_api, sesion_bd)
    yo = (await cliente_api.get("/api/auth/yo")).json()
    assert "NOTAS_REVISION" in {elemento["codigo"] for elemento in yo["menu"]}

    pendientes = (await cliente_api.get(RUTA)).json()
    entrega = next(e for e in pendientes if e["curso_id"] == curso)
    assert (entrega["estado"], entrega["alumnos"], entrega["promedio"]) == ("EN_REVISION", 2, 3.53)
    assert (entrega["por_debajo_de_la_minima"], entrega["tiene_notas_oficiales"]) == (1, False)
    entrega_id, version = entrega["id"], entrega["subido_en"]
    detalle = (await cliente_api.get(f"{RUTA}/{entrega_id}")).json()
    assert {n["cedula"]: (n["nota"], n["nota_oficial"]) for n in detalle["notas"]} == {
        primera: (4.25, None),
        segunda: (2.8, None),
    }

    # Devolver: exige observación y la versión revisada.
    sin_motivo = await accion(cliente_api, entrega_id, "devolver", {"version": version, "observacion": " "})
    assert sin_motivo.status_code == 422 and codigo_error(sin_motivo) == "DATOS_INVALIDOS"
    vieja = await accion(
        cliente_api,
        entrega_id,
        "devolver",
        {"version": "2020-01-01T00:00:00+00:00", "observacion": "Revise la segunda nota."},
    )
    assert vieja.status_code == 409 and codigo_error(vieja) == "ENTREGA_CAMBIO"
    devuelta = await accion(
        cliente_api, entrega_id, "devolver", {"version": version, "observacion": "Revise la segunda nota."}
    )
    assert devuelta.status_code == 200, devuelta.text
    assert devuelta.json()["estado"] == "DEVUELTA"
    assert devuelta.json()["observacion_revision"] == "Revise la segunda nota."
    evento = await ultimo_evento(sesion_bd, "NOTAS_DEVUELTAS")
    assert (
        evento.detalle["observacion"] == "Revise la segunda nota."
        and evento.detalle["entrega_id"] == entrega_id
    )
    # Ya devuelta, no se aprueba hasta que el instructor la suba de nuevo.
    sin_carga = await accion(cliente_api, entrega_id, "aprobar", {"version": version})
    assert sin_carga.status_code == 409 and codigo_error(sin_carga) == "ESTADO_NO_PERMITE"

    # El instructor la sube de nuevo; el Inspector la aprueba con TOTP.
    await simular_nueva_carga(sesion_bd, entrega_id, {segunda: 2.9})
    version = (await cliente_api.get(f"{RUTA}/{entrega_id}")).json()["subido_en"]
    sin_codigo = await accion(cliente_api, entrega_id, "aprobar", {"version": version})
    assert sin_codigo.status_code == 409 and codigo_error(sin_codigo) == "TOTP_REQUERIDO"
    aprobada = await accion(
        cliente_api, entrega_id, "aprobar", {"version": version, "codigo_totp": codigo_siguiente(cliente_api)}
    )
    assert aprobada.status_code == 200, aprobada.text
    assert aprobada.json()["estado"] == "APROBADA" and aprobada.json()["revisado_por"]
    assert await notas_oficiales(sesion_bd, curso) == {primera: "4.25", segunda: "2.90"}
    evento = await ultimo_evento(sesion_bd, "NOTAS_APROBADAS")
    assert (evento.detalle["es_correccion"], evento.detalle["cambios"]) == (False, [])
    assert evento.detalle["promedio"] == "3.58" and evento.detalle["por_debajo_de_la_minima"] == 1

    # Reabrir una aprobada exige TOTP (el código del intervalo ya se usó: se prueba solo que lo pide).
    sin_codigo = await accion(cliente_api, entrega_id, "reabrir", {"observacion": "Error en la segunda."})
    assert sin_codigo.status_code == 409 and codigo_error(sin_codigo) == "TOTP_REQUERIDO"
    # Para las acciones siguientes no se pide código (la sesión sigue exigiendo TOTP).
    monkeypatch.setattr(
        confirmacion_totp, "obtener_configuracion", lambda: SimpleNamespace(totp_habilitado=False)
    )
    reabierta = await accion(cliente_api, entrega_id, "reabrir", {"observacion": "Error en la segunda."})
    assert reabierta.status_code == 200, reabierta.text
    assert reabierta.json()["estado"] == "DEVUELTA" and reabierta.json()["tiene_notas_oficiales"] is True
    assert (await ultimo_evento(sesion_bd, "NOTAS_REABIERTAS")).detalle[
        "observacion"
    ] == "Error en la segunda."
    # Mientras se corrige, las oficiales siguen vigentes.
    assert await notas_oficiales(sesion_bd, curso) == {primera: "4.25", segunda: "2.90"}

    # Corrección: el detalle muestra la nota oficial anterior y la aprobación guarda antes y después.
    await simular_nueva_carga(sesion_bd, entrega_id, {segunda: 3.5})
    detalle = (await cliente_api.get(f"{RUTA}/{entrega_id}")).json()
    assert {n["cedula"]: (n["nota"], n["nota_oficial"]) for n in detalle["notas"]}[segunda] == (3.5, 2.9)
    corregida = await accion(cliente_api, entrega_id, "aprobar", {"version": detalle["subido_en"]})
    assert corregida.status_code == 200, corregida.text
    assert await notas_oficiales(sesion_bd, curso) == {primera: "4.25", segunda: "3.50"}
    evento = await ultimo_evento(sesion_bd, "NOTAS_APROBADAS")
    assert evento.detalle["es_correccion"] is True
    assert evento.detalle["cambios"] == [{"cedula": segunda, "antes": "2.90", "despues": "3.50"}]
    # Aprobada de nuevo: ni se devuelve ni se aprueba otra vez.
    otra_vez = await accion(cliente_api, entrega_id, "aprobar", {"version": detalle["subido_en"]})
    assert otra_vez.status_code == 409 and codigo_error(otra_vez) == "ESTADO_NO_PERMITE"
    aprobadas = (await cliente_api.get(RUTA, params={"estado": "APROBADA"})).json()
    assert entrega_id in {e["id"] for e in aprobadas}


@requiere_postgresql
async def test_un_alumno_nuevo_impide_aprobar_la_entrega(cliente_api, sesion_bd):  # noqa: F811
    from pruebas.test_carga_notas import agregar_alumno

    curso, malla_id, (primera, segunda), _ = await preparar(cliente_api, sesion_bd)
    plantilla = await descargar(cliente_api, curso, malla_id)
    assert (
        await subir(cliente_api, curso, malla_id, llenar(plantilla, {primera: 4, segunda: 4}))
    ).status_code == 200
    await agregar_alumno(sesion_bd, curso, 83)

    await entrar_como_inspector(cliente_api, sesion_bd)
    entrega = next(e for e in (await cliente_api.get(RUTA)).json() if e["curso_id"] == curso)
    respuesta = await accion(
        cliente_api,
        entrega["id"],
        "aprobar",
        {"version": entrega["subido_en"], "codigo_totp": codigo_siguiente(cliente_api)},
    )
    assert respuesta.status_code == 409 and codigo_error(respuesta) == "ENTREGA_DESACTUALIZADA"
    assert await notas_oficiales(sesion_bd, curso) == {}


@requiere_postgresql
async def test_permisos_de_la_revision(cliente_api, sesion_bd):  # noqa: F811
    # Sin el componente: nada.
    sin_permiso = await crear_usuario(sesion_bd, roles=("USUARIO",))
    await iniciar_sesion(cliente_api, sin_permiso.usuario)
    assert (await cliente_api.get(RUTA)).status_code == 403

    # Solo lectura: ve la bandeja pero no aprueba, devuelve ni reabre.
    await entrar_como_inspector(cliente_api, sesion_bd, puede_actualizar=False)
    assert (await cliente_api.get(RUTA)).status_code == 200
    assert (await cliente_api.get(RUTA, params={"estado": "OTRO"})).status_code == 422
    for nombre in ("aprobar", "devolver", "reabrir"):
        respuesta = await accion(cliente_api, 999999999, nombre, {})
        assert respuesta.status_code == 403, (nombre, respuesta.text)
    assert (await cliente_api.get(f"{RUTA}/999999999")).status_code == 404
