-- Solo ejecutar tras aprobación y aplicación de 0002 y sus semillas.
BEGIN READ ONLY;
DO $$ BEGIN
 IF current_database() <> 'esart_hu03_pruebas' THEN
  RAISE EXCEPTION 'Destino no autorizado';
 END IF;
 IF (SELECT version_num FROM public.alembic_version) IS DISTINCT FROM '0002' THEN
  RAISE EXCEPTION 'Se requiere revision 0002';
 END IF;
 IF EXISTS (
  SELECT 1 FROM public.unidades_militares u
  LEFT JOIN public.tipos_unidad t ON t.id=u.tipo_unidad_id
  WHERE u.tipo_unidad_id IS NOT NULL AND t.id IS NULL
 ) THEN RAISE EXCEPTION 'Clasificacion huerfana'; END IF;
 IF EXISTS (
  SELECT unnest(ARRAY['DIV','BR','BAACA','BATAR','CECFU','CEDOC','CEM','BAADA','ESART'])
  EXCEPT SELECT codigo FROM public.tipos_unidad
 ) THEN RAISE EXCEPTION 'Faltan tipos de referencia'; END IF;
END $$;
SELECT codigo, nombre, activo FROM public.tipos_unidad ORDER BY codigo;
SELECT count(*) AS total_unidades,
       count(tipo_unidad_id) AS clasificadas,
       count(*) FILTER (WHERE tipo_unidad_id IS NULL) AS pendientes
FROM public.unidades_militares;
COMMIT;
