-- ESART HU-03/HU-04 ADAPTADA. Archivo completo para DBCode; ejecutar solo por el operador.
-- No contiene conexiones, passwords, comandos psql ni referencias operativas a pruebas.
-- Backup restaurable verificado: 4d6ecc85006e37b16e92d6fdc0cafd577384fc842e49b6efcd3cd03e0f99dfcb.
-- Ante cualquier ERROR: NO continuar por bloques; ejecutar ROLLBACK y revisar el conflicto.
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL timezone = 'UTC';
SET LOCAL standard_conforming_strings = on;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '180s';
DO $identidad$
BEGIN
 IF current_database()<>'esart_db' OR current_user<>'postgres' THEN
  RAISE EXCEPTION 'Requiere esart_db y operador postgres; no ejecutar como cuenta FastAPI';
 END IF;
 IF current_setting('server_version_num')::integer/10000 <> 18 THEN
  RAISE EXCEPTION 'Se requiere PostgreSQL 18';
 END IF;
END $identidad$;
SELECT pg_advisory_xact_lock(hashtextextended('ESART_HU03_HU04_DBCODE_V1',0));

CREATE TEMP TABLE _esart_manifiesto(documento JSONB NOT NULL) ON COMMIT DROP;
INSERT INTO _esart_manifiesto VALUES (__MANIFIESTO__::jsonb);
CREATE TEMP TABLE _esart_control(instalada BOOLEAN NOT NULL) ON COMMIT DROP;
CREATE TEMP TABLE _esart_originales(esquema TEXT,tabla TEXT,fila JSONB) ON COMMIT DROP;
CREATE TEMP TABLE _esart_conteos(catalogo TEXT PRIMARY KEY,insertados INTEGER NOT NULL DEFAULT 0) ON COMMIT DROP;
INSERT INTO _esart_conteos(catalogo) VALUES ('roles'),('cargos'),('cursos'),('permisos'),('tipos'),('unidades');

DO $preflight$
DECLARE m JSONB; r JSONB; s TEXT; n TEXT; c TEXT; tabla_oid OID; real RECORD; control JSONB;
BEGIN
 SELECT documento INTO m FROM pg_temp._esart_manifiesto;
 FOR r IN SELECT value FROM jsonb_array_elements(m->'gestionadas') LOOP
  IF EXISTS(SELECT 1 FROM pg_class cl JOIN pg_namespace ns ON ns.oid=cl.relnamespace
     WHERE cl.relname=r->>1 AND ns.nspname<>r->>0 AND ns.nspname !~ '^pg_'
       AND ns.nspname<>'information_schema' AND cl.relkind IN ('r','p')) THEN
   RAISE EXCEPTION 'Entidad homonima en otro esquema para %; requiere reconciliacion',r->>1;
  END IF;
 END LOOP;
 -- Bloquear escrituras concurrentes; nunca eliminar objetos para sortear un conflicto.
 FOR real IN SELECT ns.nspname esquema,cl.relname tabla FROM pg_class cl
  JOIN pg_namespace ns ON ns.oid=cl.relnamespace
  WHERE ns.nspname IN ('esart','esart_ref') AND cl.relkind IN ('r','p') ORDER BY 1,2 LOOP
  EXECUTE format('LOCK TABLE %I.%I IN SHARE ROW EXCLUSIVE MODE',real.esquema,real.tabla);
 END LOOP;
 IF to_regclass('public.unidades_militares') IS NOT NULL OR
    to_regclass('public.tipos_unidad') IS NOT NULL THEN
  RAISE EXCEPTION 'Hay entidades paralelas en public: reconciliar antes de instalar';
 END IF;
 -- No adoptar ni sobrescribir un historial Alembic que no conocemos.
 IF EXISTS(SELECT 1 FROM pg_class cl JOIN pg_namespace ns ON ns.oid=cl.relnamespace
           WHERE cl.relname='alembic_version' AND ns.nspname !~ '^pg_') THEN
  RAISE EXCEPTION 'Existe historial Alembic: requiere revision especifica; este SQL no hace stamp';
 END IF;
 FOR r IN SELECT value FROM jsonb_array_elements(m->'origen'->'columnas') LOOP
  SELECT format_type(a.atttypid,a.atttypmod) tipo,NOT a.attnotnull permite_null,
         a.attidentity::text identidad,a.attgenerated::text generada,pg_get_expr(d.adbin,d.adrelid) defecto
  INTO real FROM pg_class cl JOIN pg_namespace ns ON ns.oid=cl.relnamespace
   JOIN pg_attribute a ON a.attrelid=cl.oid
   LEFT JOIN pg_attrdef d ON d.adrelid=cl.oid AND d.adnum=a.attnum
  WHERE ns.nspname=r->>'esquema' AND cl.relname=r->>'tabla'
    AND a.attname=r->>'columna' AND a.attnum>0 AND NOT a.attisdropped;
  IF NOT FOUND OR real.tipo IS DISTINCT FROM r->>'tipo' OR
     real.permite_null IS DISTINCT FROM (r->>'permite_null')::boolean OR
     real.identidad IS DISTINCT FROM r->>'identidad' OR
     real.generada IS DISTINCT FROM r->>'generada' OR real.defecto IS DISTINCT FROM r->>'defecto' THEN
   RAISE EXCEPTION 'Columna de origen incompatible: %.%.%',r->>'esquema',r->>'tabla',r->>'columna';
  END IF;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(m->'origen'->'restricciones') LOOP
  SELECT pg_get_constraintdef(co.oid) definicion,co.convalidated validada INTO real
  FROM pg_constraint co JOIN pg_class cl ON cl.oid=co.conrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
  WHERE ns.nspname=r->>'esquema' AND cl.relname=r->>'tabla' AND co.conname=r->>'nombre';
  IF NOT FOUND OR NOT real.validada OR
     regexp_replace(real.definicion,'\s+','','g') IS DISTINCT FROM
     regexp_replace(r->>'definicion','\s+','','g') THEN
   RAISE EXCEPTION 'Restriccion de origen incompatible: %.%',r->>'tabla',r->>'nombre';
  END IF;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(m->'origen'->'indices') LOOP
  SELECT pg_get_indexdef(ix.indexrelid) definicion,ix.indisvalid valido INTO real
  FROM pg_index ix JOIN pg_class ind ON ind.oid=ix.indexrelid JOIN pg_namespace ns ON ns.oid=ind.relnamespace
  WHERE ns.nspname=r->>'esquema' AND ind.relname=r->>'nombre';
  IF NOT FOUND OR NOT real.valido OR regexp_replace(real.definicion,'\s+','','g') IS DISTINCT FROM
     regexp_replace(r->>'definicion','\s+','','g') THEN
   RAISE EXCEPTION 'Indice de origen incompatible: %.%',r->>'esquema',r->>'nombre';
  END IF;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(m->'origen'->'vistas') LOOP
  SELECT pg_get_viewdef(cl.oid) definicion INTO real FROM pg_class cl
   JOIN pg_namespace ns ON ns.oid=cl.relnamespace
   WHERE ns.nspname=r->>'esquema' AND cl.relname=r->>'nombre' AND cl.relkind='v';
  IF NOT FOUND OR regexp_replace(real.definicion,'\s+','','g') IS DISTINCT FROM
     regexp_replace(r->>'definicion','\s+','','g') THEN
   RAISE EXCEPTION 'Vista institucional incompatible: %.%',r->>'esquema',r->>'nombre';
  END IF;
 END LOOP;
 IF to_regclass('esart.integraciones_control') IS NOT NULL THEN
  EXECUTE 'SELECT to_jsonb(t) FROM esart.integraciones_control t WHERE version=$1'
   INTO control USING m->>'version';
  IF control IS NULL OR control->>'huella_manifiesto' IS DISTINCT FROM m->>'sha256' THEN
   RAISE EXCEPTION 'Registro manual ausente o manifiesto distinto; no sobrescribirlo';
  END IF;
  INSERT INTO pg_temp._esart_control VALUES(true);
 ELSE
  INSERT INTO pg_temp._esart_control VALUES(false);
  IF EXISTS(SELECT 1 FROM pg_trigger tg JOIN pg_class cl ON cl.oid=tg.tgrelid
    JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    WHERE ns.nspname IN ('esart','esart_ref') AND NOT tg.tgisinternal) THEN
   RAISE EXCEPTION 'Hay triggers institucionales no previstos en el diagnostico; revisar antes de instalar';
  END IF;
  FOR r IN SELECT value FROM jsonb_array_elements(m->'nuevas') LOOP
   IF to_regclass(format('%I.%I',r->>0,r->>1)) IS NOT NULL THEN
    RAISE EXCEPTION 'Objeto nuevo ya existe sin registro verificable: %.%',r->>0,r->>1;
   END IF;
  END LOOP;
  FOR r IN SELECT value FROM jsonb_array_elements(m->'columnas') LOOP
   IF EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid
       JOIN pg_namespace ns ON ns.oid=cl.relnamespace WHERE ns.nspname=r->>0
       AND cl.relname=r->>1 AND a.attname=r->>2 AND a.attnum>0 AND NOT a.attisdropped) THEN
    RAISE EXCEPTION 'Columna parcial ya existe sin registro verificable: %.%.%',r->>0,r->>1,r->>2;
   END IF;
  END LOOP;
  IF EXISTS(SELECT 1 FROM esart_ref.unidades_militares) THEN
   RAISE EXCEPTION 'El stub contiene IDs heredados sin codigo: aprobar correspondencias antes de insertar';
  END IF;
  IF to_regclass('esart.v_unidades_api') IS NOT NULL OR
     EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
        WHERE ns.nspname='esart' AND p.proname IN ('actualizar_fecha_hu0304','inmutabilidad_auditoria_hu0304')) THEN
   RAISE EXCEPTION 'Funcion/vista de instalacion ya existe sin registro; no reemplazarla';
  END IF;
 END IF;
 -- Copia temporal de columnas originales: permite comparar valores aun añadiendo columnas.
 FOR real IN SELECT ns.nspname esquema,cl.relname tabla FROM pg_class cl JOIN pg_namespace ns ON ns.oid=cl.relnamespace
   WHERE ns.nspname IN ('esart','esart_ref') AND cl.relkind IN ('r','p') ORDER BY 1,2 LOOP
  EXECUTE format('INSERT INTO pg_temp._esart_originales SELECT %L,%L,to_jsonb(t) FROM %I.%I t',
                  real.esquema,real.tabla,real.esquema,real.tabla);
 END LOOP;
 RAISE NOTICE 'PRECHECK correcto: base %, operador %, instalada %',current_database(),current_user,
  (SELECT instalada FROM pg_temp._esart_control);
END $preflight$;

-- Para una repetición, verificar primero que no se hayan alterado objetos instalados.
DO $estado_anterior$
DECLARE esperado JSONB; actual JSONB;
BEGIN
 IF (SELECT instalada FROM pg_temp._esart_control) THEN
  SELECT estructura INTO esperado FROM esart.integraciones_control
   WHERE version=__VERSION__;
  __ESTRUCTURA_INTO__
  IF actual IS DISTINCT FROM esperado THEN RAISE EXCEPTION 'La estructura instalada cambio: requiere revision'; END IF;
 END IF;
END $estado_anterior$;

DO $ddl$
BEGIN
 IF NOT (SELECT instalada FROM pg_temp._esart_control) THEN
__DDL__
  CREATE TABLE esart.integraciones_control (
   version TEXT PRIMARY KEY,huella_manifiesto CHAR(64) NOT NULL,
   aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now(),operador TEXT NOT NULL,
   metodo TEXT NOT NULL CHECK (metodo='SQL manual adaptado; no revision Alembic'),
   estructura JSONB NOT NULL,resumen JSONB NOT NULL
  );
  __FUNCIONES_Y_TRIGGERS__
  __VISTA__
 END IF;
END $ddl$;

-- Solo secuencias de tablas gestionadas; no setval, no renumerar identificadores.
CREATE OR REPLACE FUNCTION pg_temp.esart_secuencia_segura(s TEXT,n TEXT) RETURNS void
LANGUAGE plpgsql AS $secuencia$
DECLARE sec TEXT; ultimo BIGINT; llamado BOOLEAN; incremento BIGINT; maximo BIGINT;
BEGIN
 sec := pg_get_serial_sequence(format('%I.%I',s,n),'id');
 IF sec IS NULL THEN RAISE EXCEPTION 'No hay identidad/secuencia segura para %.%',s,n; END IF;
 SELECT seqincrement INTO incremento FROM pg_sequence WHERE seqrelid=sec::regclass;
 IF incremento<>1 THEN RAISE EXCEPTION 'Incremento de secuencia incompatible para %.%',s,n; END IF;
 EXECUTE format('SELECT last_value,is_called FROM %s',sec) INTO ultimo,llamado;
 EXECUTE format('SELECT max(id) FROM %I.%I',s,n) INTO maximo;
 IF maximo IS NOT NULL AND ultimo+(CASE WHEN llamado THEN incremento ELSE 0 END)<=maximo THEN
  RAISE EXCEPTION 'Secuencia atrasada para %.%; requiere decision del DBA, no se reajusta',s,n;
 END IF;
END $secuencia$;

__SEEDS__

__ASERCIONES__

-- Preservar todas las filas anteriores, incluidas sus fechas, hashes y FK.
DO $preservacion$
DECLARE r RECORD; perdida BOOLEAN;
BEGIN
 FOR r IN SELECT * FROM pg_temp._esart_originales LOOP
  EXECUTE format('SELECT NOT EXISTS(SELECT 1 FROM %I.%I t WHERE
     (SELECT jsonb_object_agg(k,to_jsonb(t)->k) FROM jsonb_object_keys($1) AS x(k))=$1)',r.esquema,r.tabla)
   INTO perdida USING r.fila;
  IF perdida THEN RAISE EXCEPTION 'Cambio o perdida de fila original en %.%; rollback obligatorio',r.esquema,r.tabla; END IF;
 END LOOP;
END $preservacion$;

-- Permisos de objeto, nunca SUPERUSER/CREATEDB/CREATEROLE ni cambio de login.
GRANT USAGE ON SCHEMA esart,esart_ref TO esart_aplicacion;
__PERMISOS__
GRANT SELECT ON esart.v_unidades_api,esart.integraciones_control TO esart_aplicacion;

DO $registro$
DECLARE actual JSONB; resumen JSONB;
BEGIN
 __ESTRUCTURA_INTO__
 SELECT jsonb_object_agg(catalogo,insertados) INTO resumen FROM pg_temp._esart_conteos;
 IF NOT (SELECT instalada FROM pg_temp._esart_control) THEN
  INSERT INTO esart.integraciones_control(version,huella_manifiesto,operador,metodo,estructura,resumen)
   VALUES(__VERSION__,__FIRMA__,current_user,'SQL manual adaptado; no revision Alembic',actual,resumen);
 END IF;
 RAISE NOTICE 'VALIDADO: insertados %, 40 referencias, 39 clasificadas, FUTOM NULL. Confirmar COMMIT.',resumen;
END $registro$;

-- Prueba efectiva de lectura como usuario de FastAPI, sin contraseña ni conexión nueva.
SET LOCAL ROLE esart_aplicacion;
DO $lectura_app$
BEGIN
 IF current_database()<>'esart_db' OR (SELECT count(*) FROM esart.v_unidades_api)<>40 OR
    (SELECT count(*) FROM esart.v_unidades_api WHERE tipo_codigo IS NOT NULL)<>39 OR
    NOT EXISTS(SELECT 1 FROM esart.v_unidades_api WHERE codigo='FUTOM' AND tipo_codigo IS NULL) THEN
  RAISE EXCEPTION 'Fallo de consulta del usuario operativo';
 END IF;
END $lectura_app$;
SELECT current_database() AS base,current_user AS cuenta,count(*) AS unidades FROM esart.v_unidades_api;
RESET ROLE;
SELECT catalogo,insertados FROM pg_temp._esart_conteos ORDER BY catalogo;
COMMIT;
-- Debe responder COMMIT, no ROLLBACK. Los NOTICE previos no bastan.
-- A continuación ejecutar 02_verificar_esart_db.sql completo.
