"""Aplica únicamente p0018 a la copia local y verifica la conservación antes del commit."""

import argparse
import asyncio
import os
import sys
import warnings
from getpass import GetPassWarning, getpass
from importlib import import_module
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

BASE = "esart_ensayo"
ROL = "esart_migrador"
ANTERIOR = "p0017_restablecer_totp_admin"
OBJETIVO = "p0018_firma_documental"
SIGUIENTE = "p0019_firma_movil"
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def url_migradora(base=BASE):
    existente = os.environ.get("ESART_MIGRACIONES_URL")
    if existente:
        url = make_url(existente)
    else:
        if not sys.stdin.isatty():
            raise RuntimeError("Se requiere una terminal interactiva para introducir la contraseña.")
        puerto = int(input(f"Puerto de {base} [5432]: ").strip() or "5432")
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            contrasena = getpass(f"Contraseña de {ROL}: ")
        url = URL.create(
            "postgresql+asyncpg",
            username=ROL,
            password=contrasena,
            host="127.0.0.1",
            port=puerto,
            database=base,
        )
    if (
        url.drivername != "postgresql+asyncpg"
        or url.username != ROL
        or url.database != base
        or url.host not in {"127.0.0.1", "::1", "localhost"}
        or url.query
    ):
        raise RuntimeError(f"Se requiere una URL directa de esart_migrador a {base} local.")
    return url


def verificar_destino(conexion, destino=BASE):
    identidad = conexion.execute(
        text("""
        SELECT current_database(), current_user, host(inet_server_addr()), rolsuper,
               current_setting('server_version_num')::integer
        FROM pg_roles WHERE rolname = current_user
    """)
    ).one()
    base, usuario, servidor, superusuario, version_pg = identidad
    if (base, usuario) != (destino, ROL) or servidor not in {"127.0.0.1", "::1"}:
        raise RuntimeError(f"La identidad efectiva de la conexión no corresponde a {destino} local.")
    if superusuario or version_pg // 10000 != 18:
        raise RuntimeError("Se requiere PostgreSQL 18 y un migrador sin privilegios de superusuario.")


def verificar_revision(conexion):
    if conexion.scalars(text("SELECT version_num FROM esart.alembic_version")).all() != [ANTERIOR]:
        raise RuntimeError(f"La revisión de partida debe ser {ANTERIOR}.")


def configuracion_alembic():
    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "migraciones_principal"))
    return config


def auditar_heredado(conexion, destino=BASE):
    conexion.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
    verificar_destino(conexion, destino)
    conexion.execute(text("SET LOCAL search_path TO pg_catalog, pg_temp"))
    if destino == BASE:
        verificar_revision(conexion)
    else:
        if not conexion.scalar(text("SELECT to_regclass('esart.alembic_version') IS NOT NULL")):
            raise RuntimeError("Falta esart.alembic_version; no se puede identificar la revisión.")
        revisiones = conexion.scalars(text("SELECT version_num FROM esart.alembic_version")).all()
        if len(revisiones) != 1:
            raise RuntimeError(f"Se esperaba una revisión activa y se obtuvo {revisiones!r}.")
        actual_revision = revisiones[0]
        scripts = ScriptDirectory.from_config(configuracion_alembic())
        pendientes = list(reversed(list(scripts.iterate_revisions("heads", actual_revision))))
        print(f"Base: {destino}; rol: {ROL}; transacción de solo lectura; revisión actual: {actual_revision}")
        print("Revisiones pendientes: " + (", ".join(r.revision for r in pendientes) or "ninguna"))
        if pendientes:
            print(f"Siguiente revisión: {pendientes[0].revision}")
        if not any(r.revision == OBJETIVO for r in pendientes):
            return
    migracion = import_module(f"migraciones_principal.versions.{OBJETIVO}")
    if destino != BASE and not conexion.scalar(text("SELECT to_regnamespace('esart_firma') IS NOT NULL")):
        print("esart_firma está ausente; p0018 prevé instalar el inventario y las dos tablas documentales.")
        return
    diferencias = []
    estado = {}
    for tabla in migracion._heredado():
        nombre = tabla["tabla"]
        try:
            actual, adoptados = migracion._validar_tabla_heredada(conexion, tabla)
        except RuntimeError as error:
            diferencias.append(str(error))
            continue
        estado[nombre] = (actual, adoptados)
        print(f"{nombre}: compatible")
        base_columnas = {c[0]: c[1:] for c in tabla["columnas"]}
        for campo, tipo, no_nulo, defecto, _, _, _, secuencia in actual["columnas"]:
            if campo not in base_columnas or no_nulo != base_columnas[campo][1]:
                print(f"  columna de p0018 {campo}: tipo={tipo}, NOT NULL={no_nulo}, default={defecto!r}")
            if secuencia:
                print(f"  secuencia propia de {campo}: {secuencia}")
        for campo in sorted(
            migracion.COLUMNAS_NUEVAS.get(nombre, {}).keys() - {c[0] for c in actual["columnas"]}
        ):
            print(f"  columna de p0018 pendiente: {campo}")
        for clase, objetos in adoptados.items():
            for objeto in sorted(objetos):
                print(f"  {clase} adoptables: {objeto!r}")

    for nombre, referencia in migracion._referencia_documental().items():
        if destino != BASE and not migracion._existe_tabla(conexion, nombre):
            print(f"{nombre}: pendiente de creación por p0018")
            continue
        try:
            migracion._validar_documental(conexion, nombre, referencia)
        except RuntimeError as error:
            diferencias.append(str(error))
        else:
            print(f"{nombre}: compatible")

    catalogo_funcion = migracion._catalogo_funcion_autenticacion(conexion)
    if catalogo_funcion is not None:
        print(catalogo_funcion.definicion)
        print(
            f"  propietario={catalogo_funcion.propietario}, ACL={catalogo_funcion.acl}, "
            f"EXECUTE migrador={catalogo_funcion.migrador_ejecuta}, API={catalogo_funcion.api_ejecuta}"
        )
    try:
        funcion = migracion._validar_funciones(conexion)
    except RuntimeError as error:
        diferencias.append(str(error))
    else:
        print(f"{migracion.FUNCION_NUEVA}(): {'compatible' if funcion else 'pendiente de creación'}")
        if len(estado) == len(migracion._heredado()):
            try:
                migracion._validar_precondiciones(conexion, estado)
            except RuntimeError as error:
                diferencias.append(str(error))

    print("Propiedad y permisos de las tablas y secuencias de firma:")
    for fila in conexion.execute(
        text("""
        SELECT c.relname, c.relkind::text, pg_get_userbyid(c.relowner),
               pg_has_role(c.relowner, 'USAGE'), c.relacl::text,
               (SELECT jsonb_object_agg(attname, attacl::text) FROM pg_attribute
                WHERE attrelid = c.oid AND attacl IS NOT NULL)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'esart_firma' AND c.relkind IN ('r', 'S')
        ORDER BY c.relkind, c.relname
    """)
    ):
        print(f"  {tuple(fila)!r}")
    for fila in conexion.execute(
        text("""
        SELECT extname, extversion, nspname FROM pg_extension
        JOIN pg_namespace n ON n.oid = extnamespace ORDER BY extname
    """)
    ):
        print(f"Extensión de PostgreSQL: {tuple(fila)!r}")
    permisos = conexion.execute(
        text("""
        SELECT has_schema_privilege('esart_firma', 'USAGE'),
               has_schema_privilege('esart_firma', 'CREATE'),
               has_table_privilege('esart_ref.usuarios', 'REFERENCES'),
               has_table_privilege('esart.componentes', 'SELECT')
                   AND has_table_privilege('esart.componentes', 'INSERT'),
               has_table_privilege('esart.rol_permisos', 'SELECT')
                   AND has_table_privilege('esart.rol_permisos', 'INSERT'),
               has_table_privilege('esart.alembic_version', 'UPDATE')
    """)
    ).one()
    print(
        "Permisos efectivos del migrador (USAGE/CREATE firma, REFERENCES usuarios, "
        f"SELECT/INSERT componentes y rol_permisos, UPDATE alembic_version): {tuple(permisos)!r}"
    )
    if diferencias:
        raise RuntimeError("\n".join(diferencias))


def aplicar(conexion):
    verificar_destino(conexion)
    conexion.execute(text("LOCK TABLE esart.alembic_version IN EXCLUSIVE MODE"))
    verificar_revision(conexion)

    migracion = import_module(f"migraciones_principal.versions.{OBJETIVO}")
    siguiente = import_module(f"migraciones_principal.versions.{SIGUIENTE}")
    tablas = sorted([t["tabla"] for t in migracion._heredado()] + list(migracion.TABLAS_DOCUMENTALES))
    encontradas = conexion.scalars(
        text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'esart_firma' AND c.relkind = 'r'
    """)
    ).all()
    if set(encontradas) != set(tablas):
        raise RuntimeError("La copia debe contener las 23 tablas de firma esperadas.")
    for tabla in tablas:
        conexion.execute(text(f"LOCK TABLE ONLY esart_firma.{tabla} IN ACCESS EXCLUSIVE MODE"))  # noqa: S608

    columnas = {tabla: [c[0] for c in migracion._huella_columnas(conexion, tabla)] for tabla in tablas}

    def oids():
        return {
            tabla: conexion.scalar(text("SELECT to_regclass(:tabla)::oid"), {"tabla": f"esart_firma.{tabla}"})
            for tabla in tablas
        }

    conexion.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    oids_antes = oids()
    antes = migracion._huella_datos(conexion, columnas)
    if (antes["documentos"][0], antes["versiones_documento"][0]) != (3, 4):
        raise RuntimeError("La copia no tiene los 3 documentos y las 4 versiones esperados.")

    configuracion = configuracion_alembic()
    configuracion.attributes["connection"] = conexion
    command.upgrade(configuracion, OBJETIVO)

    if conexion.scalars(text("SELECT version_num FROM esart.alembic_version")).all() != [OBJETIVO]:
        raise RuntimeError("Alembic no registró la revisión p0018.")
    despues = migracion._huella_datos(conexion, columnas)
    if antes != despues or oids_antes != oids():
        raise RuntimeError("Cambió el contenido original o la identidad de alguna tabla.")

    if siguiente.down_revision != OBJETIVO:
        raise RuntimeError("La revisión p0019 no está enlazada a p0018.")
    for tabla, campos in {
        "solicitudes_firma": ("estado", "abierta_en", "decidida_en", "motivo_rechazo"),
        "autorizaciones_firmantes": ("revocado_en",),
        "consentimientos_firma": (),
        "desafios_autenticacion": (),
        "firmas_certificado": (),
    }.items():
        if not set(campos).issubset(columnas[tabla]):
            raise RuntimeError(f"Faltan columnas requeridas por p0019 en {tabla}.")
    return oids_antes, antes


async def principal(solo_auditar, destino=BASE):
    if destino != BASE and not solo_auditar:
        raise RuntimeError("Este ejecutor solo admite esart_db en modo de auditoría.")
    url = url_migradora(destino)
    os.environ["ESART_VALIDAR_P0018_COPIA"] = "1"
    motor = create_async_engine(url, connect_args={"ssl": False, "timeout": 5}, hide_parameters=True)
    try:
        async with motor.begin() as conexion:
            if solo_auditar:
                await conexion.run_sync(auditar_heredado, destino)
                return
            oids, huellas = await conexion.run_sync(aplicar)
    finally:
        await motor.dispose()
    print(f"{BASE}: {ANTERIOR} -> {OBJETIVO}. {SIGUIENTE} pendiente.")
    print("tabla,oid,filas,sha256_antes_y_despues")
    for tabla, (filas, huella) in huellas.items():
        print(f"{tabla},{oids[tabla]},{filas},{huella}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--solo-auditar", action="store_true", help="Compara el inventario sin ejecutar Alembic."
    )
    parser.add_argument("--base", choices=(BASE, "esart_db"), default=BASE)
    opciones = parser.parse_args()
    asyncio.run(principal(opciones.solo_auditar, opciones.base))
