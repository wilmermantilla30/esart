-- SOLO LECTURA. Ejecutar con operador autorizado; no devuelve secretos, hashes ni códigos.
BEGIN TRANSACTION READ ONLY;
SELECT current_database() AS base, current_user AS operador;
DO $$ BEGIN
 IF current_database() <> 'esart_db' THEN
   RAISE EXCEPTION 'Destino incorrecto';
 END IF;
END $$;
SELECT * FROM esart.alembic_version;
SELECT table_name,column_name,data_type,is_nullable
FROM information_schema.columns WHERE table_schema='seguridad'
ORDER BY table_name,ordinal_position;
SELECT c.relname AS tabla,k.conname,k.convalidated,pg_get_constraintdef(k.oid) AS definicion
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='seguridad'
ORDER BY c.relname,k.conname;
SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='seguridad';
SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='seguridad' AND NOT t.tgisinternal;
SELECT codigo,activa,requiere_totp,permiso_requerido,vigencia_segundos
FROM seguridad.politicas_accion ORDER BY codigo;
SELECT has_schema_privilege('esart_aplicacion','seguridad','USAGE') AS uso_esquema;
SELECT tablename,
 has_table_privilege('esart_aplicacion',format('%I.%I',schemaname,tablename),'SELECT') AS lectura,
 has_table_privilege('esart_aplicacion',format('%I.%I',schemaname,tablename),'INSERT') AS insercion,
 has_table_privilege('esart_aplicacion',format('%I.%I',schemaname,tablename),'DELETE') AS borrado
FROM pg_tables WHERE schemaname='seguridad' ORDER BY tablename;
SELECT 'usuario_totp' AS tabla,count(*) AS huerfanos FROM seguridad.usuario_totp s
LEFT JOIN esart_ref.usuarios u ON u.id=s.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'totp_recuperacion',count(*) FROM seguridad.totp_recuperacion s
LEFT JOIN esart_ref.usuarios u ON u.id=s.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'desafios',count(*) FROM seguridad.desafios s
LEFT JOIN esart_ref.usuarios u ON u.id=s.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'autorizaciones',count(*) FROM seguridad.autorizaciones s
LEFT JOIN esart_ref.usuarios u ON u.id=s.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'auditoria',count(*) FROM seguridad.auditoria s
LEFT JOIN esart_ref.usuarios u ON u.id=s.usuario_id WHERE s.usuario_id IS NOT NULL AND u.id IS NULL;
COMMIT;
