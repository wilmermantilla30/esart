-- PROPUESTA PARA EL PROPIETARIO/DBA AUTORIZADO. NO EJECUTAR DESDE LA APLICACION.
-- Revisar primero el diagnostico; este archivo NO cambia roles funcionales de usuarios.
-- Ejecutar manualmente en la base correcta. No contiene SUPERUSER, CREATE, UPDATE ni DELETE.
BEGIN;

-- Acceso a los dos esquemas utilizados por el flujo real.
GRANT USAGE ON SCHEMA esart, esart_ref TO esart_aplicacion;

-- Solo atributos de entrada: los IDs y fechas quedan generados por PostgreSQL.
GRANT INSERT (
    documento_identidad, nombres, apellidos, grado, genero, categoria,
    unidad_actual_id, especialidad_actual, activo
) ON TABLE esart.personal_militar TO esart_aplicacion;

-- Lectura minima para duplicados y RETURNING del INSERT de SQLAlchemy.
GRANT SELECT (id, documento_identidad)
ON TABLE esart.personal_militar TO esart_aplicacion;

-- Catalogo institucional: lectura para resolver la FK, sin crear ni editar unidades.
GRANT SELECT (id, codigo, nombre)
ON TABLE esart_ref.unidades_militares TO esart_aplicacion;

-- Auditoria en la misma transaccion: campos que inserta registrar_evento y RETURNING.
GRANT INSERT (
    usuario_id, nombre_usuario, accion, numero_documento_consultado,
    resultado, direccion_ip, agente_usuario, detalle
) ON TABLE esart.auditoria_eventos TO esart_aplicacion;
GRANT SELECT (id, fecha)
ON TABLE esart.auditoria_eventos TO esart_aplicacion;

-- IDENTITY genera internamente sus IDs y NO requiere USAGE de su secuencia.
-- Solo una variante SERIAL/nextval requiere USAGE en la secuencia concreta.
-- Nunca se concede ALL SEQUENCES, UPDATE de secuencias ni acceso a secuencias ajenas.
DO $secuencias_importacion$
DECLARE
    destino record;
    secuencia text;
BEGIN
    FOR destino IN
        SELECT n.nspname AS esquema, c.relname AS tabla, a.attname AS columna
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'esart'
          AND c.relname IN ('personal_militar', 'auditoria_eventos')
          AND a.attname = 'id' AND NOT a.attisdropped AND a.attidentity = ''
    LOOP
        secuencia := pg_get_serial_sequence(
            format('%I.%I', destino.esquema, destino.tabla), destino.columna);
        IF secuencia IS NOT NULL THEN
            EXECUTE format('GRANT USAGE ON SEQUENCE %s TO esart_aplicacion', secuencia::regclass);
        END IF;
    END LOOP;
END;
$secuencias_importacion$;

COMMIT;
-- Las dependencias existentes de autenticacion/MFA conservan sus privilegios actuales.
-- Este archivo no concede permisos funcionales, no activa componentes ni elimina restricciones.
-- Los privilegios previos mas amplios no se revocan aqui: requieren revision separada del DBA.
