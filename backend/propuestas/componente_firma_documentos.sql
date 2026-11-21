-- Agrega "Firma documental" (FIRMA_DOCUMENTOS) a la malla de permisos, sin esperar a p0018.
-- NO EJECUTAR DESDE LA APLICACION. Ejecutar manualmente como postgres en esart_db.
-- Es idempotente: si ya existe no cambia nada (ni los permisos que ya se hayan ajustado en la malla).
-- Es lo mismo que hace el paso 7 de p0018; p0018 lo detecta y no lo repite.
--
-- Qué habilita este componente (Administración → Malla de permisos):
--   * Leer:  ver las solicitudes de firma de todos y descargar cualquier documento firmado.
--   * Crear: autorizar firmantes (POST /api/firma/autorizaciones).
-- Ser FIRMANTE es otra cosa: requiere una autorización vigente (con cargo) y el autenticador activo.
-- Las firmas en sí siguen necesitando p0018 + p0019 aplicadas (estructura y permisos de esart_firma).

BEGIN;

INSERT INTO esart.componentes (codigo, nombre, ruta_angular, orden, activo)
VALUES ('FIRMA_DOCUMENTOS', 'Firma documental', NULL, 120, true)
ON CONFLICT (codigo) DO NOTHING;

-- Por defecto: ADMINISTRADOR accede, crea y lee; los demás roles quedan sin acceso (se habilita en la malla).
INSERT INTO esart.rol_permisos (rol_id, componente_id, puede_acceder, puede_crear, puede_leer, puede_actualizar, puede_eliminar)
SELECT r.id, c.id, (r.codigo = 'ADMINISTRADOR'), (r.codigo = 'ADMINISTRADOR'), (r.codigo = 'ADMINISTRADOR'), false, false
FROM esart.roles r CROSS JOIN esart.componentes c
WHERE c.codigo = 'FIRMA_DOCUMENTOS'
ON CONFLICT (rol_id, componente_id) DO NOTHING;

COMMIT;

-- Comprobar: debe aparecer el componente y una fila por rol.
SELECT c.codigo, c.nombre, r.codigo AS rol, rp.puede_acceder, rp.puede_crear, rp.puede_leer
FROM esart.componentes c
JOIN esart.rol_permisos rp ON rp.componente_id = c.id
JOIN esart.roles r ON r.id = rp.rol_id
WHERE c.codigo = 'FIRMA_DOCUMENTOS'
ORDER BY r.codigo;
