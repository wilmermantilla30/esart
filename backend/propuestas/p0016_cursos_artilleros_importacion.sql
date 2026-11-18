-- p0016_cursos_artilleros_importacion: el curso del cargue por Excel se registra en artillero_cursos.
-- NO EJECUTAR DESDE LA APLICACION. Ejecutar manualmente como postgres (dueno de las tablas).
-- Equivale a migraciones_principal/versions/p0016_cursos_artilleros_importacion.py.
-- 1) Permisos para que el cargue registre el curso de cada artillero.
-- 2) Repara lo ya importado (idempotente: no duplica si se ejecuta dos veces).

-- Antes: cuantos registros del historial quedarian reparados.
SELECT c.codigo AS curso, c.nombre, c.estado, tc.codigo AS tipo, count(*) AS personas_sin_curso
FROM esart.hoja_vida_artillero hv
JOIN esart.cursos c ON c.id = hv.curso_id
LEFT JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
WHERE NOT EXISTS (SELECT 1 FROM esart.artillero_cursos ac WHERE ac.hoja_vida_id = hv.id)
GROUP BY c.codigo, c.nombre, c.estado, tc.codigo
ORDER BY c.codigo;

BEGIN;
DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'esart_aplicacion') THEN
            GRANT SELECT (id) ON esart.hoja_vida_artillero TO esart_aplicacion;
            GRANT INSERT (hoja_vida_id, tipo_curso_id, nombre, institucion, fecha_inicio, fecha_fin, aprobado) ON esart.artillero_cursos TO esart_aplicacion;
            GRANT SELECT (id) ON esart.artillero_cursos TO esart_aplicacion;
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO esart_aplicacion',
                           pg_get_serial_sequence('esart.artillero_cursos', 'id'));
          END IF;
        END $$;;

INSERT INTO esart.artillero_cursos (hoja_vida_id, tipo_curso_id, nombre, institucion, fecha_inicio, fecha_fin, aprobado)
    SELECT hv.id, c.tipo_curso_id, coalesce(c.nombre, tc.nombre), 'Escuela de Artillería',
           c.fecha_inicio, c.fecha_fin, c.estado = 'CULMINADO'
    FROM esart.hoja_vida_artillero hv
    JOIN esart.cursos c ON c.id = hv.curso_id
    LEFT JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    WHERE c.estado IN ('EN_CURSO', 'CULMINADO')
      AND c.fecha_inicio IS NOT NULL
      AND coalesce(c.nombre, tc.nombre) IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM esart.artillero_cursos ac WHERE ac.hoja_vida_id = hv.id);
COMMIT;

-- Despues: el curso ya figura en artillero_cursos (aprobado = CULMINADO).
SELECT c.codigo AS curso, tc.codigo AS tipo, ac.aprobado, count(*) AS personas
FROM esart.artillero_cursos ac
JOIN esart.hoja_vida_artillero hv ON hv.id = ac.hoja_vida_id
JOIN esart.cursos c ON c.id = hv.curso_id
LEFT JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
GROUP BY c.codigo, tc.codigo, ac.aprobado
ORDER BY c.codigo;
