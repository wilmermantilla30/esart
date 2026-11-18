-- SOLO LECTURA. Ejecutar tras una actualización autorizada y antes de abrir tráfico.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SELECT current_database(),current_user,inet_server_addr(),inet_server_port();
SELECT version_num FROM esart.alembic_version ORDER BY version_num;
-- Resultado esperado: una única fila p0010_merge_hu10_totp.

SELECT c.relname,k.conname,k.convalidated,pg_get_constraintdef(k.oid)
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='seguridad' AND k.conname IN (
 'fk_usuario_totp_usuario_esart','fk_totp_recuperacion_usuario_esart',
 'fk_desafios_usuario_esart','fk_autorizaciones_usuario_esart','fk_auditoria_usuario_esart',
 'uq_desafio_contexto','fk_autorizacion_contexto') ORDER BY k.conname;
-- Siete restricciones, definiciones correctas y validadas.

SELECT n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE NOT t.tgisinternal AND
 ((n.nspname='seguridad' AND c.relname IN ('auditoria','auditoria_cambios')) OR
  (n.nspname='esart' AND c.relname='auditoria_eventos'));
-- Cuatro triggers TOTP y dos HU-11, habilitados; verificar también sus funciones.

SELECT column_name,has_column_privilege('esart_aplicacion','esart_ref.usuarios',column_name,'UPDATE')
FROM information_schema.columns WHERE table_schema='esart_ref' AND table_name='usuarios'
ORDER BY ordinal_position;
SELECT c.relname,
 has_table_privilege('esart_aplicacion',c.oid,'SELECT') AS lectura,
 has_table_privilege('esart_aplicacion',c.oid,'INSERT') AS insercion,
 has_table_privilege('esart_aplicacion',c.oid,'UPDATE') AS actualizacion,
 has_table_privilege('esart_aplicacion',c.oid,'DELETE') AS borrado,
 has_table_privilege('esart_aplicacion',c.oid,'TRUNCATE') AS truncado
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='seguridad' AND c.relkind='r' ORDER BY c.relname;
-- Comparar con la matriz aprobada; UPDATE por columna se comprueba separadamente.

SELECT count(*) AS usuarios,
 md5(COALESCE(string_agg(id::text||':'||intentos_fallidos_consecutivos::text||':'||
   COALESCE(bloqueado_hasta::text,''),',' ORDER BY id),'')) AS huella_contadores_bloqueo
FROM esart_ref.usuarios;
SELECT estado,count(*) FROM seguridad.usuario_totp GROUP BY estado ORDER BY estado;
SELECT count(*),count(consumido_en) FROM esart.desafios_captcha;
SELECT codigo,activa,requiere_totp,vigencia_segundos,permiso_requerido
FROM seguridad.politicas_accion ORDER BY codigo;
SELECT codigo,valor FROM esart.parametros_habilitacion ORDER BY codigo;
SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint
WHERE conrelid='esart.auditoria_eventos'::regclass AND contype='c';
ROLLBACK;
