-- PROPUESTA DE DML, NO EJECUTADA. Cargar solo tras respaldo, mapeo y aprobaci?n.
-- Referencia de seed para principal_0002; nunca copiar IDs de pruebas.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$ BEGIN
 IF current_database() <> 'esart_db' THEN RAISE EXCEPTION 'Destino incorrecto'; END IF;
END $$;
LOCK TABLE esart_ref.unidades_militares, esart.tipos_unidad IN SHARE ROW EXCLUSIVE MODE;
DO $integracion$
DECLARE
 datos JSONB := '{"tipos": [{"codigo": "BAACA", "nombre": "Batallón de Artillería", "activo": true}, {"codigo": "BAADA", "nombre": "Batallón de Artillería de Defensa Aérea", "activo": true}, {"codigo": "BATAR", "nombre": "Batería de Artillería", "activo": true}, {"codigo": "BR", "nombre": "Brigada", "activo": true}, {"codigo": "CECFU", "nombre": "Centro de Coordinación de Fuegos", "activo": true}, {"codigo": "CEDOC", "nombre": "Centro de Educación y Doctrina", "activo": true}, {"codigo": "CEM", "nombre": "Centro de Educación Militar", "activo": true}, {"codigo": "DIV", "nombre": "División", "activo": true}, {"codigo": "ESART", "nombre": "Escuela de Artillería", "activo": true}], "unidades": [{"codigo": "CEDOC", "nombre": "Centro de Educación y Doctrina", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "CEDOC"}, {"codigo": "DAAVA", "nombre": "División de Aviación y Asalto Aéreo", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV01", "nombre": "Primera División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV02", "nombre": "Segunda División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV03", "nombre": "Tercera División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV04", "nombre": "Cuarta División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV05", "nombre": "Quinta División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV06", "nombre": "Sexta División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV07", "nombre": "Séptima División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV08", "nombre": "Octava División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIVFE", "nombre": "División de Fuerzas Especiales", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "FUTOM", "nombre": "Fuerza de Tarea Omega", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": null}, {"codigo": "BR01", "nombre": "Primera Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR03", "nombre": "Tercera Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV03", "tipo_codigo": "BR"}, {"codigo": "BR04", "nombre": "Cuarta Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV07", "tipo_codigo": "BR"}, {"codigo": "BR05", "nombre": "Quinta Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV02", "tipo_codigo": "BR"}, {"codigo": "BR08", "nombre": "Octava Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR09", "nombre": "Novena Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR10", "nombre": "Décima Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV01", "tipo_codigo": "BR"}, {"codigo": "BR13", "nombre": "Décimo Tercera Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR18", "nombre": "Décimo Octava Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV08", "tipo_codigo": "BR"}, {"codigo": "BR27", "nombre": "Vigésimo Séptima Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV06", "tipo_codigo": "BR"}, {"codigo": "BR30", "nombre": "Trigésima Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV02", "tipo_codigo": "BR"}, {"codigo": "CEMIL", "nombre": "Centro de Educación Militar", "sigla": null, "activa": true, "superior_codigo": "CEDOC", "tipo_codigo": "CEM"}, {"codigo": "BAACA1", "nombre": "Batallón de Artillería de Campaña N°1", "sigla": null, "activa": true, "superior_codigo": "BR01", "tipo_codigo": "BAACA"}, {"codigo": "BAACA10", "nombre": "Batallón de Artillería de Campaña N°10", "sigla": null, "activa": true, "superior_codigo": "BR10", "tipo_codigo": "BAACA"}, {"codigo": "BAACA13", "nombre": "Batallón de Artillería de Campaña N°13", "sigla": null, "activa": true, "superior_codigo": "BR13", "tipo_codigo": "BAACA"}, {"codigo": "BAACA18", "nombre": "Batallón de Artillería de Campaña N°18", "sigla": null, "activa": true, "superior_codigo": "BR18", "tipo_codigo": "BAACA"}, {"codigo": "BAACA2", "nombre": "Batallón de Artillería de Campaña N°2", "sigla": null, "activa": true, "superior_codigo": "BR10", "tipo_codigo": "BAACA"}, {"codigo": "BAACA27", "nombre": "Batallón de Artillería de Campaña N°27", "sigla": null, "activa": true, "superior_codigo": "BR27", "tipo_codigo": "BAACA"}, {"codigo": "BAACA3", "nombre": "Batallón de Artillería de Campaña N°3", "sigla": null, "activa": true, "superior_codigo": "BR03", "tipo_codigo": "BAACA"}, {"codigo": "BAACA30", "nombre": "Batallón de Artillería de Campaña N°30", "sigla": null, "activa": true, "superior_codigo": "BR30", "tipo_codigo": "BAACA"}, {"codigo": "BAACA4", "nombre": "Batallón de Artillería de Campaña N°4", "sigla": null, "activa": true, "superior_codigo": "BR04", "tipo_codigo": "BAACA"}, {"codigo": "BAACA5", "nombre": "Batallón de Artillería de Campaña N°5", "sigla": null, "activa": true, "superior_codigo": "BR05", "tipo_codigo": "BAACA"}, {"codigo": "BAACA6", "nombre": "Batallón de Artillería de Campaña N°6", "sigla": null, "activa": true, "superior_codigo": "BR05", "tipo_codigo": "BAACA"}, {"codigo": "BAACA8", "nombre": "Batallón de Artillería de Campaña N°8", "sigla": null, "activa": true, "superior_codigo": "BR08", "tipo_codigo": "BAACA"}, {"codigo": "BAACA9", "nombre": "Batallón de Artillería de Campaña N°9", "sigla": null, "activa": true, "superior_codigo": "BR09", "tipo_codigo": "BAACA"}, {"codigo": "BAADA1", "nombre": "Batallón de Artillería de Defensa Aérea N°1", "sigla": null, "activa": true, "superior_codigo": "BR10", "tipo_codigo": "BAADA"}, {"codigo": "BAADA2", "nombre": "Batallón de Artillería de Defensa Aérea N°2", "sigla": null, "activa": true, "superior_codigo": "BR05", "tipo_codigo": "BAADA"}, {"codigo": "ESART", "nombre": "Escuela de Artillería", "sigla": null, "activa": true, "superior_codigo": "CEMIL", "tipo_codigo": "ESART"}]}'::jsonb;
 r JSONB;
 tipo UUID;
 padre BIGINT;
 nueva BIGINT;
 n_unidades INT := 0;
 n_tipos INT := 0;
 ultimo BIGINT;
 llamado BOOLEAN;
 maximo BIGINT;
BEGIN
 -- El caso con IDs heredados desconocidos NO autoriza crear otros 40 en paralelo.
 IF EXISTS (SELECT 1 FROM esart_ref.unidades_militares WHERE codigo IS NULL) THEN
  RAISE EXCEPTION 'Existen IDs heredados sin correspondencia: requiere mapeo institucional aprobado';
 END IF;
 IF EXISTS (SELECT 1 FROM jsonb_array_elements(datos->'unidades') j
            WHERE NOT EXISTS(SELECT 1 FROM esart_ref.unidades_militares u WHERE u.codigo=j->>'codigo')) THEN
  IF (SELECT seqincrement FROM pg_sequence WHERE seqrelid='esart_ref.unidades_militares_id_seq'::regclass) <> 1 THEN
   RAISE EXCEPTION 'Incremento de secuencia inesperado';
  END IF;
  SELECT last_value,is_called INTO ultimo,llamado FROM esart_ref.unidades_militares_id_seq;
  SELECT max(id) INTO maximo FROM esart_ref.unidades_militares;
  IF maximo IS NOT NULL AND ultimo + (CASE WHEN llamado THEN 1 ELSE 0 END) <= maximo THEN
   RAISE EXCEPTION 'Secuencia atrasada; requiere decision DBA, no se reajusta automaticamente';
  END IF;
 END IF;
 FOR r IN SELECT value FROM jsonb_array_elements(datos->'tipos') LOOP
  IF EXISTS (SELECT 1 FROM esart.tipos_unidad WHERE codigo=r->>'codigo'
             AND (nombre IS DISTINCT FROM r->>'nombre' OR activo IS DISTINCT FROM (r->>'activo')::boolean)) THEN
   RAISE EXCEPTION 'Tipo existente incompatible: %',r->>'codigo';
  END IF;
  IF EXISTS(SELECT 1 FROM esart.tipos_unidad WHERE codigo=r->>'codigo') THEN CONTINUE; END IF;
  INSERT INTO esart.tipos_unidad(codigo,nombre,activo)
  VALUES(r->>'codigo',r->>'nombre',(r->>'activo')::boolean)
  ON CONFLICT(codigo) DO NOTHING;
  GET DIAGNOSTICS nueva = ROW_COUNT;
  n_tipos := n_tipos + nueva;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(datos->'unidades') LOOP
  padre := NULL;
  tipo := NULL;
  IF r->>'superior_codigo' IS NOT NULL THEN
   SELECT id INTO STRICT padre FROM esart_ref.unidades_militares WHERE codigo=r->>'superior_codigo';
  END IF;
  IF r->>'tipo_codigo' IS NOT NULL THEN
   SELECT id INTO STRICT tipo FROM esart.tipos_unidad WHERE codigo=r->>'tipo_codigo' AND activo;
  END IF;
  IF EXISTS (SELECT 1 FROM esart_ref.unidades_militares u WHERE u.codigo=r->>'codigo' AND (
   u.uuid_publico IS NULL OR u.nombre IS DISTINCT FROM r->>'nombre' OR u.sigla IS DISTINCT FROM r->>'sigla'
   OR u.activa IS DISTINCT FROM (r->>'activa')::boolean
   OR u.unidad_superior_id IS DISTINCT FROM padre OR u.tipo_unidad_id IS DISTINCT FROM tipo)) THEN
   RAISE EXCEPTION 'Unidad existente incompatible: %',r->>'codigo';
  END IF;
  IF EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE codigo=r->>'codigo') THEN CONTINUE; END IF;
  INSERT INTO esart_ref.unidades_militares
   (uuid_publico,codigo,nombre,sigla,unidad_superior_id,tipo_unidad_id,activa,fecha_creacion,fecha_actualizacion)
  VALUES(gen_random_uuid(),r->>'codigo',r->>'nombre',r->>'sigla',padre,tipo,
         (r->>'activa')::boolean,now(),now())
  ON CONFLICT(codigo) DO NOTHING RETURNING id INTO nueva;
  IF nueva IS NOT NULL THEN n_unidades := n_unidades + 1; END IF;
 END LOOP;
 IF (SELECT count(*) FROM esart_ref.unidades_militares u
     WHERE u.codigo IN (SELECT value->>'codigo' FROM jsonb_array_elements(datos->'unidades'))) <> 40 THEN
  RAISE EXCEPTION 'Faltan unidades aprobadas';
 END IF;
 IF (SELECT count(*) FROM esart_ref.unidades_militares u
     WHERE u.codigo IN (SELECT value->>'codigo' FROM jsonb_array_elements(datos->'unidades'))
     AND u.tipo_unidad_id IS NOT NULL) <> 39 THEN
  RAISE EXCEPTION 'Clasificacion distinta a la aprobada';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE codigo='FUTOM' AND tipo_unidad_id IS NULL) THEN
  RAISE EXCEPTION 'FUTOM no debe clasificarse';
 END IF;
 IF EXISTS (
  WITH RECURSIVE j AS (
   SELECT id,unidad_superior_id,ARRAY[id] camino,false ciclo FROM esart_ref.unidades_militares
   UNION ALL
   SELECT p.id,p.unidad_superior_id,j.camino||p.id,p.id=ANY(j.camino)
   FROM j JOIN esart_ref.unidades_militares p ON p.id=j.unidad_superior_id WHERE NOT j.ciclo
  ) SELECT 1 FROM j WHERE ciclo
 ) THEN RAISE EXCEPTION 'Jerarquia ciclica'; END IF;
 RAISE NOTICE 'Tipos insertados %, unidades insertadas %, unidades omitidas %',n_tipos,n_unidades,40-n_unidades;
END $integracion$;
COMMIT;
