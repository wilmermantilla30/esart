-- p0015_registro_manual_personal: acción de auditoría PERSONAL_REGISTRADO.
-- NO EJECUTAR DESDE LA APLICACION. Ejecutar manualmente como postgres (dueño de las tablas).
-- Equivale a migraciones_principal/versions/p0015_registro_manual_personal.py.
BEGIN;
ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT ck_auditoria_eventos_ck_auditoria_eventos_accion;
ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT ck_auditoria_eventos_ck_auditoria_eventos_accion CHECK (accion IN ('LOGIN_EXITOSO', 'LOGIN_FALLIDO', 'USUARIO_BLOQUEADO', 'USUARIO_DESBLOQUEADO', 'CIERRE_SESION', 'CONSULTA_ARTILLERO', 'CONSULTA_HABILITADOS', 'CONSULTA_NO_HABILITADOS', 'CONSULTA_RESUMEN', 'ACCESO_DENEGADO', 'PERMISOS_ROL_MODIFICADOS', 'PERMISOS_USUARIO_MODIFICADOS', 'USUARIO_CREADO', 'IMPORTACION_EXCEL', 'USUARIO_ACTIVADO', 'USUARIO_DESACTIVADO', 'CONTRASENA_RESTABLECIDA', 'CONTRASENA_CAMBIADA', 'PARAMETROS_ACTUALIZADOS', 'PLANTILLA_PUBLICADA', 'PLANTILLA_DESCARGADA', 'PLANTILLA_RETIRADA', 'INSTRUCTOR_REGISTRADO', 'INSTRUCTOR_ACTUALIZADO', 'INSTRUCTOR_ACTIVADO', 'INSTRUCTOR_DESACTIVADO', 'PERSONAL_REGISTRADO'));
COMMIT;

-- Comprobar: debe mostrar PERSONAL_REGISTRADO dentro de la lista.
SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_auditoria_eventos_ck_auditoria_eventos_accion';
