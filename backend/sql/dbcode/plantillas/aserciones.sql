DO $integridad$
DECLARE d JSONB := __DATOS__::jsonb; grupo TEXT; n TEXT; clave TEXT; r JSONB; real JSONB; k TEXT;
        rel RECORD; locales TEXT; uniones TEXT; huerfanos BIGINT;
BEGIN
 FOR grupo,n,clave IN SELECT * FROM (VALUES ('roles','roles','codigo'),('cargos','tipos_cargo','nombre'),
  ('cursos','tipos_curso','codigo'),('permisos','permisos','codigo'),('tipos','tipos_unidad','codigo')) x LOOP
  FOR r IN SELECT value FROM jsonb_array_elements(d->grupo) LOOP
   EXECUTE format('SELECT to_jsonb(t) FROM esart.%I t WHERE %I=$1',n,clave) INTO real USING r->>clave;
   IF real IS NULL THEN RAISE EXCEPTION 'Referencia faltante: % / %',grupo,r->>clave; END IF;
   FOR k IN SELECT jsonb_object_keys(r) LOOP
    IF real->k IS DISTINCT FROM r->k THEN RAISE EXCEPTION 'Referencia incompatible: % / % / %',grupo,r->>clave,k; END IF;
   END LOOP;
  END LOOP;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'unidades') LOOP
  SELECT jsonb_build_object('codigo',u.codigo,'nombre',u.nombre,'sigla',u.sigla,'activa',u.activa,
                           'superior_codigo',p.codigo,'tipo_codigo',t.codigo) INTO real
  FROM esart_ref.unidades_militares u LEFT JOIN esart_ref.unidades_militares p ON p.id=u.unidad_superior_id
  LEFT JOIN esart.tipos_unidad t ON t.id=u.tipo_unidad_id WHERE u.codigo=r->>'codigo';
  IF real IS DISTINCT FROM r THEN RAISE EXCEPTION 'Unidad/jerarquia no coincide con matriz: %',r->>'codigo'; END IF;
 END LOOP;
 IF (SELECT count(*) FROM esart_ref.unidades_militares)<>40 OR
    (SELECT count(*) FROM esart_ref.unidades_militares WHERE tipo_unidad_id IS NOT NULL)<>39 OR
    NOT EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE codigo='FUTOM' AND tipo_unidad_id IS NULL) THEN
  RAISE EXCEPTION 'Se requieren 40 unidades, 39 clasificadas y FUTOM pendiente; no se borran excedentes';
 END IF;
 IF EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE uuid_publico IS NULL) THEN
  RAISE EXCEPTION 'Falta UUID publico de una unidad';
 END IF;
 IF EXISTS(WITH RECURSIVE j AS (
   SELECT id,unidad_superior_id,ARRAY[id] camino,false ciclo FROM esart_ref.unidades_militares
   UNION ALL SELECT p.id,p.unidad_superior_id,j.camino||p.id,p.id=ANY(j.camino)
   FROM j JOIN esart_ref.unidades_militares p ON p.id=j.unidad_superior_id WHERE NOT j.ciclo
  ) SELECT 1 FROM j WHERE ciclo) THEN RAISE EXCEPTION 'Ciclo en jerarquia'; END IF;
 IF EXISTS(SELECT 1 FROM pg_constraint co JOIN pg_namespace ns ON ns.oid=co.connamespace
           WHERE ns.nspname IN ('esart','esart_ref') AND NOT co.convalidated) OR
    EXISTS(SELECT 1 FROM pg_index ix JOIN pg_class cl ON cl.oid=ix.indrelid
           JOIN pg_namespace ns ON ns.oid=cl.relnamespace
           WHERE ns.nspname IN ('esart','esart_ref') AND NOT ix.indisvalid) THEN
  RAISE EXCEPTION 'Restriccion no validada o indice invalido';
 END IF;
 -- Verificar independientemente TODAS las FK institucionales, sin mostrar filas privadas.
 FOR rel IN SELECT co.oid,co.conname,co.conrelid,co.confrelid,
   sn.nspname s,sc.relname t,dn.nspname ds,dc.relname dt,co.conkey,co.confkey
  FROM pg_constraint co JOIN pg_class sc ON sc.oid=co.conrelid JOIN pg_namespace sn ON sn.oid=sc.relnamespace
  JOIN pg_class dc ON dc.oid=co.confrelid JOIN pg_namespace dn ON dn.oid=dc.relnamespace
  WHERE co.contype='f' AND sn.nspname IN ('esart','esart_ref') LOOP
  SELECT string_agg(format('o.%I IS NOT NULL',a.attname),' AND ' ORDER BY x.pos),
         string_agg(format('o.%I=d.%I',a.attname,b.attname),' AND ' ORDER BY x.pos)
   INTO locales,uniones FROM unnest(rel.conkey,rel.confkey) WITH ORDINALITY AS x(a,b,pos)
   JOIN pg_attribute a ON a.attrelid=rel.conrelid AND a.attnum=x.a
   JOIN pg_attribute b ON b.attrelid=rel.confrelid AND b.attnum=x.b;
  EXECUTE format('SELECT count(*) FROM %I.%I o WHERE %s AND NOT EXISTS(SELECT 1 FROM %I.%I d WHERE %s)',
                 rel.s,rel.t,locales,rel.ds,rel.dt,uniones) INTO huerfanos;
  IF huerfanos<>0 THEN RAISE EXCEPTION 'Huerfanos en %.% / %',rel.s,rel.t,rel.conname; END IF;
 END LOOP;
END $integridad$;
