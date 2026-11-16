> Actualizacion: el respaldo proporcionado ya fue restaurado y verificado. La prueba aislada de unidades/tipos tambien paso. La ejecucion en la principal sigue pendiente de localizar la conexion administrativa; consultar [ESART_DESPLIEGUE_BASE_PRINCIPAL.md](ESART_DESPLIEGUE_BASE_PRINCIPAL.md).

# ESART — Plan de integración de unidades sin duplicar entidades

**Propuesta para aprobación. No se ejecutó DDL, DML, migraciones ni restauraciones.**
Fecha: 15 de noviembre de 2026.

## 1. Decisión de arquitectura propuesta

**Ampliar `esart_ref.unidades_militares` como entidad canónica**, manteniendo su
`id BIGINT`, identidad, secuencia y las FK actuales. No crear otra tabla de unidades
en `public`, no mover referencias y no convertir identificadores a UUID.

Esta decisión sustituye la alternativa anterior de instalar una segunda entidad
de unidades en `public`. Las dependencias verificadas y el requisito de evitar
duplicidad justifican el cambio de propuesta. No implica que los modelos UUID de
HU-03 puedan conectarse directamente al esquema heredado.

Para conservar una identidad UUID en el contrato de API, se propone añadir
`uuid_publico UUID UNIQUE`, **en la misma fila**, generado en la principal.
Es un identificador de exposición, no una segunda entidad ni una nueva PK.
Los consumidores heredados siguen referenciando el mismo BIGINT.

El único catálogo físico nuevo propuesto es `esart.tipos_unidad`, que no tiene
equivalente en la base inventariada. Conserva los nueve códigos aprobados, con
UUID generados en la principal. La nueva FK `tipo_unidad_id UUID` sigue opcional.
No se crean estados operacionales o logísticos.

La propuesta arquitectónica queda definida; la ruta de datos sigue condicionada
al conteo y al posible mapa de IDs heredados, que no puede inventarse.

## 2. Dependencias verificadas en la principal

Consulta actual de solo lectura contra `esart_db`, PostgreSQL 18.7. El propietario
de la tabla es `postgres`. La cuenta disponible no tiene `USAGE`, `SELECT`,
`INSERT` ni `UPDATE` sobre el destino.

### Cinco FK directas, todas validadas en el catálogo

| Tabla dependiente | Columna BIGINT | Restricción | NULL permitido |
|---|---|---|---|
| `esart.personal_militar` | `unidad_actual_id` | `fk_personal_militar_unidad_actual_id` | Sí |
| `esart.artillero_cargos` | `unidad_id` | `fk_artillero_cargos_unidad_id` | Sí |
| `esart.artillero_disparos` | `unidad_id` | `fk_artillero_disparos_unidad_id` | Sí |
| `esart.egresados_curso` | `unidad_destino_id` | `fk_egresados_curso_unidad_destino_id` | Sí |
| `esart.reentrenamientos` | `unidad_id` | `fk_reentrenamientos_unidad_id` | **No** |

Todas apuntan a `esart_ref.unidades_militares(id)` y no especifican acciones de
borrado especiales. No se propone eliminarlas, recrearlas ni cambiar sus valores.

Además se identificaron las dependencias de PK, NOT NULL, el tipo compuesto de la
fila y la secuencia de identidad `esart_ref.unidades_militares_id_seq`.
La clausura transitiva por FK alcanza **20 tablas**, incluidas las cinco directas.
No significa que las veinte tengan una FK directa a unidades.

La lista completa está en [ESART_DEPENDENCIAS_UNIDADES.json](ESART_DEPENDENCIAS_UNIDADES.json),
generada desde `pg_constraint` y `pg_depend`, sin necesidad de leer datos protegidos.
Estas consultas no detectan SQL dinámico externo ni consumidores fuera de la base;
deben revisarse antes de activar la nueva aplicación.

## 3. Existencia de registros: verificación todavía bloqueada

**El número de registros del stub es desconocido. No se afirma que esté vacío.**
La ausencia de `USAGE`/`SELECT` impide `count(*)`, inspeccionar IDs y comprobar los
datos de las tablas dependientes. El diagnóstico de metadatos no sustituye esas
comprobaciones.

Se preparó [01_preflight_lectura.sql](../backend/propuestas/integracion_principal/01_preflight_lectura.sql)
para una cuenta de lectura autorizada. Verifica la base, obtiene cantidad, extremos
de ID, uso de cada ID por las cinco FK y estado de la secuencia. Solo contiene
consultas dentro de una transacción READ ONLY.

Dos rutas posibles, sin cambiar la arquitectura:

- **Tabla vacía, demostrado:** generar IDs principales al insertar las 40 unidades.
- **Tabla con filas:** exigir un mapa institucional aprobado `id BIGINT existente →
  código de unidad`. Un ID aislado no permite saber su nombre. No asignar por orden,
  número de filas, posición de secuencia o UUID de pruebas. No insertar otras 40
  unidades en paralelo mientras queden entidades heredadas sin reconciliar.

Si hay unidades legítimas adicionales, conservarlas. El objetivo es verificar las
40 unidades aprobadas, no borrar otros registros para forzar el total global.
Si todas las existentes corresponden a ese conjunto, el total final será 40;
si no, se documentará el total real y su separación funcional.

## 4. Estructura propuesta y conservación

| Campo | Tipo propuesto | Tratamiento |
|---|---|---|
| `id` | BIGINT existente | PK e identidad intactas; nunca asignar UUID aquí |
| `uuid_publico` | UUID UNIQUE | Generado en principal para filas nuevas o homologadas; nunca copiar el UUID de pruebas |
| `codigo` | VARCHAR(20) UNIQUE | Clave natural aprobada para correspondencia e idempotencia |
| `nombre` | VARCHAR(200) | Nombre aprobado; no sobrescribir uno existente incompatible |
| `sigla` | VARCHAR(30) | Valor de referencia, sin inferirlo del código |
| `unidad_superior_id` | BIGINT | FK autorreferente al ID canónico |
| `tipo_unidad_id` | UUID nullable | FK a `esart.tipos_unidad`; FUTOM NULL |
| `activa` | BOOLEAN | Valor conocido para unidades aprobadas |
| `fecha_creacion` | TIMESTAMPTZ | Fecha de inserción para filas nuevas; desconocida en filas heredadas |
| `fecha_actualizacion` | TIMESTAMPTZ | Trigger nuevo y explícito para cambios de negocio; no se dispara por omisiones del seed |

La ampliación inicial añade campos **nullable y sin defaults**. Así las filas
heredadas no reciben nombres, clasificaciones, fechas o UUID inventados durante
el DDL. Las restricciones de unicidad admiten NULL en filas pendientes.

No se propone imponer NOT NULL a toda la tabla hasta completar la homologación.
En particular, una fecha de creación histórica desconocida no se reemplaza por
la fecha actual para satisfacer un contrato. Las filas aprobadas se verifican
con todos sus campos necesarios antes de habilitar su consulta en la API.

La propuesta incluye un CHECK contra auto-superior, índices individuales de ambas
FK y validación de ciclos en el cargador. La FK por sí sola no impide ciclos largos.
Añadir columnas no cambia las cinco relaciones entrantes, aunque el DDL obtiene
bloqueos y requiere una ventana acordada.

## 5. Operaciones SQL preparadas, no ejecutadas

Carpeta: [backend/propuestas/integracion_principal](../backend/propuestas/integracion_principal).
No está registrada como migración activa ni importada por el backend.

1. `01_preflight_lectura.sql`: diagnóstico de datos pendiente de una cuenta autorizada.
2. `02_estructura_NO_EJECUTAR.sql`: comprueba destino y forma del stub; crea tipos,
   añade columnas/índices/constraints y un trigger nuevo específico. No toca la
   PK, secuencia ni las FK entrantes. No usa `IF NOT EXISTS` para ocultar diferencias.
3. `03_tipos_NO_EJECUTAR.sql`: carga los nueve tipos y rechaza códigos existentes
   con valores incompatibles; no actualiza nombres ni IDs existentes.
4. `04_homologacion_PLANTILLA_NO_EJECUTAR.sql`: operación parametrizada para un
   mapa de IDs **todavía no disponible**. No es SQL listo para ejecutar en psql.
   Completa solo columnas nuevas vacías, conserva el BIGINT y exige verificación
   de una fila por correspondencia. Una repetición debe omitir filas ya correctas.
5. `05_unidades_NO_EJECUTAR.sql`: inserta referencias ausentes, padres antes que
   dependientes; omite filas correctas y rechaza conflictos. Bloquea la carga si
   encuentra IDs heredados sin código. Verifica 40 códigos y 39 clasificaciones,
   FUTOM NULL y ausencia de ciclos. No actualiza unidades existentes.

Los archivos son fragmentos transaccionales de revisión; no constituyen un
instalador autorizado ni deben concatenarse asumiendo una única transacción.
El ejecutor definitivo debe prevalidar todo el mapa antes de iniciar la fase de
datos y registrar cada checkpoint confirmado. Una incompatibilidad detiene esa
fase; no se limpian datos de una fase anterior para intentar continuar.

La repetición omite filas antes del INSERT, evitando consumir IDs de identidad
para códigos ya existentes o actualizar fechas. El seed comprueba que la secuencia
no esté atrasada si se requieren inserciones. No la reajusta automáticamente.
Una transacción fallida puede dejar huecos normales de secuencia: PostgreSQL no
revierte `nextval`. Eso no autoriza renumerar IDs. Las simulaciones de carga deben
realizarse sobre la recuperación independiente, no consumiendo identidades en la
principal como sustituto de una prueba aislada.

## 6. Migraciones e historial real de Alembic

La estructura propuesta **no es físicamente equivalente** a `0002`: su PK canónica
es BIGINT y vive en `esart_ref`; UUID se usa como identificador de API. Por tanto
**no corresponde marcar esta base como `0002`** ni usar el baseline de la propuesta
anterior de tablas UUID paralelas.

Se propone un entorno Alembic operativo separado, con configuración explícita y
linaje real nuevo:

- `principal_0001`: ampliación canónica descrita en `02_estructura...`.
- `principal_0002`: ejecución de los datos aprobados, condicionada a la prevalidación
  del mapa heredado y a los resultados del respaldo/restauración.

La base actualmente no tiene `alembic_version`; el futuro entorno registrará sus
revisiones realmente ejecutadas en `public.alembic_version`. Su directorio de
migraciones y metadatos operativos será distinto del de HU-03/HU-04. No se ejecutará
`upgrade heads` mezclando ambos historiales, ni se modificarán `0001`/`0002`.

El futuro autogenerate deberá filtrar objetos por lista explícita de este alcance,
sin proponer borrar o recrear las otras 42 tablas. Las revisiones iniciales serán
DDL congelado y revisado, no `create_all()` ni importación de modelos mutables.
Esta decisión de historial y cambio de contrato debe aprobarse expresamente.

## 7. Datos preparados y resultado esperado

[datos_aprobados.json](../backend/propuestas/integracion_principal/datos_aprobados.json)
conserva los datos aprobados de 40 unidades y nueve tipos, sin IDs de pruebas.
Orden jerárquico validado y 39 correspondencias iguales a la matriz HU-04 fase 4:

| Tipo | Unidades |
|---|---:|
| DIV | 10 |
| BR | 11 |
| BAACA | 13 |
| BAADA | 2 |
| CEDOC | 1 |
| CEM | 1 |
| ESART | 1 |
| FUTOM pendiente | 1 |

BATAR y CECFU siguen en el catálogo sin asignaciones en ese conjunto. No se crea
un tipo para Fuerza de Tarea. En la homologación FUTOM conserva tipo NULL.

Los cargos/cursos/roles ya tienen entidades heredadas. Esta propuesta no los duplica
en `public` ni cambia sus identificadores o semántica. Su integración completa
requiere leer sus registros y aprobar sus diferencias de columnas, como se detalla
en el inventario general. El alcance de estos SQL es unidades y su catálogo de tipos.

## 8. Compatibilidad SQLAlchemy, FastAPI y Angular

Los modelos actuales de HU-03 no son compatibles directamente: `UnidadMilitar.id`
y sus consumidores son UUID y no fijan esquema. Cambiar solo la URL o añadir
`esart_ref` al `search_path` produciría un mapeo incorrecto.

El futuro modelo operativo deberá declarar explícitamente:

```python
# Especificación conceptual; no se ha instalado este modelo.
__tablename__ = "unidades_militares"
__table_args__ = {"schema": "esart_ref"}
id: Mapped[int]                       # BIGINT PK existente
uuid_publico: Mapped[UUID | None]     # UUID expuesto en DTO, no PK heredada
unidad_superior_id: Mapped[int | None]  # FK BIGINT de la misma tabla
tipo_unidad_id: Mapped[UUID | None]  # FK esart.tipos_unidad.id
```

Se necesita un registro de metadatos operativo separado del modelo de pruebas
para no mezclar tablas físicas ni alterar las comprobaciones históricas de HU-03.
Las relaciones con modelos heredados usan sus nombres reales (`unidad_actual_id`,
`unidad_id`, etc.) y tipos BIGINT. No se cambia únicamente el tipo de UnidadMilitar
dejando FK consumidoras UUID.

FastAPI debe consultar la entidad canónica mediante un repositorio operativo y
presentar `id = uuid_publico` y el UUID público del superior en el DTO. Los BIGINT
continúan siendo internos. La API no puede publicar como UUID un registro sin
homologar. Debe resolver explícitamente el acceso administrativo a pendientes
heredados, sin esconderlos ni asignarles nombres inventados.

Actualmente solo está registrado el endpoint de salud y no existe el endpoint de
unidades. La autenticación/autoridad también requiere adaptar su repositorio al
esquema heredado: los helpers actuales usan usuarios UUID y rol único, mientras
la base tiene BIGINT y `usuario_roles`. No basta con añadir UUID público a unidades.
No se activará un endpoint público para eludir esa incompatibilidad, ni se
escogerá un rol heredado arbitrariamente. Esta decisión de seguridad es otra
puerta de activación, sin alterar usuarios en el alcance actual.

Angular conserva su estructura inicial, sin servicio HTTP ni rutas de unidades.
Después de aprobación debe consumir DTO UUID y mostrar código, nombre, tipo,
superior y FUTOM pendiente; búsquedas y filtros por código/nombre/tipo. Nunca debe
conocer una conexión PostgreSQL o depender de los BIGINT internos. Conservar la
arquitectura standalone y los controles de acceso acordados.

La selección de `.env` y el marcador JWT detectados en el diagnóstico general
siguen siendo requisitos de configuración, no se corrigen cambiando datos de unidades.
No se modificó ningún modelo de runtime, endpoint, servicio Angular o secreto.

## 9. Respaldo y recuperación: bloqueantes reales

La cuenta disponible sigue sin lectura de la tabla y de las demás tablas heredadas.
Los intentos anteriores de `pg_dump` completo y de estructura produjeron archivos
de cero bytes, no respaldos válidos. No se ejecutó una restauración ni se crearon
bases para intentar recuperarlos.

Está preparado el script
[respaldar_base_principal.ps1](../backend/herramientas/respaldar_base_principal.ps1)
para una cuenta autorizada. Debe generar un archivo íntegro, validar listado y
decodificación, registrar SHA-256 y probar restauración con errores fatales en una
**instancia nueva aislada cuyo destino se autorice**, sin tocar la principal ni
las bases existentes. Verificar propietarios/ACL, las 42 tablas, datos, relaciones,
secuencias y que las referencias se preserven. Listar el dump no prueba restauración.

No se considera cumplida la restaurabilidad hasta realizar esa prueba real. No se
modifican permisos de la cuenta de aplicación como solución implícita. La migración
de la tabla propiedad de `postgres` requerirá un operador con autoridad de propietario;
`CREATE` en `public` o ser dueño de la base no bastan para alterarla.

## 10. Criterios de aceptación y autorización solicitada

Antes de ejecutar los SQL:

1. Respaldo completo restaurado satisfactoriamente en un destino independiente autorizado.
2. Conteo de IDs y referencias existentes, más mapa institucional completo si hay filas.
3. Aprobación de ampliar la entidad canónica BIGINT, añadir UUID público y usar el
   linaje operativo nuevo; no reportar falsamente la revisión histórica `0002`.
4. Revisión del DDL y de las transacciones de datos con el mapa definitivo; simulación
   solo en el entorno aislado, con evidencia de que las cinco FK y sus filas no cambian.

Al ejecutar posteriormente: verificar identidad antes de cada operación, conservar
el conjunto de IDs originales, comparar todas las referencias entrantes y sus datos,
validar claves/ciclos, comprobar las 40 correspondencias y 39 tipos con FUTOM NULL,
y repetir el seed sin cambios de datos, fechas o consumo innecesario de identidades.
No borrar filas desconocidas, no trasladar UUID de pruebas y no renumerar secuencias.

**Hoy se entrega una decisión técnica y SQL para revisión, no una integración
ejecutable sin condiciones.** El conteo, el mapa y la recuperación siguen pendientes
por falta de permisos. No se modificó `esart_db`, ninguna otra base, ni las migraciones
históricas. Las pruebas SQL de estructura/carga/restauración aún no se ejecutaron.
