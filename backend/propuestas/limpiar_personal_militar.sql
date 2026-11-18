-- Vacía esart.personal_militar y reinicia su consecutivo (id vuelve a 1).
-- NO EJECUTAR DESDE LA APLICACION. Solo para desarrollo, manualmente como postgres.
-- ¡Borra datos! TRUNCATE ... CASCADE también vacía TODAS las tablas que dependen del personal
-- (hoja de vida, inscripciones, alumnos, notas, diplomas, egresados, certificados, etc.).

-- 1. REVISAR PRIMERO cuántas filas se van a perder:
SELECT 'personal_militar' AS tabla, count(*) FROM esart.personal_militar
UNION ALL SELECT 'hoja_vida_artillero', count(*) FROM esart.hoja_vida_artillero
UNION ALL SELECT 'artillero_cargos', count(*) FROM esart.artillero_cargos
UNION ALL SELECT 'artillero_certificaciones', count(*) FROM esart.artillero_certificaciones
UNION ALL SELECT 'artillero_cursos', count(*) FROM esart.artillero_cursos
UNION ALL SELECT 'artillero_disparos', count(*) FROM esart.artillero_disparos
UNION ALL SELECT 'inscripciones_curso', count(*) FROM esart.inscripciones_curso
UNION ALL SELECT 'alumnos_activos', count(*) FROM esart.alumnos_activos
UNION ALL SELECT 'notas_materia', count(*) FROM esart.notas_materia
UNION ALL SELECT 'habilitaciones', count(*) FROM esart.habilitaciones
UNION ALL SELECT 'alertas_academicas', count(*) FROM esart.alertas_academicas
UNION ALL SELECT 'consejos_academicos', count(*) FROM esart.consejos_academicos
UNION ALL SELECT 'diplomas', count(*) FROM esart.diplomas
UNION ALL SELECT 'egresados_curso', count(*) FROM esart.egresados_curso
UNION ALL SELECT 'notas_finales_egresado', count(*) FROM esart.notas_finales_egresado
UNION ALL SELECT 'participantes_reentrenamiento', count(*) FROM esart.participantes_reentrenamiento
UNION ALL SELECT 'certificados_reentrenamiento', count(*) FROM esart.certificados_reentrenamiento
UNION ALL SELECT 'alertas_certificacion', count(*) FROM esart.alertas_certificacion
UNION ALL SELECT 'operadores_sistema', count(*) FROM esart.operadores_sistema
UNION ALL SELECT 'cursos', count(*) FROM esart.cursos;

-- 2. LIMPIAR (psql muestra en un NOTICE qué otras tablas vacía el CASCADE):
BEGIN;
TRUNCATE TABLE esart.personal_militar, esart.hoja_vida_artillero RESTART IDENTITY CASCADE;

-- Opcional: si también quieres borrar los cursos creados por los cargues y que el número
-- del curso vuelva a empezar en 1, quita los dos guiones de la línea siguiente:
-- TRUNCATE TABLE esart.cursos RESTART IDENTITY CASCADE;
COMMIT;

-- 3. Comprobar: debe dar 0.
SELECT count(*) AS personal_restante FROM esart.personal_militar;
