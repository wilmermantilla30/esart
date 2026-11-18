-- OPCIONAL: pasa los cursos ya creados al formato "<SIGLA> <NN>" (SACLI 01, SACLI 02, COFUO 01...).
-- NO EJECUTAR DESDE LA APLICACION. Ejecutar manualmente como postgres.
--
-- Antes, el numero del curso era un consecutivo global ("1", "2", "3"...). Desde este cambio el
-- cargue numera por tipo de curso. Este script renumera TODOS los cursos de cada tipo en orden
-- cronologico (fecha_inicio y, si empatan, id), para que la numeracion quede continua.
-- Los cursos se relacionan por id (historial, artillero_cursos): renumerar no rompe nada.
-- Ojo: si algun codigo viejo ya se uso en documentos impresos, cambiara.

-- 1. VISTA PREVIA: codigo actual -> codigo nuevo (no cambia nada).
SELECT c.id, tc.codigo AS tipo, c.fecha_inicio, c.codigo AS codigo_actual,
       upper(trim(tc.codigo)) || ' ' ||
       CASE WHEN n < 10 THEN '0' || n ELSE n::text END AS codigo_nuevo
FROM (
    SELECT c.*, row_number() OVER (PARTITION BY c.tipo_curso_id ORDER BY c.fecha_inicio, c.id) AS n
    FROM esart.cursos c
) c
JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
ORDER BY tc.codigo, n;

-- 2. RENUMERAR (en dos pasos: el codigo es UNICO y un intercambio chocaria en el paso directo).
BEGIN;
UPDATE esart.cursos SET codigo = 'TMP-' || id;
UPDATE esart.cursos c
SET codigo = upper(trim(tc.codigo)) || ' ' || CASE WHEN o.n < 10 THEN '0' || o.n ELSE o.n::text END
FROM (
    SELECT id, row_number() OVER (PARTITION BY tipo_curso_id ORDER BY fecha_inicio, id) AS n
    FROM esart.cursos
) o
JOIN esart.cursos c2 ON c2.id = o.id
JOIN esart.tipos_curso tc ON tc.id = c2.tipo_curso_id
WHERE c.id = o.id;
COMMIT;

-- 3. COMPROBAR: no debe quedar ningun codigo TMP- ni solo numerico.
SELECT count(*) AS pendientes FROM esart.cursos WHERE codigo LIKE 'TMP-%' OR codigo ~ '^[0-9]+$';
