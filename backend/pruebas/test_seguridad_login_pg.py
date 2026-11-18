"""Integración real solo en el clúster marcado creado por probar_seguridad_aislada."""

import asyncio
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aplicacion.modelos import IntentoInicioSesion, Rol, SesionUsuario, Usuario, UsuarioRoles
from aplicacion.modelos.seguridad import AuditoriaAcceso, EstadoAccesoAnonimo, LimiteInicioIP
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.contrasenas import generar_hash_contrasena
from aplicacion.seguridad.tokens import decodificar_token_sesion
from aplicacion.servicios import autenticacion, seguridad_login

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not os.environ.get("ESART_SEGURIDAD_TEST_URL"), reason="Solo clúster aislado marcado"),
]
CLAVE = "Clave-solo-integracion-HU06"
HASH = generar_hash_contrasena(CLAVE)


class VerificadorControlado:
    """Doble exclusivo de pruebas de CAPTCHA; las credenciales y JWT son reales."""

    async def verificar(self, identificador, respuesta, contexto):
        return identificador == "desafio-test" and respuesta == "respuesta-test"


@pytest.fixture
async def motores():
    url = os.environ["ESART_SEGURIDAD_TEST_URL"]
    u = make_url(url)
    datos = Path(os.environ["ESART_SEGURIDAD_TEST_DIR"]).resolve()
    raiz = Path(__file__).resolve().parents[1] / "respaldos"
    assert u.host == "127.0.0.1" and u.port != 5432 and u.database == "esart_db"
    assert datos.is_relative_to(raiz) and (datos.parent / "ESART_SOLO_PRUEBAS").is_file()
    admin = create_async_engine(
        os.environ["ESART_SEGURIDAD_TEST_ADMIN"], hide_parameters=True, connect_args={"ssl": False}
    )
    app = create_async_engine(url, hide_parameters=True, connect_args={"ssl": False})
    async with admin.connect() as c:
        from sqlalchemy import text

        assert Path(await c.scalar(text("SHOW data_directory"))).resolve() == datos
    try:
        yield admin, app
    finally:
        await admin.dispose()
        await app.dispose()


async def nuevo_usuario(admin):
    nombre = "hu06." + uuid.uuid4().hex
    async with AsyncSession(admin, expire_on_commit=False) as s:
        rol = await s.scalar(select(Rol).where(Rol.codigo == "USUARIO"))
        if rol is None:
            rol = Rol(codigo="USUARIO", nombre="Usuario", activo=True)
            s.add(rol)
            await s.flush()
        u = Usuario(usuario=nombre, contrasena_hash=HASH, activo=True)
        s.add(u)
        await s.flush()
        s.add(UsuarioRoles(usuario_id=u.id, rol_id=rol.id))
        await s.commit()
        return u.id, nombre


def ip():
    import ipaddress

    return str(ipaddress.IPv6Address(uuid.uuid4().int))


async def login(app, nombre, clave="incorrecta", direccion=None, captcha=True, completar=False):
    async with AsyncSession(app, expire_on_commit=False) as s:
        resultado = await autenticacion.iniciar_sesion(
            s,
            nombre,
            clave,
            direccion or ip(),
            None,
            "desafio-test" if captcha else None,
            "respuesta-test" if captcha else None,
            VerificadorControlado(),
        )
        if not completar:
            return resultado
        from urllib.parse import parse_qs, urlparse

        import pyotp

        from aplicacion.servicios.totp import TotpService

        servicio = TotpService(s)
        qr = await servicio.configurar_login(resultado.id, resultado.nonce, direccion or "127.0.0.1")
        secreto = parse_qs(urlparse(qr["uri"]).query)["secret"][0]
        usuario, _ = await servicio.vincular_login(
            resultado.id, resultado.nonce, pyotp.TOTP(secreto).now(), direccion or "127.0.0.1"
        )
        contexto = seguridad_login.ContextoIntento(
            seguridad_login.seudonimo("usuario", nombre.lower()),
            direccion,
            await seguridad_login.reloj_servidor(s),
            usuario=usuario,
            estado=usuario,
        )
        return await autenticacion.finalizar_login(s, usuario, direccion, None, contexto)


async def estado(admin, identificador):
    async with AsyncSession(admin) as s:
        u = await s.get(Usuario, identificador)
        return u.intentos_fallidos_consecutivos, u.bloqueado_hasta


async def test_umbral_septimo_bloqueo_y_no_prorroga(motores, monkeypatch):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    fin = None
    for numero in range(1, 8):
        with pytest.raises(ErrorAplicacion) as e:
            await login(app, nombre, captcha=True)
        fallos, fin = await estado(admin, identificador)
        assert fallos == numero
        assert e.value.detalle["captcha_requerido"] == (3 <= numero < 7)
        assert (fin is not None) == (numero == 7)
    async with AsyncSession(admin) as s:
        ahora = await seguridad_login.reloj_servidor(s)
        assert 10790 < (fin - ahora).total_seconds() <= 10800
    verificar = AsyncMock(side_effect=AssertionError("No verificar contraseña durante bloqueo"))
    monkeypatch.setattr(autenticacion, "verificar_contrasena", verificar)
    for _ in range(2):
        with pytest.raises(ErrorAplicacion):
            await login(app, nombre, CLAVE)
    assert await estado(admin, identificador) == (7, fin)
    verificar.assert_not_called()


@pytest.mark.parametrize("captcha", [False, "invalido"])
async def test_captcha_ausente_no_verifica_password(motores, monkeypatch, captcha):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    for _ in range(3):
        with pytest.raises(ErrorAplicacion):
            await login(app, nombre)
    verificar = AsyncMock(side_effect=AssertionError("No verificar credenciales antes de CAPTCHA"))
    monkeypatch.setattr(autenticacion, "verificar_contrasena", verificar)
    with pytest.raises(ErrorAplicacion):
        if captcha is False:
            await login(app, nombre, CLAVE, captcha=False)
        else:
            async with AsyncSession(app) as s:
                await autenticacion.iniciar_sesion(
                    s,
                    nombre,
                    CLAVE,
                    ip(),
                    None,
                    "desafio-test",
                    "respuesta-incorrecta",
                    VerificadorControlado(),
                )
    assert (await estado(admin, identificador))[0] == 3
    verificar.assert_not_called()


async def test_desbloqueo_exacto_y_jwt_roles_preservados(motores, monkeypatch):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    for _ in range(7):
        with pytest.raises(ErrorAplicacion):
            await login(app, nombre)
    _, fin = await estado(admin, identificador)

    async def reloj(_):
        return fin

    monkeypatch.setattr(seguridad_login, "reloj_servidor", reloj)
    resultado = await login(app, nombre, CLAVE, captcha=False, completar=True)
    assert decodificar_token_sesion(resultado.token_sesion).usuario_id == identificador
    assert resultado.rol == "USUARIO"
    assert await estado(admin, identificador) == (0, None)
    async with AsyncSession(admin) as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(AuditoriaAcceso)
                .join(IntentoInicioSesion, IntentoInicioSesion.id == AuditoriaAcceso.intento_id)
                .where(
                    IntentoInicioSesion.usuario_id == identificador,
                    AuditoriaAcceso.evento == "BLOQUEO_VENCIDO",
                )
            )
            == 1
        )


async def test_exito_reinicia_contador(motores):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    for _ in range(3):
        with pytest.raises(ErrorAplicacion):
            await login(app, nombre)
    await login(app, nombre, CLAVE, completar=True)
    assert await estado(admin, identificador) == (0, None)


async def test_concurrencia_y_varias_ips(motores):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    resultados = await asyncio.gather(*(login(app, nombre) for _ in range(7)), return_exceptions=True)
    assert all(isinstance(x, ErrorAplicacion) for x in resultados)
    assert (await estado(admin, identificador))[0] == 7
    async with AsyncSession(admin) as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(IntentoInicioSesion)
                .where(IntentoInicioSesion.usuario_id == identificador)
            )
            == 7
        )


async def test_ip_persistente_usuarios_inexistentes_y_auditoria(motores, monkeypatch):
    admin, app = motores
    cfg = autenticacion.obtener_configuracion()
    monkeypatch.setattr(cfg, "limite_intentos_ip", 7)
    direccion = ip()
    for _ in range(7):
        with pytest.raises(ErrorAplicacion):
            await login(app, "noexiste." + uuid.uuid4().hex, direccion=direccion)
    with pytest.raises(ErrorAplicacion) as e:
        await login(app, "noexiste." + uuid.uuid4().hex, direccion=direccion)
    assert e.value.estado_http == 429
    # Un pool nuevo lee la misma ventana; no hay contador local de proceso.
    from sqlalchemy.ext.asyncio import create_async_engine

    nuevo = create_async_engine(os.environ["ESART_SEGURIDAD_TEST_URL"], connect_args={"ssl": False})
    try:
        with pytest.raises(ErrorAplicacion) as e:
            await login(nuevo, "noexiste." + uuid.uuid4().hex, direccion=direccion)
        assert e.value.estado_http == 429
    finally:
        await nuevo.dispose()
    async with AsyncSession(admin) as s:
        clave = seguridad_login.seudonimo("ip", direccion)
        assert (await s.get(LimiteInicioIP, clave)).intentos == 7
        intentos = (
            await s.scalars(
                select(IntentoInicioSesion).where(IntentoInicioSesion.direccion_ip == cast(direccion, INET))
            )
        ).all()
        assert len(intentos) == 9 and all(len(i.nombre_usuario_intentado) == 64 for i in intentos)
        assert (
            await s.scalar(
                select(func.count())
                .select_from(AuditoriaAcceso)
                .join(IntentoInicioSesion, IntentoInicioSesion.id == AuditoriaAcceso.intento_id)
                .where(IntentoInicioSesion.direccion_ip == cast(direccion, INET))
            )
            == 9
        )


async def test_inexistente_mismo_bloqueo(motores):
    admin, app = motores
    nombre = "noexiste." + uuid.uuid4().hex
    for n in range(7):
        with pytest.raises(ErrorAplicacion) as e:
            await login(app, nombre)
        assert e.value.detalle["acceso_temporalmente_restringido"] == (n == 6)
        assert e.value.estado_http == (423 if n == 6 else 401)
    assert e.value.codigo == "CUENTA_BLOQUEADA"
    assert e.value.detalle["segundos_restantes"] == 10800
    assert "bloqueado_hasta" in e.value.detalle
    async with AsyncSession(admin) as s:
        anon = await s.get(EstadoAccesoAnonimo, seguridad_login.seudonimo("usuario", nombre))
        assert anon.intentos_fallidos_consecutivos == 7 and anon.bloqueado_hasta is not None


async def test_fallo_de_auditoria_revierte_y_no_emite_jwt(motores, monkeypatch):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    monkeypatch.setattr(
        seguridad_login, "registrar", AsyncMock(side_effect=RuntimeError("auditoria no disponible"))
    )
    with pytest.raises(RuntimeError):
        await login(app, nombre, CLAVE)
    assert await estado(admin, identificador) == (0, None)
    async with AsyncSession(admin) as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(SesionUsuario)
                .where(SesionUsuario.usuario_id == identificador)
            )
            == 0
        )


async def test_sesion_existente_no_accede_durante_bloqueo(motores):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    resultado = await login(app, nombre, CLAVE, completar=True)
    token = decodificar_token_sesion(resultado.token_sesion)
    for _ in range(7):
        with pytest.raises(ErrorAplicacion):
            await login(app, nombre)
    async with AsyncSession(app) as s:
        with pytest.raises(ErrorAplicacion) as error:
            await autenticacion.validar_sesion(s, identificador, token.sesion_id)
        assert error.value.estado_http == 401


async def test_reinicio_fastapi_y_cabeceras_no_confiables(motores):
    import httpx

    from aplicacion.base_datos.sesion import obtener_sesion_base_datos
    from aplicacion.principal import crear_aplicacion

    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    for _ in range(2):
        with pytest.raises(ErrorAplicacion):
            await login(app, nombre)
    reiniciado = create_async_engine(os.environ["ESART_SEGURIDAD_TEST_URL"], connect_args={"ssl": False})
    nueva_app = crear_aplicacion()

    async def entregar_sesion():
        async with AsyncSession(reiniciado, expire_on_commit=False) as s:
            yield s

    nueva_app.dependency_overrides[obtener_sesion_base_datos] = entregar_sesion
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=nueva_app), base_url="http://pruebas"
        ) as c:
            respuesta = await c.post(
                "/api/auth/login",
                json={"nombre_usuario": nombre, "contrasena": "incorrecta"},
                headers={"x-forwarded-for": "1.2.3.4"},
            )
            assert respuesta.status_code == 401
            assert respuesta.json()["error"]["detalle"]["captcha_requerido"] is True
        assert (await estado(admin, identificador))[0] == 3
        async with AsyncSession(admin) as s:
            ultimo = await s.scalar(
                select(IntentoInicioSesion)
                .where(IntentoInicioSesion.usuario_id == identificador)
                .order_by(IntentoInicioSesion.id.desc())
            )
            assert ultimo.direccion_ip is None
    finally:
        await reiniciado.dispose()


async def test_ventana_ip_vence_exactamente(motores, monkeypatch):
    admin, app = motores
    cfg = autenticacion.obtener_configuracion()
    monkeypatch.setattr(cfg, "limite_intentos_ip", 1)
    direccion = ip()
    with pytest.raises(ErrorAplicacion):
        await login(app, "ausente." + uuid.uuid4().hex, direccion=direccion)
    async with AsyncSession(admin) as s:
        limite = await s.get(LimiteInicioIP, seguridad_login.seudonimo("ip", direccion))
        from datetime import timedelta

        fin = limite.inicio + timedelta(seconds=cfg.ventana_intentos_ip_segundos)

    async def reloj(_):
        return fin

    monkeypatch.setattr(seguridad_login, "reloj_servidor", reloj)
    with pytest.raises(ErrorAplicacion) as error:
        await login(app, "ausente." + uuid.uuid4().hex, direccion=direccion)
    assert error.value.estado_http == 401
    async with AsyncSession(admin) as s:
        assert (await s.get(LimiteInicioIP, seguridad_login.seudonimo("ip", direccion))).intentos == 1


async def test_auditoria_solo_anexar_y_hash_roles_conservados(motores):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    with pytest.raises(ErrorAplicacion):
        await login(app, nombre)
    async with AsyncSession(app) as s:
        from sqlalchemy import text

        assert not await s.scalar(
            text("SELECT has_table_privilege(current_user,'esart.auditoria_acceso','UPDATE')")
        )
        assert not await s.scalar(
            text("SELECT has_table_privilege(current_user,'esart.auditoria_acceso','DELETE')")
        )
    async with AsyncSession(admin) as s:
        usuario = await s.get(Usuario, identificador)
        assert usuario.contrasena_hash == HASH and usuario.activo
        assert (
            await s.scalar(
                select(func.count()).select_from(UsuarioRoles).where(UsuarioRoles.usuario_id == identificador)
            )
            == 1
        )


async def test_http_real_login_cookie_y_sesion_actual(motores):
    import httpx

    from aplicacion.base_datos.sesion import obtener_sesion_base_datos
    from aplicacion.principal import crear_aplicacion
    from aplicacion.seguridad.sesion_http import NOMBRE_COOKIE_SESION

    admin, app = motores
    _, nombre = await nuevo_usuario(admin)
    api = crear_aplicacion()

    async def entregar_sesion():
        async with AsyncSession(app, expire_on_commit=False) as s:
            yield s

    api.dependency_overrides[obtener_sesion_base_datos] = entregar_sesion
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas") as c:
        respuesta = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        async with AsyncSession(admin) as s:
            from sqlalchemy import text

            esquema = await s.scalar(text("SELECT to_regclass('seguridad.usuario_totp')"))
        if esquema is None:
            assert respuesta.status_code == 503 and NOMBRE_COOKIE_SESION not in c.cookies
            assert (await c.get("/api/auth/yo")).status_code == 401
            return
        from pruebas.soporte_mfa import completar_vinculacion

        respuesta = await completar_vinculacion(c, respuesta)
        assert respuesta.status_code == 200
        assert respuesta.json()["usuario"]["rol"] == "USUARIO"
        token = respuesta.cookies[NOMBRE_COOKIE_SESION]
        assert token and token not in respuesta.text and CLAVE not in respuesta.text
        assert any("httponly" in h.lower() for h in respuesta.headers.get_list("set-cookie"))
        actual = await c.get("/api/auth/yo")
        assert actual.status_code == 200 and actual.json()["nombre_usuario"] == nombre
