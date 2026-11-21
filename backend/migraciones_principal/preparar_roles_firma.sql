-- Provisionamiento interactivo local, ejecutado una sola vez por el operador
-- administrativo despues de rotar la credencial expuesta.
-- No aplica migraciones, no cambia propietarios ni concede privilegios a la API.
-- La cuenta postgres se usa solo para esta preparacion; nunca para FastAPI/Alembic.
-- Ejecutar contra postgres con psql -X -W -v ON_ERROR_STOP=1 -f este_archivo.

BEGIN;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='esart_migrador') THEN
    CREATE ROLE esart_migrador NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;
\password esart_migrador
ALTER ROLE esart_migrador LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='esart_respaldo') THEN
    CREATE ROLE esart_respaldo NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;
\password esart_respaldo
ALTER ROLE esart_respaldo LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
    WHERE r.rolname='esart_migrador'
  ) THEN
    RAISE EXCEPTION 'esart_migrador tiene membresias; revisar y retirar manualmente antes de continuar';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_auth_members m
    JOIN pg_roles r ON r.oid=m.member
    JOIN pg_roles g ON g.oid=m.roleid
    WHERE r.rolname='esart_respaldo' AND g.rolname <> 'pg_read_all_data'
  ) THEN
    RAISE EXCEPTION 'esart_respaldo tiene membresias adicionales; revisar antes de continuar';
  END IF;
END $$;

-- pg_dump necesita leer todas las tablas y secuencias para que el respaldo sea
-- completo. Este rol no recibe escritura, DDL ni capacidad de iniciar migraciones.
GRANT CONNECT ON DATABASE esart_db TO esart_respaldo;
GRANT pg_read_all_data TO esart_respaldo;
REVOKE pg_read_all_data FROM esart_migrador;

-- Deliberadamente no se conceden grants sobre esart_db a esart_migrador.
-- En la copia de prueba, crear la base con OWNER esart_migrador y restaurar
-- con --no-owner --no-privileges; así el rol será propietario de los objetos
-- restaurados y podrá ejecutar p0015-p0018 en esa copia. Los grants de p0016
-- a esart_aplicacion se ejecutarán en esa base aislada.

-- Verificación sin imprimir secretos:
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname IN ('esart_migrador','esart_respaldo') ORDER BY rolname;

SELECT miembro.rolname AS miembro, concedido.rolname AS rol_concedido
FROM pg_auth_members m
JOIN pg_roles miembro ON miembro.oid=m.member
JOIN pg_roles concedido ON concedido.oid=m.roleid
WHERE miembro.rolname IN ('esart_migrador','esart_respaldo')
ORDER BY miembro.rolname, concedido.rolname;

COMMIT;
