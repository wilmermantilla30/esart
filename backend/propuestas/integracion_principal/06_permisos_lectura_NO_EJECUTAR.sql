-- PROPUESTA ACL, NO EJECUTADA. No cambia propietarios ni credenciales.
-- Solo habilita la lectura de unidades y tipos; no concede escritura ni administra roles.
BEGIN;
DO $$ BEGIN
 IF current_database()<>'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
END $$;
GRANT USAGE ON SCHEMA esart_ref, esart TO esart_aplicacion;
GRANT SELECT ON esart_ref.unidades_militares, esart.tipos_unidad TO esart_aplicacion;
COMMIT;
-- Los permisos necesarios para autenticación y mallas heredadas requieren revisión
-- independiente. Este archivo NO habilita endpoints públicos ni sustituye sus controles.
