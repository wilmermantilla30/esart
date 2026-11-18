BEGIN;

-- Running downgrade 0002 -> 0001

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

DO $$ BEGIN
                IF current_database() <> 'esart_hu04_fase3_temporal' THEN
                    RAISE EXCEPTION 'Reversion 0002 solo autorizada en esart_hu04_fase3_temporal';
                END IF;
            END $$;;

LOCK TABLE public.tipos_unidad, public.unidades_militares IN ACCESS EXCLUSIVE MODE;

DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM public.tipos_unidad) OR EXISTS (
                SELECT 1 FROM public.unidades_militares WHERE tipo_unidad_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Reversion rechazada: catalogo o clasificaciones con datos';
            END IF;
        END $$;;

DROP INDEX ix_unidades_militares_tipo_unidad_id;

ALTER TABLE unidades_militares DROP CONSTRAINT fk_unidades_militares_tipo_unidad_id_tipos_unidad;

ALTER TABLE unidades_militares DROP COLUMN tipo_unidad_id;

DROP TRIGGER tr_tipos_unidad_fecha ON public.tipos_unidad;

DROP TABLE tipos_unidad;

UPDATE alembic_version SET version_num='0001' WHERE alembic_version.version_num = '0002';

COMMIT;

