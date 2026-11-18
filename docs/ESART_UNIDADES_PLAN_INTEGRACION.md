> Actualizacion: el respaldo proporcionado ya fue restaurado y verificado. La prueba aislada de unidades/tipos tambien paso. La ejecucion en la principal sigue pendiente de localizar la conexion administrativa; consultar [ESART_DESPLIEGUE_BASE_PRINCIPAL.md](ESART_DESPLIEGUE_BASE_PRINCIPAL.md).

> Arquitectura de unidades revisada: [ESART_PLAN_DEFINITIVO_INTEGRACION.md](ESART_PLAN_DEFINITIVO_INTEGRACION.md) propone ampliar la tabla can?nica BIGINT, sin duplicarla en public. La alternativa de instalaci?n paralela de unidades de este documento queda sustituida, no ejecutada.

# ESART — Diagnóstico de ausencia de unidades y plan de integración

**Estado: diagnóstico actualizado; ninguna integración ejecutada.**
Fecha: 15 de noviembre de 2026. Se consultaron ambas bases en transacciones
`REPEATABLE READ, READ ONLY`, comprobando explícitamente su nombre.

## Causa confirmada

Las unidades aprobadas están en una base distinta a la principal. Además, la
principal contiene otra estructura y la interfaz aún no implementa su consulta.
No es suficiente cambiar la URL de conexión ni ejecutar otra vez los seeds de pruebas.

| Comprobación actual | `esart_db` | `esart_hu03_pruebas` |
|---|---|---|
| Conexión PostgreSQL | Verificada | Verificada |
| Tablas de aplicación e historial | 42, en `esart` y `esart_ref` | 24 en `public`, incluida `alembic_version` |
| Alembic | No existe `alembic_version` | `0002` |
| Tabla de unidades | `esart_ref.unidades_militares` | `public.unidades_militares` |
| Estructura de unidades | Solo `id BIGINT` | UUID, código, nombre, sigla, superior, activa, fechas y tipo opcional |
| Cantidad de unidades | No verificable por permisos; no asumir cero | **40** |
| Clasificación | La tabla existente no tiene esa columna | **39 clasificadas, FUTOM pendiente** |
| Tipos | No existe el catálogo contractual | **9 tipos** |

La búsqueda de tablas se hizo en todos los esquemas de usuario visibles en
`pg_catalog`, no solo en `public` o `information_schema`. En la principal no se
encontró otra tabla `unidades_militares` con la estructura de HU-04.

La cuenta disponible carece de `USAGE` en `esart` y `esart_ref` y de lectura sobre
las 42 tablas existentes. Ser propietaria de la base no la hace propietaria de
esas tablas. No puede determinarse aún qué filas del sistema heredado deben
corresponderse con el conjunto aprobado; tampoco se certifican duplicados o huérfanos.

## Migraciones y conservación del sistema existente

`0001` define el núcleo UUID en `public`, pero rechaza una base que ya contiene
tablas de aplicación. `0002` añade tipos de unidad y su FK opcional, pero su guarda
solo permite las dos bases de pruebas. Por eso un `upgrade head` directo no es
compatible con el estado actual de `esart_db`.

No se alteraron las migraciones ni se usó `stamp` para aparentar una instalación.
El procedimiento de baseline propuesto y sus alternativas están detallados en
[ESART_INTEGRACION_BASE_PRINCIPAL.md](ESART_INTEGRACION_BASE_PRINCIPAL.md).

Se propone preservar íntegramente `esart` y `esart_ref` y preparar una instalación
aditiva del contrato aprobado en `public`. La separación física no resuelve por
sí sola las correspondencias de negocio: si se deben enlazar registros heredados,
primero hay que inspeccionarlos y aprobar su mapeo. No se convertirá el stub ni
se cambiarán sus identificadores, columnas o relaciones.

## Datos preparados para revisión

Se generó [propuesta_unidades.json](../backend/seeds/integracion_principal/propuesta_unidades.json)
leyendo las unidades y los tipos actuales de `esart_hu03_pruebas`:

- 40 unidades con código, nombre, sigla, indicador activa y superior por código.
- Nueve tipos con código, nombre y estado activo.
- Las 39 clasificaciones coinciden exactamente con la matriz aprobada en fase 4.
- FUTOM tiene `tipo_codigo = null`.
- Los padres aparecen antes que sus dependientes; se validó ausencia de ciclos y
  padres faltantes en ese conjunto.
- **No contiene UUID ni otros identificadores de las bases de pruebas.** En la
  integración se resolverán códigos existentes y se generarán UUID principales
  solo para registros nuevos. No se reutilizarán IDs BIGINT del stub como UUID.

SHA-256 del archivo preparado:
`8fab13e101d30e4fc8cc39699ed5d7e06f6f04337a8d3cdf1924e1eb8d2c4524`.

Es un paquete de datos de referencia, no un seed ejecutado ni un permiso para
sobrescribir datos. Las correspondencias con filas existentes se verificarán
antes de cualquier escritura. Los otros catálogos académicos y de seguridad
mantienen las decisiones pendientes del diagnóstico general.

## Respaldo: requisito aún bloqueado

No hay un respaldo completo válido de la principal. Los intentos anteriores de
`pg_dump` quedaron bloqueados por permisos y produjeron archivos de cero bytes.
La nueva comprobación confirmó que esos permisos siguen faltando. No se repitió
un intento destinado a fallar ni se declaró válido un archivo vacío.

Está preparado el script manual
[respaldar_base_principal.ps1](../backend/herramientas/respaldar_base_principal.ps1).
Debe ejecutarse con una cuenta administrativa/de respaldo autorizada, sin cambiar
las credenciales operativas. Solicita la contraseña interactivamente, comprueba
el destino, genera el dump completo, lista y decodifica el archivo y calcula su
SHA-256. No cambia permisos ni datos de PostgreSQL.

Después debe probarse una restauración real en una instancia nueva y aislada,
con autorización de ese destino. No se utilizarán ni modificarán las dos bases
de pruebas existentes para recuperar el respaldo de la principal. Un listado
correcto del archivo no equivale a una recuperación probada.

## FastAPI y Angular: estado actual

La URL seleccionada explícitamente desde `backend/.env` ya nombra `esart_db`.
Sin embargo, el código busca por defecto `.env` en la raíz, donde no existe.
Al seleccionar el archivo de `backend`, la validación completa detecta una clave
JWT con marcador de ejemplo. No se mostró ni cambió ningún secreto. Esta es una
comprobación de configuración local; no certifica el estado de un proceso externo.

FastAPI registra solamente el endpoint de salud; no tiene registrados endpoints
de unidades o catálogos. Angular conserva rutas vacías, sin servicio de unidades,
proveedor HTTP o proxy de API. No existe actualmente un flujo de consulta real
que permita mostrar las unidades desde la principal.

No se editaron estos componentes. En la implementación posterior se requieren:

1. Selección coherente del archivo de configuración y secretos válidos, manteniendo
   `esart_db` como destino operativo y las pruebas aisladas.
2. Endpoints autenticados de unidades y tipos, con los permisos existentes y un
   contrato de código, nombre, tipo opcional y superior.
3. Servicio Angular que consuma `/api`, listado y jerarquía, búsquedas por código
   y nombre y filtro de tipo. FUTOM se mostrará como pendiente de clasificación.
4. Prueba de extremo a extremo que demuestre que la respuesta sale de `esart_db`,
   no de fixtures o de una base de pruebas. La salud `SELECT 1` no basta.

## Orden de ejecución propuesto, pendiente de autorización

1. **Desbloquear respaldo e inspección:** un DBA genera el respaldo íntegro y
   permite verificar los datos sin modificar tablas ni otorgar acceso implícito
   a la aplicación. Probar su recuperación y documentar las correspondencias.
2. **Aprobar instalación aditiva e historial:** revisar el instalador específico
   de `public` y la adopción de baseline verificada descrita en el informe general.
   No ejecutar directamente las revisiones protegidas ni falsear Alembic.
3. **Probar el procedimiento sobre la recuperación independiente:** comprobar
   que las 42 tablas heredadas y sus datos permanecen sin alteraciones.
4. **Tras autorización expresa, integrar:** instalar el contrato y cargar tipos y
   unidades por códigos, con UUID de destino, respetando jerarquía y FUTOM NULL.
   Ante un código existente incompatible, detenerse, no sobrescribirlo.
5. **Demostrar idempotencia:** repetir la carga sin insertar, reclasificar ni
   actualizar fechas de registros ya correctos. Conservar registros legítimos
   adicionales si la inspección los encuentra, sin eliminarlos para forzar un total.
6. **Integrar API e interfaz:** conectar los endpoints reales, conservar controles
   de acceso y verificar que las 40 unidades aprobadas se vean en ESART desde la
   principal. Presentar los resultados antes de dar la integración por completada.

## Evidencia y límite de esta ejecución

[ESART_UNIDADES_DIAGNOSTICO_ACTUAL.json](ESART_UNIDADES_DIAGNOSTICO_ACTUAL.json)
contiene las tablas identificadas en ambas bases y la consulta de las 40 unidades.
[ESART_UNIDADES_CONFIGURACION_DIAGNOSTICO.json](ESART_UNIDADES_CONFIGURACION_DIAGNOSTICO.json)
documenta las validaciones de configuración sin secretos.

Esta ejecución solo realizó consultas y creó documentos y un paquete JSON local.
**No se modificaron `esart_db`, `esart_hu03_pruebas`, la base temporal, la conexión
operativa, las migraciones, los endpoints ni el frontend.** El resultado final
solicitado queda pendiente de un respaldo recuperable, de las decisiones de
homologación y de autorización expresa para implementarlo.
