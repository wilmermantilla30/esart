> Validacion actualizada: los SQL 02/03/05 se probaron correctamente en una recuperacion aislada del respaldo, con 40 unidades, 39 clasificadas y FUTOM pendiente; repeticion sin cambios de filas, fechas ni secuencia. Nunca se ejecutaron en la principal. El historial Alembic, la plantilla de homologacion y los permisos de runtime aun no estan aplicados.

# Propuesta operativa — no ejecutada

Documento rector: [ESART_PLAN_DEFINITIVO_INTEGRACION.md](../../../docs/ESART_PLAN_DEFINITIVO_INTEGRACION.md).

Se propone **ampliar la entidad canónica** `esart_ref.unidades_militares`, sin
crear `public.unidades_militares`. Conservar BIGINT e incorporar UUID público.
El catálogo nuevo será `esart.tipos_unidad`, con UUID propios de la principal.

Archivos de revisión, no instalados en Alembic ni importados por la aplicación:

1. `01_preflight_lectura.sql`: para una cuenta autorizada; cuenta IDs y referencias.
2. `02_estructura_NO_EJECUTAR.sql`: DDL propuesto para el nuevo linaje `principal_0001`.
3. `03_tipos_NO_EJECUTAR.sql`: nueve tipos, sin sobrescribir existentes.
4. `04_homologacion_PLANTILLA_NO_EJECUTAR.sql`: plantilla de parámetros ligados;
   falta el mapa institucional si hay filas heredadas. No ejecutar en psql.
5. `05_unidades_NO_EJECUTAR.sql`: datos propuestos para `principal_0002`; padres
   antes que dependientes, rechazo de conflictos y comprobaciones de clasificación.
6. `06_permisos_lectura_NO_EJECUTAR.sql`: propuesta de privilegios mínimos de lectura.
7. `datos_aprobados.json`: referencias sin IDs de pruebas; 40 unidades y nueve tipos.

No ejecutar el directorio en lote. Los archivos tienen transacciones propias y
no constituyen un instalador; la revisión Alembic debe registrar las operaciones
realmente confirmadas. No crear historial artificial `0002` sobre este esquema.

**Precondiciones pendientes:** permiso de lectura para inspeccionar los datos,
respaldo completo restaurado en una instancia aislada autorizada, mapa de IDs si
el stub contiene filas y aprobación de la arquitectura/cambio de contrato.
Las pruebas de estructura, migración, carga, repetición y permisos se harán en
esa recuperación independiente antes de ejecutar nada en la principal.

No se han ejecutado estos SQL ni probado su aplicación en PostgreSQL. Su validación
actual es documental y sobre los datos de referencia; no se declara compatibilidad
operativa completa de los modelos o la interfaz actuales.

El seed omite filas correctas antes de intentar INSERT para que la repetición no
consuma identidades. No cambia PK ni reajusta secuencias. Si una fila heredada no
tiene código, la carga se bloquea hasta aprobar su homologación, evitando duplicarla.
