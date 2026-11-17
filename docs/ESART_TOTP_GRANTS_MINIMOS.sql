-- REVISAR Y EJECUTAR COMO PROPIETARIO. No modifica estructura ni aplica migraciones.
-- Destino exclusivo: esart_db. Sin ALL TABLES, ALL SEQUENCES, DDL ni permisos administrativos.
BEGIN;
DO $$ BEGIN
  IF current_database() <> 'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
END $$;

-- USAGE de seguridad y SELECT/INSERT/UPDATE de usuario_totp ya están concedidos.
GRANT SELECT ON seguridad.politicas_accion TO esart_aplicacion;
GRANT SELECT, INSERT ON seguridad.desafios, seguridad.totp_recuperacion TO esart_aplicacion;
GRANT UPDATE (estado, intentos, verificado_en, consumido_en)
  ON seguridad.desafios TO esart_aplicacion;
GRANT UPDATE (usado_en, revocado_en)
  ON seguridad.totp_recuperacion TO esart_aplicacion;
GRANT INSERT ON seguridad.auditoria, seguridad.auditoria_cambios TO esart_aplicacion;
-- SQLAlchemy usa INSERT ... RETURNING: solo se habilitan las columnas devueltas.
GRANT SELECT (id, fecha_evento) ON seguridad.auditoria TO esart_aplicacion;
GRANT SELECT (id, creado_en) ON seguridad.auditoria_cambios TO esart_aplicacion;

-- No se concede nada sobre autorizaciones: no participa en login, QR ni TOTP.
-- Los cinco id bigint reales son GENERATED ALWAYS AS IDENTITY. No necesitan USAGE
-- directo sobre sus secuencias para INSERT ... RETURNING; el ORM no llama nextval.
-- UUID de desafios y autorizaciones se generan en Python, sin secuencia.
-- No se concede SELECT/UPDATE de secuencias ni USAGE de politicas_accion_id_seq:
-- el rol de aplicación solo consulta políticas, no las crea.

COMMIT;

-- SOLO LECTURA: comprobar políticas tras los GRANT. Si faltan, el propietario debe
-- revisar ESART_TOTP_POLITICAS_MINIMAS.sql; no habilitar INSERT de políticas al backend.
SELECT codigo, activa, requiere_totp, vigencia_segundos
FROM seguridad.politicas_accion WHERE codigo IN ('LOGIN_TOTP','DESBLOQUEO_TOTP');

SELECT c.relname AS tabla, a.attidentity AS identidad,
       pg_get_serial_sequence(format('%I.%I',n.nspname,c.relname),'id') AS secuencia
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='id'
WHERE n.nspname='seguridad' AND c.relkind='r'
ORDER BY c.relname;
