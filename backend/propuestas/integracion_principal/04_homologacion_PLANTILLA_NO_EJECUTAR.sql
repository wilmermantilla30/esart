-- PLANTILLA PARAMETRIZADA; NO es un archivo ejecutable directamente en psql.
-- Solo si el conteo inicial es > 0 y existe mapa ID BIGINT -> codigo aprobado.
-- Cada fila del mapa debe aprobarse con evidencia externa: un id aislado no basta.
-- Aplicar padres antes que hijos. Resolver los valores :... en un futuro ejecutor
-- con parámetros ligados; no sustituirlos mediante concatenación de texto.
-- Precondiciones del ejecutor: base esart_db, revisión principal_0001, respaldo
-- validado, bloqueo de tablas, todos los ids del mapa existentes y sin repetidos,
-- códigos distintos, tipos válidos, jerarquía completa y ninguna ambigüedad.

UPDATE esart_ref.unidades_militares
SET uuid_publico = gen_random_uuid(),
    codigo = :codigo_aprobado,
    nombre = :nombre_aprobado,
    sigla = :sigla_aprobada,
    activa = :activa_aprobada,
    unidad_superior_id = :id_superior_bigint_verificado,
    tipo_unidad_id = :uuid_tipo_generado_en_principal
WHERE id = :id_bigint_heredado_aprobado
  AND uuid_publico IS NULL AND codigo IS NULL AND nombre IS NULL
  AND sigla IS NULL AND activa IS NULL
  AND unidad_superior_id IS NULL AND tipo_unidad_id IS NULL
RETURNING id, codigo, uuid_publico;

-- No asignar fecha_creacion a filas heredadas: su fecha histórica es desconocida.
-- El trigger propuesto asigna fecha_actualizacion automáticamente por el cambio.
-- FUTOM usa tipo_unidad_id NULL. El ejecutor debe verificar una fila por mapa,
-- que el id no cambia y que las cinco FK entrantes conservan todos sus valores.
-- Una repetición debe comparar la fila completa y OMITIRLA si ya coincide;
-- nunca regenerar uuid_publico o cambiar fechas para una homologación ya aplicada.
-- Si el mapa está incompleto o una columna fue completada por otro proceso:
-- detener antes de escribir, no sobrescribir ni crear otra unidad equivalente.
