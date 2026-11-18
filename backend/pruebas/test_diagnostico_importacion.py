"""Diagnóstico de sesión y 503 sin relajar autenticación ni revelar datos privados."""

import base64
import logging
import os
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aplicacion.base_datos.base import BaseModelo
from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import (
    AuditoriaEvento,
    Cursos,
    HojaVidaArtillero,
    Instructores,
    PersonalMilitar,
    Rol,
    TipoCurso,
    UnidadMilitar,
    Usuario,
    UsuarioRoles,
)
from aplicacion.modelos.seguridad import SesionUsuario
from aplicacion.modelos.totp import BaseSeguridad, UsuarioTotp
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.principal import aplicacion
from aplicacion.seguridad.sesion_http import NOMBRE_COOKIE_SESION, obtener_usuario_actual
from aplicacion.seguridad.tokens import crear_token_sesion
from aplicacion.servicios.importacion_personal import DatosCurso, guardar_personal, leer_excel
from aplicacion.servicios.totp import TotpService
from pruebas.test_importacion_personal import CURSO, filas
from pruebas.test_importacion_personal_aislada import enviar, excel_personal, laboratorio  # noqa: F401

pytestmark = pytest.mark.anyio


@pytest.fixture
async def sesion_real(laboratorio, cliente_api, monkeypatch):  # noqa: F811
    """Prepara cookie firmada, rol, sesión y MFA activo solamente en el laboratorio."""
    sesion, actor, _ = laboratorio
    cfg = obtener_configuracion()
    monkeypatch.setattr(cfg, "totp_habilitado", True)
    monkeypatch.setattr(
        cfg, "totp_clave_cifrado", SecretStr(base64.b64encode(secrets.token_bytes(32)).decode())
    )
    conexion = await sesion.connection()
    await conexion.execute(text("CREATE SCHEMA IF NOT EXISTS seguridad"))
    await conexion.run_sync(lambda c: BaseSeguridad.metadata.create_all(c))
    await conexion.run_sync(lambda c: BaseModelo.metadata.create_all(c, tables=[SesionUsuario.__table__]))
    rol = Rol(codigo="USUARIO", nombre="Usuario de prueba", activo=True)
    sesion.add(rol)
    await sesion.flush()
    sesion.add(UsuarioRoles(usuario_id=actor.id, rol_id=rol.id))
    ahora = datetime.now(UTC)
    factor = UsuarioTotp(
        usuario_id=actor.id,
        secreto_cifrado=TotpService.cifrar(actor.id, base64.b32encode(secrets.token_bytes(20)).decode()),
        estado="ACTIVO",
        activado_en=ahora - timedelta(minutes=2),
    )
    registro = SesionUsuario(
        id=uuid.uuid4(),
        usuario_id=actor.id,
        fecha_inicio=ahora - timedelta(minutes=1),
        fecha_ultima_actividad=ahora,
        revocada=False,
    )
    sesion.add_all([factor, registro])
    await sesion.commit()
    # Se retira solo el doble de identidad del laboratorio: se ejercita la dependencia real.
    aplicacion.dependency_overrides.pop(obtener_usuario_actual, None)
    cliente_api.cookies.set(NOMBRE_COOKIE_SESION, crear_token_sesion(actor.id, registro.id))
    yield sesion, registro, factor


async def test_cookie_jwt_vigente_y_mfa_activo_son_reconocidos(cliente_api, sesion_real):
    respuesta = await cliente_api.get("/api/auth/yo")
    assert respuesta.status_code == 200, respuesta.text
    assert "X-Sesion-Expira-En" in respuesta.headers
    assert "Authorization" not in respuesta.request.headers


async def test_sesion_expirada_sigue_denegada_y_no_importa(cliente_api, sesion_real):
    sesion, registro, _ = sesion_real
    registro.fecha_ultima_actividad = datetime.now(UTC) - timedelta(hours=1)
    await sesion.commit()
    respuesta = await cliente_api.get("/api/auth/yo")
    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["codigo"] == "SESION_EXPIRADA"
    assert registro.revocada
    respuesta = await enviar(cliente_api, excel_personal())
    assert respuesta.status_code == 401
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0


async def test_sesion_anterior_a_activar_mfa_no_es_una_sesion_valida(cliente_api, sesion_real):
    sesion, registro, factor = sesion_real
    registro.fecha_inicio = factor.activado_en - timedelta(seconds=1)
    await sesion.commit()
    respuesta = await cliente_api.get("/api/auth/yo")
    assert respuesta.status_code == 401
    assert "autenticador" in respuesta.json()["error"]["mensaje"]


async def test_401_sin_cookie_no_registra_credenciales(cliente_api, caplog):
    caplog.set_level(logging.INFO)
    respuesta = await cliente_api.get("/api/auth/yo")
    assert respuesta.status_code == 401
    assert "causa=ausente" in caplog.text
    token_ficticio = "token-invalido-no-publicable"
    cliente_api.cookies.set(NOMBRE_COOKIE_SESION, token_ficticio)
    assert (await cliente_api.get("/api/auth/yo")).status_code == 401
    assert "causa=invalido_o_vencido" in caplog.text
    assert token_ficticio not in caplog.text


async def test_error_bd_registra_solo_tipo_y_sqlstate(caplog):
    caplog.set_level(logging.INFO)
    sesion = AsyncMock()
    privado = "dato_privado_que_no_debe_aparecer"
    original = RuntimeError(privado)
    original.sqlstate = "42501"
    sesion.execute.side_effect = OperationalError("SELECT " + privado, {"documento": privado}, original)
    with pytest.raises(ErrorAplicacion) as fallo:
        await guardar_personal(sesion, "hoja-no-publicable", filas(), None, CURSO)
    assert fallo.value.codigo == "IMPORTACION_BD_NO_DISPONIBLE"
    assert "sqlstate=42501" in caplog.text
    assert privado not in caplog.text
    assert "hoja-no-publicable" not in caplog.text
    sesion.rollback.assert_awaited_once()


async def test_200_confirmados_visibles_desde_otra_conexion_aislada(laboratorio):  # noqa: F811
    """Comprueba un commit real independiente y limpia solo datos de este test.

    laboratorio verifica antes el nombre, puerto y marca de la base efímera.
    No se usa la conexión del .env ni la transacción exterior de otras pruebas.
    """
    import io
    from types import SimpleNamespace

    from openpyxl import Workbook

    from pruebas.test_importacion_personal_aislada import CABECERA

    motor = create_async_engine(
        os.environ["ESART_IMPORTACION_TEST_URL"], hide_parameters=True, connect_args={"ssl": False}
    )
    sufijo = uuid.uuid4().hex[:10]
    codigo = "SIM-PERSIST-" + sufijo
    inicio = 990000000000 + int(sufijo, 16) % 999000
    documentos = [str(inicio + i) for i in range(200)]
    referencia = None
    unidad_id = usuario_id = tipo_id = instructor_id = None
    try:
        async with AsyncSession(motor, expire_on_commit=False) as sesion:
            unidad_id = await sesion.scalar(
                insert(UnidadMilitar.__table__)
                .values(codigo=codigo, nombre="Unidad ficticia de commit")
                .returning(UnidadMilitar.id)
            )
            usuario_id = await sesion.scalar(
                insert(Usuario.__table__).values(usuario="prueba_commit_" + sufijo).returning(Usuario.id)
            )
            tipo_id = await sesion.scalar(
                insert(TipoCurso.__table__)
                .values(
                    codigo="SC-" + sufijo, nombre="Curso commit", modalidad="PRESENCIAL", duracion_semanas=1
                )
                .returning(TipoCurso.id)
            )
            instructor_id = await sesion.scalar(
                insert(Instructores.__table__)
                .values(usuario_id=usuario_id, fecha_ingreso_escuela=date(2026, 1, 1))
                .returning(Instructores.id)
            )
            await sesion.commit()
            libro = Workbook()
            libro.active.title = "CARGUE_PERSONAL"
            libro.active.append(CABECERA)
            for documento in documentos:
                libro.active.append(
                    [documento, "Persona ficticia", "Prueba", "SL", "FEMENINO", "OFICIAL", codigo, True]
                )
            salida = io.BytesIO()
            libro.save(salida)
            hoja, registros = leer_excel(salida.getvalue(), "CARGUE_PERSONAL")
            curso = DatosCurso(
                tipo_id, "Curso commit", instructor_id, date(2026, 2, 1), date(2026, 3, 1), "EN_CURSO"
            )
            respuesta = await guardar_personal(
                sesion, hoja, registros, SimpleNamespace(id=usuario_id, nombre_usuario="prueba_commit"), curso
            )
            referencia = respuesta["importacion_id"]
            assert respuesta["filas_validas"] == 200
        # La sesión que insertó ya se cerró. Esta conexión independiente solo ve datos confirmados.
        async with motor.connect() as otra:
            assert (
                await otra.scalar(
                    select(func.count())
                    .select_from(PersonalMilitar)
                    .where(PersonalMilitar.documento_identidad.in_(documentos))
                )
                == 200
            )
            assert (
                await otra.scalar(
                    select(func.count())
                    .select_from(PersonalMilitar)
                    .where(
                        PersonalMilitar.documento_identidad.in_(documentos),
                        PersonalMilitar.unidad_actual_id == unidad_id,
                        PersonalMilitar.genero == "F",
                    )
                )
                == 200
            )
    finally:
        # Las tablas pertenecen al clúster efímero marcado; jamás se ejecuta en producción.
        async with motor.begin() as limpieza:
            if tipo_id is not None:
                cursos = select(Cursos.id).where(Cursos.tipo_curso_id == tipo_id).scalar_subquery()
                await limpieza.execute(
                    delete(HojaVidaArtillero).where(HojaVidaArtillero.curso_id.in_(cursos))
                )
                await limpieza.execute(delete(Cursos).where(Cursos.tipo_curso_id == tipo_id))
            await limpieza.execute(
                delete(PersonalMilitar).where(PersonalMilitar.documento_identidad.in_(documentos))
            )
            if referencia:
                await limpieza.execute(
                    delete(AuditoriaEvento).where(
                        AuditoriaEvento.detalle["importacion_id"].astext == referencia
                    )
                )
            if instructor_id is not None:
                await limpieza.execute(delete(Instructores).where(Instructores.id == instructor_id))
            if tipo_id is not None:
                await limpieza.execute(delete(TipoCurso).where(TipoCurso.id == tipo_id))
            if usuario_id is not None:
                await limpieza.execute(delete(Usuario).where(Usuario.id == usuario_id))
            if unidad_id is not None:
                await limpieza.execute(delete(UnidadMilitar).where(UnidadMilitar.id == unidad_id))
        await motor.dispose()
