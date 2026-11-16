"""Genera entregables DBCode sin conectar a PostgreSQL ni ejecutar el SQL resultante."""

import hashlib
import json
import re
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import AddConstraint, CreateIndex, CreateTable

from aplicacion.modelos import historico as modelos  # noqa: F401
from aplicacion.modelos.historico.base import BaseModelo

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "sql/dbcode"
DIALECTO = postgresql.dialect()
ESQUEMAS_REF = {"unidades_militares", "usuarios", "sistemas_artilleria"}
ALIAS = {
    "personal_militar": {"numero_documento": "documento_identidad", "unidad_militar_id": "unidad_actual_id"},
    "hoja_vida_artillero": {"personal_militar_id": "artillero_id"},
    "usuarios": {
        "nombre_usuario": "usuario",
        "hash_contrasena": "contrasena_hash",
        "fecha_ultimo_acceso": "ultimo_acceso_en",
    },
    "artillero_cursos": {"hoja_vida_artillero_id": "hoja_vida_id"},
    "artillero_certificaciones": {
        "hoja_vida_artillero_id": "hoja_vida_id",
        "fecha_expedicion": "fecha_emision",
    },
    "artillero_cargos": {
        "hoja_vida_artillero_id": "hoja_vida_id",
        "unidad_militar_id": "unidad_id",
        "observaciones": "descripcion",
    },
}


def literal(valor):
    return "'" + valor.replace("'", "''") + "'"


def identificador(valor):
    return '"' + valor.replace('"', '""') + '"'


def nombre_objeto(prefijo, tabla, sufijo):
    nombre = prefijo + "_" + tabla + "_" + sufijo
    return (
        nombre if len(nombre) <= 60 else nombre[:47] + "_" + hashlib.sha256(nombre.encode()).hexdigest()[:12]
    )


def normalizar(valor):
    return re.sub(r"[^a-z0-9_,]", "", valor.lower().replace("::text", ""))


class TipoOrigen(sa.types.UserDefinedType):
    cache_ok = True

    def __init__(self, descripcion):
        self.descripcion = descripcion

    def get_col_spec(self, **_opciones):
        return self.descripcion


def construir(estructura):
    originales = {(t["esquema"], t["tabla"]): t for t in estructura["tablas"]}
    columnas = {(c["esquema"], c["tabla"], c["columna"]): c for c in estructura["columnas"]}
    ubicaciones = {n: ("esart_ref" if n in ESQUEMAS_REF else "esart", n) for n in BaseModelo.metadata.tables}
    for nombre, (esquema, _) in ubicaciones.items():
        disponibles = {
            c["columna"] for c in estructura["columnas"] if c["esquema"] == esquema and c["tabla"] == nombre
        }
        alias = ALIAS.setdefault(nombre, {})
        if "creado_en" in disponibles:
            alias["fecha_creacion"] = "creado_en"
        if "actualizado_en" in disponibles:
            alias["fecha_actualizacion"] = "actualizado_en"
    metadatos = sa.MetaData()
    ampliaciones, nuevas, restricciones, indices, mapa = [], [], [], [], {}
    for nombre, modelo in BaseModelo.metadata.tables.items():
        esquema, _ = ubicaciones[nombre]
        heredada = (esquema, nombre) in originales
        elementos = []
        vistas = set()
        for c in modelo.c:
            destino = ALIAS.get(nombre, {}).get(c.name, c.name)
            fuente = columnas.get((esquema, nombre, destino))
            tipo = c.type.copy()
            if fuente:
                tipo = TipoOrigen(fuente["tipo"])
            elif c.foreign_keys:
                remoto = next(iter(c.foreign_keys)).column.table.name
                if ubicaciones[remoto] in originales:
                    tipo = sa.BigInteger()
            opciones = {
                "nullable": fuente["permite_null"] if fuente else True if heredada else c.nullable,
                "primary_key": c.primary_key,
            }
            if not heredada and c.identity is not None:
                elementos.append(sa.Column(destino, tipo, sa.Identity(always=c.identity.always), **opciones))
            else:
                if not heredada and c.server_default is not None:
                    opciones["server_default"] = sa.text(str(c.server_default.arg))
                elementos.append(sa.Column(destino, tipo, **opciones))
            vistas.add(destino)
            if heredada and not fuente:
                ampliaciones.append((esquema, nombre, destino, str(tipo.compile(dialect=DIALECTO))))
        # Columnas institucionales adicionales nunca se eliminan o renombran.
        for (s, n, campo), fuente in columnas.items():
            if (s, n) == (esquema, nombre) and campo not in vistas:
                elementos.append(
                    sa.Column(campo, TipoOrigen(fuente["tipo"]), nullable=fuente["permite_null"])
                )
        if nombre == "unidades_militares":
            elementos.append(sa.Column("uuid_publico", sa.Uuid(), nullable=True))
            ampliaciones.append((esquema, nombre, "uuid_publico", "UUID"))
        tabla = sa.Table(nombre, metadatos, *elementos, schema=esquema)
        mapa[nombre] = tabla
        if not heredada:
            nuevas.append(tabla)
    for nombre, modelo in BaseModelo.metadata.tables.items():
        tabla = mapa[nombre]
        heredada = (tabla.schema, nombre) in originales
        existentes = [
            c for c in estructura["restricciones"] if (c["esquema"], c["tabla"]) == (tabla.schema, nombre)
        ]
        for numero, c in enumerate(sorted(modelo.constraints, key=lambda c: str(c.name))):
            if isinstance(c, sa.PrimaryKeyConstraint):
                continue
            nombre_c = nombre_objeto("hu0304", nombre, str(c.name or numero))
            if isinstance(c, sa.ForeignKeyConstraint):
                locales = [ALIAS.get(nombre, {}).get(x.name, x.name) for x in c.columns]
                destinos = []
                for fk in c.elements:
                    remoto = fk.column.table.name
                    s, n = ubicaciones[remoto]
                    campo = ALIAS.get(remoto, {}).get(fk.column.name, fk.column.name)
                    destinos.append(s + "." + n + "." + campo)
                # Reutilizar la FK institucional con iguales extremos, conservando sus acciones.
                prefijo = normalizar(
                    "FOREIGN KEY ("
                    + ",".join(locales)
                    + ") REFERENCES "
                    + destinos[0].rsplit(".", 1)[0]
                    + "("
                    + ",".join(d.rsplit(".", 1)[1] for d in destinos)
                    + ")"
                )
                if heredada and any(
                    x["tipo"] == "f" and normalizar(x["definicion"]).startswith(prefijo) for x in existentes
                ):
                    continue
                nueva = sa.ForeignKeyConstraint(locales, destinos, name=nombre_c, ondelete=c.ondelete)
            elif isinstance(c, sa.UniqueConstraint):
                locales = [ALIAS.get(nombre, {}).get(x.name, x.name) for x in c.columns]
                firma = normalizar("UNIQUE(" + ",".join(locales) + ")")
                if heredada and any(
                    x["tipo"] in ("u", "p")
                    and normalizar(x["definicion"])
                    in (firma, normalizar("PRIMARY KEY(" + ",".join(locales) + ")"))
                    for x in existentes
                ):
                    continue
                nueva = sa.UniqueConstraint(*locales, name=nombre_c)
            elif isinstance(c, sa.CheckConstraint):
                # Ya verificadas las restricciones heredadas equivalentes en el manifiesto.
                if heredada and (
                    nombre in ("roles", "rol_permisos", "usuario_permisos")
                    or (
                        nombre in ("artillero_cursos", "artillero_certificaciones", "artillero_cargos")
                        and str(c.name).endswith("coherencia")
                    )
                ):
                    continue
                expresion = str(c.sqltext)
                for origen, destino in ALIAS.get(nombre, {}).items():
                    expresion = re.sub(r"\b" + origen + r"\b", destino, expresion)
                nueva = sa.CheckConstraint(expresion, name=nombre_c)
            else:
                continue
            tabla.append_constraint(nueva)
            if heredada:
                restricciones.append(str(AddConstraint(nueva).compile(dialect=DIALECTO)) + ";")
        if nombre == "unidades_militares":
            for _sufijo, objeto in (
                ("uuid_publico", sa.UniqueConstraint("uuid_publico", name="hu0304_unidades_uuid_publico")),
                (
                    "no_autosuperior",
                    sa.CheckConstraint(
                        "unidad_superior_id IS DISTINCT FROM id", name="hu0304_unidades_no_autosuperior"
                    ),
                ),
            ):
                tabla.append_constraint(objeto)
                restricciones.append(str(AddConstraint(objeto).compile(dialect=DIALECTO)) + ";")
        anteriores = [
            x for x in estructura["indices"] if (x["esquema"], x["tabla"]) == (tabla.schema, nombre)
        ]
        for numero, indice in enumerate(sorted(modelo.indexes, key=lambda x: str(x.name))):
            expresiones = []
            for expresion in indice.expressions:
                valor = str(expresion).replace(nombre + ".", "")
                for origen, destino in ALIAS.get(nombre, {}).items():
                    valor = re.sub(r"\b" + origen + r"\b", destino, valor)
                expresiones.append(valor)
            firma = normalizar(",".join(expresiones))
            if any(
                (not indice.unique or x["unico"])
                and normalizar(x["definicion"].split(" USING btree ")[-1]) == firma
                for x in anteriores
            ):
                continue
            nuevo = sa.Index(
                nombre_objeto("hu0304_ix", nombre, str(numero)),
                *[sa.text(e) for e in expresiones],
                unique=indice.unique,
                _table=tabla,
            )
            indices.append(str(CreateIndex(nuevo).compile(dialect=DIALECTO)) + ";")
    ddl = [
        str(CreateTable(t).compile(dialect=DIALECTO)) + ";" for t in metadatos.sorted_tables if t in nuevas
    ]
    ddl += [f"ALTER TABLE {s}.{n} ADD COLUMN {c} {tipo};" for s, n, c, tipo in ampliaciones]
    # Las tablas nuevas pueden referenciar campos añadidos en tablas heredadas, pero sus FK
    # siempre apuntan a las PK existentes; agregar primero las columnas y después las FK.
    ddl += restricciones + indices
    return mapa, nuevas, ampliaciones, ddl


def consulta_estructura(gestionadas):
    valores = ",".join("(" + literal(s) + "," + literal(n) + ")" for s, n in gestionadas)
    return """WITH g(s,n) AS (VALUES __GESTIONADAS__)
 SELECT jsonb_build_object(
  'columnas',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,'c',a.attname,
    'tipo',format_type(a.atttypid,a.atttypmod),'null',NOT a.attnotnull,
    'identidad',a.attidentity::text,'generada',a.attgenerated::text,'collation',a.attcollation::regcollation::text,
    'defecto',pg_get_expr(d.adbin,d.adrelid)) ORDER BY ns.nspname,cl.relname,a.attnum)
    FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text
    LEFT JOIN pg_attrdef d ON d.adrelid=cl.oid AND d.adnum=a.attnum WHERE a.attnum>0 AND NOT a.attisdropped),
  'constraints',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,'nombre',co.conname,
     'def',pg_get_constraintdef(co.oid),'validada',co.convalidated) ORDER BY ns.nspname,cl.relname,co.conname)
    FROM pg_constraint co JOIN pg_class cl ON cl.oid=co.conrelid
    JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text),
  'indices',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,
     'def',pg_get_indexdef(ix.indexrelid),
     'valido',ix.indisvalid) ORDER BY ns.nspname,cl.relname,ix.indexrelid::regclass::text)
    FROM pg_index ix JOIN pg_class cl ON cl.oid=ix.indrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text),
  'triggers',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,'nombre',tg.tgname,
     'def',pg_get_triggerdef(tg.oid),'estado',tg.tgenabled::text) ORDER BY ns.nspname,cl.relname,tg.tgname)
    FROM pg_trigger tg JOIN pg_class cl ON cl.oid=tg.tgrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text WHERE NOT tg.tgisinternal),
  'funciones',(SELECT jsonb_agg(jsonb_build_object('nombre',p.proname,'cuerpo',p.prosrc,
     'seguridad',p.prosecdef,'config',p.proconfig) ORDER BY p.proname)
    FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace WHERE ns.nspname='esart'
     AND p.proname IN ('actualizar_fecha_hu0304','inmutabilidad_auditoria_hu0304')),
  'vista',(SELECT jsonb_build_object('def',pg_get_viewdef(cl.oid),'opciones',cl.reloptions)
    FROM pg_class cl JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    WHERE ns.nspname='esart' AND cl.relname='v_unidades_api')
 ) INTO actual;""".replace("__GESTIONADAS__", valores)


def funciones_y_triggers(mapa):
    sql = """CREATE FUNCTION esart.actualizar_fecha_hu0304() RETURNS trigger LANGUAGE plpgsql AS $fecha$
 BEGIN
  IF (to_jsonb(NEW)-TG_ARGV[0]) IS DISTINCT FROM (to_jsonb(OLD)-TG_ARGV[0]) THEN
   NEW:=jsonb_populate_record(NEW,jsonb_build_object(TG_ARGV[0],now()));
  ELSE
   NEW:=jsonb_populate_record(NEW,jsonb_build_object(TG_ARGV[0],to_jsonb(OLD)->TG_ARGV[0]));
  END IF;
  RETURN NEW;
 END $fecha$;
 CREATE FUNCTION esart.inmutabilidad_auditoria_hu0304() RETURNS trigger LANGUAGE plpgsql AS $auditoria$
 BEGIN RAISE EXCEPTION 'Auditoria inmutable: operacion % no permitida',TG_OP; END $auditoria$;
 CREATE TRIGGER hu0304_auditoria_filas BEFORE UPDATE OR DELETE ON esart.auditoria_eventos
 FOR EACH ROW EXECUTE FUNCTION esart.inmutabilidad_auditoria_hu0304();
 CREATE TRIGGER hu0304_auditoria_truncado BEFORE TRUNCATE ON esart.auditoria_eventos
 FOR EACH STATEMENT EXECUTE FUNCTION esart.inmutabilidad_auditoria_hu0304();
 """
    for nombre, tabla in mapa.items():
        campo = ALIAS.get(nombre, {}).get("fecha_actualizacion", "fecha_actualizacion")
        if campo in tabla.c:
            sql += (
                f"CREATE TRIGGER {nombre_objeto('hu0304_fecha', nombre, 'actualizacion')} "
                f"BEFORE UPDATE ON {tabla.fullname} FOR EACH ROW EXECUTE FUNCTION "
                f"esart.actualizar_fecha_hu0304({literal(campo)});\n"
            )
    return sql


VISTA = """CREATE VIEW esart.v_unidades_api WITH (security_invoker=true) AS
 SELECT u.uuid_publico AS id,u.codigo,u.nombre,u.sigla,u.activa,
  t.id AS tipo_id,t.codigo AS tipo_codigo,t.nombre AS tipo_nombre,
  p.uuid_publico AS unidad_superior_id,p.codigo AS superior_codigo,p.nombre AS superior_nombre,
  (u.tipo_unidad_id IS NULL) AS clasificacion_pendiente
 FROM esart_ref.unidades_militares u LEFT JOIN esart.tipos_unidad t ON t.id=u.tipo_unidad_id
 LEFT JOIN esart_ref.unidades_militares p ON p.id=u.unidad_superior_id
 WHERE u.uuid_publico IS NOT NULL AND u.codigo IS NOT NULL;"""


def permisos_objeto(mapa):
    partes = []
    for tabla in mapa.values():
        partes.append(f"GRANT SELECT ON {tabla.fullname} TO esart_aplicacion;")
        if tabla.name == "auditoria_eventos":
            partes.append("REVOKE ALL ON esart.auditoria_eventos FROM PUBLIC;")
            partes.append(
                "REVOKE UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER "
                "ON esart.auditoria_eventos FROM esart_aplicacion;"
            )
            partes.append("GRANT INSERT ON esart.auditoria_eventos TO esart_aplicacion;")
        else:
            partes.append(f"GRANT INSERT,UPDATE ON {tabla.fullname} TO esart_aplicacion;")
    partes.append(
        """DO $secuencias_app$
 DECLARE t RECORD; sec TEXT;
 BEGIN
  FOR t IN SELECT * FROM (VALUES __VALORES__) AS x(s,n) LOOP
   sec:=pg_get_serial_sequence(format('%I.%I',t.s,t.n),'id');
    IF sec IS NOT NULL THEN
     EXECUTE format('GRANT USAGE,SELECT ON SEQUENCE %s TO esart_aplicacion',sec);
    END IF;
  END LOOP;
 END $secuencias_app$;""".replace(
            "__VALORES__",
            ",".join(
                "(" + literal(t.schema) + "," + literal(t.name) + ")" for t in mapa.values() if "id" in t.c
            ),
        )
    )
    return "\n".join(partes)


def validar_datos(datos):
    for grupo, cantidad in (
        ("roles", 2),
        ("cargos", 5),
        ("cursos", 14),
        ("permisos", 36),
        ("tipos", 9),
        ("unidades", 40),
    ):
        if len(datos[grupo]) != cantidad:
            raise ValueError("Cantidad incorrecta: " + grupo)
        clave = "nombre" if grupo == "cargos" else "codigo"
        if len({r[clave].strip().lower() for r in datos[grupo]}) != cantidad:
            raise ValueError("Claves naturales duplicadas: " + grupo)
        if any("id" in r for r in datos[grupo]):
            raise ValueError("No copiar identificadores de pruebas")
    vistos = set()
    tipos = {r["codigo"] for r in datos["tipos"]}
    for u in datos["unidades"]:
        if u["superior_codigo"] is not None and u["superior_codigo"] not in vistos:
            raise ValueError("Jerarquia desordenada o incompleta")
        if u["tipo_codigo"] is not None and u["tipo_codigo"] not in tipos:
            raise ValueError("Tipo inexistente")
        vistos.add(u["codigo"])
    if [u["codigo"] for u in datos["unidades"] if u["tipo_codigo"] is None] != ["FUTOM"]:
        raise ValueError("Solo FUTOM debe quedar pendiente")


def main():
    estructura = json.loads((SALIDA / "estructura_origen.json").read_text(encoding="utf-8"))
    datos = json.loads((SALIDA / "datos_hu03_hu04.json").read_text(encoding="utf-8"))
    validar_datos(datos)
    mapa, nuevas, ampliaciones, ddl = construir(estructura)
    gestionadas = sorted((t.schema, t.name) for t in mapa.values()) + [("esart", "integraciones_control")]
    manifiesto = {
        "version": "dbcode_hu03_hu04_v1",
        "datos": datos,
        "origen": estructura,
        "nuevas": [[t.schema, t.name] for t in nuevas],
        "columnas": ampliaciones,
        "gestionadas": gestionadas,
        "alias": ALIAS,
    }
    plantillas = {p.stem: p.read_text(encoding="utf-8") for p in (SALIDA / "plantillas").glob("*.sql")}
    funciones = funciones_y_triggers(mapa)
    permisos = permisos_objeto(mapa)
    consulta = consulta_estructura(gestionadas)
    manifiesto["huellas_generacion"] = {
        "ddl": hashlib.sha256("\n".join(ddl).encode()).hexdigest(),
        "funciones": hashlib.sha256(funciones.encode()).hexdigest(),
        "vista": hashlib.sha256(VISTA.encode()).hexdigest(),
        "permisos": hashlib.sha256(permisos.encode()).hexdigest(),
        "consulta_estructura": hashlib.sha256(consulta.encode()).hexdigest(),
        **{n: hashlib.sha256(s.encode()).hexdigest() for n, s in plantillas.items()},
    }
    firma = hashlib.sha256(json.dumps(manifiesto, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    manifiesto["sha256"] = firma
    (SALIDA / "manifiesto.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (SALIDA / "_ddl_generado.sql").write_text("\n\n".join(ddl) + "\n", encoding="utf-8")
    aserciones = plantillas["aserciones"].replace("__DATOS__", literal(json.dumps(datos, ensure_ascii=False)))
    lectura = """SELECT t.tabla,has_table_privilege(current_user,t.tabla,'SELECT') lectura,
 has_table_privilege(current_user,t.tabla,'INSERT') insercion,
 has_table_privilege(current_user,t.tabla,'UPDATE') actualizacion
 FROM (VALUES ('esart_ref.unidades_militares'),('esart.tipos_unidad'),('esart.tipos_cargo'),
 ('esart.tipos_curso'),('esart.roles'),('esart.permisos')) AS t(tabla);"""
    reemplazos = {
        "__MANIFIESTO__": literal(json.dumps(manifiesto, ensure_ascii=False)),
        "__VERSION__": literal(manifiesto["version"]),
        "__FIRMA__": literal(firma),
        "__ESTRUCTURA_INTO__": consulta,
        "__DDL__": "\n".join(ddl),
        "__FUNCIONES_Y_TRIGGERS__": funciones,
        "__VISTA__": VISTA,
        "__SEEDS__": plantillas["semillas"],
        "__ASERCIONES__": aserciones,
        "__PERMISOS__": permisos,
        "__LECTURA_Y_ESCRITURA__": lectura,
    }
    for plantilla, nombre in (
        ("integracion", "01_integrar_esart_db.sql"),
        ("verificacion", "02_verificar_esart_db.sql"),
    ):
        sql = plantillas[plantilla]
        for marcador, valor in reemplazos.items():
            sql = sql.replace(marcador, valor)
        if re.search(r"__[A-Z_]+__", sql):
            raise ValueError("Marcador sin resolver")
        (SALIDA / nombre).write_text(sql, encoding="utf-8")
    resumen = {
        "version_manual": manifiesto["version"],
        "sha256_manifiesto": firma,
        "tablas_nuevas": [t.fullname for t in nuevas] + ["esart.integraciones_control"],
        "vista_nueva": "esart.v_unidades_api",
        "columnas_nuevas": ampliaciones,
        "alias_orm_requeridos": ALIAS,
        "ejecutado_en_postgresql": False,
        "archivos_sha256": {
            n: hashlib.sha256((SALIDA / n).read_bytes()).hexdigest()
            for n in ("01_integrar_esart_db.sql", "02_verificar_esart_db.sql")
        },
    }
    (SALIDA / "resumen_revision.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "nuevas": [t.fullname for t in nuevas],
                "columnas_nuevas": len(ampliaciones),
                "DDL_preparado": len(ddl),
                "huella": firma,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
