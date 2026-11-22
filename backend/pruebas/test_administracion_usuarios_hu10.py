"""
Pruebas de HU-10: gestión de usuarios (web y consola) y cambio obligatorio de contraseña.

- Validaciones, sugerencia de nombre y argumentos del comando: sin base de datos.
- Operaciones y endpoints: con PostgreSQL (ESART_URL_BD_INTEGRACION); todo se revierte al final.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from aplicacion.modelos import AuditoriaEvento, PersonalMilitar, SesionUsuario, Usuario
from aplicacion.modelos.seguridad import LimiteInicioIP
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.contrasenas import verificar_contrasena
from aplicacion.servicios import administracion_usuarios as servicio
from aplicacion.servicios.autenticacion import obtener_codigo_rol
from aplicacion.servicios.seguridad_login import seudonimo
from herramientas.administrar_usuarios import construir_argumentos
from pruebas.soporte_mfa import completar_vinculacion
from pruebas.test_auditoria_y_malla import cabecera_csrf, entrar
from pruebas.test_login_hu05 import (  # noqa: F401
    CONTRASENA_CORRECTA,
    crear_usuario,
    iniciar_sesion,
    requiere_postgresql,
    sesion_bd,
)

pytestmark = pytest.mark.anyio

CONTRASENA_VALIDA = "ClaveSegura2026"
OTRA_CONTRASENA_VALIDA = "OtraClave2027x"
ACTOR_PRUEBAS = servicio.Actor.consola("pruebas")


# --- Sin base de datos --------------------------------------------------------------


@pytest.mark.parametrize("contrasena", ["corta1", "solamenteletras", "1234567890123", "a1" * 40])
def test_contrasena_nueva_debil_se_rechaza(contrasena):
    with pytest.raises(ErrorAplicacion):
        servicio.validar_contrasena_nueva(contrasena)


def test_contrasena_nueva_valida():
    servicio.validar_contrasena_nueva(CONTRASENA_VALIDA)


@pytest.mark.parametrize("cedula", [None, "", "12ab5678", "123"])
def test_la_cedula_es_obligatoria_y_numerica(cedula):
    with pytest.raises(ErrorAplicacion):
        servicio.validar_cedula(cedula)


def test_el_comando_exige_cedula_y_no_acepta_la_contrasena_como_argumento():
    analizador = construir_argumentos()
    argumentos = analizador.parse_args(
        ["crear", "--usuario", "jperez.esart", "--rol", "USUARIO", "--cedula", "1234567890"]
    )
    assert not hasattr(argumentos, "contrasena")
    with pytest.raises(SystemExit):
        analizador.parse_args(["crear", "--usuario", "x", "--rol", "USUARIO"])
    with pytest.raises(SystemExit):
        analizador.parse_args(
            ["crear", "--usuario", "x", "--rol", "USUARIO", "--cedula", "1", "--contrasena", "secreta"]
        )
    with pytest.raises(SystemExit):
        analizador.parse_args(["crear", "--usuario", "x", "--rol", "SUPERUSUARIO", "--cedula", "1"])


# --- Con PostgreSQL -------------------------------------------------------------------


async def ultimo_evento(sesion, accion: str) -> AuditoriaEvento:
    return await sesion.scalar(
        select(AuditoriaEvento).where(AuditoriaEvento.accion == accion).order_by(AuditoriaEvento.id.desc())
    )


async def crear_militar(sesion, *, nombres="Juan Carlos", apellidos="Pérez Gómez", activo=True) -> str:
    """Militar de prueba con cédula única. Devuelve la cédula."""
    cedula = f"8{uuid.uuid4().int % 10**9:09d}"
    sesion.add(
        PersonalMilitar(
            documento_identidad=cedula,
            nombres=nombres,
            apellidos=apellidos,
            grado="MY",
            genero="M",
            categoria="OFICIAL",
            activo=activo,
        )
    )
    await sesion.flush()
    return cedula


@requiere_postgresql
async def test_sugerencia_de_usuario_sin_tildes_y_unica(sesion_bd):  # noqa: F811
    sugerido = await servicio.sugerir_nombre_usuario(sesion_bd, "Ñoño Andrés", "Muñoz Pérez")
    assert sugerido.startswith("nmunoz") and sugerido.endswith(".esart")
    existente = await crear_usuario(sesion_bd)
    await sesion_bd.execute(update(Usuario).where(Usuario.id == existente.id).values(usuario=sugerido))
    siguiente = await servicio.sugerir_nombre_usuario(sesion_bd, "Ñoño Andrés", "Muñoz Pérez")
    assert siguiente != sugerido and siguiente.endswith(".esart")


@requiere_postgresql
async def test_crear_usuario_de_un_militar_con_contrasena_temporal(cliente_api, sesion_bd):  # noqa: F811
    cedula = await crear_militar(sesion_bd)
    usuario_id = await servicio.crear_usuario(
        sesion_bd,
        nombre_usuario="hu10.creado",
        codigo_rol="USUARIO",
        contrasena=CONTRASENA_VALIDA,
        documento_identidad=cedula,
        actor=ACTOR_PRUEBAS,
    )

    usuario = await sesion_bd.get(Usuario, usuario_id)
    assert usuario.activo and usuario.requiere_cambio_contrasena
    assert usuario.documento_identidad == cedula
    assert verificar_contrasena(CONTRASENA_VALIDA, usuario.contrasena_hash)
    assert await obtener_codigo_rol(sesion_bd, usuario_id) == "USUARIO"
    evento = await ultimo_evento(sesion_bd, "USUARIO_CREADO")
    assert evento.detalle == {
        "usuario_creado": "hu10.creado",
        "rol": "USUARIO",
        "operador": "pruebas",
        "tipo_persona": "MILITAR",
    }
    assert evento.nombre_usuario == "consola" and evento.numero_documento_consultado == cedula
    assert CONTRASENA_VALIDA not in str(evento.detalle)

    # Con la contraseña temporal el login solo devuelve el desafío de cambio (202):
    # no hay sesión ni cookie, así que ninguna ruta protegida responde.
    respuesta = await iniciar_sesion(cliente_api, "hu10.creado", CONTRASENA_VALIDA)
    assert respuesta.status_code == 202
    assert respuesta.json()["cambio_contrasena_requerido"] is True
    assert respuesta.json()["metodos"] == ["CAMBIO_CONTRASENA"]
    assert "esart_sesion" not in cliente_api.cookies
    assert (await cliente_api.get("/api/auth/yo")).status_code == 401
    assert (await cliente_api.get("/api/verificar/resumen")).status_code == 401


@requiere_postgresql
async def test_no_se_crea_usuario_sin_militar_repetido_o_con_rol_inexistente(sesion_bd):  # noqa: F811
    cedula = await crear_militar(sesion_bd)
    inactivo = await crear_militar(sesion_bd, activo=False)
    existente = await crear_usuario(sesion_bd, documento_identidad=cedula)

    async def intentar(**cambios):
        datos = {
            "nombre_usuario": "hu10.otro",
            "codigo_rol": "USUARIO",
            "contrasena": CONTRASENA_VALIDA,
            "documento_identidad": cedula,
            "actor": ACTOR_PRUEBAS,
        }
        with pytest.raises(ErrorAplicacion) as error:
            await servicio.crear_usuario(sesion_bd, **{**datos, **cambios})
        return error.value

    assert (await intentar()).codigo == "USUARIO_EXISTENTE"  # Ese militar ya tiene usuario.
    assert (await intentar(nombre_usuario=existente.usuario.upper())).codigo == "USUARIO_EXISTENTE"
    assert (await intentar(documento_identidad="7000000001")).estado_http == 422  # No está en personal.
    assert (await intentar(documento_identidad=inactivo)).estado_http == 422
    assert (await intentar(codigo_rol="COMANDANTE")).estado_http == 422


@requiere_postgresql
async def test_cambiar_contrasena_temporal_habilita_el_sistema(cliente_api, sesion_bd):  # noqa: F811
    cedula = await crear_militar(sesion_bd)
    await servicio.crear_usuario(
        sesion_bd,
        nombre_usuario="hu10.cambio",
        codigo_rol="USUARIO",
        contrasena=CONTRASENA_VALIDA,
        documento_identidad=cedula,
        actor=ACTOR_PRUEBAS,
    )
    # Flujo con TOTP: login -> desafío de cambio -> cambio de contraseña -> vinculación -> sesión.
    desafio = await iniciar_sesion(cliente_api, "hu10.cambio", CONTRASENA_VALIDA)
    assert desafio.status_code == 202 and desafio.json()["cambio_contrasena_requerido"]
    desafio_id = desafio.json()["desafio_id"]

    async def cambiar(actual: str, nueva: str):
        return await cliente_api.post(
            "/api/auth/cambiar-contrasena-inicial",
            json={"desafio_id": desafio_id, "contrasena_actual": actual, "contrasena_nueva": nueva},
        )

    errada = await cambiar("no-es-esta-1", OTRA_CONTRASENA_VALIDA)
    assert errada.status_code == 422 and errada.json()["error"]["codigo"] == "CONTRASENA_ACTUAL_INCORRECTA"
    debil = await cambiar(CONTRASENA_VALIDA, "corta")
    assert debil.status_code == 422

    # Cambiada la contraseña, sigue la vinculación TOTP; solo al terminarla hay sesión.
    correcta = await cambiar(CONTRASENA_VALIDA, OTRA_CONTRASENA_VALIDA)
    assert correcta.status_code == 202 and correcta.json()["configuracion_requerida"]
    assert "esart_sesion" not in cliente_api.cookies
    sesion_final = await completar_vinculacion(cliente_api, correcta)
    assert sesion_final.json()["usuario"]["requiere_cambio_contrasena"] is False
    assert (await cliente_api.get("/api/auth/yo")).json()["requiere_cambio_contrasena"] is False
    assert (await cliente_api.get("/api/verificar/resumen")).status_code == 200
    evento = await ultimo_evento(sesion_bd, "CONTRASENA_CAMBIADA")
    assert evento.resultado == "EXITOSO" and OTRA_CONTRASENA_VALIDA not in str(evento.detalle)


@requiere_postgresql
async def test_administrador_crea_desactiva_activa_y_restablece_por_la_web(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    cedula = await crear_militar(sesion_bd, nombres="Ana María", apellidos="Gómez Ruiz")

    militar = await cliente_api.get(f"/api/administracion/usuarios/militar/{cedula}")
    assert militar.status_code == 200
    assert militar.json()["usuario_existente"] is None
    sugerido = militar.json()["nombre_usuario_sugerido"]
    assert sugerido.startswith("agomez")
    assert (await cliente_api.get("/api/administracion/usuarios/militar/7000000002")).status_code == 404

    creado = await cliente_api.post(
        "/api/administracion/usuarios",
        json={
            "documento_identidad": cedula,
            "nombre_usuario": sugerido,
            "rol": "USUARIO",
            "contrasena_temporal": CONTRASENA_VALIDA,
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert creado.status_code == 201, creado.text
    datos = creado.json()
    assert datos["requiere_cambio_contrasena"] and datos["nombre_completo"] == "MY Ana María Gómez Ruiz"
    assert CONTRASENA_VALIDA not in creado.text and "$2b$" not in creado.text and "hash" not in creado.text
    evento = await ultimo_evento(sesion_bd, "USUARIO_CREADO")
    assert evento.usuario_id == administrador.id and evento.nombre_usuario == administrador.usuario
    usuario_id = datos["id"]

    # Una sesión abierta del usuario se cierra al desactivarlo.
    sesion_abierta = SesionUsuario(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        fecha_inicio=datetime.now(UTC),
        fecha_ultima_actividad=datetime.now(UTC),
        revocada=False,
    )
    sesion_bd.add(sesion_abierta)
    await sesion_bd.flush()
    desactivado = await cliente_api.post(
        f"/api/administracion/usuarios/{usuario_id}/desactivar", headers=cabecera_csrf(cliente_api)
    )
    assert desactivado.status_code == 200 and desactivado.json()["activo"] is False
    await sesion_bd.refresh(sesion_abierta)
    assert sesion_abierta.revocada
    activado = await cliente_api.post(
        f"/api/administracion/usuarios/{usuario_id}/activar", headers=cabecera_csrf(cliente_api)
    )
    assert activado.json()["activo"] is True

    await sesion_bd.execute(
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(intentos_fallidos_consecutivos=7, bloqueado_hasta=datetime.now(UTC) + timedelta(hours=3))
    )
    restablecido = await cliente_api.post(
        f"/api/administracion/usuarios/{usuario_id}/restablecer-contrasena",
        json={"contrasena_temporal": OTRA_CONTRASENA_VALIDA},
        headers=cabecera_csrf(cliente_api),
    )
    assert restablecido.status_code == 200
    assert restablecido.json()["bloqueado"] is False and restablecido.json()["requiere_cambio_contrasena"]
    usuario = await sesion_bd.get(Usuario, usuario_id, populate_existing=True)
    assert verificar_contrasena(OTRA_CONTRASENA_VALIDA, usuario.contrasena_hash)
    for accion in ("USUARIO_DESACTIVADO", "USUARIO_ACTIVADO", "CONTRASENA_RESTABLECIDA"):
        assert (await ultimo_evento(sesion_bd, accion)).detalle["usuario_afectado"] == sugerido

    # Nadie se desactiva a sí mismo ni restablece su propia contraseña desde aquí.
    propio = await cliente_api.post(
        f"/api/administracion/usuarios/{administrador.id}/desactivar", headers=cabecera_csrf(cliente_api)
    )
    assert propio.status_code == 409


@requiere_postgresql
async def test_un_usuario_sin_permiso_no_gestiona_usuarios(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    assert (await cliente_api.get("/api/administracion/usuarios")).status_code == 403
    respuesta = await cliente_api.post(
        "/api/administracion/usuarios",
        json={
            "documento_identidad": "1234567",
            "nombre_usuario": "intruso",
            "rol": "ADMINISTRADOR",
            "contrasena_temporal": CONTRASENA_VALIDA,
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert respuesta.status_code == 403


@requiere_postgresql
async def test_desbloquear_usuario_permite_volver_a_entrar(cliente_api, sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd)
    await sesion_bd.execute(
        update(Usuario)
        .where(Usuario.id == usuario.id)
        .values(intentos_fallidos_consecutivos=7, bloqueado_hasta=datetime.now(UTC) + timedelta(hours=3))
    )
    assert (await servicio.listar_usuarios(sesion_bd, usuario.usuario))[0].bloqueado is True

    estado = await servicio.desbloquear_usuario(
        sesion_bd, nombre_usuario=usuario.usuario, actor=ACTOR_PRUEBAS
    )

    assert estado.bloqueado is False and estado.intentos_fallidos == 0
    evento = await ultimo_evento(sesion_bd, "USUARIO_DESBLOQUEADO")
    assert evento.detalle["tipo"] == "CUENTA" and evento.detalle["antes"]["intentos_fallidos"] == 7
    assert (await iniciar_sesion(cliente_api, usuario.usuario, CONTRASENA_CORRECTA)).status_code == 200


@requiere_postgresql
async def test_desbloquear_ip_pone_el_contador_en_cero(sesion_bd):  # noqa: F811
    clave = seudonimo("ip", "10.20.30.40")
    sesion_bd.add(LimiteInicioIP(clave=clave, inicio=datetime.now(UTC), intentos=9))
    await sesion_bd.flush()

    anteriores = await servicio.desbloquear_ip(sesion_bd, ip="10.20.30.40", actor=ACTOR_PRUEBAS)

    assert anteriores == 9
    limite = await sesion_bd.get(LimiteInicioIP, clave)
    await sesion_bd.refresh(limite)
    assert limite.intentos == 0
    assert (await ultimo_evento(sesion_bd, "USUARIO_DESBLOQUEADO")).detalle["ip"] == "10.20.30.40"
    with pytest.raises(ErrorAplicacion):
        await servicio.desbloquear_ip(sesion_bd, ip="no-es-una-ip", actor=ACTOR_PRUEBAS)
