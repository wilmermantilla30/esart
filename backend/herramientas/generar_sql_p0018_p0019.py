"""
Genera propuestas/p0018_p0019_firma_manual.sql: p0018 + p0019 para ejecutar a mano como postgres.

El SQL de cambios se extrae de las propias migraciones (se ejecuta su upgrade() capturando op.execute),
así el script manual y las migraciones no pueden diferir. Alrededor se agregan, en SQL, las mismas
guardas de p0018:
  - antes: el esquema esart_firma existe; las 21 tablas tienen exactamente las columnas, tipos,
    nulabilidad y restricciones del inventario; existe bloquear_mutacion_evidencia(); los objetos
    nuevos no existen; las tablas de autenticación heredada están vacías; no hay desafíos de
    LOGIN/MFA; FIRMA_DOCUMENTOS, si ya existe, es el componente especial esperado.
  - después: conteos exactos de las 21 tablas y contenido (md5) de roles, permisos, rol_permiso y
    asignaciones_rol idénticos a los de antes.
Cualquier diferencia lanza una excepción y la transacción completa se revierte (no queda nada a medias).

Uso desde backend/:  .venv\\Scripts\\python.exe herramientas\\generar_sql_p0018_p0019.py
"""

# ruff: noqa: E501, S608

import importlib.util
import json
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
VERSIONES = RAIZ / "migraciones_principal" / "versions"
SALIDA = RAIZ / "propuestas" / "p0018_p0019_firma_manual.sql"
HEREDADO = json.loads(
    (RAIZ / "migraciones_principal" / "datos" / "p0018_esart_firma_heredado.json").read_text(encoding="utf-8")
)["tablas"]


def capturar(archivo: str, preparar=None) -> list[str]:
    """Ejecuta upgrade() de una migración con un op falso y devuelve el SQL en orden."""
    capturado: list[str] = []
    falso = types.SimpleNamespace(
        execute=lambda sql: capturado.append(str(sql).strip()), get_bind=lambda: None
    )
    alembic = types.ModuleType("alembic")
    alembic.op = falso
    sys.modules["alembic"] = alembic
    spec = importlib.util.spec_from_file_location(archivo, VERSIONES / archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    if preparar:
        preparar(modulo)
    modulo.upgrade()
    return capturado


def sin_guardas_python(modulo) -> None:
    """Las guardas de p0018 consultan con la conexión de Alembic; aquí se reemplazan por las de SQL."""
    for nombre in ("_validar_entorno_local", "_validar_no_aplicada", "_validar_estructura_heredada", "_validar_precondiciones",
                   "_validar_estructura_heredada_ampliada"):  # fmt: skip
        setattr(modulo, nombre, lambda *a, **k: None)
    modulo._huella_datos = lambda *a, **k: {}
    # Con esquema existente p0018 no crea la base heredada: get_bind().scalar(to_regnamespace) ≠ None.
    modulo.op.get_bind = lambda: types.SimpleNamespace(scalar=lambda *a, **k: 1)


def literal(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def guardas_previas() -> str:
    tablas = ",\n      ".join(
        "(" + literal(t["tabla"]) + ", "
        + literal(",".join(f"{c[0]}:{c[1]}:{'true' if c[2] else 'false'}" for c in t["columnas"])) + ", "
        + "ARRAY[" + ", ".join(literal(r[1]) for r in t["restricciones"]) + "]::text[])"
        for t in HEREDADO
    )  # fmt: skip
    return f"""DO $guardas$
DECLARE
  t record;
  actual text;
  faltantes text[];
BEGIN
  IF to_regnamespace('esart_firma') IS NULL THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: no existe el esquema esart_firma (este script es para la base con el esquema heredado).';
  END IF;
  -- Objetos nuevos ausentes (si existen, el script ya se ejecutó o hay otro origen: no repetir).
  IF to_regclass('esart_firma.documentos') IS NOT NULL OR to_regclass('esart_firma.versiones_documento') IS NOT NULL
     OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('esart_firma.identidades') AND attname = 'usuario_id' AND NOT attisdropped)
     OR to_regprocedure('esart_firma.rechazar_autenticacion_heredada()') IS NOT NULL THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: ya existen objetos de p0018 (documentos, identidades.usuario_id o la función nueva). No se ejecuta dos veces.';
  END IF;
  -- Huella exacta de las 21 tablas heredadas (columnas en orden, tipos, NOT NULL y restricciones).
  FOR t IN SELECT * FROM (VALUES
      {tablas}
    ) AS v(tabla, columnas, restricciones)
  LOOP
    IF to_regclass('esart_firma.' || t.tabla) IS NULL THEN
      RAISE EXCEPTION 'p0018 abortada sin cambios: falta la tabla heredada esart_firma.%', t.tabla;
    END IF;
    SELECT string_agg(a.attname || ':' || format_type(a.atttypid, a.atttypmod) || ':' ||
                      CASE WHEN a.attnotnull THEN 'true' ELSE 'false' END, ',' ORDER BY a.attnum)
      INTO actual
      FROM pg_attribute a WHERE a.attrelid = to_regclass('esart_firma.' || t.tabla) AND a.attnum > 0 AND NOT a.attisdropped;
    IF actual IS DISTINCT FROM t.columnas THEN
      RAISE EXCEPTION 'p0018 abortada sin cambios: esart_firma.% no coincide con el inventario (columnas/tipos/nulabilidad).', t.tabla;
    END IF;
    SELECT array_agg(r) INTO faltantes FROM unnest(t.restricciones) r
      WHERE NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = to_regclass('esart_firma.' || t.tabla) AND k.conname = r);
    IF faltantes IS NOT NULL THEN
      RAISE EXCEPTION 'p0018 abortada sin cambios: esart_firma.% no tiene las restricciones %', t.tabla, faltantes;
    END IF;
  END LOOP;
  IF to_regprocedure('esart_firma.bloquear_mutacion_evidencia()') IS NULL THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: falta la función heredada esart_firma.bloquear_mutacion_evidencia().';
  END IF;
  -- Un solo mecanismo de autenticación: la autenticación heredada debe estar vacía.
  IF EXISTS (SELECT 1 FROM esart_firma.totp_factores) OR EXISTS (SELECT 1 FROM esart_firma.totp_recuperacion)
     OR EXISTS (SELECT 1 FROM esart_firma.sesiones_firma) THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: totp_factores, totp_recuperacion o sesiones_firma tienen registros; decidir su migración a TOTP de ESART antes.';
  END IF;
  IF EXISTS (SELECT 1 FROM esart_firma.desafios_autenticacion WHERE proposito <> 'FIRMAR') THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: hay desafíos heredados de login/MFA.';
  END IF;
  IF EXISTS (SELECT 1 FROM esart.componentes WHERE codigo = 'FIRMA_DOCUMENTOS'
             AND (ruta_angular IS NOT NULL OR componente_padre_id IS NOT NULL)) THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: existe un componente FIRMA_DOCUMENTOS distinto (con ruta o padre).';
  END IF;
END
$guardas$;

-- Huella de los datos heredados antes de cambiar nada (se compara al final).
CREATE TEMP TABLE p0018_huella ON COMMIT DROP AS
SELECT 'conteo:' || c.relname AS clave,
       (xpath('/row/n/text()', query_to_xml('SELECT count(*) AS n FROM esart_firma.' || quote_ident(c.relname), false, true, '')))[1]::text AS valor
FROM pg_class c
WHERE c.relnamespace = to_regnamespace('esart_firma') AND c.relkind = 'r'
  AND c.relname IN ({", ".join(literal(t["tabla"]) for t in HEREDADO)})
UNION ALL SELECT 'md5:roles_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.roles_firma t
UNION ALL SELECT 'md5:permisos_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.permisos_firma t
UNION ALL SELECT 'md5:rol_permiso', md5(coalesce(string_agg(t::text, '|' ORDER BY rol_id, permiso_id), '')) FROM esart_firma.rol_permiso t
UNION ALL SELECT 'md5:asignaciones_rol', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.asignaciones_rol t;"""


COMPROBACION_FINAL = """DO $comprobacion$
DECLARE
  diferencias text;
BEGIN
  -- Las filas de roles/permisos y los conteos se recalculan y se comparan con la huella previa.
  -- (Las tablas heredadas ahora tienen columnas extra: el md5 se calcula solo con las originales.)
  WITH ahora AS (
    SELECT 'conteo:' || c.relname AS clave,
           (xpath('/row/n/text()', query_to_xml('SELECT count(*) AS n FROM esart_firma.' || quote_ident(c.relname), false, true, '')))[1]::text AS valor
    FROM pg_class c
    WHERE c.relnamespace = to_regnamespace('esart_firma') AND c.relkind = 'r'
      AND 'conteo:' || c.relname IN (SELECT clave FROM p0018_huella)
    UNION ALL SELECT 'md5:roles_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.roles_firma t
    UNION ALL SELECT 'md5:permisos_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.permisos_firma t
    UNION ALL SELECT 'md5:rol_permiso', md5(coalesce(string_agg(t::text, '|' ORDER BY rol_id, permiso_id), '')) FROM esart_firma.rol_permiso t
    UNION ALL SELECT 'md5:asignaciones_rol', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.asignaciones_rol t
  )
  SELECT string_agg(h.clave, ', ') INTO diferencias
  FROM p0018_huella h LEFT JOIN ahora a ON a.clave = h.clave
  WHERE a.valor IS DISTINCT FROM h.valor;
  IF diferencias IS NOT NULL THEN
    RAISE EXCEPTION 'p0018 revertida: cambió el contenido heredado (%)', diferencias;
  END IF;
  IF (SELECT count(*) FROM pg_class WHERE relnamespace = to_regnamespace('esart_firma') AND relkind = 'r') <> 23 THEN
    RAISE EXCEPTION 'p0018 revertida: esart_firma debía quedar con 23 tablas (21 heredadas + 2 nuevas).';
  END IF;
END
$comprobacion$;"""


def main() -> int:
    p0018 = capturar("p0018_firma_documental.py", sin_guardas_python)
    p0019 = capturar("p0019_firma_movil.py")
    cuerpo_p0018 = ";\n\n".join(s.rstrip(";") for s in p0018) + ";"
    cuerpo_p0019 = ";\n\n".join(s.rstrip(";") for s in p0019) + ";"
    # Comprobaciones del SQL extraído: debe traer lo esencial y nada destructivo.
    if not all(f in cuerpo_p0018 for f in ("identidades ADD COLUMN usuario_id", "CREATE TABLE esart_firma.documentos",
                                           "CREATE TABLE esart_firma.versiones_documento")):  # fmt: skip
        raise RuntimeError("El SQL extraído de p0018 está incompleto.")
    if "CREATE SCHEMA" in cuerpo_p0018 or "DROP " in cuerpo_p0018.upper().replace("DROP NOT NULL", ""):
        raise RuntimeError(
            "El SQL extraído de p0018 contiene operaciones no esperadas (esquema nuevo o DROP)."
        )
    sql = f"""-- =====================================================================================
-- ESART — p0018 (firma documental conciliada) + p0019 (permisos de la firma desde el celular)
-- Ejecución MANUAL como postgres sobre esart_db. NO EJECUTAR DESDE LA APLICACIÓN.
-- Generado por herramientas/generar_sql_p0018_p0019.py desde las migraciones (no editar a mano).
--
-- ANTES: sacar un respaldo de esart_db (ver docs/ESART_FIRMA_MOVIL.md, sección "Aplicar en esart_db").
--
-- Todo va en UNA transacción: si una guarda falla, PostgreSQL revierte todo y no queda nada a medias.
-- Las guardas abortan si la estructura de esart_firma no es exactamente la inventariada, si ya se
-- ejecutó antes, o si la autenticación heredada tiene datos. Al final se verifica que los conteos de
-- las 21 tablas y los 5 roles / 8 permisos sigan idénticos.
--
-- No modifica esart.alembic_version: esart_db sigue marcando p0014 porque p0015/p0016 también se
-- aplicaron a mano y p0017 (TOTP administrativo) no está aplicada. Si en el futuro se usa Alembic,
-- p0018 detectará sus objetos y se detendrá sin tocar nada (ver la documentación).
-- =====================================================================================

\\set ON_ERROR_STOP on

-- Estado ANTES (solo lectura)
SELECT 'antes' AS momento, count(*) FILTER (WHERE relkind = 'r') AS tablas_esart_firma
FROM pg_class WHERE relnamespace = to_regnamespace('esart_firma');
SELECT 'roles_firma' AS tabla, count(*) FROM esart_firma.roles_firma
UNION ALL SELECT 'permisos_firma', count(*) FROM esart_firma.permisos_firma;

BEGIN;

-- 1. Guardas previas -----------------------------------------------------------------
{guardas_previas()}

-- 2. p0018: conciliación (solo adiciones) --------------------------------------------
{cuerpo_p0018}

-- 3. p0019: permisos de la API para la firma desde el celular -----------------------
{cuerpo_p0019}

-- 4. Comprobación final (si algo cambió, se revierte todo) ---------------------------
{COMPROBACION_FINAL}

COMMIT;

-- Estado DESPUÉS (solo lectura)
SELECT 'despues' AS momento, count(*) FILTER (WHERE relkind = 'r') AS tablas_esart_firma
FROM pg_class WHERE relnamespace = to_regnamespace('esart_firma');
SELECT 'roles_firma' AS tabla, count(*) FROM esart_firma.roles_firma
UNION ALL SELECT 'permisos_firma', count(*) FROM esart_firma.permisos_firma
UNION ALL SELECT 'documentos (nueva)', count(*) FROM esart_firma.documentos;
SELECT codigo, nombre FROM esart.componentes WHERE codigo = 'FIRMA_DOCUMENTOS';
"""
    SALIDA.write_text(sql, encoding="utf-8", newline="\n")
    print(f"{SALIDA.relative_to(RAIZ)}: {len(p0018)} sentencias p0018, {len(p0019)} p0019")
    return 0


if __name__ == "__main__":
    sys.exit(main())
