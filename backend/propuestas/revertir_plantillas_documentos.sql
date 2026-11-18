-- Revierte aplicacion/base_datos/plantillas_documentos.sql (gestión de plantillas documentales).
-- NO EJECUTAR DESDE LA APLICACION. Ejecutar manualmente como postgres.
-- No toca el esquema esart (ya existía y lo usa todo el sistema).
-- Sin CASCADE: si algo más depende de estas tablas, falla y no borra nada.
-- Los índices (idx_plantilla_version_vigente, idx_plantillas_nombre, idx_plantillas_estado,
-- idx_plantillas_versiones_fecha) y restricciones se eliminan junto con sus tablas.

-- 1. Revisar antes qué existe y cuántas filas tiene (las filas se pierden al borrar):
SELECT c.relname AS tabla, c.reltuples::bigint AS filas_aprox
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'esart' AND c.relname IN ('plantillas_documentos', 'plantillas_versiones');

-- 2. Eliminar (la hija primero, por la llave foránea):
BEGIN;
DROP TABLE IF EXISTS esart.plantillas_versiones;
DROP TABLE IF EXISTS esart.plantillas_documentos;
COMMIT;

-- 3. Comprobar: no debe devolver filas.
SELECT to_regclass('esart.plantillas_documentos') AS documentos,
       to_regclass('esart.plantillas_versiones') AS versiones
WHERE to_regclass('esart.plantillas_documentos') IS NOT NULL
   OR to_regclass('esart.plantillas_versiones') IS NOT NULL;
