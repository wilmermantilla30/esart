"""Concilia el esquema heredado de firma y crea o adopta las tablas documentales.

La revisión conserva las filas existentes y bloquea el downgrade por falta de
un registro de procedencia de objetos y concesiones.
"""

# El SQL se arma solo con constantes de este módulo y del inventario versionado (nunca con datos
# de usuario); las líneas de DDL se dejan completas para poder leerlas.
# ruff: noqa: E501, S608

import json
import re
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "p0018_firma_documental"
down_revision = "p0017_restablecer_totp_admin"
branch_labels = None
depends_on = None

ESQUEMA = "esart_firma"
CUENTA_APLICACION = "esart_aplicacion"
ARCHIVO_HEREDADO = Path(__file__).resolve().parents[1] / "datos" / "p0018_esart_firma_heredado.json"
TABLAS_DOCUMENTALES = ("documentos", "versiones_documento")
# Autenticación heredada que queda deshabilitada (debe estar vacía para conciliar sin decidir datos).
TABLAS_AUTENTICACION_HEREDADA = ("totp_factores", "totp_recuperacion", "sesiones_firma")
COLUMNAS_NUEVAS = {
    "identidades": {"usuario_id": "bigint"},
    "evidencias": {"documento_id": "uuid"},
    "solicitudes_firma": {"documento_id": "uuid", "documento_version_id": "uuid"},
}
FUNCION_HEREDADA = "bloquear_mutacion_evidencia"
FUNCION_NUEVA = "rechazar_autenticacion_heredada"
CUERPO_FUNCION = """
BEGIN
  RAISE EXCEPTION 'Mecanismo heredado deshabilitado (%): la autenticación y el TOTP son los de ESART.',
    TG_TABLE_NAME;
END """
CHECK_OBJETO = (
    "CHECK (certificado_id IS NOT NULL AND version_id IS NOT NULL "
    "AND documento_id IS NULL AND documento_version_id IS NULL "
    "OR certificado_id IS NULL AND version_id IS NULL "
    "AND documento_id IS NOT NULL AND documento_version_id IS NOT NULL)"
)
RESTRICCIONES_NUEVAS = {
    "identidades": (
        (
            "f",
            "fk_identidades_usuario",
            "FOREIGN KEY (usuario_id) REFERENCES esart_ref.usuarios(id) ON DELETE RESTRICT",
        ),
    ),
    "evidencias": (
        (
            "f",
            "fk_evidencias_documento",
            "FOREIGN KEY (documento_id) REFERENCES esart_firma.documentos(id) ON DELETE RESTRICT",
        ),
    ),
    "solicitudes_firma": (
        (
            "f",
            "fk_solicitudes_version_documento",
            "FOREIGN KEY (documento_id, documento_version_id) "
            "REFERENCES esart_firma.versiones_documento(documento_id, id) ON DELETE RESTRICT",
        ),
        ("c", "ck_solicitudes_objeto_unico", CHECK_OBJETO),
    ),
    "desafios_autenticacion": (("c", "ck_desafios_solo_firma", "CHECK (proposito = 'FIRMAR'::text)"),),
}
INDICES_NUEVOS = {
    "identidades": (
        "uq_identidades_usuario",
        "CREATE UNIQUE INDEX uq_identidades_usuario "
        "ON esart_firma.identidades USING btree (usuario_id) WHERE (usuario_id IS NOT NULL)",
    ),
    "evidencias": (
        "ix_evidencias_documento",
        "CREATE INDEX ix_evidencias_documento "
        "ON esart_firma.evidencias USING btree (documento_id) WHERE (documento_id IS NOT NULL)",
    ),
    "solicitudes_firma": (
        "uq_solicitudes_documento_firmante",
        "CREATE UNIQUE INDEX uq_solicitudes_documento_firmante "
        "ON esart_firma.solicitudes_firma USING btree "
        "(documento_id, documento_version_id, firmante_id, orden_firma) "
        "WHERE (documento_id IS NOT NULL)",
    ),
}
TRIGGER_NUEVO = "trg_autenticacion_heredada"
CHECKS_DOCUMENTOS_TEXT = {
    "ck_documentos_estado": (
        "CHECK (estado::text = ANY (ARRAY['BORRADOR'::text, 'PENDIENTE_FIRMA'::text, "
        "'FIRMADO'::text, 'EMITIDO'::text, 'ANULADO'::text]))"
    ),
    "ck_documentos_tipo": (
        "CHECK (tipo::text = ANY (ARRAY['CERTIFICACION'::text, 'OFICIO_REMISORIO'::text]))"
    ),
}
RECHAZO_INCONDICIONAL = re.compile(
    r"\s*BEGIN\s+RAISE\s+EXCEPTION\s+'(?P<mensaje>(?:[^'\\\r\n]|'')*)'"
    r"(?P<tabla>\s*,\s*TG_TABLE_NAME)?\s*;\s*END\s*;?\s*",
    re.IGNORECASE,
)


def _cuerpo_rechaza_escrituras(cuerpo):
    # La gramática admite una única excepción P0001 incondicional, con mensaje
    # literal y, opcionalmente, TG_TABLE_NAME como único argumento de formato.
    coincidencia = RECHAZO_INCONDICIONAL.fullmatch(cuerpo)
    if coincidencia is None:
        return False
    marcadores = coincidencia["mensaje"].replace("%%", "").count("%")
    return marcadores == int(coincidencia["tabla"] is not None)


def _ddl_trigger(tabla):
    return (
        f"CREATE TRIGGER {TRIGGER_NUEVO} BEFORE INSERT OR UPDATE ON {ESQUEMA}.{tabla} "
        f"FOR EACH ROW EXECUTE FUNCTION {ESQUEMA}.{FUNCION_NUEVA}()"
    )


# --- Guardas ------------------------------------------------------------------------------


def _validar_entorno_local():
    """Solo PostgreSQL local de desarrollo con esart_migrador no superusuario (sin cambios)."""
    import os

    from sqlalchemy.engine import make_url

    from aplicacion.base_datos.configuracion import obtener_configuracion_conexion

    configuracion = obtener_configuracion_conexion()
    url_configurada = make_url(configuracion.url_base_datos.get_secret_value())
    if configuracion.entorno != "desarrollo":
        raise RuntimeError("p0018 requiere ENTORNO=desarrollo en la configuracion ESART.")
    if url_configurada.database != "esart_db" or url_configurada.host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise RuntimeError("La URL de aplicacion ESART no apunta a PostgreSQL local.")
    datos = (
        op.get_bind()
        .execute(
            text("""
        SELECT current_database(), current_user, host(inet_server_addr()), r.rolsuper
        FROM pg_roles r WHERE r.rolname=current_user
    """)
        )
        .one_or_none()
    )
    if datos is None:
        raise RuntimeError("No fue posible validar el rol de la conexion Alembic.")
    base, usuario, servidor, superusuario = datos
    prueba_copia = os.environ.get("ESART_VALIDAR_P0018_COPIA") == "1"
    base_permitida = base == "esart_db" or (
        prueba_copia and base in {"esart_db_p0018_restore_test", "esart_ensayo"}
    )
    if (
        not base_permitida
        or usuario != "esart_migrador"
        or servidor not in ("127.0.0.1", "::1")
        or superusuario
    ):
        raise RuntimeError(
            "p0018 requiere la base local permitida y la cuenta esart_migrador no-superusuario."
        )


def _heredado() -> list[dict]:
    return json.loads(ARCHIVO_HEREDADO.read_text(encoding="utf-8"))["tablas"]


def _abortar(motivo: str):
    raise RuntimeError(f"p0018 abortada sin cambios: {motivo}")


def _existe_tabla(conexion, tabla: str) -> bool:
    return conexion.scalar(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"{ESQUEMA}.{tabla}"})


def _huella_columnas(conexion, tabla: str) -> list[list]:
    filas = conexion.execute(
        text("""
            SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull
            FROM pg_attribute a
            WHERE a.attrelid = to_regclass(:t) AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """),
        {"t": f"{ESQUEMA}.{tabla}"},
    ).all()
    return [[f[0], f[1], f[2]] for f in filas]


def _catalogo_tabla(conexion, esquema, tabla):
    parametros = {"t": f"{esquema}.{tabla}"}
    relacion = conexion.execute(
        text("""
        SELECT relkind::text, relpersistence::text, relrowsecurity, relforcerowsecurity,
               EXISTS (SELECT 1 FROM pg_inherits WHERE inhrelid = c.oid OR inhparent = c.oid),
               EXISTS (SELECT 1 FROM pg_rewrite WHERE ev_class = c.oid)
        FROM pg_class c WHERE oid = to_regclass(:t)
    """),
        parametros,
    ).one_or_none()
    if relacion != ("r", "p", False, False, False, False):
        _abortar(f"{esquema}.{tabla} debe ser una tabla ordinaria permanente sin herencia, RLS ni reglas.")

    consultas = {
        "columnas": """
            SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
                   pg_get_expr(d.adbin, d.adrelid), a.attidentity::text, a.attgenerated::text,
                   a.attcollation = t.typcollation, pg_get_serial_sequence(:t, a.attname)
            FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
            LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            WHERE a.attrelid = to_regclass(:t) AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """,
        "restricciones": """
            SELECT contype::text, conname, pg_get_constraintdef(oid, true), convalidated AND conenforced
            FROM pg_constraint WHERE conrelid = to_regclass(:t) AND contype <> 'n'
            ORDER BY conname
        """,
        "indices": """
            SELECT c.relname, pg_get_indexdef(i.indexrelid), i.indisvalid AND i.indisready AND i.indislive
            FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
            WHERE i.indrelid = to_regclass(:t) ORDER BY c.relname
        """,
        "disparadores": """
            SELECT tgname, pg_get_triggerdef(oid), tgenabled::text
            FROM pg_trigger WHERE tgrelid = to_regclass(:t) AND NOT tgisinternal
            ORDER BY tgname
        """,
    }
    catalogo = {clave: conexion.execute(text(sql), parametros).all() for clave, sql in consultas.items()}
    if conexion.scalar(
        text("""
        SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = to_regclass(:t)
                       AND contype = 'n' AND NOT (convalidated AND conenforced))
    """),
        parametros,
    ):
        _abortar(f"{esquema}.{tabla} tiene restricciones NOT NULL pendientes o sin aplicar.")
    if conexion.scalar(
        text("""
        SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = to_regclass(:t)
                       AND tgisinternal AND tgenabled NOT IN ('O', 'A'))
    """),
        parametros,
    ):
        _abortar(f"{esquema}.{tabla} tiene disparadores internos deshabilitados para escrituras ordinarias.")
    return catalogo


def _diferencias_columnas(columnas, inventario, nuevas, relajadas=()):
    base = {c[0]: tuple(c[1:]) for c in inventario}
    reales = {c[0]: tuple(c[1:4]) for c in columnas}
    diferencias = [
        f"{nombre}: falta (esperada {base[nombre]!r})" for nombre in sorted(base.keys() - reales.keys())
    ]
    diferencias.extend(
        f"{nombre}: adicional no prevista (real {reales[nombre]!r})"
        for nombre in sorted(reales.keys() - base.keys() - nuevas.keys())
    )
    for nombre in sorted(reales.keys() & (base.keys() | nuevas.keys())):
        esperado = base[nombre] if nombre in base else (nuevas[nombre], False, None)
        actual = reales[nombre]
        if nombre in relajadas and not actual[1]:
            esperado = (esperado[0], False, esperado[2])
        for atributo, real, valor in zip(("tipo", "NOT NULL", "default"), actual, esperado, strict=True):
            if real != valor:
                diferencias.append(f"{nombre}.{atributo}: real {real!r}, esperado {valor!r}")
    return diferencias


def _objetos_previstos(nombre):
    return {
        "restricciones": {(*r, True) for r in RESTRICCIONES_NUEVAS.get(nombre, ())},
        "indices": {(*INDICES_NUEVOS[nombre], True)} if nombre in INDICES_NUEVOS else set(),
        "disparadores": {(TRIGGER_NUEVO, _ddl_trigger(nombre), "O")}
        if nombre in TABLAS_AUTENTICACION_HEREDADA
        else set(),
    }


def _validar_tabla_heredada(conexion, tabla):
    nombre = tabla["tabla"]
    actual = _catalogo_tabla(conexion, ESQUEMA, nombre)
    columnas = actual["columnas"]
    nuevas = COLUMNAS_NUEVAS.get(nombre, {})
    relajadas = ("certificado_id", "version_id") if nombre == "solicitudes_firma" else ()
    # SERIAL tiene un default que el inventario representa mediante la secuencia, no el texto.
    comparables = [(c[0], c[1], c[2], None if c[0] in tabla["secuencias"] else c[3]) for c in columnas]
    diferencias = _diferencias_columnas(comparables, tabla["columnas"], nuevas, relajadas)
    orden_base = [c[0] for c in tabla["columnas"]]
    if [c[0] for c in columnas if c[0] in orden_base] != orden_base and not diferencias:
        diferencias.append("orden relativo de columnas heredadas distinto")
    for campo, _, _, defecto, identidad, generada, colacion_normal, secuencia in columnas:
        if campo in tabla["secuencias"]:
            compatible = secuencia and (
                (identidad in ("a", "d") and defecto is None)
                or (not identidad and defecto == f"nextval('{secuencia}'::regclass)")
            )
        else:
            compatible = not identidad and secuencia is None
        if not compatible or generada or not colacion_normal:
            diferencias.append(f"{campo}: secuencia, identidad, generación o colación incompatible")

    esperadas = {
        "restricciones": {(*r, True) for r in tabla["restricciones"]},
        "indices": {(*i, True) for i in tabla["indices"]},
        "disparadores": {(*d, "O") for d in tabla["disparadores"]},
    }
    adoptados = {}
    for clase, previstos in _objetos_previstos(nombre).items():
        reales = set(actual[clase])
        adoptados[clase] = reales & previstos
        faltan = esperadas[clase] - reales
        sobran = reales - esperadas[clase] - previstos
        if faltan or sobran:
            diferencias.append(f"{clase}: faltan {sorted(faltan)!r}; sobran o difieren {sorted(sobran)!r}")
    if diferencias:
        _abortar(f"{ESQUEMA}.{nombre} no coincide con el inventario ni con p0018: " + " | ".join(diferencias))
    return actual, adoptados


def _catalogo_funcion_autenticacion(conexion):
    return conexion.execute(
        text("""
        SELECT p.prosrc, l.lanname, p.prorettype = 'pg_catalog.trigger'::regtype,
               p.prokind::text, p.provolatile::text, p.proparallel::text,
               p.prosecdef, p.proisstrict, p.proretset, p.proleakproof,
               p.proconfig IS NULL, p.prosupport = 0,
               pg_get_functiondef(p.oid) AS definicion, pg_get_userbyid(p.proowner) AS propietario,
               coalesce(p.proacl, acldefault('f', p.proowner))::text AS acl,
               has_function_privilege(p.oid, 'EXECUTE') AS migrador_ejecuta,
               has_function_privilege(to_regrole('esart_aplicacion'), p.oid, 'EXECUTE') AS api_ejecuta
        FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
        WHERE p.oid = to_regprocedure(:firma) AND p.prokind = 'f'
    """),
        {"firma": f"{ESQUEMA}.{FUNCION_NUEVA}()"},
    ).one_or_none()


def _validar_funciones(conexion):
    firma = {"heredada": f"{ESQUEMA}.{FUNCION_HEREDADA}()", "nueva": f"{ESQUEMA}.{FUNCION_NUEVA}()"}
    if not conexion.scalar(
        text("""
        SELECT EXISTS (SELECT FROM pg_proc WHERE oid = to_regprocedure(:heredada)
                       AND prorettype = 'pg_catalog.trigger'::regtype AND prokind = 'f')
    """),
        {"heredada": firma["heredada"]},
    ):
        _abortar(f"falta la función heredada de disparador {firma['heredada']}.")
    funcion = _catalogo_funcion_autenticacion(conexion)
    if funcion is None:
        if conexion.scalar(text("SELECT to_regprocedure(:firma) IS NOT NULL"), {"firma": firma["nueva"]}):
            _abortar(f"{firma['nueva']} está ocupada por un objeto incompatible.")
        return False

    if tuple(funcion[1:12]) != (
        "plpgsql",
        True,
        "f",
        "v",
        "u",
        False,
        False,
        False,
        False,
        True,
        True,
    ) or not _cuerpo_rechaza_escrituras(funcion.prosrc):
        _abortar(f"{firma['nueva']} tiene un cuerpo o atributos incompatibles con p0018.")
    return True


def _validar_estructura_heredada(conexion, heredado):
    return {tabla["tabla"]: _validar_tabla_heredada(conexion, tabla) for tabla in heredado}


def _validar_precondiciones(conexion, estado):
    for tabla, (indice, _) in INDICES_NUEVOS.items():
        adoptados = estado[tabla][1]["indices"]
        if not adoptados and _existe_tabla(conexion, indice):
            _abortar(f"el nombre {ESQUEMA}.{indice} está ocupado por otro objeto.")
    for tabla in TABLAS_AUTENTICACION_HEREDADA:
        if conexion.scalar(text(f"SELECT EXISTS (SELECT 1 FROM {ESQUEMA}.{tabla})")):  # noqa: S608
            _abortar(
                f"{ESQUEMA}.{tabla} tiene registros: hay que decidir manualmente su migración a TOTP de "
                "ESART antes de deshabilitar el mecanismo heredado."
            )
    if conexion.scalar(
        text(f"SELECT EXISTS (SELECT 1 FROM {ESQUEMA}.desafios_autenticacion WHERE proposito <> 'FIRMAR')")
    ):  # noqa: S608,E501
        _abortar("desafios_autenticacion tiene desafíos de login/MFA heredados; revisar antes de restringir.")
    # FIRMA_DOCUMENTOS puede existir ya (propuestas/componente_firma_documentos.sql lo agrega a la malla
    # antes de p0018). Se acepta solo si es el mismo componente: especial (sin ruta) y sin padre.
    existente = conexion.execute(
        text(
            "SELECT ruta_angular, componente_padre_id FROM esart.componentes WHERE codigo='FIRMA_DOCUMENTOS'"
        )
    ).one_or_none()
    if existente is not None and (
        existente.ruta_angular is not None or existente.componente_padre_id is not None
    ):
        _abortar("ya existe un componente FIRMA_DOCUMENTOS distinto (con ruta o padre); revisar su origen.")


def _huella_datos(conexion, columnas_por_tabla):
    """Cuenta y firma las filas completas, proyectando las columnas existentes al inicio."""
    huellas = {}
    citar = conexion.dialect.identifier_preparer.quote
    for tabla, columnas in columnas_por_tabla.items():
        proyeccion = ", ".join(citar(columna) for columna in columnas)
        huellas[tabla] = tuple(
            conexion.execute(
                text(f"""
            SELECT count(*), encode(sha256(convert_to(
                coalesce(string_agg(fila, '' ORDER BY fila COLLATE "C"), ''), 'UTF8')), 'hex')
            FROM (
                SELECT encode(sha256(convert_to(to_jsonb(datos)::text, 'UTF8')), 'hex') AS fila
                FROM (SELECT {proyeccion} FROM {ESQUEMA}.{tabla}) datos
            ) filas
        """)
            ).one()
        )
    return huellas


# --- Instalación nueva (sin esquema heredado) ------------------------------------------------


def _crear_base_heredada(heredado):
    """
    Bases sin esart_firma (instalaciones nuevas, laboratorio): crea las 21 tablas tal como están en
    esart_db, para que todas las bases terminen con la misma estructura. Sin datos.
    Las columnas id con secuencia se crean como IDENTITY (el inventario no distingue serial/identity).
    El cuerpo de bloquear_mutacion_evidencia no está en el inventario: aquí rechaza UPDATE/DELETE.
    """
    op.execute(f"CREATE SCHEMA {ESQUEMA}")
    op.execute(f"""
        CREATE FUNCTION {ESQUEMA}.{FUNCION_HEREDADA}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Registro inmutable: %', TG_TABLE_NAME; END $$
    """)
    for tabla in heredado:
        columnas = []
        for nombre, tipo, no_nulo, defecto in tabla["columnas"]:
            partes = [nombre, tipo]
            if nombre in tabla["secuencias"]:
                partes.append("GENERATED BY DEFAULT AS IDENTITY")
            elif defecto:
                partes.append(f"DEFAULT {defecto}")
            if no_nulo:
                partes.append("NOT NULL")
            columnas.append(" ".join(partes))
        op.execute(f"CREATE TABLE {ESQUEMA}.{tabla['tabla']} ({', '.join(columnas)})")
    for tipos in ("pu", "c", "f"):  # PK/UNIQUE antes que las FK que las referencian
        for tabla in heredado:
            for tipo, nombre, definicion in tabla["restricciones"]:
                if tipo in tipos:
                    op.execute(f"ALTER TABLE {ESQUEMA}.{tabla['tabla']} ADD CONSTRAINT {nombre} {definicion}")
    for tabla in heredado:
        de_restriccion = {r[1] for r in tabla["restricciones"]}
        for nombre, definicion in tabla["indices"]:
            if nombre not in de_restriccion:
                op.execute(definicion)
        for _, definicion in tabla["disparadores"]:
            op.execute(definicion)


def _ddl_documental(esquema, tabla):
    """DDL compartido por la creación y la referencia de catálogo para la adopción."""
    if tabla == "documentos":
        yield (
            f"""
            CREATE TABLE {esquema}.documentos (
              id uuid PRIMARY KEY,
              tipo varchar(30) NOT NULL CONSTRAINT ck_documentos_tipo CHECK (tipo IN ('CERTIFICACION', 'OFICIO_REMISORIO')),
              numero varchar(80) NOT NULL CONSTRAINT uq_documentos_numero UNIQUE,
              personal_id bigint NOT NULL CONSTRAINT fk_documentos_personal REFERENCES esart.personal_militar(id) ON DELETE RESTRICT,
              curso_id bigint CONSTRAINT fk_documentos_curso REFERENCES esart.cursos(id) ON DELETE RESTRICT,
              datos_emitidos jsonb NOT NULL,
              estado varchar(24) NOT NULL DEFAULT 'BORRADOR'
                CONSTRAINT ck_documentos_estado CHECK (estado IN ('BORRADOR','PENDIENTE_FIRMA','FIRMADO','EMITIDO','ANULADO')),
              version_actual integer NOT NULL DEFAULT 1 CONSTRAINT ck_documentos_version CHECK (version_actual > 0),
              creado_por bigint NOT NULL CONSTRAINT fk_documentos_creado_por REFERENCES esart_ref.usuarios(id) ON DELETE RESTRICT,
              creado_en timestamptz NOT NULL DEFAULT now(),
              emitido_en timestamptz
            )
        """
        )  # noqa: E501
        yield (
            f"CREATE INDEX ix_documentos_personal_fecha ON {esquema}.documentos (personal_id, creado_en DESC)"
        )
    else:
        yield (
            f"""
            CREATE TABLE {esquema}.versiones_documento (
              id uuid PRIMARY KEY,
              documento_id uuid NOT NULL CONSTRAINT fk_versiones_documento_documento
                REFERENCES {esquema}.documentos(id) ON DELETE RESTRICT,
              numero_version integer NOT NULL CONSTRAINT ck_versiones_documento_numero CHECK (numero_version > 0),
              sha256 char(64) NOT NULL CONSTRAINT ck_versiones_documento_sha256 CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
              ubicacion_privada text NOT NULL,
              tamano_bytes bigint NOT NULL CONSTRAINT ck_versiones_documento_tamano CHECK (tamano_bytes > 0),
              mime_type varchar(40) NOT NULL DEFAULT 'application/pdf'
                CONSTRAINT ck_versiones_documento_mime CHECK (mime_type = 'application/pdf'),
              creado_por bigint NOT NULL CONSTRAINT fk_versiones_documento_creado_por
                REFERENCES esart_ref.usuarios(id) ON DELETE RESTRICT,
              creado_en timestamptz NOT NULL DEFAULT now(),
              CONSTRAINT uq_versiones_documento_numero UNIQUE (documento_id, numero_version),
              CONSTRAINT uq_versiones_documento_id UNIQUE (documento_id, id)
            )
        """
        )
        # Mismo trigger de inmutabilidad que las versiones de certificado heredadas.
        yield (
            f"""
            CREATE TRIGGER trg_inmutable BEFORE DELETE OR UPDATE ON {esquema}.versiones_documento
            FOR EACH ROW EXECUTE FUNCTION {ESQUEMA}.{FUNCION_HEREDADA}()
        """
        )


def _referencia_documental():
    archivo = ARCHIVO_HEREDADO.with_name("p0018_documentales_pg18.json")
    return json.loads(archivo.read_text(encoding="utf-8"))


def _validar_documental(conexion, tabla, referencia):
    actual = _catalogo_tabla(conexion, ESQUEMA, tabla)
    diferencias = []
    for clase, filas in referencia.items():
        esperadas = [tuple(fila) for fila in filas]
        reales = [tuple(fila) for fila in actual[clase]]
        if tabla == "documentos" and clase == "restricciones":
            equivalencias = {
                ("c", nombre, CHECKS_DOCUMENTOS_TEXT[nombre], True): (tipo, nombre, definicion, valida)
                for tipo, nombre, definicion, valida in esperadas
                if tipo == "c" and valida and nombre in CHECKS_DOCUMENTOS_TEXT
            }
            reales = [equivalencias.get(fila, fila) for fila in reales]
        if esperadas == reales:
            continue
        if clase == "columnas":
            diferencias.extend(_diferencias_columnas(reales, [c[:4] for c in esperadas], {}))
        faltan, sobran = set(esperadas) - set(reales), set(reales) - set(esperadas)
        diferencias.append(
            f"{clase} incompatibles: faltan o difieren {sorted(faltan)!r}; "
            f"sobran o difieren {sorted(sobran)!r}"
        )
    if diferencias:
        _abortar(f"{ESQUEMA}.{tabla} " + " | ".join(diferencias))
    return actual


# --- Upgrade ------------------------------------------------------------------------------


def upgrade():
    _validar_entorno_local()
    conexion = op.get_bind()
    heredado = _heredado()
    ruta = conexion.scalar(text("SHOW search_path"))
    conexion.execute(text("SET LOCAL search_path TO pg_catalog, pg_temp"))
    if conexion.scalar(text("SELECT to_regnamespace(:e)"), {"e": ESQUEMA}) is None:
        _crear_base_heredada(heredado)

    existentes = [tabla for tabla in TABLAS_DOCUMENTALES if _existe_tabla(conexion, tabla)]
    for tabla in sorted([t["tabla"] for t in heredado] + existentes):
        if not _existe_tabla(conexion, tabla):
            _abortar(f"falta la tabla heredada {ESQUEMA}.{tabla}.")
        conexion.execute(text(f"LOCK TABLE ONLY {ESQUEMA}.{tabla} IN ACCESS EXCLUSIVE MODE"))
    conexion.execute(text("LOCK TABLE esart.componentes IN SHARE ROW EXCLUSIVE MODE"))
    estado = _validar_estructura_heredada(conexion, heredado)
    tiene_funcion = _validar_funciones(conexion)
    _validar_precondiciones(conexion, estado)
    referencia = _referencia_documental()
    for tabla in existentes:
        _validar_documental(conexion, tabla, referencia[tabla])

    columnas = {nombre: [c[0] for c in actual["columnas"]] for nombre, (actual, _) in estado.items()}
    for tabla in existentes:
        columnas[tabla] = [c[0] for c in _huella_columnas(conexion, tabla)]
    antes = _huella_datos(conexion, columnas)
    for tabla in TABLAS_DOCUMENTALES:
        if tabla not in existentes:
            for sentencia in _ddl_documental(ESQUEMA, tabla):
                op.execute(sentencia)

    _completar_extensiones(estado, tiene_funcion)

    # 6. Permisos mínimos de la API (solo lo que usa la persistencia documental).
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA {ESQUEMA} FROM PUBLIC")
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{CUENTA_APLICACION}') THEN
            GRANT USAGE ON SCHEMA {ESQUEMA} TO {CUENTA_APLICACION};
            GRANT SELECT, INSERT ON {ESQUEMA}.documentos, {ESQUEMA}.versiones_documento,
              {ESQUEMA}.evidencias, {ESQUEMA}.auditoria_eventos TO {CUENTA_APLICACION};
            GRANT UPDATE (estado, version_actual, emitido_en) ON {ESQUEMA}.documentos TO {CUENTA_APLICACION};
            GRANT SELECT (id, usuario_externo_id, nombre_mostrado, activo, usuario_id),
                  INSERT (usuario_externo_id, nombre_mostrado, usuario_id)
              ON {ESQUEMA}.identidades TO {CUENTA_APLICACION};
            EXECUTE format('GRANT USAGE ON SEQUENCE %s, %s TO {CUENTA_APLICACION}',
              pg_get_serial_sequence('{ESQUEMA}.identidades', 'id'),
              pg_get_serial_sequence('{ESQUEMA}.auditoria_eventos', 'id'));
            REVOKE ALL ON {ESQUEMA}.totp_factores, {ESQUEMA}.totp_recuperacion, {ESQUEMA}.sesiones_firma
              FROM {CUENTA_APLICACION};
          END IF;
        END $$
    """)  # noqa: S608

    # 7. Componente de la malla (acceso solo para ADMINISTRADOR, como antes). Si ya se agregó con
    #    propuestas/componente_firma_documentos.sql no se repite ni se cambian sus permisos.
    op.execute("""
        INSERT INTO esart.componentes(codigo,nombre,ruta_angular,orden,activo)
        VALUES ('FIRMA_DOCUMENTOS','Firma documental',NULL,120,true)
        ON CONFLICT (codigo) DO NOTHING
    """)
    op.execute("""
        INSERT INTO esart.rol_permisos(rol_id,componente_id,puede_acceder,puede_crear,puede_leer,puede_actualizar,puede_eliminar)
        SELECT r.id,c.id,(r.codigo='ADMINISTRADOR'),(r.codigo='ADMINISTRADOR'),(r.codigo='ADMINISTRADOR'),false,false
        FROM esart.roles r CROSS JOIN esart.componentes c
        WHERE c.codigo='FIRMA_DOCUMENTOS'
        ON CONFLICT (rol_id,componente_id) DO NOTHING
    """)  # noqa: E501

    despues = _huella_datos(conexion, columnas)
    if despues != antes:
        _abortar(f"cambió el contenido heredado (antes={antes}, después={despues}).")
    _validar_estructura_heredada_ampliada(conexion, heredado)
    for tabla in TABLAS_DOCUMENTALES:
        _validar_documental(conexion, tabla, referencia[tabla])
    conexion.execute(text("SELECT set_config('search_path', :ruta, true)"), {"ruta": ruta})


def _completar_extensiones(estado, tiene_funcion):
    for tabla, nuevas in COLUMNAS_NUEVAS.items():
        existentes = {c[0]: c for c in estado[tabla][0]["columnas"]}
        for nombre, tipo in nuevas.items():
            if nombre not in existentes:
                op.execute(f"ALTER TABLE {ESQUEMA}.{tabla} ADD COLUMN {nombre} {tipo}")
        if tabla == "solicitudes_firma":
            for nombre in ("certificado_id", "version_id"):
                if existentes[nombre][2]:
                    op.execute(f"ALTER TABLE {ESQUEMA}.{tabla} ALTER COLUMN {nombre} DROP NOT NULL")
    for tabla, restricciones in RESTRICCIONES_NUEVAS.items():
        for clase, nombre, definicion in restricciones:
            if (clase, nombre, definicion, True) not in estado[tabla][1]["restricciones"]:
                op.execute(f"ALTER TABLE {ESQUEMA}.{tabla} ADD CONSTRAINT {nombre} {definicion}")
    for tabla, (_, ddl) in INDICES_NUEVOS.items():
        if not estado[tabla][1]["indices"]:
            op.execute(ddl)
    if not tiene_funcion:
        op.execute(
            f"CREATE FUNCTION {ESQUEMA}.{FUNCION_NUEVA}() RETURNS trigger LANGUAGE plpgsql AS $cuerpo${CUERPO_FUNCION}$cuerpo$"
        )
    for tabla in TABLAS_AUTENTICACION_HEREDADA:
        if not estado[tabla][1]["disparadores"]:
            op.execute(_ddl_trigger(tabla))


def _validar_estructura_heredada_ampliada(conexion, heredado):
    estado = _validar_estructura_heredada(conexion, heredado)
    for tabla, (actual, adoptados) in estado.items():
        columnas = {c[0]: c for c in actual["columnas"]}
        if not COLUMNAS_NUEVAS.get(tabla, {}).keys() <= columnas.keys():
            _abortar(f"faltan columnas previstas en {ESQUEMA}.{tabla}.")
        if adoptados != _objetos_previstos(tabla):
            _abortar(f"faltan objetos previstos en {ESQUEMA}.{tabla}.")
        if tabla == "solicitudes_firma" and any(columnas[c][2] for c in ("certificado_id", "version_id")):
            _abortar("las referencias a certificados deben admitir NULL.")
    if not _validar_funciones(conexion):
        _abortar(f"falta la función {FUNCION_NUEVA}.")


# --- Downgrade ----------------------------------------------------------------------------


def downgrade():
    """Bloquea la reversión porque la revisión no registra el origen de objetos ni concesiones."""
    _validar_entorno_local()
    raise RuntimeError(
        "No se puede revertir p0018: no se puede distinguir con certeza qué estructuras y permisos "
        "existían antes de la migración."
    )
