-- Diagnostico (SOLO LECTURA) de los privilegios que exige el cargue por Excel.
-- Ejecutar como postgres. No cambia nada. Generado desde PRIVILEGIOS_IMPORTACION
-- (aplicacion/servicios/importacion_personal.py): es la misma lista que revisa el backend.
-- Cada fila con ok = false explica el 503 IMPORTACION_NO_DISPONIBLE.

SELECT p.tabla, p.columna, p.privilegio,
       CASE WHEN to_regclass(p.tabla) IS NULL THEN 'NO EXISTE LA TABLA'
            WHEN has_column_privilege('esart_aplicacion', p.tabla, p.columna, p.privilegio) THEN 'ok'
            ELSE 'FALTA (ejecutar p0011 / p0016)' END AS estado
FROM (VALUES
  ('esart.personal_militar', 'documento_identidad', 'INSERT'),
  ('esart.personal_militar', 'nombres', 'INSERT'),
  ('esart.personal_militar', 'apellidos', 'INSERT'),
  ('esart.personal_militar', 'grado', 'INSERT'),
  ('esart.personal_militar', 'genero', 'INSERT'),
  ('esart.personal_militar', 'categoria', 'INSERT'),
  ('esart.personal_militar', 'unidad_actual_id', 'INSERT'),
  ('esart.personal_militar', 'especialidad_actual', 'INSERT'),
  ('esart.personal_militar', 'activo', 'INSERT'),
  ('esart.personal_militar', 'grado', 'UPDATE'),
  ('esart.personal_militar', 'actualizado_en', 'UPDATE'),
  ('esart.tipos_curso', 'activo', 'SELECT'),
  ('esart.instructores', 'activo', 'SELECT'),
  ('esart.cursos', 'codigo', 'SELECT'),
  ('esart.cursos', 'tipo_curso_id', 'SELECT'),
  ('esart.cursos', 'tipo_curso_id', 'INSERT'),
  ('esart.cursos', 'comandante_id', 'INSERT'),
  ('esart.cursos', 'codigo', 'INSERT'),
  ('esart.cursos', 'nombre', 'INSERT'),
  ('esart.cursos', 'fecha_inicio', 'INSERT'),
  ('esart.cursos', 'fecha_fin', 'INSERT'),
  ('esart.cursos', 'estado', 'INSERT'),
  ('esart.cursos', 'observaciones', 'INSERT'),
  ('esart.cursos', 'creado_por_id', 'INSERT'),
  ('esart.hoja_vida_artillero', 'curso_id', 'SELECT'),
  ('esart.hoja_vida_artillero', 'artillero_id', 'INSERT'),
  ('esart.hoja_vida_artillero', 'grado', 'INSERT'),
  ('esart.hoja_vida_artillero', 'curso_id', 'INSERT'),
  ('esart.hoja_vida_artillero', 'unidad_id', 'INSERT'),
  ('esart.hoja_vida_artillero', 'id', 'SELECT'),
  ('esart.artillero_cursos', 'id', 'SELECT'),
  ('esart.artillero_cursos', 'hoja_vida_id', 'INSERT'),
  ('esart.artillero_cursos', 'tipo_curso_id', 'INSERT'),
  ('esart.artillero_cursos', 'nombre', 'INSERT'),
  ('esart.artillero_cursos', 'institucion', 'INSERT'),
  ('esart.artillero_cursos', 'fecha_inicio', 'INSERT'),
  ('esart.artillero_cursos', 'fecha_fin', 'INSERT'),
  ('esart.artillero_cursos', 'aprobado', 'INSERT')
) AS p(tabla, columna, privilegio)
WHERE to_regclass(p.tabla) IS NULL
   OR NOT has_column_privilege('esart_aplicacion', p.tabla, p.columna, p.privilegio)
ORDER BY p.tabla, p.columna;

-- Si la consulta anterior no devuelve filas, todos los privilegios estan bien.
-- Resumen de la migracion p0016:
SELECT has_column_privilege('esart_aplicacion', 'esart.artillero_cursos', 'nombre', 'INSERT') AS p0016_insert_cursos,
       has_column_privilege('esart_aplicacion', 'esart.artillero_cursos', 'id', 'SELECT') AS p0016_select_id,
       has_column_privilege('esart_aplicacion', 'esart.hoja_vida_artillero', 'id', 'SELECT') AS p0016_historial_id;
