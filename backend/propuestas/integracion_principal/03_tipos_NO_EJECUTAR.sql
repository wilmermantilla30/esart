-- PROPUESTA, NO EJECUTADA. Solo tras respaldo, aprobacion y mapeo resuelto.
BEGIN;
DO $$ BEGIN
 IF current_database()<>'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
END $$;
LOCK TABLE esart.tipos_unidad IN SHARE ROW EXCLUSIVE MODE;
DO $tipos$
DECLARE r RECORD;
BEGIN
 FOR r IN SELECT * FROM (VALUES ('BAACA','Batallón de Artillería',true),('BAADA','Batallón de Artillería de Defensa Aérea',true),('BATAR','Batería de Artillería',true),('BR','Brigada',true),('CECFU','Centro de Coordinación de Fuegos',true),('CEDOC','Centro de Educación y Doctrina',true),('CEM','Centro de Educación Militar',true),('DIV','División',true),('ESART','Escuela de Artillería',true)) AS datos(codigo,nombre,activo) LOOP
  IF EXISTS (SELECT 1 FROM esart.tipos_unidad t WHERE t.codigo=r.codigo AND
             (t.nombre IS DISTINCT FROM r.nombre OR t.activo IS DISTINCT FROM r.activo)) THEN
   RAISE EXCEPTION 'Tipo incompatible: %',r.codigo;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM esart.tipos_unidad t WHERE t.codigo=r.codigo) THEN
   INSERT INTO esart.tipos_unidad(codigo,nombre,activo) VALUES(r.codigo,r.nombre,r.activo);
  END IF;
 END LOOP;
END $tipos$;
COMMIT;
