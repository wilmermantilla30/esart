\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL search_path TO pg_catalog, pg_temp;
SET LOCAL TIME ZONE 'UTC';

DO $$
BEGIN
    IF current_database() <> 'esart_ensayo'
       OR current_user <> 'esart_migrador'
       OR host(inet_server_addr()) IS NULL
       OR host(inet_server_addr()) NOT IN ('127.0.0.1', '::1')
       OR NOT EXISTS (SELECT FROM pg_roles WHERE rolname = current_user AND NOT rolsuper)
    THEN
        RAISE EXCEPTION 'Preflight requiere esart_migrador no superusuario en esart_ensayo local';
    END IF;
    IF (SELECT array_agg(version_num::text) FROM esart.alembic_version)
       IS DISTINCT FROM ARRAY['p0017_restablecer_totp_admin'] THEN
        RAISE EXCEPTION 'La revisión de partida debe ser p0017_restablecer_totp_admin';
    END IF;
    IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'esart_firma' AND c.relkind IN ('r', 'p')) <> 23
       OR to_regclass('esart_firma.documentos') IS NULL
       OR to_regclass('esart_firma.versiones_documento') IS NULL THEN
        RAISE EXCEPTION 'Se esperaban 23 tablas de firma, incluidos documentos y versiones';
    END IF;
END
$$;

SELECT current_database() AS base, current_user AS usuario, host(inet_server_addr()) AS servidor,
       current_setting('server_version') AS version_pg, current_setting('transaction_read_only') AS solo_lectura,
       rolsuper, version_num,
       has_database_privilege(current_user, current_database(), 'CREATE') AS puede_crear_esquema
FROM esart.alembic_version JOIN pg_roles ON rolname = current_user;

SELECT string_agg(format(
    $consulta$
    SELECT %L AS tabla, %s::oid AS oid, count(*) AS filas,
           encode(sha256(convert_to(
               coalesce(string_agg(huella, '' ORDER BY huella COLLATE "C"), ''), 'UTF8')), 'hex') AS sha256
    FROM (
        SELECT encode(sha256(convert_to(to_jsonb(t)::text, 'UTF8')), 'hex') AS huella
        FROM %I.%I t
    ) datos
    $consulta$, c.relname, c.oid, n.nspname, c.relname), ' UNION ALL ' ORDER BY c.relname) || ' ORDER BY tabla'
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'esart_firma' AND c.relkind IN ('r', 'p')
\gexec

ROLLBACK;
