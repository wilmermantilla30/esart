"""Permisos efectivos del flujo TOTP; sin DDL ni dependencia de operaciones académicas."""

import json

from sqlalchemy import text

# SELECT completos porque el ORM carga estas entidades. Auditoría solo lee RETURNING.
LECTURA = ("usuario_totp", "totp_recuperacion", "politicas_accion", "desafios")
INSERCION = ("usuario_totp", "totp_recuperacion", "desafios", "auditoria", "auditoria_cambios")
ACTUALIZACION = {
    "usuario_totp": (
        "secreto_cifrado",
        "estado",
        "activado_en",
        "expira_configuracion_en",
        "revocado_en",
        "ultimo_intervalo_aceptado",
        "actualizado_en",
    ),
    "totp_recuperacion": ("usado_en", "revocado_en"),
    "desafios": ("estado", "intentos", "verificado_en", "consumido_en"),
}
RETORNO = {"auditoria": ("id", "fecha_evento"), "auditoria_cambios": ("id", "creado_en")}


def requisitos():
    salida = [{"tabla": t, "permiso": "SELECT", "columna": ""} for t in LECTURA]
    salida += [{"tabla": t, "permiso": "INSERT", "columna": ""} for t in INSERCION]
    for permiso, tablas in (("UPDATE", ACTUALIZACION), ("SELECT", RETORNO)):
        salida += [
            {"tabla": t, "permiso": permiso, "columna": c} for t, columnas in tablas.items() for c in columnas
        ]
    return salida


async def permisos_faltantes(sesion):
    uso = await sesion.scalar(
        text("SELECT COALESCE(has_schema_privilege(to_regnamespace('seguridad'),'USAGE'),false)")
    )
    if not uso:
        return ["seguridad:USAGE"]
    filas = (
        await sesion.execute(
            text("""
        SELECT r.tabla,r.permiso,r.columna FROM jsonb_to_recordset(CAST(:requisitos AS jsonb))
          AS r(tabla text,permiso text,columna text)
        WHERE NOT CASE
          WHEN to_regclass('seguridad.' || r.tabla) IS NULL THEN false
          WHEN r.columna='' THEN has_table_privilege('seguridad.' || r.tabla,r.permiso)
          WHEN NOT EXISTS(SELECT 1 FROM pg_attribute a
            WHERE a.attrelid=to_regclass('seguridad.' || r.tabla)
            AND a.attname=r.columna AND NOT a.attisdropped) THEN false
          ELSE has_column_privilege('seguridad.' || r.tabla,r.columna,r.permiso)
        END ORDER BY r.tabla,r.permiso,r.columna
    """),
            {"requisitos": json.dumps(requisitos())},
        )
    ).mappings()
    faltantes = [f"seguridad.{r['tabla']}:{r['permiso']}({r['columna'] or '*'})" for r in filas]
    # Identity usa generación interna; no exigir USAGE de secuencia como si fuera serial.
    secuencias = (
        await sesion.execute(
            text("""
        SELECT c.relname AS tabla,a.attidentity::text AS identidad,
          pg_get_serial_sequence(format('%I.%I',n.nspname,c.relname),a.attname) AS secuencia
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='id' AND NOT a.attisdropped
        WHERE n.nspname='seguridad' AND c.relname=ANY(CAST(:tablas AS text[]))
    """),
            {"tablas": list(INSERCION)},
        )
    ).mappings()
    for fila in secuencias:
        if fila["secuencia"] and not fila["identidad"]:
            permitido = await sesion.scalar(
                text("SELECT has_sequence_privilege(CAST(:secuencia AS regclass),'USAGE,UPDATE')"),
                {"secuencia": fila["secuencia"]},
            )
            if not permitido:
                faltantes.append(f"{fila['secuencia']}:USAGE")
    return faltantes
