-- HU-04: solo prueba aislada; sin UPDATE, DELETE, DDL ni usuarios.
BEGIN;
SET LOCAL search_path = public, pg_catalog;
DO $$ BEGIN
 IF current_database() <> 'esart_hu03_pruebas' THEN
   RAISE EXCEPTION 'Destino no autorizado: solo esart_hu03_pruebas';
 END IF;
 IF (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) THEN
   RAISE EXCEPTION 'No se permite superusuario';
 END IF;
 IF (SELECT version_num FROM public.alembic_version) IS DISTINCT FROM '0001' THEN
   RAISE EXCEPTION 'Se requiere HU-03 revision 0001';
 END IF;
END $$;
LOCK TABLE public.unidades_militares IN SHARE ROW EXCLUSIVE MODE;
DO $seed$
DECLARE r jsonb; nuevo uuid; padre uuid; insertados int := 0; omitidos int := 0;
BEGIN
 FOR r IN SELECT value FROM jsonb_array_elements('[{"codigo": "DIV01", "nombre": "Primera División", "padre": null}, {"codigo": "DIV02", "nombre": "Segunda División", "padre": null}, {"codigo": "DIV03", "nombre": "Tercera División", "padre": null}, {"codigo": "DIV04", "nombre": "Cuarta División", "padre": null}, {"codigo": "DIV05", "nombre": "Quinta División", "padre": null}, {"codigo": "DIV06", "nombre": "Sexta División", "padre": null}, {"codigo": "DIV07", "nombre": "Séptima División", "padre": null}, {"codigo": "DIV08", "nombre": "Octava División", "padre": null}, {"codigo": "DIVFE", "nombre": "División de Fuerzas Especiales", "padre": null}, {"codigo": "DAAVA", "nombre": "División de Aviación y Asalto Aéreo", "padre": null}, {"codigo": "FUTOM", "nombre": "Fuerza de Tarea Omega", "padre": null}, {"codigo": "CEDOC", "nombre": "Centro de Educación y Doctrina", "padre": null}, {"codigo": "BR01", "nombre": "Primera Brigada", "padre": "DIV05"}, {"codigo": "BR03", "nombre": "Tercera Brigada", "padre": "DIV03"}, {"codigo": "BR04", "nombre": "Cuarta Brigada", "padre": "DIV07"}, {"codigo": "BR05", "nombre": "Quinta Brigada", "padre": "DIV02"}, {"codigo": "BR08", "nombre": "Octava Brigada", "padre": "DIV05"}, {"codigo": "BR09", "nombre": "Novena Brigada", "padre": "DIV05"}, {"codigo": "BR10", "nombre": "Décima Brigada", "padre": "DIV01"}, {"codigo": "BR13", "nombre": "Décimo Tercera Brigada", "padre": "DIV05"}, {"codigo": "BR18", "nombre": "Décimo Octava Brigada", "padre": "DIV08"}, {"codigo": "BR27", "nombre": "Vigésimo Séptima Brigada", "padre": "DIV06"}, {"codigo": "BR30", "nombre": "Trigésima Brigada", "padre": "DIV02"}, {"codigo": "CEMIL", "nombre": "Centro de Educación Militar", "padre": "CEDOC"}, {"codigo": "BAACA1", "nombre": "Batallón de Artillería de Campaña N°1", "padre": "BR01"}, {"codigo": "BAACA2", "nombre": "Batallón de Artillería de Campaña N°2", "padre": "BR10"}, {"codigo": "BAACA3", "nombre": "Batallón de Artillería de Campaña N°3", "padre": "BR03"}, {"codigo": "BAACA4", "nombre": "Batallón de Artillería de Campaña N°4", "padre": "BR04"}, {"codigo": "BAACA5", "nombre": "Batallón de Artillería de Campaña N°5", "padre": "BR05"}, {"codigo": "BAACA6", "nombre": "Batallón de Artillería de Campaña N°6", "padre": "BR05"}, {"codigo": "BAACA8", "nombre": "Batallón de Artillería de Campaña N°8", "padre": "BR08"}, {"codigo": "BAACA9", "nombre": "Batallón de Artillería de Campaña N°9", "padre": "BR09"}, {"codigo": "BAACA10", "nombre": "Batallón de Artillería de Campaña N°10", "padre": "BR10"}, {"codigo": "BAACA13", "nombre": "Batallón de Artillería de Campaña N°13", "padre": "BR13"}, {"codigo": "BAACA18", "nombre": "Batallón de Artillería de Campaña N°18", "padre": "BR18"}, {"codigo": "BAACA27", "nombre": "Batallón de Artillería de Campaña N°27", "padre": "BR27"}, {"codigo": "BAACA30", "nombre": "Batallón de Artillería de Campaña N°30", "padre": "BR30"}, {"codigo": "BAADA1", "nombre": "Batallón de Artillería de Defensa Aérea N°1", "padre": "BR10"}, {"codigo": "BAADA2", "nombre": "Batallón de Artillería de Defensa Aérea N°2", "padre": "BR05"}, {"codigo": "ESART", "nombre": "Escuela de Artillería", "padre": "CEMIL"}]'::jsonb) LOOP
  padre := NULL;
  IF r->>'padre' IS NOT NULL THEN
   SELECT id INTO padre FROM public.unidades_militares WHERE codigo=r->>'padre';
   IF padre IS NULL THEN RAISE EXCEPTION 'Falta padre % de %', r->>'padre', r->>'codigo'; END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM public.unidades_militares WHERE codigo=r->>'codigo'
             AND unidad_superior_id IS DISTINCT FROM padre) THEN
   RAISE EXCEPTION 'Jerarquia existente incompatible: %', r->>'codigo';
  END IF;
  INSERT INTO public.unidades_militares (codigo,nombre,unidad_superior_id) VALUES (r->>'codigo',r->>'nombre',padre)
  ON CONFLICT (codigo) DO NOTHING RETURNING id INTO nuevo;
  IF nuevo IS NULL THEN omitidos := omitidos + 1; ELSE insertados := insertados + 1; END IF;
 END LOOP;
 RAISE NOTICE '%', json_build_object('tabla','unidades_militares','insertados',insertados,'omitidos',omitidos,'errores',0);
END $seed$;
COMMIT;
