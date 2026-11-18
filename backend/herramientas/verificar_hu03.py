"""Prueba real de HU-03 exclusivamente en esart_hu03_pruebas, inicialmente vacía."""

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from aplicacion.base_datos.base import BaseModelo
from aplicacion.base_datos.configuracion import ConfiguracionConexion
from aplicacion.modelos import UsuarioPermiso
from aplicacion.seguridad.permisos import OperacionCRUD, tiene_permiso_codigo, tiene_permiso_componente
from herramientas.inspeccionar_base_datos import inspeccionar

BASE_PRUEBAS = "esart_hu03_pruebas"


def exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise RuntimeError(mensaje)


def motor_para(url):
    return create_async_engine(
        url,
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={"timeout": 5, "command_timeout": 30},
    )


async def preparar_base(configuracion: ConfiguracionConexion, crear: bool):
    url = make_url(configuracion.url_base_datos.get_secret_value())
    exigir(url.username == "esart_aplicacion", "Se requiere la cuenta esart_aplicacion.")
    # Solo SELECT y, si se autorizó expresamente, CREATE DATABASE con nombre constante.
    motor = motor_para(url)
    try:
        async with motor.connect() as conexion:
            rol = (
                (
                    await conexion.execute(
                        text("SELECT rolsuper, rolcreatedb FROM pg_roles WHERE rolname=current_user")
                    )
                )
                .mappings()
                .one()
            )
            exigir(not rol["rolsuper"], "No se permite utilizar un superusuario.")
            existe = await conexion.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:nombre"), {"nombre": BASE_PRUEBAS}
            )
        if not existe:
            exigir(crear, "La base aislada no existe; use --crear-base solo con autorización.")
            exigir(
                rol["rolcreatedb"],
                "La cuenta no tiene CREATEDB. Un administrador debe ejecutar fuera de una transacción: "
                "CREATE DATABASE esart_hu03_pruebas OWNER esart_aplicacion;",
            )
            async with motor.connect() as conexion:
                conexion = await conexion.execution_options(isolation_level="AUTOCOMMIT")
                await conexion.execute(text("CREATE DATABASE esart_hu03_pruebas"))
            print("Base aislada creada.")
    finally:
        await motor.dispose()
    return url.set(database=BASE_PRUEBAS)


async def rechazar(conexion, sentencia, parametros=None, *, codigo="23514"):
    """Cada caso inválido se revierte con SAVEPOINT; comprueba SQLSTATE real."""
    try:
        async with conexion.begin_nested():
            await conexion.execute(text(sentencia), parametros or {})
    except DBAPIError as error:
        exigir(getattr(error.orig, "sqlstate", None) == codigo, "SQLSTATE inesperado en restricción.")
    else:
        raise RuntimeError("La base aceptó una operación que debía rechazar.")


def comprobar_esquema(conexion):
    inspector = inspect(conexion)
    exigir(
        set(inspector.get_table_names()) == set(BaseModelo.metadata.tables) | {"alembic_version"},
        "El inventario no coincide con las 22 tablas.",
    )
    contexto = MigrationContext.configure(
        conexion, opts={"compare_type": True, "compare_server_default": True}
    )
    exigir(not compare_metadata(contexto, BaseModelo.metadata), "Hay diferencias entre ORM y migración.")
    for tabla in BaseModelo.metadata.tables.values():
        checks_orm = {str(c.name) for c in tabla.constraints if isinstance(c, CheckConstraint)}
        checks_bd = {c["name"] for c in inspector.get_check_constraints(tabla.name)}
        exigir(checks_orm == checks_bd, f"CHECK no coinciden en {tabla.name}.")


async def comprobar_datos(conexion):
    # Datos sintéticos solo dentro de una transacción que se revierte íntegramente.
    rol, usuario, unidad, personal, hoja, curso, certificado, cargo, componente = [uuid4() for _ in range(9)]
    datos = {
        "r": rol,
        "u": usuario,
        "un": unidad,
        "p": personal,
        "h": hoja,
        "tc": curso,
        "te": certificado,
        "ca": cargo,
        "co": componente,
    }
    sentencias = [
        "INSERT INTO roles(id,codigo,nombre) VALUES (:r,'ADMINISTRADOR','Prueba')",
        "INSERT INTO usuarios(id,nombre_usuario,nombre_completo,hash_contrasena,rol_id) "
        "VALUES (:u,'Hu03','Prueba','hash-sintetico-no-utilizable',:r)",
        "INSERT INTO unidades_militares(id,codigo,nombre) VALUES (:un,'HU03','Prueba')",
        "INSERT INTO personal_militar(id,numero_documento,primer_nombre,primer_apellido,grado,categoria,"
        "estado_servicio,unidad_militar_id) "
        "VALUES (:p,'12345678','Prueba','Prueba','LIBRE','OFICIAL','ACTIVO',:un)",
        "INSERT INTO hoja_vida_artillero(id,personal_militar_id) VALUES (:h,:p)",
        "INSERT INTO tipos_curso(id,codigo,nombre) VALUES (:tc,'HU03','Prueba')",
        "INSERT INTO tipos_certificacion(id,codigo,nombre) VALUES (:te,'HU03','Prueba')",
        "INSERT INTO tipos_cargo(id,codigo,nombre) VALUES (:ca,'HU03','Prueba')",
        "INSERT INTO componentes(id,codigo,nombre) VALUES (:co,'HU03','Prueba')",
        "INSERT INTO rol_permisos(rol_id,componente_id,puede_acceder,puede_crear,puede_leer,"
        "puede_actualizar,puede_eliminar) VALUES (:r,:co,true,true,true,true,true)",
    ]
    for sql in sentencias:
        await conexion.execute(text(sql), datos)
    casos_check = [
        "UPDATE roles SET codigo='OTRO' WHERE id=:r",
        "UPDATE personal_militar SET numero_documento='abc' WHERE id=:p",
        "UPDATE personal_militar SET categoria='OTRA' WHERE id=:p",
        "UPDATE personal_militar SET estado_servicio='OTRO' WHERE id=:p",
        "UPDATE tipos_curso SET vigencia_meses=0 WHERE id=:tc",
        "UPDATE tipos_curso SET nota_minima_aprobacion=6 WHERE id=:tc",
        "INSERT INTO artillero_cursos(hoja_vida_artillero_id,tipo_curso_id,estado) VALUES (:h,:tc,'OTRO')",
        "INSERT INTO artillero_cursos(hoja_vida_artillero_id,tipo_curso_id,estado,nota_final) "
        "VALUES (:h,:tc,'APROBADO',6)",
        "INSERT INTO artillero_cursos(hoja_vida_artillero_id,tipo_curso_id,estado,fecha_inicio,fecha_fin) "
        "VALUES (:h,:tc,'APROBADO','2026-02-01','2026-01-01')",
        "INSERT INTO artillero_certificaciones(hoja_vida_artillero_id,tipo_certificacion_id,estado,"
        "fecha_expedicion) VALUES (:h,:te,'OTRA','2026-01-01')",
        "INSERT INTO artillero_certificaciones(hoja_vida_artillero_id,tipo_certificacion_id,estado,"
        "fecha_expedicion,fecha_vencimiento) VALUES (:h,:te,'ACTIVA','2026-02-01','2026-01-01')",
        "INSERT INTO requisitos_habilitacion(tipo_requisito,descripcion) VALUES ('OTRO','Prueba')",
        "INSERT INTO requisitos_habilitacion(tipo_requisito,descripcion) VALUES ('CURSO','Prueba')",
        "INSERT INTO artillero_cargos(hoja_vida_artillero_id,tipo_cargo_id,fecha_inicio,fecha_fin) "
        "VALUES (:h,:ca,'2026-02-01','2026-01-01')",
        "INSERT INTO importaciones_excel(usuario_id,nombre_archivo,hash_sha256_archivo,estado) "
        "VALUES (:u,'prueba.xlsx',repeat('a',64),'OTRO')",
        "INSERT INTO auditoria_eventos(accion) VALUES ('OTRA')",
        "UPDATE rol_permisos SET puede_acceder=false WHERE rol_id=:r AND componente_id=:co",
        "INSERT INTO usuario_permisos(usuario_id,componente_id,puede_leer) VALUES (:u,:co,true)",
    ]
    for sql in casos_check:
        await rechazar(conexion, sql, datos)
    await rechazar(
        conexion, "INSERT INTO unidades_militares(codigo,nombre) VALUES ('HU03','Duplicada')", codigo="23505"
    )
    await rechazar(
        conexion, "INSERT INTO hoja_vida_artillero(personal_militar_id) VALUES (:p)", datos, codigo="23505"
    )
    await rechazar(
        conexion,
        "INSERT INTO usuarios(nombre_usuario,nombre_completo,hash_contrasena,rol_id) "
        "VALUES ('hu03','Duplicado','sintetico',:r)",
        datos,
        codigo="23505",
    )
    for _ in range(2):
        sql = "INSERT INTO importaciones_excel(usuario_id,nombre_archivo,hash_sha256_archivo,estado) "
        sql += "VALUES (:u,'prueba.xlsx',repeat('a',64),'RECHAZADA')"
        if _ == 0:
            await conexion.execute(text(sql), datos)
        else:
            await rechazar(conexion, sql, datos, codigo="23505")
    await rechazar(
        conexion, "INSERT INTO sesiones_usuario(id,usuario_id) VALUES (:x,:x)", {"x": uuid4()}, codigo="23503"
    )
    await conexion.execute(text("INSERT INTO auditoria_eventos(accion) VALUES ('LOGIN_FALLIDO')"))
    privilegios = (
        await conexion.execute(
            text(
                "SELECT has_table_privilege(current_user,'public.auditoria_eventos','INSERT'), "
                "has_table_privilege(current_user,'public.auditoria_eventos','SELECT'), "
                "has_table_privilege(current_user,'public.auditoria_eventos','UPDATE'), "
                "has_table_privilege(current_user,'public.auditoria_eventos','DELETE'), "
                "has_table_privilege(current_user,'public.auditoria_eventos','TRUNCATE')"
            )
        )
    ).one()
    exigir(tuple(privilegios) == (True, True, False, False, False), "Privilegios de auditoría incorrectos.")
    # Probar los triggers aun si un operador concediera DML por error. Esta
    # concesión temporal solo existe en la transacción sintética que se revierte.
    await conexion.execute(text("GRANT UPDATE, DELETE, TRUNCATE ON public.auditoria_eventos TO CURRENT_USER"))
    for sql in (
        "UPDATE auditoria_eventos SET resultado='OTRO'",
        "DELETE FROM auditoria_eventos",
        "TRUNCATE auditoria_eventos",
    ):
        await rechazar(conexion, sql, codigo="P0001")
    for tabla in BaseModelo.metadata.tables.values():
        if "fecha_actualizacion" not in tabla.c:
            continue
        # Inserción de filas adicionales no es necesaria para verificar la función
        # en cada tabla: el catálogo debe mostrar el trigger en las 19 tablas.
        cantidad = await conexion.scalar(
            text(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid=to_regclass(:tabla) "
                "AND tgname=:trigger AND NOT tgisinternal"
            ),
            {"tabla": f"public.{tabla.name}", "trigger": f"tr_{tabla.name}_fecha"},
        )
        exigir(cantidad == 1, f"Falta trigger de fecha en {tabla.name}.")
    fecha = await conexion.scalar(
        text(
            "UPDATE unidades_militares SET fecha_actualizacion='2000-01-01' WHERE id=:un "
            "RETURNING fecha_actualizacion=now()"
        ),
        datos,
    )
    exigir(fecha is True, "El trigger no actualizó fecha_actualizacion.")
    sesion = AsyncSession(bind=conexion, join_transaction_mode="create_savepoint")
    try:
        permiso = uuid4()
        await conexion.execute(
            text(
                "INSERT INTO permisos(id,codigo,descripcion) VALUES (:id,'VER_DOCUMENTO_COMPLETO','Prueba')"
            ),
            {"id": permiso},
        )
        await conexion.execute(
            text("INSERT INTO roles_permisos(rol_id,permiso_id) VALUES (:rol,:permiso)"),
            {"rol": rol, "permiso": permiso},
        )
        exigir(
            await tiene_permiso_codigo(sesion, usuario, "VER_DOCUMENTO_COMPLETO"),
            "El permiso por código no se reconoció.",
        )
        for accion in OperacionCRUD:
            exigir(await tiene_permiso_componente(sesion, usuario, "HU03", accion), "Permiso de rol perdido.")
        sesion.add(UsuarioPermiso(usuario_id=usuario, componente_id=componente))
        await sesion.flush()
        for accion in OperacionCRUD:
            exigir(
                not await tiene_permiso_componente(sesion, usuario, "HU03", accion),
                "La excepción individual no denegó.",
            )
        excepcion = await sesion.get(UsuarioPermiso, (usuario, componente))
        excepcion.puede_acceder = excepcion.puede_leer = True
        await sesion.flush()
        exigir(
            await tiene_permiso_componente(sesion, usuario, "HU03", OperacionCRUD.READ),
            "La excepción individual no concedió READ.",
        )
        exigir(
            not await tiene_permiso_componente(sesion, usuario, "HU03", OperacionCRUD.DELETE),
            "La excepción heredó indebidamente DELETE.",
        )
        await conexion.execute(text("UPDATE usuarios SET activo=false WHERE id=:u"), datos)
        exigir(
            not await tiene_permiso_componente(sesion, usuario, "HU03", OperacionCRUD.READ),
            "Usuario inactivo autorizado.",
        )
        exigir(
            not await tiene_permiso_codigo(sesion, usuario, "VER_DOCUMENTO_COMPLETO"),
            "Código no asignado autorizado.",
        )
    finally:
        await sesion.close()
    print(f"CHECK: {len(casos_check)} casos rechazados; UNIQUE, FK, auditoría y CRUD verificados.")


async def verificar(configuracion: ConfiguracionConexion, crear: bool):
    inventario = await inspeccionar(configuracion)
    print("Conexión origen (solo lectura):", inventario["conexion"])
    print("Tablas origen:", inventario["tablas"], "Alembic:", inventario["alembic"])
    url = await preparar_base(configuracion, crear)
    config_pruebas = ConfiguracionConexion(
        _env_file=None,
        entorno="pruebas",
        url_base_datos=url.render_as_string(hide_password=False),
    )
    motor = motor_para(url)
    configuracion_alembic = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    configuracion_alembic.attributes["configuracion_conexion"] = config_pruebas

    def ejecutar(conexion, accion, destino):
        configuracion_alembic.attributes["connection"] = conexion
        accion(configuracion_alembic, destino)

    try:
        async with motor.connect() as conexion:
            identidad = (
                await conexion.execute(
                    text("SELECT current_database(), current_user, inet_server_port(), current_schema()")
                )
            ).one()
            print("Destino aislado:", tuple(identidad))
            exigir(
                identidad[0] == BASE_PRUEBAS
                and identidad[1] == "esart_aplicacion"
                and identidad[3] == "public",
                "Destino de pruebas no permitido.",
            )
            tablas = await conexion.run_sync(lambda c: inspect(c).get_table_names())
            exigir(not tablas, "La base de pruebas debe estar vacía; no se elimina información existente.")
            await conexion.rollback()
            # No dejar un esquema parcialmente validado si falla un caso. Los
            # datos sintéticos se revierten antes de confirmar el primer upgrade.
            async with conexion.begin():
                await conexion.run_sync(ejecutar, command.upgrade, "head")
                await conexion.run_sync(comprobar_esquema)
                async with conexion.begin_nested() as transaccion:
                    await comprobar_datos(conexion)
                    await transaccion.rollback()
            await conexion.run_sync(ejecutar, command.downgrade, "base")
            await conexion.commit()
            restantes = await conexion.run_sync(lambda c: inspect(c).get_table_names())
            exigir(restantes == ["alembic_version"], "Downgrade dejó tablas de la revisión.")
            funciones = await conexion.scalar(
                text(
                    "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' AND p.proname IN "
                    "('actualizar_fecha_actualizacion','impedir_modificacion_auditoria')"
                )
            )
            exigir(funciones == 0, "Downgrade dejó funciones propias.")
            await conexion.rollback()
            await conexion.run_sync(ejecutar, command.upgrade, "head")
            await conexion.commit()
            await conexion.run_sync(comprobar_esquema)
            version = await conexion.scalar(text("SELECT version_num FROM alembic_version"))
            exigir(version == "0001", "Revisión final inesperada.")
            print(
                "OK: upgrade head, esquema/ORM, restricciones, triggers, downgrade base y nuevo upgrade head."
            )
            print("La base aislada queda en 0001 sin datos sintéticos de prueba.")
    finally:
        await motor.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo-env", type=Path, required=True)
    parser.add_argument("--crear-base", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(verificar(ConfiguracionConexion(_env_file=args.archivo_env), args.crear_base))
    except Exception as error:
        # No mostrar excepciones de drivers que puedan exponer conexión o parámetros.
        if isinstance(error, RuntimeError):
            print(str(error))
        else:
            print(f"Verificación detenida ({type(error).__name__}); no se muestran secretos.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
