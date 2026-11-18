"""
Pruebas del inicio de sesión (HU-05) sobre el modelo de HU-04.

- Las que no necesitan base de datos corren siempre.
- Las de integración usan PostgreSQL real y solo corren si existe ESART_URL_BD_INTEGRACION
  con una base que ya tenga la migración p0002. Todo ocurre dentro de una transacción
  que se revierte al final: la base queda exactamente como estaba.

    $env:ESART_URL_BD_INTEGRACION = "postgresql+asyncpg://esart_aplicacion:...@127.0.0.1:5433/esart_db"
"""

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import PersonalMilitar, Rol, SesionUsuario, Usuario, UsuarioRoles
from aplicacion.principal import aplicacion
from aplicacion.seguridad.contrasenas import generar_hash_contrasena
from aplicacion.seguridad.sesion_http import NOMBRE_CABECERA_CSRF, NOMBRE_COOKIE_CSRF, NOMBRE_COOKIE_SESION
from aplicacion.seguridad.tokens import decodificar_token_sesion
from aplicacion.servicios.autenticacion import asegurar_administrador_inicial
from pruebas.soporte_mfa import completar_vinculacion

pytestmark = pytest.mark.anyio

URL_BASE_DATOS_INTEGRACION = os.environ.get("ESART_URL_BD_INTEGRACION")
requiere_postgresql = pytest.mark.skipif(
    not URL_BASE_DATOS_INTEGRACION, reason="ESART_URL_BD_INTEGRACION no está definida"
)

CONTRASENA_CORRECTA = "Clave-Integracion-2026"
HASH_CONTRASENA_CORRECTA = generar_hash_contrasena(CONTRASENA_CORRECTA)
# Error genérico de HU-06 tras UN fallo: todavía sin captcha ni restricción.
ERROR_CREDENCIALES = {
    "error": {
        "codigo": "CREDENCIALES_INVALIDAS",
        "mensaje": "No fue posible iniciar sesión. Compruebe los datos o inténtelo más tarde.",
        # captcha_validado: None porque en el primer fallo todavía no se pide captcha.
        "detalle": {
            "captcha_requerido": False,
            "acceso_temporalmente_restringido": False,
            "captcha_validado": None,
        },
    }
}


# --- Sin base de datos ------------------------------------------------------------


async def test_login_con_datos_invalidos_no_devuelve_la_contrasena(cliente_api):
    respuesta = await cliente_api.post(
        "/api/auth/login",
        json={"nombre_usuario": "ab", "contrasena": "Secreta-Que-No-Debe-Volver", "campo_extra": 1},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["codigo"] == "DATOS_INVALIDOS"
    assert "Secreta-Que-No-Debe-Volver" not in respuesta.text


@pytest.mark.parametrize("cookie", [None, "token-basura"])
async def test_yo_sin_sesion_valida_responde_401(cliente_api, cookie):
    if cookie:
        cliente_api.cookies.set(NOMBRE_COOKIE_SESION, cookie)
    respuesta = await cliente_api.get("/api/auth/yo")
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "NO_AUTENTICADO"
    # Sin sesión válida no se informa ningún tiempo de expiración.
    assert "X-Sesion-Expira-En" not in respuesta.headers


async def test_cerrar_sesion_sin_cabecera_csrf_responde_403(cliente_api):
    cliente_api.cookies.set(NOMBRE_COOKIE_CSRF, "valor-csrf")
    respuesta = await cliente_api.post("/api/auth/cerrar-sesion")
    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "SIN_PERMISO"


# --- Con PostgreSQL real ------------------------------------------------------------


@pytest.fixture
async def sesion_bd():
    """
    Sesión real cuyos commit() se convierten en savepoints de una transacción externa
    que siempre se revierte (join_transaction_mode="create_savepoint").
    """
    motor = create_async_engine(URL_BASE_DATOS_INTEGRACION, hide_parameters=True)
    async with motor.connect() as conexion:
        transaccion_externa = await conexion.begin()
        sesion = AsyncSession(bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint")

        async def entregar_sesion_real():
            yield sesion

        aplicacion.dependency_overrides[obtener_sesion_base_datos] = entregar_sesion_real
        try:
            yield sesion
        finally:
            aplicacion.dependency_overrides.pop(obtener_sesion_base_datos, None)
            await sesion.close()
            await transaccion_externa.rollback()
    await motor.dispose()


async def obtener_o_crear_rol(sesion: AsyncSession, codigo: str) -> Rol:
    rol = await sesion.scalar(select(Rol).where(Rol.codigo == codigo))
    if rol is None:
        rol = Rol(codigo=codigo, nombre=codigo.title(), activo=True)
        sesion.add(rol)
        await sesion.flush()
    return rol


async def crear_usuario(
    sesion: AsyncSession,
    *,
    roles: tuple[str, ...] = ("USUARIO",),
    activo: bool = True,
    documento_identidad: str | None = None,
) -> Usuario:
    """Usuario de prueba con nombre único, contraseña conocida y los roles pedidos."""
    usuario = Usuario(
        usuario=f"prueba.{uuid.uuid4().hex[:10]}",
        contrasena_hash=HASH_CONTRASENA_CORRECTA,
        documento_identidad=documento_identidad,
        activo=activo,
    )
    sesion.add(usuario)
    await sesion.flush()
    for codigo in roles:
        rol = await obtener_o_crear_rol(sesion, codigo)
        sesion.add(UsuarioRoles(usuario_id=usuario.id, rol_id=rol.id))
    await sesion.flush()
    return usuario


async def iniciar_sesion(cliente_api, nombre_usuario: str, contrasena: str = CONTRASENA_CORRECTA):
    """
    Login completo como lo hace el navegador. Toda cuenta exige TOTP: si la cuenta aún no
    tiene autenticador, el primer paso responde 202 y aquí se completa la vinculación
    (QR + primer código) para obtener la sesión. Cualquier otra respuesta se devuelve tal cual.
    """
    # Como un navegador: el mismo agente en todas las peticiones (la sesión se crea al
    # final de la vinculación, no en el primer POST).
    cliente_api.headers["user-agent"] = "navegador-de-prueba"
    respuesta = await cliente_api.post(
        "/api/auth/login",
        json={"nombre_usuario": nombre_usuario, "contrasena": contrasena},
    )
    if respuesta.status_code == 202 and respuesta.json().get("configuracion_requerida"):
        respuesta = await completar_vinculacion(cliente_api, respuesta)
    return respuesta


@requiere_postgresql
async def test_login_correcto_crea_sesion_y_entrega_cookies(cliente_api, sesion_bd):
    documento = f"9{uuid.uuid4().int % 10**9:09d}"
    sesion_bd.add(
        PersonalMilitar(
            documento_identidad=documento,
            nombres="Juan Carlos",
            apellidos="Pérez Gómez",
            grado="MY",
            genero="M",
            categoria="OFICIAL",
        )
    )
    usuario = await crear_usuario(sesion_bd, documento_identidad=documento)

    respuesta = await iniciar_sesion(cliente_api, usuario.usuario.upper())

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["usuario"] == {
        "nombre_usuario": usuario.usuario,
        "nombre_completo": "MY Juan Carlos Pérez Gómez",
        "rol": "USUARIO",
        "requiere_cambio_contrasena": False,
    }
    segundos_inactividad = obtener_configuracion().minutos_inactividad_sesion * 60
    assert cuerpo["expira_por_inactividad_segundos"] == segundos_inactividad
    # Al vincular por primera vez se entregan, una sola vez, los 10 códigos de recuperación.
    assert len(cuerpo["codigos_recuperacion"]) == 10
    cookies = {c.split("=", 1)[0]: c.lower() for c in respuesta.headers.get_list("set-cookie")}
    assert "httponly" in cookies[NOMBRE_COOKIE_SESION] and "samesite=strict" in cookies[NOMBRE_COOKIE_SESION]
    assert "httponly" not in cookies[NOMBRE_COOKIE_CSRF]
    token = respuesta.cookies[NOMBRE_COOKIE_SESION]
    assert token not in respuesta.text

    datos_token = decodificar_token_sesion(token)
    assert datos_token.usuario_id == usuario.id
    sesion_guardada = await sesion_bd.get(SesionUsuario, datos_token.sesion_id)
    assert sesion_guardada is not None and sesion_guardada.revocada is False
    assert str(sesion_guardada.direccion_ip) == "127.0.0.1"
    assert sesion_guardada.agente_usuario == "navegador-de-prueba"
    await sesion_bd.refresh(usuario)
    assert usuario.ultimo_acceso_en is not None


@requiere_postgresql
async def test_usuario_sin_militar_asociado_muestra_su_nombre_de_usuario(cliente_api, sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    respuesta = await iniciar_sesion(cliente_api, usuario.usuario)
    assert respuesta.json()["usuario"]["nombre_completo"] == usuario.usuario


@requiere_postgresql
async def test_usuario_con_varios_roles_se_informa_como_administrador(cliente_api, sesion_bd):
    usuario = await crear_usuario(sesion_bd, roles=("USUARIO", "ADMINISTRADOR"))
    respuesta = await iniciar_sesion(cliente_api, usuario.usuario)
    assert respuesta.json()["usuario"]["rol"] == "ADMINISTRADOR"


@requiere_postgresql
@pytest.mark.parametrize("caso", ["contrasena_incorrecta", "inexistente", "inactivo", "sin_rol"])
async def test_login_fallido_da_siempre_el_mismo_error_y_no_crea_sesion(cliente_api, sesion_bd, caso):
    usuario = await crear_usuario(
        sesion_bd, activo=(caso != "inactivo"), roles=() if caso == "sin_rol" else ("USUARIO",)
    )
    nombre = "no.existe.nunca" if caso == "inexistente" else usuario.usuario
    contrasena = "Otra-Clave-2026" if caso == "contrasena_incorrecta" else CONTRASENA_CORRECTA
    sesiones_antes = await sesion_bd.scalar(select(func.count()).select_from(SesionUsuario))

    respuesta = await iniciar_sesion(cliente_api, nombre, contrasena)

    assert respuesta.status_code == 401, caso
    assert respuesta.json() == ERROR_CREDENCIALES
    assert "set-cookie" not in respuesta.headers
    assert await sesion_bd.scalar(select(func.count()).select_from(SesionUsuario)) == sesiones_antes


@requiere_postgresql
async def test_yo_devuelve_el_usuario_y_renueva_la_actividad(cliente_api, sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    respuesta_login = await iniciar_sesion(cliente_api, usuario.usuario)
    sesion_id = decodificar_token_sesion(respuesta_login.cookies[NOMBRE_COOKIE_SESION]).sesion_id
    actividad_antes = (await sesion_bd.get(SesionUsuario, sesion_id)).fecha_ultima_actividad

    respuesta = await cliente_api.get("/api/auth/yo")

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre_usuario"] == usuario.usuario
    assert respuesta.json()["rol"] == "USUARIO"
    # La malla de p0005 da a USUARIO acceso de consulta (detalle en test_menu_permisos_hu09.py).
    assert "PERSONAL_VERIFICAR" in respuesta.json()["permisos"]
    # HU-08: cada respuesta autenticada informa cuánto le queda a la sesión (contrato §1.4).
    assert respuesta.headers["X-Sesion-Expira-En"] == str(
        obtener_configuracion().minutos_inactividad_sesion * 60
    )
    await sesion_bd.refresh(await sesion_bd.get(SesionUsuario, sesion_id))
    assert (await sesion_bd.get(SesionUsuario, sesion_id)).fecha_ultima_actividad >= actividad_antes


@requiere_postgresql
async def test_sesion_inactiva_mas_de_30_minutos_expira_y_queda_revocada(cliente_api, sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    respuesta_login = await iniciar_sesion(cliente_api, usuario.usuario)
    sesion_id = decodificar_token_sesion(respuesta_login.cookies[NOMBRE_COOKIE_SESION]).sesion_id
    minutos = obtener_configuracion().minutos_inactividad_sesion
    await sesion_bd.execute(
        update(SesionUsuario)
        .where(SesionUsuario.id == sesion_id)
        .values(fecha_ultima_actividad=datetime.now(UTC) - timedelta(minutes=minutos + 1))
    )

    respuesta = await cliente_api.get("/api/auth/yo")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "SESION_EXPIRADA"
    assert "X-Sesion-Expira-En" not in respuesta.headers
    sesion_guardada = await sesion_bd.get(SesionUsuario, sesion_id)
    await sesion_bd.refresh(sesion_guardada)
    assert sesion_guardada.revocada is True and sesion_guardada.fecha_revocacion is not None


@requiere_postgresql
async def test_cerrar_sesion_revoca_y_el_token_deja_de_servir(cliente_api, sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    respuesta_login = await iniciar_sesion(cliente_api, usuario.usuario)
    token = respuesta_login.cookies[NOMBRE_COOKIE_SESION]
    valor_csrf = respuesta_login.cookies[NOMBRE_COOKIE_CSRF]

    respuesta = await cliente_api.post("/api/auth/cerrar-sesion", headers={NOMBRE_CABECERA_CSRF: valor_csrf})

    assert respuesta.status_code == 204
    sesion_guardada = await sesion_bd.get(SesionUsuario, decodificar_token_sesion(token).sesion_id)
    await sesion_bd.refresh(sesion_guardada)
    assert sesion_guardada.revocada is True
    # Aunque alguien haya copiado el token, ya no sirve.
    cliente_api.cookies.set(NOMBRE_COOKIE_SESION, token)
    assert (await cliente_api.get("/api/auth/yo")).status_code == 401


@requiere_postgresql
async def test_catalogos_responden_con_sesion_valida(cliente_api, sesion_bd):
    usuario = await crear_usuario(sesion_bd)
    await iniciar_sesion(cliente_api, usuario.usuario)
    respuesta = await cliente_api.get("/api/catalogos/unidades")
    assert respuesta.status_code == 200
    assert respuesta.headers["X-Sesion-Expira-En"] == str(
        obtener_configuracion().minutos_inactividad_sesion * 60
    )
    assert isinstance(respuesta.json(), list)


@requiere_postgresql
async def test_login_no_escribe_contrasena_ni_token_en_los_registros(cliente_api, sesion_bd, caplog):
    usuario = await crear_usuario(sesion_bd)
    with caplog.at_level(logging.DEBUG):
        respuesta = await iniciar_sesion(cliente_api, usuario.usuario)
    assert CONTRASENA_CORRECTA not in caplog.text
    assert respuesta.cookies[NOMBRE_COOKIE_SESION] not in caplog.text


@requiere_postgresql
async def test_administrador_inicial_se_crea_una_sola_vez_con_rol_administrador(sesion_bd):
    configuracion = obtener_configuracion()

    primera_vez = await asegurar_administrador_inicial(sesion_bd)
    segunda_vez = await asegurar_administrador_inicial(sesion_bd)

    assert segunda_vez is False
    administrador = await sesion_bd.scalar(
        select(Usuario).where(func.lower(Usuario.usuario) == configuracion.admin_usuario.lower())
    )
    assert administrador is not None
    if primera_vez:
        assert administrador.contrasena_hash == configuracion.admin_hash_contrasena.get_secret_value()
    roles = set(
        await sesion_bd.scalars(
            select(Rol.codigo)
            .join(UsuarioRoles, UsuarioRoles.rol_id == Rol.id)
            .where(UsuarioRoles.usuario_id == administrador.id)
        )
    )
    assert "ADMINISTRADOR" in roles
