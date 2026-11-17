-- SOLO LECTURA. Ejecutar como propietario autorizado, conectado a esart_db.
-- No invoca env.py, no crea objetos, no usa stamp ni avanza secuencias.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;

SELECT current_database() AS base, current_user AS cuenta,
       inet_server_addr() AS servidor, inet_server_port() AS puerto,
       current_setting('server_version') AS version,
       pg_postmaster_start_time() AS inicio_instancia;

SELECT version_num FROM esart.alembic_version ORDER BY version_num;

SELECT n.nspname AS esquema, c.relname AS tabla, pg_get_userbyid(c.relowner) AS propietario
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p') AND
  (n.nspname='seguridad' OR
   (n.nspname='esart' AND c.relname IN ('alembic_version','componentes','rol_permisos',
       'usuario_permisos','parametros_habilitacion','auditoria_eventos','desafios_captcha',
       'auditoria_acceso','limites_inicio_ip','estados_acceso_anonimos')) OR
   (n.nspname='esart_ref' AND c.relname='usuarios'))
ORDER BY n.nspname,c.relname;

-- Los siete objetos deben ser tablas con columnas/tipos y PK/UQ compatibles.
SELECT c.relname AS tabla,a.attname AS columna,
       format_type(a.atttypid,a.atttypmod) AS tipo,a.attnotnull AS obligatorio,
       a.attidentity AS identidad,pg_get_expr(d.adbin,d.adrelid) AS defecto
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
WHERE n.nspname='seguridad' AND c.relkind='r' ORDER BY c.relname,a.attnum;

SELECT n.nspname AS esquema,c.relname AS tabla,k.conname,k.convalidated,
       pg_get_constraintdef(k.oid) AS definicion
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname IN ('seguridad','esart','esart_ref') ORDER BY n.nspname,c.relname,k.conname;

SELECT n.nspname AS esquema,c.relname AS tabla,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname IN ('seguridad','esart','esart_ref') AND NOT t.tgisinternal;

-- Cada resultado debe ser cero. No borrar filas para conseguirlo.
SELECT 'usuario_totp' AS tabla,count(*) AS huerfanos FROM seguridad.usuario_totp t
LEFT JOIN esart_ref.usuarios u ON u.id=t.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'totp_recuperacion',count(*) FROM seguridad.totp_recuperacion t
LEFT JOIN esart_ref.usuarios u ON u.id=t.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'desafios',count(*) FROM seguridad.desafios t
LEFT JOIN esart_ref.usuarios u ON u.id=t.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'autorizaciones',count(*) FROM seguridad.autorizaciones t
LEFT JOIN esart_ref.usuarios u ON u.id=t.usuario_id WHERE u.id IS NULL
UNION ALL SELECT 'auditoria',count(*) FROM seguridad.auditoria t
LEFT JOIN esart_ref.usuarios u ON u.id=t.usuario_id WHERE t.usuario_id IS NOT NULL AND u.id IS NULL;

SELECT count(*) AS contextos_incompatibles FROM seguridad.autorizaciones a
LEFT JOIN seguridad.desafios d
ON (a.desafio_id,a.usuario_id,a.politica_id,a.operacion_hash)=
   (d.id,d.usuario_id,d.politica_id,d.operacion_hash) WHERE d.id IS NULL;

SELECT codigo,activa,requiere_totp,vigencia_segundos,permiso_requerido
FROM seguridad.politicas_accion ORDER BY codigo;

-- Referencia antes/después, con la aplicación detenida y sin ejecutar pruebas entre capturas.
-- No devuelve contraseñas, hashes de contraseña, secretos ni códigos de recuperación.
SELECT count(*) AS usuarios,
       md5(COALESCE(string_agg(id::text||':'||intentos_fallidos_consecutivos::text||':'||
         COALESCE(bloqueado_hasta::text,''),',' ORDER BY id),'')) AS huella_contadores_bloqueo
FROM esart_ref.usuarios;
SELECT estado,count(*) FROM seguridad.usuario_totp GROUP BY estado ORDER BY estado;
SELECT count(*) AS captchas, count(consumido_en) AS consumidos FROM esart.desafios_captcha;
SELECT schemaname,sequencename,increment_by,last_value
FROM pg_sequences WHERE schemaname IN ('seguridad','esart','esart_ref') ORDER BY schemaname,sequencename;

-- Revisar sesiones largas/bloqueos antes de abrir la ventana de actualización.
SELECT pid,usename,application_name,state,xact_start,wait_event_type,wait_event
FROM pg_stat_activity WHERE datname='esart_db' AND pid<>pg_backend_pid();

ROLLBACK;
