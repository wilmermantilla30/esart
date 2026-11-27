"""
S2-14: habilitación de materias perdidas y decisiones del Consejo Académico.

- Validación de la decisión del Consejo: sin base de datos.
- Flujo completo con PostgreSQL (ESART_URL_BD_INTEGRACION); se revierte al final. Para no pasar
  del límite de inicios de sesión por prueba (TOTP), la aprobación de la planilla ordinaria y la
  nueva carga tras reabrir se simulan en la base: ya se prueban en test_revision_notas.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import confirmacion_totp
from aplicacion.servicios.consejo import validar_decision
from pruebas.test_auditoria_y_malla import cabecera_csrf, conceder_por_excepcion
from pruebas.test_carga_notas import agregar_alumno, descargar, llenar, preparar, subir
from pruebas.test_login_hu05 import crear_usuario, iniciar_sesion, requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_nota_minima import fijar_nota_inicial
from pruebas.test_panel_parametros import ultimo_evento
from pruebas.test_revision_notas import accion, codigo_error, simular_nueva_carga

pytestmark = pytest.mark.anyio

RUTA_REVISION = "/api/notas/revision/entregas"
RUTA_CONSEJO = "/api/notas/consejo/casos"


# --- Sin base de datos ----------------------------------------------------------------


def test_la_decision_del_consejo_se_valida():
    hoy = date.today()
    datos = validar_decision("REPITE_CURSO", "  Acta  012 ", hoy, "  ")
    assert (datos["numero_acta"], datos["observacion"]) == ("Acta 012", None)
    casos_invalidos = [
        ("SUSPENDE", "Acta 1", hoy, None),
        ("APRUEBA_MATERIA", "  ", hoy, None),
        ("APRUEBA_MATERIA", "x" * 51, hoy, None),
        ("APRUEBA_MATERIA", "Acta 1", hoy + timedelta(days=1), None),
        ("OTRA", "Acta 1", hoy, "   "),
    ]
    for decision, acta, fecha, observacion in casos_invalidos:
        with pytest.raises(ErrorAplicacion) as error:
            validar_decision(decision, acta, fecha, observacion)
        assert error.value.codigo == "DATOS_INVALIDOS"


# --- Con PostgreSQL -------------------------------------------------------------------


async def aprobar_planilla_en_la_base(sesion, curso_id: int) -> None:
    """Lo que hace el Inspector al aprobar la planilla ordinaria (S2-13)."""
    await sesion.execute(
        text("""
            INSERT INTO esart.notas_oficiales
              (curso_id, malla_id, personal_id, nota, nota_ordinaria, entrega_id)
            SELECT e.curso_id, e.malla_id, n.personal_id, n.nota, n.nota, e.id
            FROM esart.entregas_notas e JOIN esart.notas_entrega n ON n.entrega_id = e.id
            WHERE e.curso_id = :curso AND e.tipo = 'ORDINARIA'
        """),
        {"curso": curso_id},
    )
    await sesion.execute(
        text("UPDATE esart.entregas_notas SET estado = 'APROBADA' WHERE curso_id = :curso"),
        {"curso": curso_id},
    )


async def oficiales(sesion, curso_id: int) -> dict[str, tuple[str, str]]:
    filas = await sesion.execute(
        text("""
            SELECT p.documento_identidad, o.nota, o.origen FROM esart.notas_oficiales o
            JOIN esart.personal_militar p ON p.id = o.personal_id
            WHERE o.curso_id = :curso
        """),
        {"curso": curso_id},
    )
    return {fila.documento_identidad: (str(fila.nota), fila.origen) for fila in filas}


@requiere_postgresql
async def test_habilitar_aprobar_y_decidir_en_consejo(cliente_api, sesion_bd, monkeypatch):  # noqa: F811
    # Nota mínima 3,00 para el curso que se crea (la base local puede tener otra).
    await fijar_nota_inicial(sesion_bd)
    curso, malla_id, (primera, segunda), _ = await preparar(cliente_api, sesion_bd)
    tercera = await agregar_alumno(sesion_bd, curso, 83)
    ruta_habilitacion = f"/api/notas/habilitaciones/{curso}/{malla_id}"
    plantilla = await descargar(cliente_api, curso, malla_id)
    enviada = await subir(
        cliente_api, curso, malla_id, llenar(plantilla, {primera: 4.25, segunda: 2.0, tercera: 1.5})
    )
    assert enviada.status_code == 200, enviada.text

    # Sin notas oficiales nadie debe habilitar todavía.
    sin_oficiales = await cliente_api.post(
        ruta_habilitacion, json={"notas": []}, headers=cabecera_csrf(cliente_api)
    )
    assert sin_oficiales.status_code == 409 and codigo_error(sin_oficiales) == "SIN_HABILITACIONES"

    await aprobar_planilla_en_la_base(sesion_bd, curso)
    materia = next(
        m
        for m in (await cliente_api.get("/api/notas/mis-materias")).json()["materias"]
        if m["curso_id"] == curso
    )
    assert (materia["alumnos_a_habilitar"], materia["estado_habilitacion"]) == (2, None)
    formulario = (await cliente_api.get(ruta_habilitacion)).json()
    assert {a["cedula"]: a["nota_ordinaria"] for a in formulario["alumnos"]} == {segunda: 2.0, tercera: 1.5}

    # Se exige la nota de todos los que deben habilitar, con el mismo formato de la planilla.
    invalida = await cliente_api.post(
        ruta_habilitacion,
        json={"notas": [{"cedula": segunda, "nota": "3,555"}, {"cedula": primera, "nota": 4}]},
        headers=cabecera_csrf(cliente_api),
    )
    assert invalida.status_code == 422 and codigo_error(invalida) == "NOTAS_INVALIDAS"
    mensajes = [e["mensaje"] for e in invalida.json()["error"]["detalle"]["errores"]]
    assert any("2 decimales" in m for m in mensajes) and any("no debe habilitar" in m for m in mensajes)
    assert any("Falta la nota" in m for m in mensajes)

    registrada = await cliente_api.post(
        ruta_habilitacion,
        json={"notas": [{"cedula": segunda, "nota": "3,2"}, {"cedula": tercera, "nota": 2}]},
        headers=cabecera_csrf(cliente_api),
    )
    assert registrada.status_code == 200, registrada.text
    assert registrada.json()["estado"] == "EN_REVISION"
    evento = await ultimo_evento(sesion_bd, "NOTAS_ENTREGADAS")
    assert (evento.detalle["tipo"], evento.detalle["alumnos"]) == ("HABILITACION", 2)

    # El Inspector la aprueba: quien alcanza la mínima habilita y quien no, va al Consejo.
    inspector = await crear_usuario(sesion_bd, roles=("USUARIO",))
    for componente, operaciones in (
        ("NOTAS_REVISION", {"puede_leer": True, "puede_actualizar": True}),
        ("CONSEJO_ACADEMICO", {"puede_leer": True, "puede_crear": True}),
    ):
        await conceder_por_excepcion(sesion_bd, inspector, componente, puede_acceder=True, **operaciones)
    await iniciar_sesion(cliente_api, inspector.usuario)
    pendientes = (await cliente_api.get(RUTA_REVISION)).json()
    habilitacion = next(e for e in pendientes if e["curso_id"] == curso and e["tipo"] == "HABILITACION")
    detalle = (await cliente_api.get(f"{RUTA_REVISION}/{habilitacion['id']}")).json()
    assert {n["cedula"]: (n["nota"], n["nota_ordinaria"], n["nota_oficial"]) for n in detalle["notas"]} == {
        segunda: (3.2, 2.0, None),
        tercera: (2.0, 1.5, None),
    }
    aprobada = await accion(
        cliente_api,
        habilitacion["id"],
        "aprobar",
        {"version": habilitacion["subido_en"]},
    )
    assert aprobada.status_code == 200, aprobada.text
    assert await oficiales(sesion_bd, curso) == {
        primera: ("4.25", "ORDINARIA"),
        segunda: ("3.20", "HABILITACION"),
        tercera: ("1.50", "ORDINARIA"),
    }
    evento = await ultimo_evento(sesion_bd, "NOTAS_APROBADAS")
    assert (evento.detalle["habilitaron"], evento.detalle["al_consejo_academico"]) == (1, 1)

    # Con habilitaciones, las notas ordinarias ya no se reabren.
    ordinaria = next(
        e
        for e in (await cliente_api.get(RUTA_REVISION, params={"estado": "APROBADA"})).json()
        if e["curso_id"] == curso and e["tipo"] == "ORDINARIA"
    )
    sin_codigo = await accion(cliente_api, ordinaria["id"], "reabrir", {"observacion": "Corregir una nota."})
    assert sin_codigo.status_code == 409 and codigo_error(sin_codigo) == "MATERIA_CON_HABILITACION"

    # Consejo: el caso pendiente exige TOTP.
    casos = [c for c in (await cliente_api.get(RUTA_CONSEJO)).json() if c["curso_id"] == curso]
    assert [(c["cedula"], c["nota_habilitacion"]) for c in casos] == [(tercera, 2.0)]
    decision = {"decision": "APRUEBA_MATERIA", "numero_acta": "Acta 014", "fecha_acta": str(date.today())}
    sin_codigo = await cliente_api.post(
        f"{RUTA_CONSEJO}/{casos[0]['id']}/decision", json=decision, headers=cabecera_csrf(cliente_api)
    )
    assert sin_codigo.status_code == 409 and codigo_error(sin_codigo) == "TOTP_REQUERIDO"
    monkeypatch.setattr(
        confirmacion_totp, "obtener_configuracion", lambda: SimpleNamespace(totp_habilitado=False)
    )

    # Corrección de la habilitación antes de que decida el Consejo: se deshace y se aplica la nueva.
    reabierta = await accion(cliente_api, habilitacion["id"], "reabrir", {"observacion": "Notas cruzadas."})
    assert reabierta.status_code == 200, reabierta.text
    await simular_nueva_carga(sesion_bd, habilitacion["id"], {segunda: 2.8, tercera: 3.0})
    version = (await cliente_api.get(f"{RUTA_REVISION}/{habilitacion['id']}")).json()["subido_en"]
    corregida = await accion(cliente_api, habilitacion["id"], "aprobar", {"version": version})
    assert corregida.status_code == 200, corregida.text
    assert await oficiales(sesion_bd, curso) == {
        primera: ("4.25", "ORDINARIA"),
        segunda: ("2.00", "ORDINARIA"),
        tercera: ("3.00", "HABILITACION"),
    }
    evento = await ultimo_evento(sesion_bd, "NOTAS_APROBADAS")
    assert evento.detalle["es_correccion"] is True
    assert sorted(evento.detalle["cambios"], key=lambda c: c["cedula"]) == sorted(
        [
            {"cedula": segunda, "antes": "3.20", "despues": "2.80"},
            {"cedula": tercera, "antes": "2.00", "despues": "3.00"},
        ],
        key=lambda c: c["cedula"],
    )

    # El Consejo decide sobre quien perdió ahora la habilitación.
    caso = next(c for c in (await cliente_api.get(RUTA_CONSEJO)).json() if c["curso_id"] == curso)
    assert caso["cedula"] == segunda
    otra_sin_motivo = await cliente_api.post(
        f"{RUTA_CONSEJO}/{caso['id']}/decision",
        json={**decision, "decision": "OTRA"},
        headers=cabecera_csrf(cliente_api),
    )
    assert otra_sin_motivo.status_code == 422 and codigo_error(otra_sin_motivo) == "DATOS_INVALIDOS"
    decidido = await cliente_api.post(
        f"{RUTA_CONSEJO}/{caso['id']}/decision", json=decision, headers=cabecera_csrf(cliente_api)
    )
    assert decidido.status_code == 200, decidido.text
    assert (decidido.json()["decision"], decidido.json()["numero_acta"]) == ("APRUEBA_MATERIA", "Acta 014")
    assert (await oficiales(sesion_bd, curso))[segunda] == ("3.00", "CONSEJO")
    evento = await ultimo_evento(sesion_bd, "CONSEJO_DECISION_REGISTRADA")
    assert (evento.detalle["cedula"], evento.detalle["nota_que_cuenta"]) == (segunda, "3.00")

    otra_vez = await cliente_api.post(
        f"{RUTA_CONSEJO}/{caso['id']}/decision", json=decision, headers=cabecera_csrf(cliente_api)
    )
    assert otra_vez.status_code == 409 and codigo_error(otra_vez) == "CASO_DECIDIDO"
    decididos = (await cliente_api.get(RUTA_CONSEJO, params={"filtro": "DECIDIDOS"})).json()
    assert caso["id"] in {c["id"] for c in decididos}
    # Con decisión del Consejo, la habilitación ya no se reabre.
    bloqueada = await accion(cliente_api, habilitacion["id"], "reabrir", {"observacion": "Otro cambio."})
    assert bloqueada.status_code == 409 and codigo_error(bloqueada) == "HABILITACION_CON_DECISION"


@requiere_postgresql
async def test_permisos_del_consejo(cliente_api, sesion_bd):  # noqa: F811
    sin_permiso = await crear_usuario(sesion_bd, roles=("USUARIO",))
    await iniciar_sesion(cliente_api, sin_permiso.usuario)
    assert (await cliente_api.get(RUTA_CONSEJO)).status_code == 403

    solo_lectura = await crear_usuario(sesion_bd, roles=("USUARIO",))
    await conceder_por_excepcion(
        sesion_bd, solo_lectura, "CONSEJO_ACADEMICO", puede_acceder=True, puede_leer=True
    )
    await iniciar_sesion(cliente_api, solo_lectura.usuario)
    yo = (await cliente_api.get("/api/auth/yo")).json()
    assert "CONSEJO_ACADEMICO" in {elemento["codigo"] for elemento in yo["menu"]}
    assert (await cliente_api.get(RUTA_CONSEJO, params={"filtro": "TODOS"})).status_code == 200
    assert (await cliente_api.get(RUTA_CONSEJO, params={"filtro": "OTRO"})).status_code == 422
    respuesta = await cliente_api.post(
        f"{RUTA_CONSEJO}/999999999/decision", json={}, headers=cabecera_csrf(cliente_api)
    )
    assert respuesta.status_code == 403
