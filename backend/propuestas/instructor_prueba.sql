-- Instructor de PRUEBA para el selector "Comandante del curso" del cargue Excel.
-- NO EJECUTAR DESDE LA APLICACION. Ejecutar manualmente como postgres en un entorno de desarrollo.
-- Es idempotente: si ya existe, no duplica nada.
--
-- Crea:
--   1. Personal militar  9999000001  MY INSTRUCTOR DE PRUEBA (para mostrar grado y nombre).
--   2. Usuario esart_ref "instructor.prueba", INACTIVO y sin contraseña (no puede iniciar sesión).
--   3. Registro activo en esart.instructores.
-- En el selector aparecerá como: "MY INSTRUCTOR DE PRUEBA".

BEGIN;

INSERT INTO esart.personal_militar (documento_identidad, nombres, apellidos, grado, genero, categoria)
SELECT '9999000001', 'INSTRUCTOR', 'DE PRUEBA', 'MY', 'M', 'OFICIAL'
WHERE NOT EXISTS (
    SELECT 1 FROM esart.personal_militar WHERE documento_identidad = '9999000001'
);

INSERT INTO esart_ref.usuarios (usuario, contrasena_hash, documento_identidad, activo)
SELECT 'instructor.prueba', NULL, '9999000001', false
WHERE NOT EXISTS (
    SELECT 1 FROM esart_ref.usuarios
    WHERE lower(usuario) = 'instructor.prueba' OR documento_identidad = '9999000001'
);

INSERT INTO esart.instructores (usuario_id, fecha_ingreso_escuela, activo)
SELECT u.id, CURRENT_DATE, true
FROM esart_ref.usuarios u
WHERE u.documento_identidad = '9999000001'
  AND NOT EXISTS (SELECT 1 FROM esart.instructores i WHERE i.usuario_id = u.id);

-- Lo mismo que consulta el backend para llenar el selector:
SELECT i.id,
       COALESCE(NULLIF(TRIM(CONCAT_WS(' ', p.grado, p.nombres, p.apellidos)), ''),
                u.usuario, 'Instructor ' || i.id) AS nombre
FROM esart.instructores i
JOIN esart_ref.usuarios u ON u.id = i.usuario_id
LEFT JOIN esart.personal_militar p ON p.documento_identidad = u.documento_identidad
WHERE i.activo
ORDER BY nombre;

COMMIT;

-- Para retirarlo del selector más adelante (sin borrar referencias de cursos ya creados):
--   UPDATE esart.instructores SET activo = false
--   WHERE usuario_id = (SELECT id FROM esart_ref.usuarios WHERE documento_identidad = '9999000001');
