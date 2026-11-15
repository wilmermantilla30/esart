BEGIN;

-- Running upgrade 0001 -> 0002

DO $$ BEGIN
            IF current_database() NOT IN ('esart_hu03_pruebas', 'esart_hu04_fase3_temporal') THEN
                RAISE EXCEPTION '0002 solo autorizada en las dos bases de pruebas';
            END IF;
            IF current_schema() <> 'public' OR
               (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
                RAISE EXCEPTION '0002 requiere public y cuenta sin superusuario';
            END IF;
            IF current_setting('server_version_num')::integer / 10000 <> 18 THEN
                RAISE EXCEPTION '0002 requiere PostgreSQL 18';
            END IF;
        END $$;;

CREATE TABLE tipos_unidad (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    codigo VARCHAR(20) NOT NULL, 
    nombre VARCHAR(200) NOT NULL, 
    activo BOOLEAN DEFAULT true NOT NULL, 
    fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_tipos_unidad PRIMARY KEY (id), 
    CONSTRAINT uq_tipos_unidad_codigo UNIQUE (codigo), 
    CONSTRAINT ck_tipos_unidad_codigo CHECK (codigo ~ '^[A-Z][A-Z0-9_]{0,19}$'), 
    CONSTRAINT ck_tipos_unidad_nombre CHECK (length(btrim(nombre)) > 0)
);

ALTER TABLE unidades_militares ADD COLUMN tipo_unidad_id UUID;

ALTER TABLE unidades_militares ADD CONSTRAINT fk_unidades_militares_tipo_unidad_id_tipos_unidad FOREIGN KEY(tipo_unidad_id) REFERENCES tipos_unidad (id) ON DELETE RESTRICT;

CREATE INDEX ix_unidades_militares_tipo_unidad_id ON unidades_militares (tipo_unidad_id);

CREATE TRIGGER tr_tipos_unidad_fecha BEFORE UPDATE ON public.tipos_unidad
        FOR EACH ROW EXECUTE FUNCTION public.actualizar_fecha_actualizacion();

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

COMMIT;

