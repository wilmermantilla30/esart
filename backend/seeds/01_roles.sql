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
LOCK TABLE public.roles IN SHARE ROW EXCLUSIVE MODE;
DO $seed$
DECLARE r jsonb; nuevo uuid; padre uuid; insertados int := 0; omitidos int := 0;
BEGIN
 FOR r IN SELECT value FROM jsonb_array_elements('[{"codigo": "ADMINISTRADOR", "nombre": "Administrador"}, {"codigo": "USUARIO", "nombre": "Usuario"}]'::jsonb) LOOP
  INSERT INTO public.roles (codigo,nombre) VALUES (r->>'codigo',r->>'nombre')
  ON CONFLICT (codigo) DO NOTHING RETURNING id INTO nuevo;
  IF nuevo IS NULL THEN omitidos := omitidos + 1; ELSE insertados := insertados + 1; END IF;
 END LOOP;
 RAISE NOTICE '%', json_build_object('tabla','roles','insertados',insertados,'omitidos',omitidos,'errores',0);
END $seed$;
COMMIT;
