-- AUTORIZADA por el usuario; todavía no ejecutada desde Codex.
-- Ejecutar con propietario/administrador en esart_db; no como esart_aplicacion.
-- Solo lectura institucional para las rutas de catálogos, sin permisos globales.
BEGIN;
DO $$ BEGIN
  IF current_database()<>'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
END $$;
GRANT USAGE ON SCHEMA esart, esart_ref TO esart_aplicacion;
GRANT SELECT ON esart_ref.unidades_militares,
                esart.tipos_unidad, esart.tipos_cargo, esart.tipos_curso TO esart_aplicacion;
COMMIT;
