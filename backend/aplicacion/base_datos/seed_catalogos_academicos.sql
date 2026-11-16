-- ESART: datos iniciales de catálogos académicos (5 cargos, 14 cursos)
-- Ejecutar únicamente tras confirmar esquema y base de datos de destino.
-- Repetible: ON CONFLICT DO NOTHING no modifica registros existentes.
BEGIN;
DO $$
BEGIN
  IF to_regclass('esart.tipos_cargo') IS NULL OR to_regclass('esart.tipos_curso') IS NULL THEN
    RAISE EXCEPTION 'Faltan esart.tipos_cargo o esart.tipos_curso. No se cargaron datos.';
  END IF;
END $$;

INSERT INTO esart.tipos_cargo (nombre, descripcion, cuenta_para_coofu, activo) VALUES
('Comandante de pieza', 'Oficial o suboficial responsable de la operacion y empleo tactico de una pieza de artilleria.', TRUE, TRUE),
('Comandante de Bateria', 'Oficial responsable del mando, control y empleo operacional de una bateria de artilleria.', TRUE, TRUE),
('Armamento Mayor', 'Suboficial tecnico responsable del mantenimiento y control del armamento de la unidad.', FALSE, TRUE),
('Tecnico Mantenimiento', 'Especialista tecnico en mantenimiento de sistemas y equipos de artilleria.', FALSE, TRUE),
('Coordinador de Fuegos', 'Oficial responsable de planear, coordinar y controlar el empleo del fuego de artilleria en apoyo de la maniobra.', TRUE, TRUE)
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO esart.tipos_curso (codigo, nombre, tipo, modalidad, duracion_semanas, activo) VALUES
('TECNICA', 'Tecnico profesional en mantenimiento mecanico aplicado a la operacion de armas de artilleria', 'EDUCACION_SUPERIOR', 'PRESENCIAL', 43, TRUE),
('COOFU', 'Coordinador de Fuegos', 'EDUCACION_MILITAR', 'VIRTUAL', 2, TRUE),
('SACLI', 'Curso sistemas de artilleria liviana', 'EDUCACION_MILITAR', 'PRESENCIAL', 10, TRUE),
('SACME', 'Curso sistemas de artilleria mediana', 'EDUCACION_MILITAR', 'PRESENCIAL', 11, TRUE),
('COSET', 'Curso control y seguimiento al tiro', 'EDUCACION_MILITAR', 'PRESENCIAL', 10, TRUE),
('ADA', 'Curso de artilleria de defensa aerea', 'EDUCACION_MILITAR', 'PRESENCIAL', 8, TRUE),
('OA', 'Curso observacion adelantada', 'EDUCACION_MILITAR', 'PRESENCIAL', 5, TRUE),
('CAPINTE', 'Curso capacitacion intermedia', 'EDUCACION_MILITAR', 'PRESENCIAL', 12, TRUE),
('COMANDO', 'Especializacion del arma — curso Comando', 'ESPECIALIZACION', 'PRESENCIAL', 4, TRUE),
('INTERMEDIO', 'Especializacion del arma — curso Intermedio', 'ESPECIALIZACION', 'PRESENCIAL', 5, TRUE),
('COTAC', 'Especializacion del arma — curso COTAC', 'ESPECIALIZACION', 'PRESENCIAL', 2, TRUE),
('CAPAVAN', 'Especializacion del arma — curso CAPAVAN', 'ESPECIALIZACION', 'PRESENCIAL', 2, TRUE),
('ALFEREZ', 'Especializacion del arma — curso Alfereces', 'ESPECIALIZACION', 'PRESENCIAL', 5, TRUE),
('DRAGONEANTES', 'Especializacion del arma — curso Dragoneantes', 'ESPECIALIZACION', 'PRESENCIAL', 8, TRUE)
ON CONFLICT (codigo) DO NOTHING;
COMMIT;

SELECT 'tipos_cargo' AS catalogo, COUNT(*) AS total FROM esart.tipos_cargo
UNION ALL
SELECT 'tipos_curso', COUNT(*) FROM esart.tipos_curso;
