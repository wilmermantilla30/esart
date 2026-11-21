\set ON_ERROR_STOP on
-- Ejecutar con esart_respaldo solo despues de su aprovisionamiento.
-- Lectura estricta: no modifica datos, secuencias ni esquemas.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT current_database() AS base, current_user AS cuenta,
       inet_server_addr() AS servidor, current_setting('transaction_read_only') AS solo_lectura;

SELECT version_num AS revision_alembic FROM esart.alembic_version;

SELECT count(*) AS tablas_esart_firma
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='esart_firma' AND c.relkind='r';

SELECT 'asignaciones_rol' AS tabla, count(*) AS filas FROM esart_firma.asignaciones_rol
UNION ALL SELECT 'auditoria_cambios', count(*) FROM esart_firma.auditoria_cambios
UNION ALL SELECT 'auditoria_eventos', count(*) FROM esart_firma.auditoria_eventos
UNION ALL SELECT 'autorizaciones_firmantes', count(*) FROM esart_firma.autorizaciones_firmantes
UNION ALL SELECT 'certificados', count(*) FROM esart_firma.certificados
UNION ALL SELECT 'consentimientos_firma', count(*) FROM esart_firma.consentimientos_firma
UNION ALL SELECT 'desafios_autenticacion', count(*) FROM esart_firma.desafios_autenticacion
UNION ALL SELECT 'evidencias', count(*) FROM esart_firma.evidencias
UNION ALL SELECT 'firmas_certificado', count(*) FROM esart_firma.firmas_certificado
UNION ALL SELECT 'identidades', count(*) FROM esart_firma.identidades
UNION ALL SELECT 'permisos_firma', count(*) FROM esart_firma.permisos_firma
UNION ALL SELECT 'plantillas_certificado', count(*) FROM esart_firma.plantillas_certificado
UNION ALL SELECT 'rol_permiso', count(*) FROM esart_firma.rol_permiso
UNION ALL SELECT 'roles_firma', count(*) FROM esart_firma.roles_firma
UNION ALL SELECT 'sesiones_firma', count(*) FROM esart_firma.sesiones_firma
UNION ALL SELECT 'solicitudes_firma', count(*) FROM esart_firma.solicitudes_firma
UNION ALL SELECT 'totp_factores', count(*) FROM esart_firma.totp_factores
UNION ALL SELECT 'totp_recuperacion', count(*) FROM esart_firma.totp_recuperacion
UNION ALL SELECT 'validaciones_criptograficas', count(*) FROM esart_firma.validaciones_criptograficas
UNION ALL SELECT 'verificaciones_publicas', count(*) FROM esart_firma.verificaciones_publicas
UNION ALL SELECT 'versiones_certificado', count(*) FROM esart_firma.versiones_certificado
ORDER BY tabla;

SELECT co.conname AS restriccion, co.contype AS tipo,
       co.conrelid::regclass AS tabla_origen,
       co.confrelid::regclass AS tabla_destino,
       pg_get_constraintdef(co.oid, true) AS definicion
FROM pg_constraint co
JOIN pg_namespace n ON n.oid=co.connamespace
WHERE n.nspname='esart_firma'
ORDER BY co.conrelid::regclass::text, co.conname;

COMMIT;
