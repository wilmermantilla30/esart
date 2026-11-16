"""
Pruebas de HU-10: crear usuario con rol, desbloquear cuenta e IP, todo auditado.

- Validaciones y argumentos del comando: sin base de datos.
- Operaciones: con PostgreSQL (ESART_URL_BD_INTEGRACION); todo se revierte al final.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from aplicacion.modelos import AuditoriaEvento, Usuario
from aplicacion.modelos.seguridad import LimiteInicioIP
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.contrasenas import verificar_contrasena
from aplicacion.servicios import administracion_usuarios as servicio
from aplicacion.servicios.autenticacion import obtener_codigo_rol
from aplicacion.servicios.seguridad_login import seudonimo
from herramientas.administrar_usuarios import construir_argumentos
from pruebas.test_login_hu05 import crear_usuario, iniciar_sesion, requiere_postgresql, sesion_bd  # noqa: F401

pytestmark = pytest.mark.anyio

CONTRASENA_VALIDA = "ClaveSegura2026"


# --- Sin base de datos --------------------------------------------------------------


@pytest.mark.parametrize("contrasena", ["corta1", "solamenteletras", "1234567890123", "a1" * 40])
def test_contrasena_nueva_debil_se_rechaza(contrasena):
    with pytest.raises(ErrorAplicacion):
        servicio.validar_contrasena_nueva(contrasena)


def test_contrasena_nueva_valida():
    servicio.validar_contrasena_nueva(CONTRASENA_VALIDA)


def test_el_comando_no_acepta_la_contrasena_como_argumento():
    analizador = construir_argumentos()
    argumentos = analizador.parse_args(["crear", "--usuario", "jperez.esart", "--rol", "USUARIO"])
    assert not hasattr(argumentos, "contrasena")
    with pytest.raises(SystemExit):
        analizador.parse_args(["crear", "--usuario", "x", "--rol", "USUARIO", "--contrasena", "secreta"])
    with pytest.raises(SystemExit):
        analizador.parse_args(["crear", "--usuario", "x", "--rol", "SUPERUSUARIO"])


# --- Con PostgreSQL -------------------------------------------------------------------


async def ultimo_evento(sesion, accion: str) -> AuditoriaEvento:
    return await sesion.scalar(
        select(AuditoriaEvento).where(AuditoriaEvento.accion == accion).order_by(AuditoriaEvento.id.desc())
    )


@requiere_postgresql
async def test_crear_usuario_con_rol_y_entrar(cliente_api, sesion_bd):  # noqa: F811
    usuario_id = await servicio.crear_usuario(
        sesion_bd,
        nombre_usuario="hu10.creado",
        codigo_rol="USUARIO",
        contrasena=CONTRASENA_VALIDA,
        documento_identidad=None,
        operador="pruebas",
    )

    usuario = await sesion_bd.get(Usuario, usuario_id)
    assert usuario.activo and verificar_contrasena(CONTRASENA_VALIDA, usuario.contrasena_hash)
    assert await obtener_codigo_rol(sesion_bd, usuario_id) == "USUARIO"
    evento = await ultimo_evento(sesion_bd, "USUARIO_CREADO")
    assert evento.detalle == {"usuario_creado": "hu10.creado", "rol": "USUARIO", "operador": "pruebas"}
    assert evento.nombre_usuario == "consola"
    assert CONTRASENA_VALIDA not in str(evento.detalle)

    respuesta = await iniciar_sesion(cliente_api, "hu10.creado", CONTRASENA_VALIDA)
    assert respuesta.status_code == 200


@requiere_postgresql
async def test_no_se_crea_un_usuario_repetido_ni_con_rol_inexistente(sesion_bd):  # noqa: F811
    existente = await crear_usuario(sesion_bd)
    with pytest.raises(ErrorAplicacion) as repetido:
        await servicio.crear_usuario(
            sesion_bd,
            nombre_usuario=existente.usuario.upper(),
            codigo_rol="USUARIO",
            contrasena=CONTRASENA_VALIDA,
            documento_identidad=None,
            operador="pruebas",
        )
    assert repetido.value.codigo == "USUARIO_EXISTENTE"
    with pytest.raises(ErrorAplicacion) as rol:
        await servicio.crear_usuario(
            sesion_bd,
            nombre_usuario="hu10.otro",
            codigo_rol="COMANDANTE",
            contrasena=CONTRASENA_VALIDA,
            documento_identidad=None,
            operador="pruebas",
        )
    assert rol.value.estado_http == 422


@requiere_postgresql
async def test_desbloquear_usuario_permite_volver_a_entrar(cliente_api, sesion_bd):  # noqa: F811
    usuario = await crear_usuario(sesion_bd)
    await sesion_bd.execute(
        update(Usuario)
        .where(Usuario.id == usuario.id)
        .values(intentos_fallidos_consecutivos=7, bloqueado_hasta=datetime.now(UTC) + timedelta(hours=3))
    )
    assert (await servicio.listar_usuarios(sesion_bd, usuario.usuario))[0].bloqueado is True

    estado = await servicio.desbloquear_usuario(sesion_bd, nombre_usuario=usuario.usuario, operador="pruebas")

    assert estado.bloqueado is False and estado.intentos_fallidos == 0
    evento = await ultimo_evento(sesion_bd, "USUARIO_DESBLOQUEADO")
    assert evento.detalle["tipo"] == "CUENTA" and evento.detalle["antes"]["intentos_fallidos"] == 7


@requiere_postgresql
async def test_desbloquear_ip_pone_el_contador_en_cero(sesion_bd):  # noqa: F811
    clave = seudonimo("ip", "10.20.30.40")
    sesion_bd.add(LimiteInicioIP(clave=clave, inicio=datetime.now(UTC), intentos=9))
    await sesion_bd.flush()

    anteriores = await servicio.desbloquear_ip(sesion_bd, ip="10.20.30.40", operador="pruebas")

    assert anteriores == 9
    limite = await sesion_bd.get(LimiteInicioIP, clave)
    await sesion_bd.refresh(limite)
    assert limite.intentos == 0
    assert (await ultimo_evento(sesion_bd, "USUARIO_DESBLOQUEADO")).detalle["ip"] == "10.20.30.40"
    with pytest.raises(ErrorAplicacion):
        await servicio.desbloquear_ip(sesion_bd, ip="no-es-una-ip", operador="pruebas")
