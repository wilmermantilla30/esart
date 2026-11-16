"""
Pruebas del menú y la malla de permisos (HU-09).

- construir_menu: sin base de datos.
- Menú real por rol y excepciones por usuario: con PostgreSQL (ESART_URL_BD_INTEGRACION),
  usando la malla inicial de la migración p0005. Todo se revierte al final.
"""

import pytest
from sqlalchemy import select

from aplicacion.modelos import Componente, UsuarioPermiso
from aplicacion.seguridad.permisos import PermisoEfectivo, obtener_permisos_efectivos
from aplicacion.servicios.menu import construir_menu
from pruebas.test_login_hu05 import crear_usuario, iniciar_sesion, requiere_postgresql, sesion_bd  # noqa: F401

pytestmark = pytest.mark.anyio


def permiso(codigo, *, ruta="/x", padre=None, acceder=True, crear=False, leer=True, orden=0):
    return PermisoEfectivo(
        codigo=codigo,
        nombre=codigo.title(),
        ruta_angular=ruta,
        orden=orden,
        codigo_padre=padre,
        puede_acceder=acceder,
        puede_crear=crear,
        puede_leer=leer,
        puede_actualizar=False,
        puede_eliminar=False,
    )


# --- Sin base de datos --------------------------------------------------------------


def test_construir_menu_agrupa_hijos_bajo_su_padre_y_respeta_el_orden():
    resultado = construir_menu(
        [
            permiso("DASHBOARD", orden=10),
            permiso("PERSONAL", orden=20),
            permiso("PERSONAL_VERIFICAR", padre="PERSONAL", orden=21),
            permiso("PERSONAL_CARGUE", padre="PERSONAL", orden=22, crear=True),
        ]
    )
    assert [e.codigo for e in resultado.menu] == ["DASHBOARD", "PERSONAL"]
    assert [h.codigo for h in resultado.menu[1].hijos] == ["PERSONAL_VERIFICAR", "PERSONAL_CARGUE"]
    assert resultado.menu[1].hijos[1].operaciones == ["crear", "leer"]


def test_construir_menu_oculta_lo_no_accesible_y_lo_que_no_es_menu():
    resultado = construir_menu(
        [
            permiso("DASHBOARD"),
            permiso("USUARIOS", acceder=False),
            permiso("VER_DOCUMENTO_COMPLETO", ruta=None),
            # Hijo accesible de un padre al que no puede entrar: no aparece.
            permiso("ADMIN", acceder=False),
            permiso("ADMIN_HIJO", padre="ADMIN"),
        ]
    )
    assert [e.codigo for e in resultado.menu] == ["DASHBOARD"]
    # La lista de permisos sí incluye lo que no es menú.
    assert "VER_DOCUMENTO_COMPLETO" in resultado.permisos
    assert "USUARIOS" not in resultado.permisos


# --- Con PostgreSQL (malla inicial de p0005) ---------------------------------------


@requiere_postgresql
async def test_menu_de_usuario_solo_consulta_y_sin_administracion(cliente_api, sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd, roles=("USUARIO",))
    await iniciar_sesion(cliente_api, usuario.usuario)

    respuesta = await cliente_api.get("/api/auth/yo")

    assert respuesta.status_code == 200
    menu = respuesta.json()["menu"]
    assert [e["codigo"] for e in menu] == ["DASHBOARD", "PERSONAL_MILITAR"]
    pestanas = [h["codigo"] for h in menu[1]["hijos"]]
    assert pestanas == ["PERSONAL_VERIFICAR", "PERSONAL_HABILITADOS"]
    assert all(h["operaciones"] == ["leer"] for h in menu[1]["hijos"])
    # El Comandante (USUARIO) ve la cédula completa; no administra.
    permisos = respuesta.json()["permisos"]
    assert "VER_DOCUMENTO_COMPLETO" in permisos
    assert not {"USUARIOS", "PERMISOS", "AUDITORIA", "PARAMETROS_HABILITACION"} & set(permisos)


@requiere_postgresql
async def test_menu_de_administrador_incluye_cargue_y_administracion(cliente_api, sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd, roles=("ADMINISTRADOR",))
    await iniciar_sesion(cliente_api, usuario.usuario)

    menu = (await cliente_api.get("/api/auth/yo")).json()["menu"]

    assert [e["codigo"] for e in menu] == [
        "DASHBOARD",
        "PERSONAL_MILITAR",
        "USUARIOS",
        "PARAMETROS_HABILITACION",
        "PERMISOS",
        "AUDITORIA",
    ]
    personal = next(e for e in menu if e["codigo"] == "PERSONAL_MILITAR")
    assert [h["codigo"] for h in personal["hijos"]] == [
        "PERSONAL_VERIFICAR",
        "PERSONAL_HABILITADOS",
        "PERSONAL_CARGUE_EXCEL",
        "PERSONAL_CARGUE_MANUAL",
    ]
    auditoria = next(e for e in menu if e["codigo"] == "AUDITORIA")
    assert auditoria["operaciones"] == ["leer"]  # Inmutable: ni el administrador la edita.
    # Los módulos de la segunda entrega están inactivos y no aparecen.
    assert not {"HOJAS_VIDA", "DOCTRINA", "NOTAS"} & {e["codigo"] for e in menu}


@requiere_postgresql
async def test_excepcion_por_usuario_sustituye_al_rol(sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd, roles=("USUARIO",))
    cargue = await sesion_bd.scalar(select(Componente).where(Componente.codigo == "PERSONAL_CARGUE_EXCEL"))
    verificar = await sesion_bd.scalar(select(Componente).where(Componente.codigo == "PERSONAL_VERIFICAR"))
    # Se le concede el cargue y se le quita la verificación, solo a este usuario.
    sesion_bd.add(
        UsuarioPermiso(usuario_id=usuario.id, componente_id=cargue.id, puede_acceder=True, puede_crear=True)
    )
    sesion_bd.add(UsuarioPermiso(usuario_id=usuario.id, componente_id=verificar.id, puede_acceder=False))
    await sesion_bd.flush()

    efectivos = {p.codigo: p for p in await obtener_permisos_efectivos(sesion_bd, usuario.id)}

    assert efectivos["PERSONAL_CARGUE_EXCEL"].puede_acceder and efectivos["PERSONAL_CARGUE_EXCEL"].puede_crear
    assert not efectivos["PERSONAL_VERIFICAR"].puede_acceder
    assert efectivos["PERSONAL_HABILITADOS"].puede_leer  # Lo demás sigue igual que su rol.
