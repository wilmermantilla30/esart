-- SOLO LECTURA. Para que lo ejecute una cuenta autorizada a leer los datos.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
DO $$ BEGIN
 IF current_database() <> 'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
END $$;
SELECT current_database() AS base, current_user AS cuenta;
SELECT count(*) AS registros, min(id) AS minimo_id, max(id) AS maximo_id
FROM esart_ref.unidades_militares;
-- Un ID sin referencias tampoco puede suponerse libre o asignarse por su posición.
SELECT u.id,
 (SELECT count(*) FROM esart.personal_militar x WHERE x.unidad_actual_id=u.id) AS personal,
 (SELECT count(*) FROM esart.artillero_cargos x WHERE x.unidad_id=u.id) AS cargos,
 (SELECT count(*) FROM esart.artillero_disparos x WHERE x.unidad_id=u.id) AS disparos,
 (SELECT count(*) FROM esart.egresados_curso x WHERE x.unidad_destino_id=u.id) AS egresados,
 (SELECT count(*) FROM esart.reentrenamientos x WHERE x.unidad_id=u.id) AS reentrenamientos
FROM esart_ref.unidades_militares u ORDER BY u.id;
SELECT n.nspname AS esquema,c.relname AS tabla,k.conname,pg_get_constraintdef(k.oid)
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE k.contype='f' AND k.confrelid=(
 SELECT c2.oid FROM pg_class c2 JOIN pg_namespace n2 ON n2.oid=c2.relnamespace
 WHERE n2.nspname='esart_ref' AND c2.relname='unidades_militares');
SELECT last_value,is_called FROM esart_ref.unidades_militares_id_seq;
COMMIT;
