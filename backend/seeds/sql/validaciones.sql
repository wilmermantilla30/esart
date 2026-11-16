-- Solo lectura. Ejecutar con ON_ERROR_STOP=1 sobre esart_hu03_pruebas.
BEGIN READ ONLY;
DO $$ BEGIN
 IF current_database() <> 'esart_hu03_pruebas' THEN
  RAISE EXCEPTION 'Destino no autorizado';
 END IF;
END $$;
SELECT 'roles' AS tabla, count(*) AS total FROM public.roles
UNION ALL SELECT 'permisos', count(*) FROM public.permisos
UNION ALL SELECT 'unidades_militares', count(*) FROM public.unidades_militares;
-- Las siguientes consultas deben devolver cero filas.
SELECT codigo FROM public.roles GROUP BY codigo HAVING count(*) > 1;
SELECT codigo FROM public.permisos GROUP BY codigo HAVING count(*) > 1;
SELECT codigo FROM public.unidades_militares GROUP BY codigo HAVING count(*) > 1;
SELECT u.codigo FROM public.unidades_militares u
LEFT JOIN public.unidades_militares p ON p.id = u.unidad_superior_id
WHERE u.unidad_superior_id IS NOT NULL AND p.id IS NULL;
WITH RECURSIVE jerarquia AS (
 SELECT id, unidad_superior_id, ARRAY[id] AS camino, false AS ciclo
 FROM public.unidades_militares
 UNION ALL
 SELECT p.id, p.unidad_superior_id, j.camino || p.id, p.id = ANY(j.camino)
 FROM jerarquia j JOIN public.unidades_militares p ON p.id = j.unidad_superior_id
 WHERE NOT j.ciclo
)
SELECT camino FROM jerarquia WHERE ciclo;
SELECT rp.rol_id, rp.permiso_id FROM public.roles_permisos rp
LEFT JOIN public.roles r ON r.id = rp.rol_id
LEFT JOIN public.permisos p ON p.id = rp.permiso_id
WHERE r.id IS NULL OR p.id IS NULL;
DO $$ BEGIN
 IF EXISTS (
  WITH RECURSIVE j AS (
   SELECT id, unidad_superior_id, ARRAY[id] camino, false ciclo FROM public.unidades_militares
   UNION ALL
   SELECT p.id, p.unidad_superior_id, j.camino || p.id, p.id = ANY(j.camino)
   FROM j JOIN public.unidades_militares p ON p.id = j.unidad_superior_id WHERE NOT j.ciclo
  ) SELECT 1 FROM j WHERE ciclo
 ) THEN RAISE EXCEPTION 'Ciclo en jerarquia militar'; END IF;
 IF EXISTS (
  SELECT 1 FROM public.unidades_militares u
  LEFT JOIN public.unidades_militares p ON p.id=u.unidad_superior_id
  WHERE u.unidad_superior_id IS NOT NULL AND p.id IS NULL
 ) THEN RAISE EXCEPTION 'Unidad huerfana'; END IF;
END $$;
COMMIT;
