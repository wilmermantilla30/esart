"""CAPTCHA real en la instancia marcada, misma fuente de estado para procesos distintos."""

import asyncio
import base64
import json
import os
import sys
import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos.seguridad import AuditoriaAcceso, DesafioCaptcha
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import captcha_local as captcha
from aplicacion.servicios import seguridad_login
from pruebas.test_seguridad_login_pg import CLAVE, estado, ip, nuevo_usuario
from pruebas.test_seguridad_login_pg import login as login_credenciales
from pruebas.test_seguridad_login_pg import motores as fixture_motores

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not os.environ.get("ESART_SEGURIDAD_TEST_URL"), reason="Solo clúster aislado marcado"),
]


@pytest.fixture
async def motores():
    async for par in fixture_motores.__wrapped__():
        yield par


@pytest.fixture
def emitidos(monkeypatch):
    valores = []
    original = captcha.generar_texto

    def capturar():
        texto = original()
        valores.append(texto)
        return texto

    monkeypatch.setattr(captcha, "generar_texto", capturar)
    return valores


async def emitir(app, nombre, anterior=None, direccion=None):
    async with AsyncSession(app, expire_on_commit=False) as s:
        return await captcha.generar(s, nombre, direccion or ip(), anterior)


async def consumir(app, reto, respuesta, nombre):
    async with AsyncSession(app) as s:
        contexto = seguridad_login.seudonimo("usuario", nombre.lower())
        resultado = await captcha.CaptchaPostgres(s).verificar(reto["captcha_id"], respuesta, contexto)
        await s.commit()
        return resultado


async def test_emitir_png_hash_privacidad_y_consumo(motores, emitidos):
    admin, app = motores
    nombre = "captcha." + uuid.uuid4().hex
    reto = await emitir(app, nombre)
    codigo = emitidos[-1]
    assert set(reto) == {"captcha_id", "imagen_png_base64", "expira_en", "longitud"}
    assert len(reto["captcha_id"]) == 43 and codigo not in json.dumps(reto, default=str)
    assert base64.b64decode(reto["imagen_png_base64"]).startswith(b"\x89PNG")
    async with AsyncSession(admin) as s:
        registro = await s.get(DesafioCaptcha, reto["captcha_id"])
        assert len(registro.respuesta_hmac) == 64 and registro.respuesta_hmac != codigo
        assert registro.expira_en - registro.creado_en == timedelta(minutes=5)
    assert await consumir(app, reto, codigo.lower(), nombre)
    assert not await consumir(app, reto, codigo, nombre)


async def test_respuesta_erronea_consume_y_contexto_no_coincidente_no_valida(motores, emitidos):
    _, app = motores
    nombre = "captcha." + uuid.uuid4().hex
    reto = await emitir(app, nombre)
    codigo = emitidos[-1]
    assert not await consumir(app, reto, codigo, "otra-cuenta")
    assert not await consumir(app, reto, "XXXXXX", nombre)
    assert not await consumir(app, reto, codigo, nombre)
    assert not await consumir(app, {"captcha_id": "a" * 43}, codigo, nombre)


async def test_expiracion_exacta(motores, emitidos, monkeypatch):
    _, app = motores
    nombre = "captcha." + uuid.uuid4().hex
    reto = await emitir(app, nombre)
    codigo = emitidos[-1]

    async def reloj(_):
        return reto["expira_en"]

    monkeypatch.setattr(captcha, "reloj_servidor", reloj)
    assert not await consumir(app, reto, codigo, nombre)


async def test_regenerar_invalida_anterior_y_concurrencia(motores, emitidos):
    _, app = motores
    nombre = "captcha." + uuid.uuid4().hex
    inicial = await emitir(app, nombre)
    viejo = emitidos[-1]
    nuevo = await emitir(app, nombre, inicial["captcha_id"])
    correcto = emitidos[-1]
    assert nuevo["captcha_id"] != inicial["captcha_id"]
    assert not await consumir(app, inicial, viejo, nombre)
    resultados = await asyncio.gather(*(consumir(app, nuevo, correcto, nombre) for _ in range(2)))
    assert sorted(resultados) == [False, True]


async def test_regeneracion_simultanea_solo_un_sucesor(motores, emitidos):
    _, app = motores
    nombre = "captcha." + uuid.uuid4().hex
    inicial = await emitir(app, nombre)
    resultados = await asyncio.gather(
        *(emitir(app, nombre, inicial["captcha_id"]) for _ in range(2)), return_exceptions=True
    )
    assert sum(isinstance(r, dict) for r in resultados) == 1
    assert sum(isinstance(r, ErrorAplicacion) and r.estado_http == 409 for r in resultados) == 1


async def test_limite_generacion_y_auditoria(motores, emitidos, monkeypatch):
    admin, app = motores
    cfg = captcha.obtener_configuracion()
    monkeypatch.setattr(cfg, "limite_generacion_captcha_ip", 1)
    nombre = "captcha." + uuid.uuid4().hex
    direccion = ip()
    reto = await emitir(app, nombre, direccion=direccion)
    with pytest.raises(ErrorAplicacion) as error:
        # El presupuesto es de la IP, no del nombre proporcionado por el cliente.
        await emitir(app, nombre + ".otro", direccion=direccion)
    assert error.value.estado_http == 429
    async with AsyncSession(admin) as s:
        assert (
            await s.scalars(
                select(AuditoriaAcceso.evento).where(AuditoriaAcceso.captcha_id == reto["captcha_id"])
            )
        ).all() == ["CAPTCHA_EMITIDO"]
        assert await s.scalar(
            select(AuditoriaAcceso.id).where(AuditoriaAcceso.evento == "CAPTCHA_IP_LIMITADA")
        )


async def test_consumo_desde_dos_procesos(motores, emitidos):
    _, app = motores
    nombre = "captcha." + uuid.uuid4().hex
    reto = await emitir(app, nombre)
    entorno = os.environ.copy()
    entorno["ESART_RETO_TEST"] = reto["captcha_id"]
    entorno["ESART_RESPUESTA_TEST"] = emitidos[-1]
    entorno["ESART_CONTEXTO_TEST"] = seguridad_login.seudonimo("usuario", nombre)
    programa = """
import asyncio,os
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession
from aplicacion.servicios.captcha_local import CaptchaPostgres
async def main():
 e=create_async_engine(os.environ['ESART_SEGURIDAD_TEST_URL'],hide_parameters=True,connect_args={'ssl':False})
 async with AsyncSession(e) as s:
  r=await CaptchaPostgres(s).verificar(
   os.environ['ESART_RETO_TEST'],os.environ['ESART_RESPUESTA_TEST'],os.environ['ESART_CONTEXTO_TEST'])
  await s.commit()
  print('ACEPTADO' if r else 'RECHAZADO')
 await e.dispose()
asyncio.run(main())
"""

    async def worker():
        p = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            programa,
            env=entorno,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        salida, _ = await p.communicate()
        assert p.returncode == 0
        return salida.decode().strip()

    assert sorted(await asyncio.gather(worker(), worker())) == ["ACEPTADO", "RECHAZADO"]


async def test_http_integrado_desde_cuarto_intento_sin_dobles_de_captcha(motores, emitidos):
    from aplicacion.base_datos.sesion import obtener_sesion_base_datos
    from aplicacion.principal import crear_aplicacion

    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    api = crear_aplicacion()

    async def entregar():
        async with AsyncSession(app, expire_on_commit=False) as s:
            yield s

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas") as c:
        for _ in range(3):
            r = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": "incorrecta"})
            assert r.status_code == 401
        assert r.json()["error"]["detalle"]["captcha_requerido"]
        desafio = await c.get("/api/auth/captcha", headers={"X-ESART-Usuario": nombre})
        assert desafio.status_code == 200 and desafio.headers["cache-control"] == "no-store"
        contenido = desafio.json()
        codigo = emitidos[-1]
        fallo = await c.post(
            "/api/auth/login",
            json={
                "nombre_usuario": nombre,
                "contrasena": CLAVE,
                "captcha_id": contenido["captcha_id"],
                "captcha_respuesta": "XXXXXX",
            },
        )
        assert fallo.status_code == 401 and (await estado(admin, identificador))[0] == 4
        nuevo = await c.get("/api/auth/captcha", headers={"X-ESART-Usuario": nombre})
        codigo = emitidos[-1]
        bien = await c.post(
            "/api/auth/login",
            json={
                "nombre_usuario": nombre,
                "contrasena": CLAVE,
                "captcha_id": nuevo.json()["captcha_id"],
                "captcha_respuesta": codigo.lower(),
            },
        )
        assert bien.status_code == 200 and bien.headers["cache-control"] == "no-store"
        assert (await estado(admin, identificador)) == (0, None)
        assert codigo not in bien.text and "esart_sesion" in bien.cookies


async def test_septimo_fallo_con_captcha_real_bloquea_tres_horas(motores, emitidos):
    from aplicacion.base_datos.sesion import obtener_sesion_base_datos
    from aplicacion.principal import crear_aplicacion

    admin, app = motores
    identificador, nombre = await nuevo_usuario(admin)
    api = crear_aplicacion()

    async def entregar():
        async with AsyncSession(app, expire_on_commit=False) as s:
            yield s

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://pruebas") as c:
        for numero in range(1, 8):
            datos = {"nombre_usuario": nombre, "contrasena": "incorrecta"}
            if numero >= 4:
                reto = await c.get("/api/auth/captcha", headers={"X-ESART-Usuario": nombre})
                assert reto.status_code == 200
                datos.update(captcha_id=reto.json()["captcha_id"], captcha_respuesta=emitidos[-1])
            rechazo = await c.post("/api/auth/login", json=datos)
            assert rechazo.status_code == (423 if numero == 7 else 401)
            assert (await estado(admin, identificador))[0] == numero
        contador, bloqueo = await estado(admin, identificador)
        from sqlalchemy import func

        async with AsyncSession(admin) as s:
            ahora = await s.scalar(select(func.clock_timestamp()))
        assert contador == 7 and timedelta(hours=2, minutes=59) < bloqueo - ahora <= timedelta(hours=3)
        bloqueado = await c.post("/api/auth/login", json={"nombre_usuario": nombre, "contrasena": CLAVE})
        assert bloqueado.status_code == 423 and "esart_sesion" not in bloqueado.cookies
        assert (await estado(admin, identificador)) == (7, bloqueo)
        # Un navegador nuevo conserva solo el comprobante HttpOnly, no un contador local.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://pruebas", cookies=c.cookies
        ) as recargado:
            recuperado = await recargado.get("/api/auth/bloqueo")
            assert recuperado.status_code == 200
            datos = recuperado.json()
            assert datos["bloqueado"] is True
            assert datos["bloqueado_hasta"] == bloqueo.isoformat()
            assert datos["intentos_fallidos_consecutivos"] is None
            assert datos["direccion_ip"] is None
            assert (await estado(admin, identificador)) == (7, bloqueo)
            protegido = await recargado.get(f"/api/auth/administracion/bloqueos/{identificador}")
            assert protegido.status_code == 401
        from types import SimpleNamespace

        from aplicacion.seguridad.sesion_http import obtener_usuario_actual

        api.dependency_overrides[obtener_usuario_actual] = lambda: SimpleNamespace(rol="USUARIO")
        assert (await c.get(f"/api/auth/administracion/bloqueos/{identificador}")).status_code == 403
        api.dependency_overrides[obtener_usuario_actual] = lambda: SimpleNamespace(rol="ADMINISTRADOR")
        lectura = await c.get(f"/api/auth/administracion/bloqueos/{identificador}")
        assert lectura.status_code == 200
        assert lectura.json()["intentos_fallidos_consecutivos"] == 7
        assert lectura.json()["detalles_autorizados"] is True
        assert lectura.json()["usuario_intentado"] == nombre
        assert lectura.json()["direccion_ip"] == "127.0.0.1"
        assert lectura.json()["ip_es_loopback"] is True
        assert lectura.json()["ip_terminal_verificada"] is False


async def test_registro_terminal_con_sesion_jwt_administrativa_real(motores):
    from pathlib import Path

    from sqlalchemy import func

    from aplicacion.base_datos.sesion import obtener_sesion_base_datos
    from aplicacion.modelos import IntentoInicioSesion, Rol, UsuarioRoles
    from aplicacion.principal import crear_aplicacion

    admin, app = motores
    objetivo_id, objetivo = await nuevo_usuario(admin)
    operador_id, operador = await nuevo_usuario(admin)
    _, ordinario = await nuevo_usuario(admin)
    async with AsyncSession(admin) as s:
        rol = await s.scalar(select(Rol).where(Rol.codigo == "ADMINISTRADOR"))
        if rol is None:
            rol = Rol(codigo="ADMINISTRADOR", nombre="Administrador", activo=True)
            s.add(rol)
            await s.flush()
        s.add(UsuarioRoles(usuario_id=operador_id, rol_id=rol.id))
        await s.commit()
    api = crear_aplicacion()

    async def entregar():
        async with AsyncSession(app, expire_on_commit=False) as s:
            yield s

    api.dependency_overrides[obtener_sesion_base_datos] = entregar
    transporte = httpx.ASGITransport(app=api)
    async with httpx.AsyncClient(transport=transporte, base_url="http://pruebas") as c:
        for numero in range(1, 8):
            datos = {"nombre_usuario": objetivo, "contrasena": "incorrecta"}
            if numero >= 4:
                reto = await c.get("/api/auth/captcha", headers={"X-ESART-Usuario": objetivo})
                assert reto.status_code == 200
                datos.update(captcha_id=reto.json()["captcha_id"], captcha_respuesta="!!!!!!")
            respuesta = await c.post("/api/auth/login", json=datos)
            assert respuesta.status_code == (423 if numero == 7 else 401)
        assert (await c.get(f"/api/auth/administracion/bloqueos/{objetivo_id}")).status_code == 401
        publico = (await c.get("/api/auth/bloqueo")).json()
        assert publico["intentos_fallidos_consecutivos"] is None and publico["direccion_ip"] is None
    ruta = f"/api/auth/administracion/bloqueos/{objetivo_id}"
    async with httpx.AsyncClient(transport=transporte, base_url="http://pruebas") as c:
        assert (
            await c.post("/api/auth/login", json={"nombre_usuario": ordinario, "contrasena": CLAVE})
        ).status_code == 200
        assert (await c.get(ruta)).status_code == 403
    async with httpx.AsyncClient(transport=transporte, base_url="http://pruebas") as c:
        login = await c.post("/api/auth/login", json={"nombre_usuario": operador, "contrasena": CLAVE})
        assert login.status_code == 200 and login.json()["usuario"]["rol"] == "ADMINISTRADOR"
        respuesta = await c.get(ruta)
        assert respuesta.status_code == 200 and respuesta.headers["cache-control"] == "no-store"
        datos = respuesta.json()
        assert datos["intentos_fallidos_consecutivos"] == 7 and datos["detalles_autorizados"] is True
        assert datos["direccion_ip"] == "127.0.0.1" and datos["ip_es_loopback"] is True
        assert datos["ip_terminal_verificada"] is False
    async with AsyncSession(admin) as s:
        real = await estado(admin, objetivo_id)
        ultimo = (
            await s.execute(
                select(
                    func.host(IntentoInicioSesion.direccion_ip),
                    IntentoInicioSesion.fecha,
                    IntentoInicioSesion.motivo_fallo,
                )
                .where(IntentoInicioSesion.usuario_id == objetivo_id)
                .order_by(IntentoInicioSesion.fecha.desc(), IntentoInicioSesion.id.desc())
                .limit(1)
            )
        ).one()
        assert real[0] == datos["intentos_fallidos_consecutivos"]
        assert real[1].isoformat() == datos["bloqueado_hasta"]
        assert ultimo[0] == datos["direccion_ip"] and ultimo[2] == datos["motivo_ultimo_intento"]
    # Solo datos autorizados de cuentas aisladas: sin cookie, token, contraseña o hash.
    Path("respaldos/registro_terminal_http_real.json").write_text(
        json.dumps(
            {
                "procedencia": "HTTP y JWT administrativos reales sobre cluster aislado",
                "datos": datos,
            }
        ),
        encoding="utf-8",
    )


async def preparar_tres_fallos(admin, app):
    identificador, nombre = await nuevo_usuario(admin)
    for _ in range(3):
        with pytest.raises(ErrorAplicacion):
            await login_credenciales(app, nombre)
    return identificador, nombre


async def test_flujo_publico_completo_chrome_sin_sesion(motores):
    from sqlalchemy import func

    from aplicacion.modelos import IntentoInicioSesion
    from herramientas.probar_flujo_publico_navegador import ejecutar

    admin, _ = motores
    identificador, nombre = await nuevo_usuario(admin)
    resultado = await asyncio.to_thread(ejecutar, nombre)
    assert resultado["estados_login"] == [401, 401, 401, 401, 401, 401, 423]
    assert resultado["sin_sesion_jwt"] is True
    assert resultado["recuperado"]["intento_actual"] == resultado["bloqueo"]["intento_actual"]
    async with AsyncSession(admin) as s:
        fallos, hasta = await estado(admin, identificador)
        assert fallos == 7 and hasta.isoformat() == resultado["bloqueo"]["bloqueado_hasta"]
        intentos = await s.scalar(
            select(func.count())
            .select_from(IntentoInicioSesion)
            .where(IntentoInicioSesion.usuario_id == identificador)
        )
        assert intentos == 7
        ultimo = await s.scalar(
            select(IntentoInicioSesion)
            .where(IntentoInicioSesion.usuario_id == identificador)
            .order_by(IntentoInicioSesion.id.desc())
            .limit(1)
        )
        assert str(ultimo.direccion_ip) == resultado["bloqueo"]["intento_actual"]["direccion_ip_observada"]


async def login_captcha(app, nombre, reto, respuesta):
    from aplicacion.servicios.autenticacion import iniciar_sesion

    async with AsyncSession(app, expire_on_commit=False) as s:
        return await iniciar_sesion(s, nombre, CLAVE, ip(), None, reto["captcha_id"], respuesta)


async def test_cuatro_captcha_incorrectos_bloquean_y_auditan(motores, emitidos, monkeypatch):
    from unittest.mock import Mock

    from sqlalchemy import func

    from aplicacion.modelos import IntentoInicioSesion
    from aplicacion.servicios import autenticacion

    admin, app = motores
    identificador, nombre = await preparar_tres_fallos(admin, app)
    verificar = Mock(side_effect=AssertionError("CAPTCHA incorrecto no debe verificar contraseña"))
    monkeypatch.setattr(autenticacion, "verificar_contrasena", verificar)
    for numero in range(4, 8):
        reto = await emitir(app, nombre)
        codigo = emitidos[-1]
        incorrecto = ("C" if codigo[0] == "A" else "A") + codigo[1:]
        with pytest.raises(ErrorAplicacion) as error:
            await login_captcha(app, nombre, reto, incorrecto)
        assert (await estado(admin, identificador))[0] == numero
        assert error.value.estado_http == (423 if numero == 7 else 401)
    assert error.value.codigo == "CUENTA_BLOQUEADA"
    assert error.value.detalle["segundos_restantes"] == 10800
    assert error.value.detalle["captcha_requerido"] is False
    verificar.assert_not_called()
    async with AsyncSession(admin) as s:
        intentos = (
            await s.scalars(
                select(IntentoInicioSesion).where(IntentoInicioSesion.usuario_id == identificador)
            )
        ).all()
        assert len(intentos) == 7
        assert sum(i.motivo_fallo == "CAPTCHA_INVALIDO" for i in intentos) == 4
        assert (
            await s.scalar(
                select(func.count())
                .select_from(AuditoriaAcceso)
                .join(IntentoInicioSesion, IntentoInicioSesion.id == AuditoriaAcceso.intento_id)
                .where(
                    IntentoInicioSesion.usuario_id == identificador,
                    AuditoriaAcceso.evento == "CUENTA_BLOQUEADA",
                )
            )
            == 1
        )
    # Incluso respuesta y credenciales correctas no permiten acceso durante el bloqueo.
    nuevo = await emitir(app, nombre)
    with pytest.raises(ErrorAplicacion) as vigente:
        await login_captcha(app, nombre, nuevo, emitidos[-1])
    assert vigente.value.estado_http == 423
    assert (await estado(admin, identificador))[0] == 7


async def test_mismo_captcha_incorrecto_concurrente_cuenta_solo_una_vez(motores, emitidos):
    admin, app = motores
    identificador, nombre = await preparar_tres_fallos(admin, app)
    reto = await emitir(app, nombre)
    resultados = await asyncio.gather(
        *(login_captcha(app, nombre, reto, "!!!!!!") for _ in range(6)), return_exceptions=True
    )
    assert all(isinstance(r, ErrorAplicacion) and r.estado_http == 401 for r in resultados)
    assert (await estado(admin, identificador)) == (4, None)


async def test_captcha_vencido_cuenta_y_regenerar_no_cuenta(motores, emitidos, monkeypatch):
    admin, app = motores
    identificador, nombre = await preparar_tres_fallos(admin, app)
    anterior = await emitir(app, nombre)
    reto = await emitir(app, nombre, anterior["captcha_id"])
    assert (await estado(admin, identificador)) == (3, None)
    async with AsyncSession(admin) as s:
        vencimiento = (await s.get(DesafioCaptcha, reto["captcha_id"])).expira_en

    async def reloj(_):
        return vencimiento

    monkeypatch.setattr(captcha, "reloj_servidor", reloj)
    with pytest.raises(ErrorAplicacion) as error:
        await login_captcha(app, nombre, reto, emitidos[-1])
    assert error.value.estado_http == 401
    assert (await estado(admin, identificador)) == (4, None)


async def test_averia_captcha_no_cuenta_ni_confirma_intento(motores, monkeypatch):
    from unittest.mock import AsyncMock

    from sqlalchemy import func

    from aplicacion.modelos import IntentoInicioSesion

    admin, app = motores
    identificador, nombre = await preparar_tres_fallos(admin, app)
    monkeypatch.setattr(captcha.CaptchaPostgres, "verificar", AsyncMock(side_effect=RuntimeError("avería")))
    with pytest.raises(ErrorAplicacion) as error:
        await login_captcha(app, nombre, {"captcha_id": "a" * 43}, "ACD346")
    assert error.value.estado_http == 503
    assert (await estado(admin, identificador)) == (3, None)
    async with AsyncSession(admin) as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(IntentoInicioSesion)
                .where(IntentoInicioSesion.usuario_id == identificador)
            )
            == 3
        )
