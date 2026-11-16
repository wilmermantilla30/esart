CREATE OR REPLACE FUNCTION pg_temp.esart_fila_correcta(s TEXT,n TEXT,clave TEXT,r JSONB) RETURNS boolean
LANGUAGE plpgsql AS $fila$
DECLARE actual JSONB; k TEXT; repetidos BIGINT;
BEGIN
 EXECUTE format('SELECT count(*) FROM %I.%I WHERE lower(btrim(%I::text))=lower(btrim($1))',s,n,clave)
  INTO repetidos USING r->>clave;
 IF repetidos>1 THEN RAISE EXCEPTION 'Clave natural ambigua en %.%: %',s,n,r->>clave; END IF;
 EXECUTE format('SELECT to_jsonb(t) FROM %I.%I t WHERE %I=$1',s,n,clave) INTO actual USING r->>clave;
 IF actual IS NULL THEN
  IF repetidos<>0 THEN RAISE EXCEPTION 'Clave equivalente con otra escritura en %.%: %',s,n,r->>clave; END IF;
  RETURN false;
 END IF;
 FOR k IN SELECT jsonb_object_keys(r) LOOP
  IF actual->k IS DISTINCT FROM r->k THEN
   RAISE EXCEPTION 'Valor existente incompatible en %.%, clave %, campo %; no se sobrescribe',s,n,r->>clave,k;
  END IF;
 END LOOP;
 RETURN true;
END $fila$;

DO $catalogos$
DECLARE d JSONB; r JSONB;
BEGIN
 SELECT documento->'datos' INTO d FROM pg_temp._esart_manifiesto;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'roles') LOOP
  IF pg_temp.esart_fila_correcta('esart','roles','codigo',r) THEN CONTINUE; END IF;
  PERFORM pg_temp.esart_secuencia_segura('esart','roles');
  INSERT INTO esart.roles(codigo,nombre,descripcion,activo)
   VALUES(r->>'codigo',r->>'nombre',r->>'descripcion',(r->>'activo')::boolean);
  UPDATE pg_temp._esart_conteos SET insertados=insertados+1 WHERE catalogo='roles';
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'cargos') LOOP
  IF pg_temp.esart_fila_correcta('esart','tipos_cargo','nombre',r) THEN CONTINUE; END IF;
  PERFORM pg_temp.esart_secuencia_segura('esart','tipos_cargo');
  INSERT INTO esart.tipos_cargo(nombre,descripcion,cuenta_para_coofu,activo)
   VALUES(r->>'nombre',r->>'descripcion',(r->>'cuenta_para_coofu')::boolean,(r->>'activo')::boolean);
  UPDATE pg_temp._esart_conteos SET insertados=insertados+1 WHERE catalogo='cargos';
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'cursos') LOOP
  IF pg_temp.esart_fila_correcta('esart','tipos_curso','codigo',r) THEN CONTINUE; END IF;
  PERFORM pg_temp.esart_secuencia_segura('esart','tipos_curso');
  INSERT INTO esart.tipos_curso(codigo,nombre,tipo,modalidad,duracion_semanas,activo)
   VALUES(r->>'codigo',r->>'nombre',r->>'tipo',r->>'modalidad',(r->>'duracion_semanas')::integer,(r->>'activo')::boolean);
  UPDATE pg_temp._esart_conteos SET insertados=insertados+1 WHERE catalogo='cursos';
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'permisos') LOOP
  IF pg_temp.esart_fila_correcta('esart','permisos','codigo',r) THEN CONTINUE; END IF;
  INSERT INTO esart.permisos(codigo,descripcion) VALUES(r->>'codigo',r->>'descripcion');
  UPDATE pg_temp._esart_conteos SET insertados=insertados+1 WHERE catalogo='permisos';
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'tipos') LOOP
  IF pg_temp.esart_fila_correcta('esart','tipos_unidad','codigo',r) THEN CONTINUE; END IF;
  INSERT INTO esart.tipos_unidad(codigo,nombre,activo)
   VALUES(r->>'codigo',r->>'nombre',(r->>'activo')::boolean);
  UPDATE pg_temp._esart_conteos SET insertados=insertados+1 WHERE catalogo='tipos';
 END LOOP;
END $catalogos$;

DO $unidades$
DECLARE d JSONB; r JSONB; actual JSONB; padre BIGINT; tipo UUID;
BEGIN
 SELECT documento->'datos' INTO d FROM pg_temp._esart_manifiesto;
 IF EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE codigo IS NULL OR uuid_publico IS NULL) THEN
  RAISE EXCEPTION 'Unidad heredada sin correspondencia verificada; no crear duplicados ni inferir identidad';
 END IF;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'unidades') LOOP
  padre:=NULL; tipo:=NULL;
  IF r->>'superior_codigo' IS NOT NULL THEN
   SELECT id INTO STRICT padre FROM esart_ref.unidades_militares WHERE codigo=r->>'superior_codigo';
  END IF;
  IF r->>'tipo_codigo' IS NOT NULL THEN
   SELECT id INTO STRICT tipo FROM esart.tipos_unidad WHERE codigo=r->>'tipo_codigo' AND activo;
  END IF;
  SELECT to_jsonb(u) INTO actual FROM esart_ref.unidades_militares u WHERE codigo=r->>'codigo';
  IF actual IS NOT NULL THEN
   IF actual->>'uuid_publico' IS NULL OR actual->'nombre' IS DISTINCT FROM r->'nombre' OR
      actual->'sigla' IS DISTINCT FROM r->'sigla' OR actual->'activa' IS DISTINCT FROM r->'activa' OR
      actual->>'unidad_superior_id' IS DISTINCT FROM padre::text OR
      actual->>'tipo_unidad_id' IS DISTINCT FROM tipo::text THEN
    RAISE EXCEPTION 'Unidad incompatible: %; no se sobrescribe',r->>'codigo';
   END IF;
   CONTINUE; -- Ningún INSERT, nextval, UPDATE o trigger para filas ya correctas.
  END IF;
  IF EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE lower(btrim(codigo))=lower(btrim(r->>'codigo'))) THEN
   RAISE EXCEPTION 'Codigo de unidad equivalente pero distinto: %',r->>'codigo';
  END IF;
  PERFORM pg_temp.esart_secuencia_segura('esart_ref','unidades_militares');
  INSERT INTO esart_ref.unidades_militares
   (uuid_publico,codigo,nombre,sigla,unidad_superior_id,tipo_unidad_id,activa,fecha_creacion,fecha_actualizacion)
  VALUES(gen_random_uuid(),r->>'codigo',r->>'nombre',r->>'sigla',padre,tipo,(r->>'activa')::boolean,now(),now());
  UPDATE pg_temp._esart_conteos SET insertados=insertados+1 WHERE catalogo='unidades';
 END LOOP;
END $unidades$;
