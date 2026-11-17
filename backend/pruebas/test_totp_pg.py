"""TOTP real, solo contra el clúster aislado marcado del ejecutor."""

import asyncio
import base64
import os
import secrets
import sys
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pyotp
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import Usuario
from aplicacion.modelos.seguridad import SesionUsuario
from aplicacion.modelos.totp import AuditoriaSeguridad, DesafioTotp, UsuarioTotp
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.principal import crear_aplicacion
from aplicacion.servicios import totp
from pruebas.test_seguridad_login_pg import CLAVE, estado, nuevo_usuario
from pruebas.test_seguridad_login_pg import login as fallar_login
from pruebas.test_seguridad_login_pg import motores as fixture_motores

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not os.environ.get("ESART_SEGURIDAD_TEST_URL"), reason="Solo clúster aislado marcado"),
]


@pytest.fixture
async def motores():
    async for par in fixture_motores.__wrapped__():
        yield par


@pytest.fixture(autouse=True)
def habilitar(monkeypatch):
    cfg = obtener_configuracion()
    monkeypatch.setattr(cfg, "totp_habilitado", True)
    monkeypatch.setattr(
        cfg, "totp_clave_cifrado", SecretStr(base64.b64encode(secrets.token_bytes(32)).decode())
    )
    monkeypatch.setattr(cfg, "jwt_clave_secreta", SecretStr(secrets.token_urlsafe(48)))


def cliente(app):
    api = crear_aplicacion()

    async def entregar():
        async with AsyncSession(app, expire_on_commit=False) as s:
            yield s

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas")


async def vincular(admin, app):
    usuario_id, nombre = await nuevo_usuario(admin)
    c = cliente(app)
    acceso = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
    assert acceso.status_code == 202 and acceso.json()["configuracion_requerida"]
    assert "esart_sesion" not in c.cookies
    assert (await c.get("/api/auth/yo")).status_code == 401
    datos = {"desafio_id": acceso.json()["desafio_id"]}
    respuesta = await c.post("/api/v1/auth/totp/login/configurar", json=datos)
    assert respuesta.status_code == 200
    recuperada = await c.post("/api/v1/auth/totp/login/configurar", json=datos)
    assert recuperada.status_code == 200 and recuperada.json() == respuesta.json()
    rechazada = await c.post(
        "/api/v1/auth/totp/login/configurar", json={**datos, "usuario_id": usuario_id + 1}
    )
    assert rechazada.status_code == 422
    secreto = parse_qs(urlparse(respuesta.json()["uri"]).query)["secret"][0]
    async with AsyncSession(admin) as s:
        fila = await s.scalar(select(UsuarioTotp).where(UsuarioTotp.usuario_id == usuario_id))
        assert fila.estado == "PENDIENTE" and secreto not in fila.secreto_cifrado
        assert fila.secreto_cifrado.startswith("v1.")
    confirmar = await c.post(
        "/api/auth/totp/login/vincular", json={**datos, "codigo": pyotp.TOTP(secreto).now()}
    )
    assert confirmar.status_code == 200 and confirmar.json()["activo"]
    assert "esart_sesion" in c.cookies and len(confirmar.json()["codigos_recuperacion"]) == 10
    c.headers["X-CSRF-Token"] = c.cookies.get("esart_csrf")
    estado_publico = await c.get("/api/auth/totp/estado")
    assert set(estado_publico.json()) == {"configurado", "activo", "fecha_activacion"}
    return usuario_id, nombre, secreto, c


async def avanzar(admin, monkeypatch, segundos=30):
    async with AsyncSession(admin) as s:
        ahora = await s.scalar(select(func.clock_timestamp())) + timedelta(seconds=segundos)

    async def reloj(_):
        return ahora

    monkeypatch.setattr(totp, "reloj_servidor", reloj)
    return ahora


async def test_vinculacion_inicial_no_permite_acceso_ni_cookie_ajena(motores):
    admin, app = motores
    usuario_id, nombre = await nuevo_usuario(admin)
    async with cliente(app) as c, cliente(app) as ajeno:
        acceso = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        assert acceso.status_code == 202 and acceso.json()["configuracion_requerida"]
        datos = {"desafio_id": acceso.json()["desafio_id"]}
        assert (await ajeno.post("/api/auth/totp/login/configurar", json=datos)).status_code == 401
        qr = await c.post("/api/auth/totp/login/configurar", json=datos)
        assert qr.status_code == 200 and qr.headers["cache-control"] == "no-store"
        secreto = parse_qs(urlparse(qr.json()["uri"]).query)["secret"][0]
        codigo = pyotp.TOTP(secreto).now()
        assert (
            await ajeno.post("/api/auth/totp/login/vincular", json={**datos, "codigo": codigo})
        ).status_code == 401
        assert (
            await c.post("/api/auth/totp/login/confirmar", json={**datos, "codigo": codigo})
        ).status_code == 401
        assert (await c.get("/api/auth/yo")).status_code == 401
        assert (await c.get("/api/auth/totp/estado")).status_code == 401
        async with AsyncSession(admin) as s:
            assert not await s.scalar(
                select(func.count())
                .select_from(SesionUsuario)
                .where(
                    SesionUsuario.usuario_id == usuario_id,
                )
            )
        fin = await c.post("/api/auth/totp/login/vincular", json={**datos, "codigo": codigo})
        assert fin.status_code == 200
        assert (await c.get("/api/auth/yo")).status_code == 200
        assert (
            await c.post("/api/auth/totp/login/vincular", json={**datos, "codigo": codigo})
        ).status_code == 401


async def test_desafio_vinculacion_vencido_exige_otra_prueba_de_contrasena(motores, monkeypatch):
    admin, app = motores
    usuario_id, nombre = await nuevo_usuario(admin)
    async with cliente(app) as c:
        acceso = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        datos = {"desafio_id": acceso.json()["desafio_id"]}
        qr = await c.post("/api/auth/totp/login/configurar", json=datos)
        secreto = parse_qs(urlparse(qr.json()["uri"]).query)["secret"][0]
        await avanzar(admin, monkeypatch, 601)
        assert (await c.post("/api/auth/totp/login/configurar", json=datos)).status_code == 401
        assert (
            await c.post(
                "/api/auth/totp/login/vincular",
                json={
                    **datos,
                    "codigo": pyotp.TOTP(secreto).now(),
                },
            )
        ).status_code == 401
        assert (await c.get("/api/auth/yo")).status_code == 401
        async with AsyncSession(admin) as s:
            factor = await s.scalar(select(UsuarioTotp).where(UsuarioTotp.usuario_id == usuario_id))
            assert factor.estado == "PENDIENTE"


async def test_recuperacion_login_concurrente_y_revocacion_dispositivo_perdido(motores, monkeypatch):
    admin, app = motores
    usuario_id, nombre, secreto, configurador = await vincular(admin, app)
    ahora = await avanzar(admin, monkeypatch)
    lote = await configurador.post(
        "/api/auth/totp/recuperacion/renovar",
        json={
            "contrasena": CLAVE,
            "codigo": pyotp.TOTP(secreto).at(ahora),
        },
    )
    assert lote.status_code == 200 and lote.headers["cache-control"] == "no-store"
    codigos = lote.json()["codigos_recuperacion"]
    async with cliente(app) as origen:
        paso = await origen.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        assert paso.status_code == 202 and (await origen.get("/api/auth/yo")).status_code == 401
        datos = {"desafio_id": paso.json()["desafio_id"], "codigo": codigos[0], "recuperacion": True}

        async def completar():
            async with cliente(app) as c:
                c.cookies.update(origen.cookies)
                return (await c.post("/api/auth/totp/login/confirmar", json=datos)).status_code

        assert sorted(await asyncio.gather(completar(), completar())) == [200, 401]
        otro = await origen.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        datos["desafio_id"] = otro.json()["desafio_id"]
        assert (await origen.post("/api/auth/totp/login/confirmar", json=datos)).status_code == 401
    revocar = await configurador.post(
        "/api/auth/totp/recuperacion/revocar",
        json={
            "contrasena": CLAVE,
            "codigo": codigos[1],
        },
    )
    assert revocar.status_code == 200
    assert (await configurador.get("/api/auth/yo")).status_code == 401
    async with AsyncSession(admin) as s:
        assert not await s.scalar(
            select(func.count())
            .select_from(SesionUsuario)
            .where(
                SesionUsuario.usuario_id == usuario_id,
                SesionUsuario.revocada.is_(False),
            )
        )
    await configurador.aclose()


async def test_desactivar_servicio_no_omite_factor_de_cuenta_vinculada(motores, monkeypatch):
    admin, app = motores
    _, nombre, _, configurador = await vincular(admin, app)
    monkeypatch.setattr(obtener_configuracion(), "totp_habilitado", False)
    async with cliente(app) as c:
        respuesta = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        assert respuesta.status_code == 503 and "esart_sesion" not in c.cookies
        assert (await c.get("/api/auth/yo")).status_code == 401
    await configurador.aclose()


async def test_vinculacion_login_real_sin_jwt_antes_del_codigo(motores, monkeypatch):
    admin, app = motores
    usuario_id, nombre, secreto, configurador = await vincular(admin, app)
    ahora = await avanzar(admin, monkeypatch)
    async with cliente(app) as c:
        paso = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        assert paso.status_code == 202 and paso.json()["totp_requerido"]
        assert "esart_sesion" not in c.cookies and "usuario" not in paso.json()
        assert (await c.get("/api/auth/yo")).status_code == 401
        codigo = pyotp.TOTP(secreto).at(ahora)
        fin = await c.post(
            "/api/auth/totp/login/confirmar", json={"desafio_id": paso.json()["desafio_id"], "codigo": codigo}
        )
        assert fin.status_code == 200 and "esart_sesion" in c.cookies
        assert (await c.get("/api/auth/yo")).status_code == 200
        assert secreto not in fin.text and "token" not in fin.json()
        assert (await estado(admin, usuario_id)) == (0, None)
    await configurador.aclose()


async def test_codigo_y_desafio_no_reutilizables_concurrentemente(motores, monkeypatch):
    admin, app = motores
    usuario_id, nombre, secreto, configurador = await vincular(admin, app)
    ahora = await avanzar(admin, monkeypatch)
    async with cliente(app) as origen:
        paso = await origen.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        datos = {"desafio_id": paso.json()["desafio_id"], "codigo": pyotp.TOTP(secreto).at(ahora)}

        async def completar():
            async with cliente(app) as c:
                c.cookies.update(origen.cookies)
                return (await c.post("/api/auth/totp/login/confirmar", json=datos)).status_code

        assert sorted(await asyncio.gather(completar(), completar())) == [200, 401]
    async with AsyncSession(admin) as s:
        assert (
            await s.scalar(
                select(func.count()).select_from(SesionUsuario).where(SesionUsuario.usuario_id == usuario_id)
            )
            == 2
        )  # configuración y un único login 2FA
    await configurador.aclose()


async def test_otra_cookie_no_puede_usar_desafio_y_codigo_incorrecto(motores, monkeypatch):
    admin, app = motores
    _, nombre, secreto, configurador = await vincular(admin, app)
    ahora = await avanzar(admin, monkeypatch)
    async with cliente(app) as c:
        paso = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        datos = {"desafio_id": paso.json()["desafio_id"], "codigo": pyotp.TOTP(secreto).at(ahora)}
        async with cliente(app) as ajeno:
            assert (await ajeno.post("/api/auth/totp/login/confirmar", json=datos)).status_code == 401
        datos["codigo"] = "000000" if datos["codigo"] != "000000" else "111111"
        assert (await c.post("/api/auth/totp/login/confirmar", json=datos)).status_code == 401
        assert "esart_sesion" not in c.cookies
    await configurador.aclose()


async def test_desbloqueo_temprano_real_sin_emitir_jwt(motores, monkeypatch):
    admin, app = motores
    usuario_id, nombre, secreto, configurador = await vincular(admin, app)
    for _ in range(7):
        with pytest.raises(ErrorAplicacion):
            await fallar_login(app, nombre)
    assert (await estado(admin, usuario_id))[0] == 7
    ahora = await avanzar(admin, monkeypatch)
    async with cliente(app) as c:
        paso = await c.post("/api/auth/desbloqueo/solicitar", json={"nombre_usuario": nombre})
        assert paso.status_code == 202
        fin = await c.post(
            "/api/auth/desbloqueo/confirmar",
            json={"desafio_id": paso.json()["desafio_id"], "codigo": pyotp.TOTP(secreto).at(ahora)},
        )
        assert fin.status_code == 200 and "esart_sesion" not in c.cookies
    assert await estado(admin, usuario_id) == (0, None)
    async with AsyncSession(admin) as s:
        assert await s.scalar(
            select(AuditoriaSeguridad.id).where(
                AuditoriaSeguridad.usuario_id == usuario_id,
                AuditoriaSeguridad.accion == "CUENTA_DESBLOQUEADA_TOTP",
            )
        )
    await configurador.aclose()


async def test_sin_autenticador_y_cuenta_inexistente_son_indistinguibles(motores):
    admin, app = motores
    _, nombre = await nuevo_usuario(admin)
    async with cliente(app) as c:
        a = await c.post("/api/auth/desbloqueo/solicitar", json={"nombre_usuario": nombre})
        b = await c.post("/api/auth/desbloqueo/solicitar", json={"nombre_usuario": "noexiste.prueba"})
        assert a.status_code == b.status_code == 202 and a.json().keys() == b.json().keys()
        r = await c.post(
            "/api/auth/desbloqueo/confirmar", json={"desafio_id": b.json()["desafio_id"], "codigo": "000000"}
        )
        assert r.status_code == 401 and "esart_sesion" not in c.cookies


async def test_desactivacion_requiere_password_y_codigo_y_cancela_desafios(motores, monkeypatch):
    admin, app = motores
    _, nombre, secreto, c = await vincular(admin, app)
    ahora = await avanzar(admin, monkeypatch)
    async with cliente(app) as pendiente:
        paso = await pendiente.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        r = await c.post(
            "/api/auth/totp/desactivar", json={"contrasena": CLAVE, "codigo": pyotp.TOTP(secreto).at(ahora)}
        )
        assert r.status_code == 200 and r.json()["activo"] is False
        async with AsyncSession(admin) as s:
            import uuid

            assert (await s.get(DesafioTotp, uuid.UUID(paso.json()["desafio_id"]))).estado == "CANCELADO"
    await c.aclose()


async def test_pendiente_vencido_no_activa_y_auditoria_inmutable(motores, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    admin, app = motores
    usuario_id, _ = await nuevo_usuario(admin)
    async with AsyncSession(app, expire_on_commit=False) as s:
        r = await totp.TotpService(s).configurar(usuario_id, CLAVE, "127.0.0.1")
        secreto = parse_qs(urlparse(r["uri"]).query)["secret"][0]
    await avanzar(admin, monkeypatch, 601)
    async with AsyncSession(app, expire_on_commit=False) as s:
        from aplicacion.nucleo.errores import ErrorAplicacion

        with pytest.raises(ErrorAplicacion):
            await totp.TotpService(s).confirmar(usuario_id, pyotp.TOTP(secreto).now(), "127.0.0.1")
    async with AsyncSession(admin) as s:
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE seguridad.auditoria SET resultado='ALTERADO'"))


async def test_navegador_real_qr_y_login_2fa(motores):
    from herramientas.probar_flujo_publico_navegador import ejecutar

    admin, _ = motores
    usuario_id, nombre = await nuevo_usuario(admin)
    clave = obtener_configuracion().totp_clave_cifrado.get_secret_value()
    resultado = await asyncio.to_thread(ejecutar, nombre, "totp", clave, CLAVE)
    assert resultado["qr_local_valido"] and resultado["sin_jwt_antes_de_totp"]
    assert resultado["primer_factor_2fa"] == 202 and resultado["segundo_factor"] == 200
    async with AsyncSession(admin) as s:
        factor = await s.scalar(select(UsuarioTotp).where(UsuarioTotp.usuario_id == usuario_id))
        assert factor.estado == "ACTIVO" and factor.secreto_cifrado.startswith("v1.")
        assert (
            await s.scalar(
                select(func.count())
                .select_from(SesionUsuario)
                .where(SesionUsuario.usuario_id == usuario_id, SesionUsuario.revocada.is_(False))
            )
            == 1
        )


async def test_navegador_real_desbloqueo_totp_sin_sesion(motores):
    from herramientas.probar_flujo_publico_navegador import ejecutar

    admin, app = motores
    usuario_id, nombre, secreto, configurador = await vincular(admin, app)
    clave = obtener_configuracion().totp_clave_cifrado.get_secret_value()
    try:
        resultado = await asyncio.to_thread(ejecutar, nombre, "desbloqueo", clave, CLAVE, secreto)
        assert resultado["bloqueo_septimo"] == 423 and resultado["desbloqueo"] == 200
        assert resultado["sin_jwt"]
        assert await estado(admin, usuario_id) == (0, None)
    finally:
        await configurador.aclose()


async def preparar_accion_prueba(admin, app, monkeypatch):
    """Adaptador de infraestructura sobre un registro aislado, no CRUD académico ficticio."""
    import uuid
    from datetime import UTC, datetime

    from aplicacion.modelos.totp import PoliticaAccion
    from aplicacion.servicios.autorizacion_acciones import ADAPTADORES, AdaptadorAccion

    actor_id, _, secreto, c = await vincular(admin, app)
    recurso_id, _ = await nuevo_usuario(admin)
    codigo = "PRUEBA_" + uuid.uuid4().hex
    async with AsyncSession(admin) as s:
        s.add(
            PoliticaAccion(
                codigo=codigo,
                nombre="Recurso de prueba transaccional",
                modulo="PRUEBAS",
                permiso_requerido="PRUEBA_RECURSO",
                requiere_totp=True,
                activa=True,
            )
        )
        await s.commit()
    control = {"permitido": True, "fallar": False}

    async def permitir(_, identidad):
        return identidad.id == actor_id and control["permitido"]

    async def preparar(s, identificador, _):
        assert int(identificador) == recurso_id
        usuario = await s.scalar(
            select(Usuario)
            .where(Usuario.id == recurso_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {
            "version": usuario.actualizado_en.isoformat(),
            "valor": usuario.ultimo_acceso_en.isoformat() if usuario.ultimo_acceso_en else None,
        }

    async def ejecutar(s, identificador, datos):
        usuario = await s.get(Usuario, int(identificador))
        anterior = usuario.ultimo_acceso_en.isoformat() if usuario.ultimo_acceso_en else None
        usuario.ultimo_acceso_en = datetime.fromisoformat(datos["valor"])
        await s.flush()
        if control["fallar"]:
            raise RuntimeError("Fallo transaccional de prueba")
        return {
            "resultado": {"actualizado": True},
            "cambios": {"ultimo_acceso_en": (anterior, usuario.ultimo_acceso_en.isoformat())},
        }

    monkeypatch.setitem(
        ADAPTADORES,
        codigo,
        AdaptadorAccion(
            "PRUEBA", "PRUEBA_RECURSO", permitir, preparar, ejecutar, frozenset({"ultimo_acceso_en"})
        ),
    )
    operacion = {
        "codigo_politica": codigo,
        "recurso_id": str(recurso_id),
        "datos": {"valor": datetime.now(UTC).isoformat()},
    }
    return recurso_id, secreto, c, operacion, control


async def autorizar_prueba(admin, monkeypatch, c, secreto, operacion):
    ahora = await avanzar(admin, monkeypatch)
    creado = await c.post("/api/v1/seguridad/desafios", json=operacion)
    assert creado.status_code == 200
    autorizado = await c.post(
        f"/api/seguridad/desafios/{creado.json()['desafio_id']}/verificar",
        json={**operacion, "codigo": pyotp.TOTP(secreto).at(ahora)},
    )
    assert autorizado.status_code == 200
    return autorizado.json()["autorizacion_id"]


async def test_autorizacion_consumo_y_mutacion_atomicos_con_rollback(motores, monkeypatch):
    import uuid

    from aplicacion.modelos.totp import AutorizacionTotp, CambioSeguridad

    admin, app = motores
    recurso_id, secreto, c, operacion, control = await preparar_accion_prueba(admin, app, monkeypatch)
    try:
        identificador = await autorizar_prueba(admin, monkeypatch, c, secreto, operacion)
        control["fallar"] = True
        with pytest.raises(RuntimeError):
            await c.post(f"/api/seguridad/autorizaciones/{identificador}/ejecutar", json=operacion)
        async with AsyncSession(admin) as s:
            assert (await s.get(Usuario, recurso_id)).ultimo_acceso_en is None
            assert (await s.get(AutorizacionTotp, uuid.UUID(identificador))).resultado == "AUTORIZADA"
        control["fallar"] = False
        correcto = await c.post(f"/api/seguridad/autorizaciones/{identificador}/ejecutar", json=operacion)
        assert correcto.status_code == 200 and correcto.json()["actualizado"]
        assert (
            await c.post(f"/api/seguridad/autorizaciones/{identificador}/ejecutar", json=operacion)
        ).status_code == 409
        async with AsyncSession(admin) as s:
            assert (await s.get(AutorizacionTotp, uuid.UUID(identificador))).resultado == "CONSUMIDA"
            assert await s.scalar(
                select(CambioSeguridad.id)
                .join(AuditoriaSeguridad, CambioSeguridad.auditoria_id == AuditoriaSeguridad.id)
                .where(AuditoriaSeguridad.autorizacion_id == uuid.UUID(identificador))
            )
    finally:
        await c.aclose()


async def test_recurso_o_permisos_cambiados_invalidan_autorizacion(motores, monkeypatch):
    from datetime import UTC, datetime

    admin, app = motores
    recurso_id, secreto, c, operacion, control = await preparar_accion_prueba(admin, app, monkeypatch)
    try:
        identificador = await autorizar_prueba(admin, monkeypatch, c, secreto, operacion)
        control["permitido"] = False
        assert (
            await c.post(f"/api/seguridad/autorizaciones/{identificador}/ejecutar", json=operacion)
        ).status_code == 403
        control["permitido"] = True
        async with AsyncSession(admin) as s:
            (await s.get(Usuario, recurso_id)).ultimo_acceso_en = datetime.now(UTC)
            await s.commit()
        assert (
            await c.post(f"/api/seguridad/autorizaciones/{identificador}/ejecutar", json=operacion)
        ).status_code == 409
    finally:
        await c.aclose()


async def test_politica_academica_sin_adaptador_no_simula_operacion(motores):
    admin, app = motores
    _, _, _, c = await vincular(admin, app)
    try:
        r = await c.post(
            "/api/seguridad/desafios",
            json={"codigo_politica": "CURSO_APROBAR", "recurso_id": "1", "datos": {}},
        )
        assert r.status_code == 501 and r.json()["error"]["codigo"] == "OPERACION_NO_INTEGRADA"
    finally:
        await c.aclose()


@pytest.mark.parametrize("averia", ["disponibilidad", "auditoria_sql"])
async def test_bloqueo_persiste_aunque_falle_integracion_totp(motores, monkeypatch, averia):
    """Regresión: antes del arreglo devuelve 503 o revierte el contador por error SQL."""
    from aplicacion.servicios import captcha_local

    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    emitidos = []
    generar = captcha_local.generar_texto

    def capturar():
        codigo = generar()
        emitidos.append(codigo)
        return codigo

    monkeypatch.setattr(captcha_local, "generar_texto", capturar)
    if averia == "disponibilidad":

        async def no_disponible(self):
            raise ErrorAplicacion(503, "TOTP_NO_DISPONIBLE", "Servicio no disponible.")

        monkeypatch.setattr(totp.TotpService, "preparar", no_disponible)
    else:

        async def error_sql(self, *args, **kwargs):
            await self.sesion.execute(text("SELECT 1/0"))

        monkeypatch.setattr(totp.TotpService, "auditar", error_sql)
    fin = None
    async with cliente(app) as c:
        for numero in range(1, 8):
            datos = {"nombre_usuario": nombre, "contrasena": "incorrecta-solo-prueba"}
            if numero >= 4:
                reto = await c.get("/api/auth/captcha", headers={"X-ESART-Usuario": nombre})
                assert reto.status_code == 200
                datos.update(captcha_id=reto.json()["captcha_id"], captcha_respuesta=emitidos[-1])
            r = await c.post("/api/auth/login", json=datos)
            assert r.status_code == (423 if numero == 7 else 401)
            contador, fin = await estado(admin, identificador)
            assert contador == numero and (fin is not None) == (numero == 7)
            if numero == 1 and averia == "disponibilidad":
                correcto = await c.post(
                    "/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE}
                )
                assert correcto.status_code == 503 and "esart_sesion" not in c.cookies
                assert await estado(admin, identificador) == (1, None)
        bloqueada = await c.post("/api/v1/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        assert bloqueada.status_code == 423
        assert await estado(admin, identificador) == (7, fin)
    async with AsyncSession(admin) as s:
        from aplicacion.modelos import IntentoInicioSesion
        from aplicacion.modelos.seguridad import AuditoriaAcceso

        assert (
            await s.scalar(
                select(func.count())
                .select_from(AuditoriaAcceso)
                .join(IntentoInicioSesion, IntentoInicioSesion.id == AuditoriaAcceso.intento_id)
                .where(IntentoInicioSesion.usuario_id == identificador)
            )
            == 8
        )
        ahora = await s.scalar(select(func.clock_timestamp()))
        assert 10780 < (fin - ahora).total_seconds() <= 10800


async def test_contadores_contrasena_y_totp_independientes(motores, monkeypatch):
    from aplicacion.servicios import captcha_local

    admin, app = motores
    identificador, nombre, secreto, configurador = await vincular(admin, app)
    for _ in range(3):
        with pytest.raises(ErrorAplicacion):
            await fallar_login(app, nombre)
    emitidos = []
    original = captcha_local.generar_texto

    def capturar():
        valor = original()
        emitidos.append(valor)
        return valor

    monkeypatch.setattr(captcha_local, "generar_texto", capturar)
    ahora = await avanzar(admin, monkeypatch)
    async with cliente(app) as c:
        sin_captcha = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        assert sin_captcha.status_code == 401 and sin_captcha.json()["error"]["codigo"] == "CAPTCHA_INVALIDO"
        assert await estado(admin, identificador) == (3, None)
        reto = await c.get("/api/auth/captcha", headers={"X-ESART-Usuario": nombre})
        paso = await c.post(
            "/api/auth/login",
            json={
                "nombre_usuario": nombre,
                "contrasena": CLAVE,
                "captcha_id": reto.json()["captcha_id"],
                "captcha_respuesta": emitidos[-1],
            },
        )
        assert paso.status_code == 202
        assert await estado(admin, identificador) == (3, None)
        codigo = pyotp.TOTP(secreto).at(ahora)
        incorrecto = "000000" if codigo != "000000" else "111111"
        rechazo = await c.post(
            "/api/auth/totp/login/confirmar",
            json={
                "desafio_id": paso.json()["desafio_id"],
                "codigo": incorrecto,
            },
        )
        assert rechazo.status_code == 401 and await estado(admin, identificador) == (3, None)
        aceptado = await c.post(
            "/api/auth/totp/login/confirmar",
            json={
                "desafio_id": paso.json()["desafio_id"],
                "codigo": codigo,
            },
        )
        assert aceptado.status_code == 200 and await estado(admin, identificador) == (0, None)
    await configurador.aclose()


async def test_bloqueo_recuperado_por_otro_proceso_fastapi(motores):
    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    for _ in range(7):
        with pytest.raises(ErrorAplicacion):
            await fallar_login(app, nombre)
    contador, fin = await estado(admin, identificador)
    assert contador == 7 and fin is not None
    # Otro intérprete, aplicación y pool: no hereda objetos ni contadores de Python.
    programa = """
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from pruebas.test_totp_pg import cliente, CLAVE
async def main():
    motor = create_async_engine(os.environ['ESART_SEGURIDAD_TEST_URL'],
        hide_parameters=True, connect_args={'ssl':False})
    try:
        async with cliente(motor) as c:
            r = await c.post('/api/auth/login', json={
                'nombre_usuario':os.environ['ESART_PRUEBA_NOMBRE'], 'contrasena':CLAVE})
            assert r.status_code == 423 and 'esart_sesion' not in c.cookies
            print('BLOQUEO_PERSISTENTE_423')
    finally:
        await motor.dispose()
asyncio.run(main())
"""
    proceso = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        programa,
        env={**os.environ, "ESART_PRUEBA_NOMBRE": nombre},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    salida, _ = await asyncio.wait_for(proceso.communicate(), timeout=30)
    assert proceso.returncode == 0 and b"BLOQUEO_PERSISTENTE_423" in salida
    assert await estado(admin, identificador) == (7, fin)
