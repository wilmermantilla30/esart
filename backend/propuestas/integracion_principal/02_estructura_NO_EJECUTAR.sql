-- PROPUESTA DDL, NO EJECUTADA. Requiere respaldo recuperado y aprobación expresa.
-- Referencia para principal_0001; NO pertenece al historial HU-03/HU-04 de pruebas.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$ BEGIN
 IF current_database() <> 'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
 IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname='unidades_militares') THEN
  RAISE EXCEPTION 'Ya existe otra entidad de unidades: reconciliar antes de continuar';
 END IF;
 IF (SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
     JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='esart_ref' AND c.relname='unidades_militares'
       AND a.attnum>0 AND NOT a.attisdropped) <> 1 THEN
  RAISE EXCEPTION 'El stub ya cambio: repetir diagnostico';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
     JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='esart_ref' AND c.relname='unidades_militares'
       AND a.attname='id' AND format_type(a.atttypid,a.atttypmod)='bigint') THEN
  RAISE EXCEPTION 'PK incompatible';
 END IF;
END $$;
-- No IF NOT EXISTS: un objeto imprevisto debe detener la migración.
CREATE TABLE esart.tipos_unidad (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 codigo VARCHAR(20) NOT NULL UNIQUE CHECK (codigo ~ '^[A-Z][A-Z0-9_]{0,19}$'),
 nombre VARCHAR(200) NOT NULL CHECK (length(btrim(nombre))>0),
 activo BOOLEAN NOT NULL DEFAULT true,
 fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now(),
 fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Sin defaults: las filas históricas conservan su id y no reciben datos inventados.
ALTER TABLE esart_ref.unidades_militares
 ADD COLUMN uuid_publico UUID,
 ADD COLUMN codigo VARCHAR(20),
 ADD COLUMN nombre VARCHAR(200),
 ADD COLUMN sigla VARCHAR(30),
 ADD COLUMN unidad_superior_id BIGINT,
 ADD COLUMN tipo_unidad_id UUID,
 ADD COLUMN activa BOOLEAN,
 ADD COLUMN fecha_creacion TIMESTAMPTZ,
 ADD COLUMN fecha_actualizacion TIMESTAMPTZ,
 ADD CONSTRAINT uq_unidades_uuid_publico UNIQUE (uuid_publico),
 ADD CONSTRAINT uq_unidades_codigo_integracion UNIQUE (codigo),
 ADD CONSTRAINT ck_unidades_codigo_integracion CHECK (codigo ~ '^[A-Z][A-Z0-9_]{0,19}$'),
 ADD CONSTRAINT ck_unidades_nombre_integracion CHECK (length(btrim(nombre))>0),
 ADD CONSTRAINT ck_unidades_superior_distinto CHECK (unidad_superior_id IS DISTINCT FROM id),
 ADD CONSTRAINT fk_unidades_superior_integracion FOREIGN KEY (unidad_superior_id)
     REFERENCES esart_ref.unidades_militares(id) ON DELETE RESTRICT,
 ADD CONSTRAINT fk_unidades_tipo_integracion FOREIGN KEY (tipo_unidad_id)
     REFERENCES esart.tipos_unidad(id) ON DELETE RESTRICT;
CREATE INDEX ix_unidades_superior_integracion ON esart_ref.unidades_militares(unidad_superior_id);
CREATE INDEX ix_unidades_tipo_integracion ON esart_ref.unidades_militares(tipo_unidad_id);
-- La FK de tipo sigue nullable; FUTOM permanece NULL.
-- No se alteran PK, identidad, secuencia ni las cinco FK entrantes.
CREATE FUNCTION esart_ref.actualizar_fecha_unidad_integracion() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 IF ROW(NEW.uuid_publico,NEW.codigo,NEW.nombre,NEW.sigla,NEW.unidad_superior_id,NEW.tipo_unidad_id,NEW.activa)
    IS DISTINCT FROM
    ROW(OLD.uuid_publico,OLD.codigo,OLD.nombre,OLD.sigla,OLD.unidad_superior_id,OLD.tipo_unidad_id,OLD.activa) THEN
  NEW.fecha_actualizacion = now();
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER tr_unidades_fecha_integracion BEFORE UPDATE ON esart_ref.unidades_militares
FOR EACH ROW EXECUTE FUNCTION esart_ref.actualizar_fecha_unidad_integracion();
COMMIT;
