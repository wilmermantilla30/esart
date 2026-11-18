"""Política administrativa vigente y privilegios mínimos solo en PostgreSQL efímero."""

import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyotp
import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from aplicacion.modelos import (
    AuditoriaEvento,
    Componente,
    PersonalMilitar,
    Rol,
    RolPermiso,
    Usuario,
    UsuarioPermiso,
    UsuarioRoles,
)
from aplicacion.modelos.seguridad import LimiteInicioIP
from aplicacion.modelos.totp import PoliticaAccion
from aplicacion.seguridad.permisos import (
    OperacionCRUD,
    es_administrador,
    obtener_permisos_efectivos,
    tiene_permiso_codigo,
    tiene_permiso_componente,
)
from aplicacion.servicios import malla_permisos
from aplicacion.servicios.importacion_personal import DatosCurso, guardar_personal, leer_excel
from aplicacion.servicios.menu import obtener_menu_y_permisos
from aplicacion.servicios.seguridad_login import reloj_servidor
from aplicacion.servicios.totp import TotpService
from pruebas.test_diagnostico_importacion import sesion_real  # noqa: F401
from pruebas.test_importacion_personal_aislada import (  # noqa: F401
    CURSO_PRUEBA,
    enviar,
    excel_personal,
    laboratorio,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
async def administrador(laboratorio):  # noqa: F811
    """Admin real sin asignaciones CRUD; el nombre no participa de la autorización."""
    sesion, actor, unidad_id = laboratorio
    await sesion.execute(delete(UsuarioPermiso).where(UsuarioPermiso.usuario_id == actor.id))
    rol = Rol(codigo="ADMINISTRADOR", nombre="Administrador", activo=True)
    sesion.add(rol)
    await sesion.flush()
    sesion.add(UsuarioRoles(usuario_id=actor.id, rol_id=rol.id))
    usuario = await sesion.get(Usuario, actor.id)
    usuario.usuario = "admin.esart"
    for codigo in ("USUARIOS", "PERMISOS", "AUDITORIA"):
        sesion.add(
            Componente(
                codigo=codigo, nombre=codigo, ruta_angular="/administracion/" + codigo.lower(), activo=True
            )
        )
    await sesion.commit()
    return sesion, actor, rol, unidad_id


async def test_admin_tiene_todo_sin_crud_y_excepciones_no_lo_restringen(administrador):
    sesion, actor, _, _ = administrador
    assert await sesion.scalar(select(func.count()).select_from(RolPermiso)) == 0
    for codigo in ("USUARIOS", "PERMISOS", "AUDITORIA", "PERSONAL_CARGUE_EXCEL"):
        for operacion in OperacionCRUD:
            assert await tiene_permiso_componente(sesion, actor.id, codigo, operacion)
    componente = await sesion.scalar(select(Componente).where(Componente.codigo == "USUARIOS"))
    sesion.add(UsuarioPermiso(usuario_id=actor.id, componente_id=componente.id, puede_acceder=False))
    await sesion.commit()
    assert await tiene_permiso_componente(sesion, actor.id, "USUARIOS", OperacionCRUD.CREATE)
    assert await tiene_permiso_codigo(sesion, actor.id, "PERMISO_FUNCIONAL_DE_POLITICA")
    assert not await tiene_permiso_componente(sesion, actor.id, "NO_EXISTE", OperacionCRUD.READ)
    componente.activo = False
    await sesion.commit()
    assert not await tiene_permiso_componente(sesion, actor.id, "USUARIOS", OperacionCRUD.READ)


async def test_menu_y_malla_admin_reflejan_politica_completa(administrador):
    sesion, actor, _, _ = administrador
    permisos = await obtener_permisos_efectivos(sesion, actor.id)
    assert permisos and all(
        p.puede_crear and p.puede_leer and p.puede_actualizar and p.puede_eliminar for p in permisos
    )
    menu = await obtener_menu_y_permisos(sesion, actor.id)
    assert {"USUARIOS", "PERMISOS", "AUDITORIA"} <= set(menu.permisos)
    assert all(set(e.operaciones) == {"crear", "leer", "actualizar", "eliminar"} for e in menu.menu)
    malla = await malla_permisos.obtener_permisos_rol(sesion, "ADMINISTRADOR")
    assert not malla.editable
    assert all(f.permisos.acceder and f.permisos.crear and f.permisos.eliminar for f in malla.filas)
    componente = await sesion.scalar(select(Componente).where(Componente.codigo == "USUARIOS"))
    sesion.add(UsuarioPermiso(usuario_id=actor.id, componente_id=componente.id, puede_acceder=False))
    await sesion.commit()
    individual = await malla_permisos.obtener_permisos_usuario(sesion, actor.id)
    assert not individual.editable
    assert all(
        f.modo == "HEREDAR" and f.excepcion is None and f.rol.crear and f.efectivo.crear
        for f in individual.filas
    )


async def test_revocar_rol_o_desactivar_usuario_quita_la_concesion(administrador):
    sesion, actor, rol, _ = administrador
    rol.activo = False
    await sesion.commit()
    assert not await es_administrador(sesion, actor.id)
    assert not await tiene_permiso_componente(sesion, actor.id, "USUARIOS", OperacionCRUD.READ)
    rol.activo = True
    usuario = await sesion.get(Usuario, actor.id)
    usuario.activo = False
    await sesion.commit()
    assert not await es_administrador(sesion, actor.id)
    assert await obtener_permisos_efectivos(sesion, actor.id) == []
    usuario.activo = True
    await sesion.execute(delete(UsuarioRoles).where(UsuarioRoles.usuario_id == actor.id))
    await sesion.commit()
    assert not await tiene_permiso_componente(sesion, actor.id, "USUARIOS", OperacionCRUD.DELETE)


async def test_nombre_o_rol_en_identidad_cliente_no_conceden_acceso(cliente_api, laboratorio):  # noqa: F811
    sesion, actor, _ = laboratorio
    actor.rol = "ADMINISTRADOR"  # dato ajeno a la consulta autorizativa: debe ignorarse
    usuario = await sesion.get(Usuario, actor.id)
    usuario.usuario = "admin.esart"
    await sesion.execute(delete(UsuarioPermiso).where(UsuarioPermiso.usuario_id == actor.id))
    await sesion.commit()
    assert not await es_administrador(sesion, actor.id)
    assert not await tiene_permiso_codigo(sesion, actor.id, "PERMISO_FUNCIONAL_DE_POLITICA")
    respuesta = await enviar(cliente_api, excel_personal())
    assert respuesta.status_code == 403
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0
    assert await sesion.scalar(select(AuditoriaEvento.accion)) == "ACCESO_DENEGADO"


async def test_otros_roles_conservan_herencia_y_excepciones(laboratorio):  # noqa: F811
    sesion, actor, _ = laboratorio
    await sesion.execute(delete(UsuarioPermiso).where(UsuarioPermiso.usuario_id == actor.id))
    rol = Rol(codigo="USUARIO", nombre="Usuario", activo=True)
    sesion.add(rol)
    await sesion.flush()
    componente = await sesion.scalar(select(Componente).where(Componente.codigo == "PERSONAL_CARGUE_EXCEL"))
    sesion.add_all(
        [
            UsuarioRoles(usuario_id=actor.id, rol_id=rol.id),
            RolPermiso(
                rol_id=rol.id,
                componente_id=componente.id,
                puede_acceder=True,
                puede_leer=True,
                puede_crear=False,
            ),
        ]
    )
    await sesion.commit()
    assert await tiene_permiso_componente(sesion, actor.id, componente.codigo, OperacionCRUD.READ)
    assert not await tiene_permiso_componente(sesion, actor.id, componente.codigo, OperacionCRUD.CREATE)
    excepcion = UsuarioPermiso(usuario_id=actor.id, componente_id=componente.id, puede_acceder=False)
    sesion.add(excepcion)
    await sesion.commit()
    assert not await tiene_permiso_componente(sesion, actor.id, componente.codigo, OperacionCRUD.READ)
    excepcion.puede_acceder = excepcion.puede_crear = True
    await sesion.commit()
    assert await tiene_permiso_componente(sesion, actor.id, componente.codigo, OperacionCRUD.CREATE)
    assert not await tiene_permiso_componente(sesion, actor.id, componente.codigo, OperacionCRUD.READ)


async def test_admin_jwt_mfa_importa_200_y_no_omite_codigo_totp(cliente_api, administrador, sesion_real):  # noqa: F811
    sesion, actor, _, unidad_id = administrador
    _, _, factor = sesion_real
    conexion = await sesion.connection()
    await conexion.run_sync(lambda c: LimiteInicioIP.__table__.create(c, checkfirst=True))
    sesion.add(
        PoliticaAccion(
            codigo="PERSONAL_CARGUE_EXCEL",
            nombre="Importar personal",
            modulo="PERSONAL",
            requiere_totp=True,
            activa=True,
            permiso_requerido="PERSONAL_CARGUE_EXCEL",
        )
    )
    await sesion.commit()
    yo = await cliente_api.get("/api/auth/yo")
    assert yo.status_code == 200 and yo.json()["rol"] == "ADMINISTRADOR"
    assert await sesion.scalar(select(func.count()).select_from(RolPermiso)) == 0
    sin_codigo = await enviar(cliente_api, excel_personal(200))
    assert sin_codigo.status_code == 409 and sin_codigo.json()["error"]["codigo"] == "TOTP_REQUERIDO"
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0
    ahora = await reloj_servidor(sesion)
    await sesion.refresh(factor)  # el rechazo sin código ejecutó rollback y expiró las instancias ORM
    codigo = pyotp.TOTP(TotpService.descifrar(factor)).at(int(ahora.timestamp()))
    respuesta = await enviar(cliente_api, excel_personal(200), codigo_totp=codigo)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["filas_validas"] == 200
    assert (
        await sesion.scalar(
            select(func.count())
            .select_from(PersonalMilitar)
            .where(PersonalMilitar.unidad_actual_id == unidad_id)
        )
        == 200
    )
    assert (
        await sesion.scalar(
            select(func.count())
            .select_from(AuditoriaEvento)
            .where(AuditoriaEvento.accion == "IMPORTACION_EXCEL")
        )
        == 1
    )


@pytest.mark.parametrize("estado", ["expirada", "bloqueada"])
async def test_admin_no_omite_expiracion_ni_bloqueo(cliente_api, administrador, sesion_real, estado):  # noqa: F811
    sesion, actor, _, _ = administrador
    _, registro, _ = sesion_real
    if estado == "expirada":
        registro.fecha_ultima_actividad = datetime.now(UTC) - timedelta(hours=1)
    else:
        usuario = await sesion.get(Usuario, actor.id)
        usuario.bloqueado_hasta = datetime.now(UTC) + timedelta(hours=1)
    await sesion.commit()
    assert (await cliente_api.get("/api/auth/yo")).status_code == 401
    assert (await enviar(cliente_api, excel_personal())).status_code == 401
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0


async def test_admin_no_omite_validacion_de_unidades(cliente_api, administrador):
    sesion, _, _, _ = administrador
    respuesta = await enviar(cliente_api, excel_personal(unidad="UNIDAD-INEXISTENTE"))
    assert respuesta.status_code == 422
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0


async def test_sql_propuesto_es_suficiente_sin_privilegios_excesivos(laboratorio):  # noqa: F811
    """Ejecuta la propuesta SOLO en el clúster marcado, nunca en la base operativa."""
    sesion, actor, _ = laboratorio
    motor = create_async_engine(
        os.environ["ESART_IMPORTACION_TEST_URL"], hide_parameters=True, connect_args={"ssl": False}
    )
    try:
        async with motor.connect() as conexion:
            await conexion.execute(
                text(
                    "CREATE ROLE esart_aplicacion NOLOGIN NOSUPERUSER "
                    "NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
                )
            )
            await conexion.commit()
            original = await conexion.get_raw_connection()
            propuestas = Path(__file__).resolve().parents[1] / "propuestas"
            await original.driver_connection.execute(
                (propuestas / "habilitar_insert_personal.sql").read_text(encoding="utf-8-sig")
            )
        # p0011 altera tablas que la transacción del laboratorio ya tocó: en otra conexión
        # su ALTER TABLE esperaría indefinidamente, así que se aplica en la misma (sin BEGIN/COMMIT).
        p0011 = (propuestas / "p0011_cursos_importacion.sql").read_text(encoding="utf-8-sig")
        p0011 = "\n".join(linea for linea in p0011.splitlines() if linea.strip() not in ("BEGIN;", "COMMIT;"))
        crudo = await (await sesion.connection()).get_raw_connection()
        await crudo.driver_connection.execute(p0011)
        await sesion.execute(text("SET LOCAL ROLE esart_aplicacion"))
        privilegios = (
            (
                await sesion.execute(
                    text("""
            SELECT has_schema_privilege('esart','USAGE') AS uso,
                   has_schema_privilege('esart_ref','USAGE') AS catalogo,
                   has_column_privilege('esart.personal_militar','documento_identidad','INSERT') AS insertar,
                   has_column_privilege('esart_ref.unidades_militares','codigo','SELECT') AS leer_unidad,
                   has_table_privilege('esart.personal_militar','UPDATE') AS actualizar,
                   has_table_privilege('esart.personal_militar','DELETE') AS eliminar,
                   has_table_privilege('esart_ref.unidades_militares','INSERT') AS crear_unidad,
                   has_schema_privilege('esart','CREATE') AS crear,
                   has_sequence_privilege(
                       pg_get_serial_sequence('esart.personal_militar','id'),'USAGE') AS secuencia,
                   rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
            FROM pg_roles WHERE rolname=current_user
        """)
                )
            )
            .mappings()
            .one()
        )
        assert all(privilegios[k] for k in ("uso", "catalogo", "insertar", "leer_unidad"))
        assert not any(
            privilegios[k]
            for k in (
                "actualizar",
                "eliminar",
                "crear_unidad",
                "crear",
                "secuencia",
                "rolsuper",
                "rolcreatedb",
                "rolcreaterole",
                "rolbypassrls",
            )
        )
        hoja, filas = leer_excel(excel_personal(), "CARGUE_PERSONAL")
        curso = DatosCurso(
            CURSO_PRUEBA["tipo_curso_id"],
            "Curso",
            CURSO_PRUEBA["comandante_id"],
            date(2026, 2, 1),
            date(2026, 3, 1),
            "EN_CURSO",
        )
        respuesta = await guardar_personal(sesion, hoja, filas, actor, curso)
        assert respuesta["filas_validas"] == 1
        # Con otro grado, la misma cuenta actualiza el grado y agrega historial (p0011).
        hoja, filas = leer_excel(excel_personal(grado="CS"), "CARGUE_PERSONAL")
        curso = replace(curso, fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 7, 1), estado="CULMINADO")
        respuesta = await guardar_personal(sesion, hoja, filas, actor, curso)
        assert respuesta["grados_actualizados"] == 1 and respuesta["curso_codigo"] == "2"
        assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 1
    finally:
        await motor.dispose()
