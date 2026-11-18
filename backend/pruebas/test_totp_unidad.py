import base64
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos.totp import UsuarioTotp
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import totp
from aplicacion.servicios.autorizacion_acciones import AdaptadorAccion, hash_operacion


@pytest.mark.anyio
@pytest.mark.parametrize("estado_factor", [None, "PENDIENTE", "ACTIVO", "REVOCADO"])
async def test_estado_para_menu_distingue_factor_sin_devolver_secreto(monkeypatch, estado_factor):
    from aplicacion.rutas.totp import estado

    ahora = datetime.now(UTC)
    fila = (
        SimpleNamespace(estado=estado_factor, activado_en=ahora, secreto_cifrado=b"no-exponer")
        if estado_factor
        else None
    )
    sesion = SimpleNamespace(scalar=AsyncMock(return_value=fila), commit=AsyncMock())
    monkeypatch.setattr(totp.TotpService, "preparar", AsyncMock())
    respuesta = await estado(identidad=SimpleNamespace(id=73), sesion=sesion)
    assert respuesta == {
        "configurado": fila is not None,
        "activo": estado_factor == "ACTIVO",
        "estado": estado_factor or "NO_CONFIGURADO",
        "fecha_activacion": ahora if estado_factor == "ACTIVO" else None,
    }
    sesion.scalar.assert_awaited_once()
    sesion.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_preparar_login_no_exige_tabla_autorizaciones_ni_migracion(clave, monkeypatch):
    from aplicacion.servicios import requisitos_totp

    comprobar = AsyncMock(return_value=[])
    monkeypatch.setattr(requisitos_totp, "permisos_faltantes", comprobar)
    servicio = totp.TotpService(None)
    integridad = AsyncMock(side_effect=AssertionError("No es un requisito de autenticación"))
    monkeypatch.setattr(servicio, "verificar_integridad_acciones", integridad)
    await servicio.preparar()
    await servicio.preparar()
    comprobar.assert_awaited_once()
    integridad.assert_not_awaited()


@pytest.mark.anyio
async def test_permisos_faltantes_fallan_cerrado_con_diagnostico_preciso(clave, monkeypatch, caplog):
    from aplicacion.servicios import requisitos_totp

    monkeypatch.setattr(
        requisitos_totp,
        "permisos_faltantes",
        AsyncMock(
            return_value=["seguridad.desafios:INSERT(*)"],
        ),
    )
    with pytest.raises(ErrorAplicacion) as error:
        await totp.TotpService(None).preparar()
    assert error.value.estado_http == 503 and error.value.codigo == "TOTP_PERMISOS_FALTANTES"
    assert "seguridad.desafios:INSERT(*)" in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("identidad,requiere_uso", [("a", False), ("d", False), ("", True)])
async def test_secuencia_identity_no_necesita_privilegio_serial_si(identidad, requiere_uso):
    from aplicacion.servicios.requisitos_totp import permisos_faltantes

    resultados = [
        SimpleNamespace(mappings=lambda: []),
        SimpleNamespace(
            mappings=lambda: [
                {
                    "tabla": "usuario_totp",
                    "identidad": identidad,
                    "secuencia": "seguridad.usuario_totp_id_seq",
                }
            ]
        ),
    ]
    sesion = SimpleNamespace(
        scalar=AsyncMock(side_effect=[True, False]), execute=AsyncMock(side_effect=resultados)
    )
    faltantes = await permisos_faltantes(sesion)
    assert bool(faltantes) is requiere_uso
    assert sesion.scalar.await_count == (2 if requiere_uso else 1)


@pytest.mark.anyio
async def test_acciones_conservan_verificacion_de_integridad(clave, monkeypatch):
    from aplicacion.servicios import requisitos_totp
    from aplicacion.servicios.autorizacion_acciones import AutorizacionAccionesService

    monkeypatch.setattr(requisitos_totp, "permisos_faltantes", AsyncMock(return_value=[]))
    servicio = AutorizacionAccionesService(None)
    comprobar = AsyncMock(side_effect=ErrorAplicacion(503, "TOTP_INTEGRIDAD_ACCIONES", "No disponible"))
    monkeypatch.setattr(servicio, "verificar_integridad_acciones", comprobar)
    with pytest.raises(ErrorAplicacion):
        await servicio.preparar()
    comprobar.assert_awaited_once()
    assert not servicio._preparado


@pytest.mark.anyio
@pytest.mark.parametrize("activo", [False, True])
@pytest.mark.parametrize("temporal", [False, True])
async def test_contrasena_solo_crea_desafio_nunca_sesion(clave, monkeypatch, activo, temporal):
    from aplicacion.servicios import autenticacion

    usuario = SimpleNamespace(
        id=73,
        usuario="prueba",
        activo=True,
        contrasena_hash="hash-de-prueba",
        requiere_cambio_contrasena=temporal,
    )
    contexto = SimpleNamespace(usuario=usuario)
    monkeypatch.setattr(autenticacion.seguridad_login, "preparar", AsyncMock(return_value=contexto))
    monkeypatch.setattr(autenticacion.seguridad_login, "registrar", AsyncMock())
    monkeypatch.setattr(autenticacion, "verificar_contrasena", lambda *_: True)
    monkeypatch.setattr(autenticacion, "obtener_codigo_rol", AsyncMock(return_value="USUARIO"))
    finalizar = AsyncMock()
    monkeypatch.setattr(autenticacion, "finalizar_login", finalizar)
    monkeypatch.setattr(totp.TotpService, "preparar", AsyncMock())
    monkeypatch.setattr(
        totp.TotpService,
        "registro",
        AsyncMock(
            return_value=SimpleNamespace(estado="ACTIVO") if activo else None,
        ),
    )
    crear = AsyncMock(
        return_value=totp.DesafioLoginTotp(uuid.uuid4(), datetime.now(UTC), "nonce", not activo)
    )
    monkeypatch.setattr(totp.TotpService, "crear_desafio", crear)
    sesion = SimpleNamespace(commit=AsyncMock())
    salida = await autenticacion.iniciar_sesion(sesion, "prueba", "contraseña", "127.0.0.1", None)
    crear.assert_awaited_once_with(
        73, "CAMBIO_CONTRASENA" if temporal else "LOGIN" if activo else "VINCULACION", "127.0.0.1"
    )
    assert salida.configuracion_requerida is not activo
    finalizar.assert_not_awaited()


@pytest.mark.anyio
async def test_no_emite_jwt_con_contrasena_temporal_aunque_totp_sea_correcto(monkeypatch):
    from aplicacion.servicios import autenticacion

    monkeypatch.setattr(autenticacion, "obtener_codigo_rol", AsyncMock(return_value="USUARIO"))
    emitir = MagicMock()
    monkeypatch.setattr(autenticacion, "crear_token_sesion", emitir)
    with pytest.raises(ErrorAplicacion) as error:
        await autenticacion.finalizar_login(
            None, SimpleNamespace(id=73, activo=True, requiere_cambio_contrasena=True), None, None, None
        )
    assert error.value.codigo == "CAMBIO_CONTRASENA_REQUERIDO"
    emitir.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("activo", [False, True])
async def test_cambio_inicial_consume_desafio_y_continua_mfa_sin_sesion(clave, monkeypatch, activo):
    from aplicacion.servicios import administracion_usuarios

    usuario = SimpleNamespace(id=73, usuario="prueba", requiere_cambio_contrasena=True)
    desafio = SimpleNamespace(intentos=0, estado="PENDIENTE")
    sesion = SimpleNamespace(commit=AsyncMock())
    servicio = totp.TotpService(sesion)
    contexto = AsyncMock(return_value=(usuario, desafio))
    monkeypatch.setattr(servicio, "contexto_vinculacion", contexto)
    cambiar = AsyncMock()
    monkeypatch.setattr(administracion_usuarios, "cambiar_contrasena_comprobada", cambiar)
    monkeypatch.setattr(
        servicio, "registro", AsyncMock(return_value=SimpleNamespace(estado="ACTIVO") if activo else None)
    )
    siguiente = totp.DesafioLoginTotp(uuid.uuid4(), datetime.now(UTC), "nonce-nuevo", not activo)
    crear = AsyncMock(return_value=siguiente)
    monkeypatch.setattr(servicio, "crear_desafio", crear)
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=datetime.now(UTC)))
    salida = await servicio.cambiar_contrasena_inicial(uuid.uuid4(), "nonce", "actual", "nueva", "127.0.0.1")
    assert salida is siguiente and desafio.estado == "CONSUMIDO" and desafio.intentos == 1
    assert contexto.call_args.kwargs["proposito"] == "CAMBIO_CONTRASENA"
    assert cambiar.call_args.kwargs["confirmar"] is False
    crear.assert_awaited_once_with(73, "LOGIN" if activo else "VINCULACION", "127.0.0.1")
    sesion.commit.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("proposito,temporal", [("VINCULACION", True), ("CAMBIO_CONTRASENA", False)])
async def test_no_cruza_propositos_ni_salta_cambio_inicial(clave, monkeypatch, proposito, temporal):
    ahora, identificador = datetime.now(UTC), uuid.uuid4()
    nonce = totp.TotpService.nonce_contexto("prueba", identificador, proposito)
    desafio = SimpleNamespace(
        usuario_id=73,
        recurso_tipo=proposito,
        estado="PENDIENTE",
        expira_en=ahora + timedelta(seconds=120),
        intentos=0,
        operacion_hash=totp.TotpService.vinculo(73, proposito, nonce),
    )
    sesion = SimpleNamespace(get=AsyncMock(return_value=desafio), scalar=AsyncMock(return_value=desafio))
    servicio = totp.TotpService(sesion)
    monkeypatch.setattr(servicio, "preparar", AsyncMock())
    monkeypatch.setattr(servicio, "limitar", AsyncMock())
    monkeypatch.setattr(
        servicio,
        "usuario",
        AsyncMock(return_value=SimpleNamespace(id=73, requiere_cambio_contrasena=temporal)),
    )
    monkeypatch.setattr(servicio, "registro", AsyncMock(return_value=None))
    monkeypatch.setattr(
        servicio, "rechazar", AsyncMock(side_effect=ErrorAplicacion(401, "INVALIDO", "Inválido"))
    )
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=ahora))
    with pytest.raises(ErrorAplicacion):
        await servicio.contexto_vinculacion(identificador, nonce, "127.0.0.1", proposito=proposito)


@pytest.mark.anyio
async def test_servicio_deshabilitado_no_permite_login_sin_factor(clave, monkeypatch):
    from aplicacion.servicios import autenticacion

    usuario = SimpleNamespace(id=73, activo=True, contrasena_hash="hash-de-prueba")
    monkeypatch.setattr(
        autenticacion.seguridad_login,
        "preparar",
        AsyncMock(
            return_value=SimpleNamespace(usuario=usuario),
        ),
    )
    monkeypatch.setattr(autenticacion, "verificar_contrasena", lambda *_: True)
    monkeypatch.setattr(autenticacion, "obtener_codigo_rol", AsyncMock(return_value="USUARIO"))
    monkeypatch.setattr(obtener_configuracion(), "totp_habilitado", False)
    with pytest.raises(ErrorAplicacion) as error:
        await autenticacion.iniciar_sesion(None, "prueba", "contraseña", "127.0.0.1", None)
    assert error.value.estado_http == 503


@pytest.mark.anyio
@pytest.mark.parametrize(
    "fallo", ["cookie", "proposito", "vencido", "consumido", "intentos", "otro_vinculo", "activo"]
)
async def test_vinculacion_rechaza_contextos_invalidos(clave, monkeypatch, fallo):
    ahora = datetime.now(UTC)
    identificador = uuid.uuid4()
    nonce = totp.TotpService.nonce_contexto("prueba", identificador, "VINCULACION")
    desafio = SimpleNamespace(
        usuario_id=73,
        recurso_tipo="VINCULACION",
        estado="PENDIENTE",
        expira_en=ahora + timedelta(seconds=120),
        intentos=0,
        operacion_hash=totp.TotpService.vinculo(73, "VINCULACION", nonce),
    )
    if fallo == "cookie":
        nonce = None
    elif fallo == "proposito":
        desafio.recurso_tipo = "LOGIN"
    elif fallo == "vencido":
        desafio.expira_en = ahora
    elif fallo == "consumido":
        desafio.estado = "CONSUMIDO"
    elif fallo == "intentos":
        desafio.intentos = 5
    elif fallo == "otro_vinculo":
        desafio.operacion_hash = "0" * 64
    sesion = SimpleNamespace(get=AsyncMock(return_value=desafio), scalar=AsyncMock(return_value=desafio))
    servicio = totp.TotpService(sesion)
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=ahora))
    monkeypatch.setattr(servicio, "preparar", AsyncMock())
    monkeypatch.setattr(servicio, "limitar", AsyncMock())
    monkeypatch.setattr(servicio, "usuario", AsyncMock(return_value=SimpleNamespace(id=73)))
    monkeypatch.setattr(
        servicio,
        "registro",
        AsyncMock(
            return_value=SimpleNamespace(estado="ACTIVO") if fallo == "activo" else None,
        ),
    )
    monkeypatch.setattr(
        servicio, "rechazar", AsyncMock(side_effect=ErrorAplicacion(401, "INVALIDO", "Inválido"))
    )
    with pytest.raises(ErrorAplicacion) as error:
        await servicio.contexto_vinculacion(identificador, nonce, "127.0.0.1")
    assert error.value.estado_http == 401


@pytest.mark.anyio
async def test_vinculacion_codigo_real_no_confirma_antes_de_crear_sesion(clave, monkeypatch):
    import pyotp

    ahora = datetime.now(UTC)
    secreto = pyotp.random_base32()
    registro = UsuarioTotp(
        usuario_id=73,
        estado="PENDIENTE",
        secreto_cifrado=totp.TotpService.cifrar(73, secreto),
        expira_configuracion_en=ahora + timedelta(seconds=120),
    )
    desafio = SimpleNamespace(intentos=0, estado="PENDIENTE", correlacion_id=uuid.uuid4())
    usuario = SimpleNamespace(id=73)
    sesion = SimpleNamespace(flush=AsyncMock(), execute=AsyncMock(), add=MagicMock(), commit=AsyncMock())
    servicio = totp.TotpService(sesion)
    monkeypatch.setattr(servicio, "contexto_vinculacion", AsyncMock(return_value=(usuario, desafio)))
    monkeypatch.setattr(servicio, "registro", AsyncMock(return_value=registro))
    monkeypatch.setattr(servicio, "auditar", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=ahora))
    _, salida = await servicio.vincular_login(
        uuid.uuid4(), "nonce", pyotp.TOTP(secreto).at(ahora), "127.0.0.1"
    )
    assert registro.estado == "ACTIVO" and desafio.estado == "CONSUMIDO"
    assert len(salida["codigos_recuperacion"]) == 10
    sesion.commit.assert_not_awaited()  # El llamador confirma junto con JWT/sesión; un error revierte todo.
    assert not await servicio.verificar(registro, pyotp.TOTP(secreto).at(ahora))


@pytest.mark.anyio
@pytest.mark.parametrize("estado", ["AUSENTE", "PENDIENTE", "REVOCADO", "SESION_ANTIGUA"])
async def test_cookie_anterior_no_accede_sin_vinculacion_completa(clave, monkeypatch, estado):
    from aplicacion.servicios import autenticacion

    ahora = datetime.now(UTC)
    sesion_usuario = SimpleNamespace(
        usuario_id=73, revocada=False, fecha_inicio=ahora - timedelta(minutes=1), fecha_ultima_actividad=ahora
    )
    usuario = SimpleNamespace(activo=True, bloqueado_hasta=None)
    sesion = SimpleNamespace(get=AsyncMock(side_effect=[sesion_usuario, usuario]))
    monkeypatch.setattr(totp.TotpService, "preparar", AsyncMock())
    factor = (
        None
        if estado == "AUSENTE"
        else SimpleNamespace(
            estado="ACTIVO" if estado == "SESION_ANTIGUA" else estado,
            activado_en=ahora,
        )
    )
    monkeypatch.setattr(totp.TotpService, "registro", AsyncMock(return_value=factor))
    with pytest.raises(ErrorAplicacion) as error:
        await autenticacion.validar_sesion(sesion, 73, uuid.uuid4())
    assert error.value.estado_http == 401


@pytest.fixture
def clave(monkeypatch):
    cfg = obtener_configuracion()
    monkeypatch.setattr(cfg, "totp_habilitado", True)
    monkeypatch.setattr(
        cfg, "totp_clave_cifrado", SecretStr(base64.b64encode(secrets.token_bytes(32)).decode())
    )


def test_cifrado_autenticado_no_se_puede_trasladar_entre_usuarios(clave):
    secreto = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    a = totp.TotpService.cifrar(73, secreto)
    b = totp.TotpService.cifrar(73, secreto)
    assert a != b and secreto not in a
    assert totp.TotpService.descifrar(UsuarioTotp(usuario_id=73, secreto_cifrado=a)) == secreto
    with pytest.raises(ErrorAplicacion) as error:
        totp.TotpService.descifrar(UsuarioTotp(usuario_id=74, secreto_cifrado=a))
    assert error.value.estado_http == 503 and secreto not in str(error.value)


@pytest.mark.anyio
async def test_vector_rfc6238_seis_digitos_y_replay(clave, monkeypatch):
    instante = datetime.fromtimestamp(59, UTC)
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=instante))
    registro = UsuarioTotp(
        usuario_id=73,
        secreto_cifrado=totp.TotpService.cifrar(73, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"),
        ultimo_intervalo_aceptado=None,
    )
    servicio = totp.TotpService(None)
    # SHA1 vector 59s: 94287082 en 8 dígitos; los seis últimos son 287082.
    assert await servicio.verificar(registro, "287082")
    assert not await servicio.verificar(registro, "287082")
    assert not await servicio.verificar(registro, "１２３４５６")


def test_clave_ausente_no_usa_jwt_como_fallback(monkeypatch):
    monkeypatch.setattr(obtener_configuracion(), "totp_clave_cifrado", None)
    with pytest.raises(ErrorAplicacion) as error:
        totp.TotpService.clave()
    assert error.value.estado_http == 503


def test_hash_canonico_vincula_sesion_recurso_datos_y_version():
    actor = SimpleNamespace(id=1, sesion_id=uuid.uuid4())

    def huella(datos, version=1, recurso="9"):
        return hash_operacion(actor, "PRUEBA", recurso, datos, {"version": version}, "LOTE")

    assert huella({"b": 2, "a": 1}) == huella({"a": 1, "b": 2})
    assert huella({"a": 1}) != huella({"a": 2})
    assert huella({"a": 1}) != huella({"a": 1}, version=2)
    assert huella({"a": 1}) != huella({"a": 1}, recurso="10")
    anterior = huella({"a": 1})
    actor.sesion_id = uuid.uuid4()
    assert anterior != huella({"a": 1})


def test_adaptador_no_puede_auditar_secretos():
    with pytest.raises(ValueError):
        AdaptadorAccion("PRUEBA", "PRUEBA", None, None, None, frozenset({"contrasena_hash"}))


def test_recuperacion_hash_vinculado_al_usuario_y_separado_del_secreto(clave):
    codigo = secrets.token_hex(16)
    huella = totp.TotpService.hash_recuperacion(73, codigo)
    assert huella != totp.TotpService.hash_recuperacion(74, codigo)
    assert len(huella) == 64 and codigo not in huella


@pytest.mark.anyio
async def test_recuperacion_emite_diez_codigos_y_solo_persiste_hashes(clave, monkeypatch):
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=datetime.now(UTC)))
    sesion = SimpleNamespace(execute=AsyncMock(), add=MagicMock())
    codigos = await totp.TotpService(sesion).generar_recuperacion(73)
    assert len(set(codigos)) == 10
    sesion.execute.assert_awaited_once()  # Revoca el lote anterior dentro de la transacción.
    filas = [llamada.args[0] for llamada in sesion.add.call_args_list]
    assert len(filas) == 10
    for codigo, fila in zip(codigos, filas, strict=True):
        assert len(codigo) == 32
        assert fila.codigo_hash == totp.TotpService.hash_recuperacion(73, codigo)
        assert codigo not in fila.codigo_hash


@pytest.mark.anyio
async def test_recuperacion_invalida_no_consulta_y_codigo_ausente_no_autentica(clave):
    sesion = SimpleNamespace(scalar=AsyncMock(return_value=None))
    servicio = totp.TotpService(sesion)
    assert not await servicio.verificar_recuperacion(73, "123456")
    sesion.scalar.assert_not_awaited()
    assert not await servicio.verificar_recuperacion(73, secrets.token_hex(16))


@pytest.mark.anyio
async def test_recuperacion_marca_consumo_y_filtra_usados_y_revocados(clave, monkeypatch):
    ahora = datetime.now(UTC)
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=ahora))
    fila = SimpleNamespace(usado_en=None)
    sesion = SimpleNamespace(scalar=AsyncMock(return_value=fila))
    assert await totp.TotpService(sesion).verificar_recuperacion(73, secrets.token_hex(16))
    assert fila.usado_en == ahora
    consulta = str(sesion.scalar.call_args.args[0])
    assert "usado_en IS NULL" in consulta and "revocado_en IS NULL" in consulta
    assert "FOR UPDATE" in consulta
