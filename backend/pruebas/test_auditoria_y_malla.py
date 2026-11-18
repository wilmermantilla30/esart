"""
Pruebas de la auditoría (HU-11) y de la malla de permisos editable.

Las de integración usan PostgreSQL (ESART_URL_BD_INTEGRACION) y todo se revierte al final.
"""

import pytest
from sqlalchemy import select, text

from aplicacion.modelos import AuditoriaEvento, Componente, UsuarioPermiso
from aplicacion.seguridad.sesion_http import NOMBRE_CABECERA_CSRF, NOMBRE_COOKIE_CSRF
from aplicacion.servicios.auditoria import _validar_detalle
from pruebas.test_login_hu05 import (  # noqa: F401
    CONTRASENA_CORRECTA,
    crear_usuario,
    iniciar_sesion,
    requiere_postgresql,
    sesion_bd,
)
from pruebas.test_verificacion_habilitacion import crear_militar

pytestmark = pytest.mark.anyio


# --- Sin base de datos --------------------------------------------------------------


@pytest.mark.parametrize(
    "detalle",
    [
        {"contrasena": "x"},
        {"datos": {"Token_Sesion": "x"}},
        {"lista": [{"password": "x"}]},
        {"hash_admin": "x"},
    ],
)
def test_la_auditoria_rechaza_detalles_con_credenciales(detalle):
    with pytest.raises(ValueError):
        _validar_detalle(detalle)


def test_la_auditoria_acepta_detalles_normales():
    _validar_detalle({"filtros": {"estado": "APTO", "texto": None}, "total": 5})


# --- Utilidades ---------------------------------------------------------------------


async def eventos(sesion, accion: str) -> list[AuditoriaEvento]:
    return list(
        await sesion.scalars(
            select(AuditoriaEvento)
            .where(AuditoriaEvento.accion == accion)
            .order_by(AuditoriaEvento.id.desc())
        )
    )


async def entrar(cliente_api, sesion, roles=("USUARIO",)):
    usuario = await crear_usuario(sesion, roles=roles)
    await iniciar_sesion(cliente_api, usuario.usuario)
    return usuario


def cabecera_csrf(cliente_api) -> dict:
    return {NOMBRE_CABECERA_CSRF: cliente_api.cookies.get(NOMBRE_COOKIE_CSRF)}


async def conceder_por_excepcion(sesion, usuario, codigo: str, **operaciones):
    componente = await sesion.scalar(select(Componente).where(Componente.codigo == codigo))
    sesion.add(UsuarioPermiso(usuario_id=usuario.id, componente_id=componente.id, **operaciones))
    await sesion.flush()


# --- Auditoría ----------------------------------------------------------------------


@requiere_postgresql
async def test_login_exitoso_y_fallido_quedan_auditados_sin_contrasena(cliente_api, sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd)

    await iniciar_sesion(cliente_api, usuario.usuario, "Clave-Equivocada-1")
    await iniciar_sesion(cliente_api, usuario.usuario)

    fallido = (await eventos(sesion_bd, "LOGIN_FALLIDO"))[0]
    assert fallido.nombre_usuario == usuario.usuario and fallido.resultado == "RECHAZADO"
    exitoso = (await eventos(sesion_bd, "LOGIN_EXITOSO"))[0]
    assert exitoso.usuario_id == usuario.id and str(exitoso.direccion_ip) == "127.0.0.1"
    filas = (
        (await sesion_bd.execute(text("SELECT detalle::text FROM esart.auditoria_eventos"))).scalars().all()
    )
    assert not any(
        CONTRASENA_CORRECTA in (fila or "") or "Clave-Equivocada-1" in (fila or "") for fila in filas
    )


@requiere_postgresql
async def test_consultas_de_verificacion_quedan_auditadas(cliente_api, sesion_bd):  # noqa: F811
    cedula = await crear_militar(sesion_bd, "sacli", 41)
    usuario = await entrar(cliente_api, sesion_bd)

    await cliente_api.get(f"/api/verificar/artillero/{cedula}")
    await cliente_api.get("/api/verificar/artillero/1111111111")
    await cliente_api.get("/api/verificar/no-habilitados", params={"texto": "Integración"})

    consultas = await eventos(sesion_bd, "CONSULTA_ARTILLERO")
    assert (consultas[1].numero_documento_consultado, consultas[1].resultado) == (cedula, "APTO")
    assert (consultas[0].numero_documento_consultado, consultas[0].resultado) == (
        "1111111111",
        "NO_ENCONTRADO",
    )
    assert consultas[0].usuario_id == usuario.id
    listado = (await eventos(sesion_bd, "CONSULTA_NO_HABILITADOS"))[0]
    assert listado.detalle["filtros"]["texto"] == "Integración"


@requiere_postgresql
async def test_el_acceso_denegado_queda_auditado(cliente_api, sesion_bd):  # noqa: F811
    usuario = await entrar(cliente_api, sesion_bd)

    respuesta = await cliente_api.get("/api/administracion/permisos/roles")

    assert respuesta.status_code == 403
    denegado = (await eventos(sesion_bd, "ACCESO_DENEGADO"))[0]
    assert denegado.usuario_id == usuario.id
    assert denegado.detalle["componente"] == "PERMISOS"


@requiere_postgresql
async def test_la_auditoria_es_inmutable(sesion_bd):  # noqa: F811
    sesion_bd.add(AuditoriaEvento(accion="CONSULTA_RESUMEN", resultado="EXITOSO"))
    await sesion_bd.flush()
    with pytest.raises(Exception, match="inmutable"):
        async with sesion_bd.begin_nested():
            await sesion_bd.execute(text("UPDATE esart.auditoria_eventos SET resultado = 'X'"))


@requiere_postgresql
async def test_consulta_de_auditoria_solo_administrador(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    respuesta = await cliente_api.get("/api/administracion/auditoria", params={"accion": "LOGIN_EXITOSO"})
    assert respuesta.status_code == 200
    assert respuesta.json()["elementos"][0]["accion"] == "LOGIN_EXITOSO"


# --- Malla de permisos ----------------------------------------------------------------


@requiere_postgresql
async def test_el_rol_administrador_es_fijo(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))

    lectura = await cliente_api.get("/api/administracion/permisos/roles/ADMINISTRADOR")
    assert lectura.json()["editable"] is False
    intento = await cliente_api.put(
        "/api/administracion/permisos/roles/ADMINISTRADOR",
        json={"permisos": [{"componente": "PERMISOS", "acceder": False}]},
        headers=cabecera_csrf(cliente_api),
    )
    assert intento.status_code == 409 and intento.json()["error"]["codigo"] == "ROL_NO_EDITABLE"


@requiere_postgresql
async def test_cambiar_permisos_del_rol_usuario_se_refleja_en_su_menu(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))

    respuesta = await cliente_api.put(
        "/api/administracion/permisos/roles/USUARIO",
        json={"permisos": [{"componente": "AUDITORIA", "acceder": True, "leer": True}]},
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 200, respuesta.text
    fila = next(f for f in respuesta.json()["filas"] if f["codigo"] == "AUDITORIA")
    assert fila["permisos"]["leer"] is True
    assert (await eventos(sesion_bd, "PERMISOS_ROL_MODIFICADOS"))[0].detalle["rol"] == "USUARIO"

    cliente_api.cookies.clear()
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    menu = (await cliente_api.get("/api/auth/yo")).json()["menu"]
    assert "AUDITORIA" in {m["codigo"] for m in menu}


@requiere_postgresql
async def test_excepciones_por_usuario_conceder_quitar_y_heredar(cliente_api, sesion_bd):  # noqa: F811
    objetivo = await crear_usuario(sesion_bd, roles=("USUARIO",))
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    url = f"/api/administracion/permisos/usuarios/{objetivo.id}"

    respuesta = await cliente_api.put(
        url,
        json={
            "cambios": [
                {"componente": "PERSONAL_CARGUE_EXCEL", "modo": "CONCEDER", "crear": True, "leer": True},
                {"componente": "PERSONAL_VERIFICAR", "modo": "QUITAR"},
            ]
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 200, respuesta.text
    filas = {f["codigo"]: f for f in respuesta.json()["filas"]}
    assert (
        filas["PERSONAL_CARGUE_EXCEL"]["modo"] == "CONCEDER"
        and filas["PERSONAL_CARGUE_EXCEL"]["efectivo"]["crear"]
    )
    assert (
        filas["PERSONAL_VERIFICAR"]["modo"] == "QUITAR"
        and not filas["PERSONAL_VERIFICAR"]["efectivo"]["acceder"]
    )
    assert filas["PERSONAL_VERIFICAR"]["rol"]["acceder"]  # Su rol sí lo daba.

    respuesta = await cliente_api.put(
        url,
        json={"cambios": [{"componente": "PERSONAL_VERIFICAR", "modo": "HEREDAR"}]},
        headers=cabecera_csrf(cliente_api),
    )
    assert {f["codigo"]: f for f in respuesta.json()["filas"]}["PERSONAL_VERIFICAR"]["efectivo"][
        "acceder"
    ] is True
    assert (await eventos(sesion_bd, "PERMISOS_USUARIO_MODIFICADOS"))[0].detalle[
        "usuario_modificado"
    ] == objetivo.usuario


@requiere_postgresql
async def test_un_administrador_no_admite_excepciones(cliente_api, sesion_bd):  # noqa: F811
    otro_administrador = await crear_usuario(sesion_bd, roles=("ADMINISTRADOR",))
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    respuesta = await cliente_api.put(
        f"/api/administracion/permisos/usuarios/{otro_administrador.id}",
        json={"cambios": [{"componente": "PERMISOS", "modo": "QUITAR"}]},
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 409 and respuesta.json()["error"]["codigo"] == "USUARIO_NO_EDITABLE"


@requiere_postgresql
async def test_nadie_se_quita_a_si_mismo_la_malla(cliente_api, sesion_bd):  # noqa: F811
    # Un USUARIO al que se le concedió administrar la malla por excepción.
    usuario = await crear_usuario(sesion_bd, roles=("USUARIO",))
    await conceder_por_excepcion(
        sesion_bd, usuario, "PERMISOS", puede_acceder=True, puede_leer=True, puede_actualizar=True
    )
    await iniciar_sesion(cliente_api, usuario.usuario)

    respuesta = await cliente_api.put(
        f"/api/administracion/permisos/usuarios/{usuario.id}",
        json={"cambios": [{"componente": "PERMISOS", "modo": "QUITAR"}]},
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 409 and respuesta.json()["error"]["codigo"] == "AUTOBLOQUEO"


@requiere_postgresql
async def test_guardar_exige_csrf_y_usuario_no_entra_a_la_malla(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    sin_csrf = await cliente_api.put("/api/administracion/permisos/roles/USUARIO", json={"permisos": []})
    assert sin_csrf.status_code == 403

    cliente_api.cookies.clear()
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    assert (await cliente_api.get("/api/administracion/permisos/usuarios")).status_code == 403
