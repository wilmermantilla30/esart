# HU-04 — Población de datos institucionales

## Alcance y evolución

HU-04 reutilizó referencias suministradas para roles, permisos, unidades y catálogos académicos. Los primeros scripts se validaron sobre un contrato UUID en public; la persistencia operativa posterior usa BIGINT y los esquemas esart/esart_ref de esart_db. **Esos contratos no son intercambiables.** Este documento complementa los informes de cada fase sin atribuir sus pruebas a la principal.

| Etapa | Trabajo y evidencia | Límite |
|---|---|---|
| Fase 2 | 2 roles, 36 permisos, 40 unidades; generador, SQL por catálogo, validación de códigos y superiores. [Informe](../backend/seeds/INFORME_HU04_FASE2.md) | Destino histórico esart_hu03_pruebas/public, revisión 0001 |
| Fase 3 | Catálogo de nueve tipos, FK opcional y pruebas estructurales/reversión. [Análisis](HU04_FASE3_ANALISIS.md), [ejecución histórica](HU04_FASE3_EJECUCION.md) | Migración UUID 0002; ciclo sobre una temporal, no sobre la principal |
| Fase 4 | Matriz de 39 clasificaciones, simulación, actualización estricta e idempotencia. [Propuesta](HU04_FASE4_PROPUESTA.md), [ejecución histórica](HU04_FASE4_EJECUCION.md) | FUTOM pendiente; estas evidencias originales corresponden a pruebas |
| Principal | Operador cargó estructura y referencias BIGINT; ORM y consultas se conciliaron con el catálogo real | No hay instalador único validado ni prueba HTTP autenticada completa |

Los estados operacionales y logísticos heredados describen material de VULCANO y se excluyeron de ESART. No se generó un tipo artificial para FUTOM.

## Fuentes y trazabilidad

- `backend/aplicacion/base_datos/initial_data.py`: fuente heredada de literales; no es un cargador seguro de ESART. Importa módulos app inexistentes aquí e incluye comportamiento ajeno y administrador de prueba. No ejecutarlo.
- `backend/seeds/catalogos.json`: referencias históricas de roles/permisos/unidades y catálogos sin tabla en esa fase. Conserva estados VULCANO como referencia, no como orden de carga.
- `backend/seeds/fase4_matriz.json`: correspondencias aprobadas. Los identificadores de su snapshot no deben copiarse a la principal.
- `backend/sql/dbcode/datos_hu03_hu04.json` y `backend/propuestas/integracion_principal/datos_aprobados.json`: referencias por claves naturales, sin trasladar IDs. Los SQL asociados fueron propuestas para otro estado estructural.
- `backend/aplicacion/base_datos/tipos_cargo_artillero.py` y `tipos_curso_esart.py`: 5 cargos y 14 cursos de referencia; sus ejecutores dependen de la arquitectura Vulcano. Los cursos citan una hoja oficial como origen; no se debe asumir que ese archivo fuente esté incluido en el repositorio.
- `seed_catalogos_academicos.sql`: versión SQL de referencias académicas; requiere tablas preexistentes y revisión del destino.
- `ESART_CARGAR_ESART_DB.sql`: cargador manual utilizado por el operador como parte de la integración BIGINT; contiene DDL, inserciones y una actualización de padres. No es un seed puramente insertivo ni una migración Alembic inicial completa.

El [inventario de scripts](HU04_INVENTARIO_SCRIPTS.md) detalla requisitos, comandos y riesgos. La existencia de un JSON o un SQL generado no demuestra que su contenido se haya aplicado en la principal.

## Fotografías de datos

| Catálogo | Referencia previamente verificada | Reconsulta SQL 2026-11-15 como esart_aplicacion |
|---|---:|---:|
| Unidades militares | 40 | 40 |
| Tipos de unidad | 9 | 9 |
| Tipos de cargo | 5 | 5 |
| Tipos de curso | 14 | 14 |
| Personal militar | 0 | No autorizado SELECT; pendiente de reconsulta por propietario |

La reconsulta también confirmó **39 clasificadas, una pendiente y FUTOM con tipo NULL**. No se insertó ni actualizó nada durante la documentación. Los dos roles y 36 permisos pertenecen a la evidencia histórica de HU-04: no se certifica ese catálogo granular en la principal. Actualmente `esart.permisos` y `esart.roles_permisos` no forman parte de los modelos operativos auditados; la autorización principal usa roles/componentes y excepciones individuales.

## Modelo operativo y dependencias

`UnidadMilitar` → `esart_ref.unidades_militares`: PK id BIGINT con identidad; código varchar(30), nombre varchar(200), tipo_unidad_id BIGINT opcional, unidad_padre_id BIGINT opcional, coordenadas double precision, activo boolean y fechas timestamptz.

`TipoUnidad` → `esart.tipos_unidad`: id BIGINT, código varchar(20), nombre varchar(150), activo boolean. La FK de clasificación conserva NULL para FUTOM. La jerarquía se relaciona con el id real de la misma tabla, no con un UUID público ni un código convertido a identificador.

Referencias entrantes de unidades: personal_militar.unidad_actual_id, artillero_cargos.unidad_id, artillero_disparos.unidad_id, egresados_curso.unidad_destino_id y reentrenamientos.unidad_id, además de su relación autorreferencial. Cambiar una PK afectaría esos vínculos; no se realiza.

Los códigos de unidades se protegen con índice único; padre y tipo tienen índices y FK. No existe un CHECK jerárquico que por sí solo impida ciclos de varios niveles: deben revisarse con las consultas recursivas y la validación de la API. No asumir que código/nombre sean NOT NULL por estar siempre informados en las referencias: contrastar la nulabilidad real del inventario.

Roles, cargos, cursos y entidades académicas conservan las claves y columnas heredadas. Usuarios se relacionan con roles mediante esart.usuario_roles, no mediante un campo rol_id en usuarios. La auditoría de 43 tablas de negocio registra 335 columnas, 436 restricciones —incluido NOT NULL de PostgreSQL 18—, 134 índices, 40 secuencias y ausencia de triggers de usuario/funciones institucionales. Es una fotografía; el historial Alembic suma su propia tabla e índices. Consulte [auditoría](ESART_AUDITORIA_PERSISTENCIA.json), [snapshot congelado](../backend/migraciones_principal/estructura_p0001.json) y [matriz de modelos](ESART_CORRECCION_INTEGRAL.md).

## Validación e idempotencia

Los seeds históricos usan claves naturales y ON CONFLICT DO NOTHING; insertan superiores antes que dependientes y rechazan códigos, relaciones o destinos incompatibles. Esto evita duplicar filas en su esquema histórico; no certifica una carga en la principal. Un intento INSERT omitido puede consumir una secuencia: idempotencia de filas no significa ausencia de avance de secuencia.

La clasificación histórica de fase 4 actualiza solo tipos y permite la fecha automática del trigger existente allí. La segunda ejecución se documentó sin cambios de fechas. La auditoría principal no encontró ese trigger, por lo que no se debe extrapolar su comportamiento a esart_db.

El cargador manual BIGINT omite códigos existentes, pero rellena padres NULL: puede modificar relaciones existentes que carezcan de padre, no concilia todos los nombres/tipos previos y no debe repetirse sin revisión. ON CONFLICT no demuestra equivalencia de referencias. Para cargas futuras se requiere seed operativo independiente, transacción, comparación previa, resolución de IDs por código y reporte de insertados/omitidos/conflictos.

Las pruebas actuales distinguen metadatos reales y contratos históricos. Los tests optativos de escritura permanecen omitidos; no habilitarlos para esta entrega. La consulta SQL real no sustituye la prueba HTTP autenticada ni una verificación visual de Angular.

## Entrega y pendientes

Se entregan modelos conciliados, referencias, validadores, scripts históricos, propuestas y pantalla de consulta. No se entregan como terminados el login, JWT/sesiones, lectura HTTP autenticada, interfaz verificada con sesión, instalación vacía ni despliegue productivo. Véanse [instalación](ESART_INSTALACION_BASE_DATOS.md) y [matriz de seguimiento](ESART_ESTADO_DESARROLLO.md).
