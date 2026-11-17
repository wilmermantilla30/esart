-- OPCIONAL, REQUIERE REVISIÓN DEL PROPIETARIO: solo datos, sin cambios de estructura.
-- Ejecutar únicamente si el diagnóstico confirma que faltan estas políticas.
BEGIN;
DO $$ BEGIN
  IF current_database() <> 'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
END $$;
INSERT INTO seguridad.politicas_accion
  (codigo, nombre, modulo, requiere_totp, activa, vigencia_segundos)
VALUES
  ('LOGIN_TOTP','Autenticación multifactor','SEGURIDAD',true,true,120),
  ('DESBLOQUEO_TOTP','Desbloqueo con autenticador vinculado','SEGURIDAD',true,true,120)
ON CONFLICT (codigo) DO NOTHING;
COMMIT;
-- No reemplaza una política existente ni cambia sus valores sin revisión.
