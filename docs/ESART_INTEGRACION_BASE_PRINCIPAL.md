> Actualizacion: el respaldo proporcionado ya fue restaurado y verificado. La prueba aislada de unidades/tipos tambien paso. La ejecucion en la principal sigue pendiente de localizar la conexion administrativa; consultar [ESART_DESPLIEGUE_BASE_PRINCIPAL.md](ESART_DESPLIEGUE_BASE_PRINCIPAL.md).

> Arquitectura de unidades revisada: [ESART_PLAN_DEFINITIVO_INTEGRACION.md](ESART_PLAN_DEFINITIVO_INTEGRACION.md) propone ampliar la tabla can?nica BIGINT, sin duplicarla en public. La alternativa de instalaci?n paralela de unidades de este documento queda sustituida, no ejecutada.

> Comprobaci?n actualizada de ambas bases: [ESART_UNIDADES_PLAN_INTEGRACION.md](ESART_UNIDADES_PLAN_INTEGRACION.md). Las 40 unidades siguen en pruebas; la principal solo tiene el stub BIGINT, y el respaldo contin?a bloqueado por permisos. Se prepar? un paquete de datos sin UUID, sin ejecutar inserciones.

# ESART — Diagnóstico y plan de integración de la base principal

**Alcance ejecutado: únicamente fases 1 y 2. No se autoriza iniciar la integración.**

El inventario estructural está completo para los objetos visibles en los catálogos
de PostgreSQL. La inspección de datos y la obtención de un respaldo completo están
**bloqueadas por privilegios**. No existe todavía un respaldo válido cuya recuperación
se haya probado. No se modificaron la base principal, las bases de pruebas ni la
configuración operativa.

## 1. Identidad y estado inicial confirmado

| Comprobación | Resultado |
|---|---|
| Base conectada | `esart_db` |
| PostgreSQL | 18.7 |
| Cuenta utilizada | `esart_aplicacion`, sin cambiar credenciales |
| Propietario de la base | `esart_aplicacion` |
| Esquemas de aplicación | `esart`, `esart_ref`, `public` |
| Propietarios de `esart` y `esart_ref` | `postgres` |
| Tablas | **42**: 38 en `esart`, 4 en `esart_ref`; ninguna en `public` |
| Columnas | 322 |
| Claves primarias | 42 |
| Claves foráneas | 75 |
| Restricciones UNIQUE | 16 |
| Restricciones CHECK | 34 |
| Restricciones NOT NULL en catálogo PostgreSQL 18 | 258 |
| Índices | 129; ninguno marcado inválido |
| Secuencias | 39 |
| Vista de aplicación | `esart.v_permisos_efectivos` |
| Triggers de usuario y funciones de usuario | Ninguno encontrado en estos esquemas |
| Extensiones | `plpgsql` 1.0 |
| `alembic_version` | No existe en ninguno de los esquemas inventariados |
| Revisión Alembic de la base | **Sin historial registrado**; no es `0001` ni `0002` |

Las consultas del diagnóstico se ejecutaron en transacciones `REPEATABLE READ,
READ ONLY`, verificando `current_database()` y `transaction_read_only`. No se
leyeron ni mostraron valores de contraseñas, hashes de usuarios o claves JWT.
El archivo `.env` no fue modificado ni impreso.

El inventario completo de tablas, columnas, tipos, defaults, restricciones, índices,
secuencias, relaciones, propietarios y permisos está en
[ESART_INTEGRACION_INVENTARIO.json](ESART_INTEGRACION_INVENTARIO.json).

## 2. Límite de acceso: no asumir ausencia de datos

La cuenta es propietaria de la **base**, pero no de las tablas existentes. Carece de
`USAGE` sobre `esart` y `esart_ref`, y `has_table_privilege(..., 'SELECT')` es falso
para las 42 tablas. Sí tiene `USAGE` y `CREATE` en `public`; eso no le permite leer
las tablas de los otros esquemas.

La consulta inicial a `esart.alertas_academicas` fue rechazada con SQLSTATE `42501`.
Después se comprobó la falta de permisos sin seguir intentando leer cada tabla.

Por tanto:

- Los conteos exactos de filas son **desconocidos**, no cero.
- No se pudo confirmar qué datos académicos, usuarios, roles o material existen.
- Los duplicados por código, nombre normalizado, documento o usuario están pendientes
  de comprobación. Tener índices UNIQUE no descarta equivalencias semánticas o
  diferencias de mayúsculas, espacios o acentos.
- Las 75 FK aparecen validadas en el catálogo, pero la consulta independiente de
  huérfanos está bloqueada. No se afirma que su resultado sea cero.
- Se identificaron las secuencias, pero no se certifica su posición ni su correspondencia
  con máximos de PK. No se invocó `nextval` ni se modificaron secuencias.
- Toda información existente debe conservarse hasta completar la inspección con
  una cuenta que pueda leerla. Las 40 unidades y los catálogos de las bases de
  pruebas no se consideran automáticamente presentes en la principal.

No se concedieron privilegios, cambiaron propietarios ni utilizaron credenciales
administrativas para sortear este límite.

## 3. Comparación con HU-03 y HU-04

### 3.1 Diferencia de arquitectura

El contrato aprobado tiene **23 tablas en `public`**: 22 de `0001` y `tipos_unidad`
de `0002`. Ninguna de esas 23 tablas existe actualmente en `public`.
Hay 14 nombres homónimos en los esquemas heredados y nueve nombres sin equivalente
en toda la base. Compartir nombre no significa compartir estructura ni semántica.

Las entidades heredadas utilizan PK `BIGINT` y, en general, identidades/secuencias.
Los modelos aprobados usan UUID para entidades de negocio y seguridad, excepto las
identidades BIGINT específicas de intentos y auditoría. Las PK compuestas de las
mallas también cambian sus FK de BIGINT a UUID.

No es válido convertir BIGINT a UUID mediante cast ni copiar los UUID de pruebas.
Se requieren correspondencias verificadas por claves naturales y, para datos
heredados sin clave suficiente, una decisión institucional documentada.

### 3.2 Incompatibilidades que requieren tratamiento explícito

| Área | Estructura existente | Contrato HU-03/HU-04 | Decisión necesaria |
|---|---|---|---|
| Unidades | `esart_ref.unidades_militares` es un stub: únicamente `id BIGINT` | Código único, nombre, superior autorreferente, tipo opcional y fechas, con UUID | No permite vincular por código las unidades heredadas con las 40 aprobadas. No inferir equivalencias por posición o ID. |
| Personal | `documento_identidad`, `nombres`, `apellidos`, `unidad_actual_id`, `activo`; BIGINT | Documento restringido, nombres/apellidos separados, estado de servicio y FK UUID | No dividir nombres automáticamente ni convertir `activo` en un estado de servicio sin regla aprobada. |
| Roles | `esart.roles` tiene BIGINT y CHECK ADMINISTRADOR/USUARIO | `public.roles` con UUID, mismo conjunto de códigos y fechas distintas | Códigos pueden corresponder; IDs, filas y asignaciones no están verificados. |
| Usuarios | `esart_ref.usuarios`, campos de autenticación y relación `esart.usuario_roles` | `usuarios.rol_id`, sesiones, intentos y permisos por código | La relación multirrol heredada no equivale al rol único del contrato. No seleccionar un rol ni elevar permisos automáticamente. |
| Cargos | `esart.tipos_cargo`: nombre único, sin código, con `cuenta_para_coofu` | Código único obligatorio, descripción y fechas | Aprobar códigos estables para los cinco cargos. No perder el indicador heredado ni inventar su equivalencia con requisitos. |
| Cursos | Código de hasta 20 caracteres, `tipo`, `modalidad`, `duracion_semanas` | Código de hasta 30, descripción, `tipo_sistema`, `vigencia_meses`, nota mínima | No mapear duración en semanas a vigencia en meses, ni categoría educativa a tipo de sistema. Conservar atributos heredados sin sobrescribirlos. |
| Cursos de artillero | `hoja_vida_id`, curso con nombre, horas, aprobado | `hoja_vida_artillero_id`, estado, nota, cohorte e importación | Exige mapeo de columnas y reglas de validación; no basta renombrar una FK. |
| Certificaciones | Nombre y datos de emisión por certificación | Catálogo `tipos_certificacion` y FK desde certificaciones | Definir equivalencias y vigencias antes de importar filas. |
| Permisos | Mallas por componente y vista de permisos efectivos | Conserva mallas, añade catálogo de códigos y controles adicionales | No conceder permisos por cargar códigos ni trasladar IDs de mallas. |
| Sistemas | `esart_ref.sistemas_artilleria` es un stub BIGINT | Catálogo UUID para requisitos y habilitación | No confundirlo con inventario operativo de piezas. |
| Fechas y auditoría | Nombres como `creado_en`/`actualizado_en`, sin triggers de usuario encontrados | Fechas contractuales y triggers aprobados; auditoría inmutable | Verificar funciones, triggers e índices al construir el esquema nuevo. |

Los nueve nombres sin equivalente son: `tipos_unidad`, `permisos`, `roles_permisos`,
`intentos_inicio_sesion`, `sesiones_usuario`, `importaciones_excel`, `auditoria_eventos`,
`tipos_certificacion` y `requisitos_habilitacion`.

### 3.3 Por qué no ejecutar `alembic upgrade head`

- `0001` rechaza cualquier base con tablas de aplicación en otros esquemas. Las
  42 tablas existentes activan esa protección aunque `public` esté vacío.
- `0002` admite exclusivamente los dos nombres de bases de pruebas autorizados
  anteriormente. Rechaza `esart_db` antes de crear su tabla o columna.
- Las herramientas de seeds y clasificación también están fijadas a las bases
  de pruebas y a UUID concretos de sus snapshots.
- No hay una revisión existente que se pueda actualizar; escribir `0002` en
  `alembic_version` no crearía las tablas ni resolvería las incompatibilidades.

No se ejecutaron migraciones ni `stamp`. Los archivos `0001` y `0002` permanecen
intactos. Este diagnóstico no autoriza cambiar guardas o simular un historial.

## 4. Respaldo: intentos, resultado y procedimiento pendiente

Se localizaron los clientes PostgreSQL 18 y se intentó un `pg_dump` completo en
formato custom, incluyendo definición de base, propietarios y ACL. Se utilizó un
snapshot exportado de la misma transacción de diagnóstico y conexiones de solo
lectura. Las credenciales se pasaron exclusivamente al entorno temporal del proceso,
no a sus argumentos ni a archivos de código.

El respaldo completo fue rechazado por permisos; el intento de respaldo únicamente
estructural también fue rechazado. **Ambos archivos tienen cero bytes y son
inutilizables. No se listaron, restauraron ni declararon válidos.**

Ubicación local excluida de Git: `backend/respaldos/integracion_esart_db_20261115/`.
Esta carpeta contiene el inventario y los intentos fallidos; no contiene un respaldo
recuperable. No debe emplearse ninguno de esos `.dump` para recuperación.

Se preparó [respaldar_base_principal.ps1](../backend/herramientas/respaldar_base_principal.ps1)
para ejecución manual por una cuenta administrativa/de respaldo que pueda leer
los objetos. El script verifica `esart_db`, impone conexiones de solo lectura,
solicita la contraseña interactivamente sin guardarla, usa un directorio nuevo,
genera `pg_dump --format=custom --create`, comprueba el listado del archivo,
decodifica todo su contenido a SQL y calcula SHA-256. **No fue ejecutado con otra
cuenta ni modifica permisos o la configuración del backend.**

Para considerar el respaldo recuperable faltan, en este orden:

1. Obtener un dump completo sin errores con una cuenta autorizada. Incluir todos
   los esquemas, datos, secuencias, funciones, vistas, extensiones y ACL, sin filtros.
   Registrar versión del cliente/servidor, fecha, tamaño y SHA-256.
2. Confirmar el archivo con `pg_restore --list` y su decodificación completa. El
   simple listado no prueba recuperación.
3. Restaurarlo con `pg_restore --exit-on-error` en una **instancia nueva e independiente**,
   nunca en `esart_db` ni en las dos bases de pruebas existentes. El destino y su
   preparación requieren autorización específica; no se creó ninguno en esta fase.
4. Verificar allí conteos, claves, FK, CHECK, secuencias, vistas y las 42 tablas.
   Documentar propietarios y permisos. Si se utiliza una restauración sin propietarios
   o ACL para validación técnica, no certificar por ello la recuperación de permisos.
5. Conservar de forma protegida el respaldo y el resultado de la recuperación.
   `pg_dump` es un respaldo lógico de una base; los roles globales y sus credenciales
   no forman parte de ese archivo. El DBA debe documentar los roles necesarios sin
   introducir contraseñas en el repositorio.

El contenido del respaldo puede contener datos personales y hashes. El archivo y
el SQL decodificado deben permanecer fuera de Git; las reglas existentes ya excluyen
`respaldos/` y los archivos `.dump`.

## 5. Plan de integración propuesto, pendiente de aprobación

### Puerta A — Completar el diagnóstico de datos y recuperación

Resolver primero la lectura mediante una cuenta administrativa autorizada, sin
dar por hecho que deben ampliarse privilegios de la cuenta operativa. Confirmar
conteos y huellas de las 42 tablas, catálogo de cargos/cursos, posibles usuarios,
roles, documentos, duplicados exactos y normalizados y consultas independientes
de huérfanos. Verificar secuencias frente a las PK. Completar el respaldo y su
prueba real de recuperación. Si aparece una correspondencia ambigua, detenerla
y documentarla antes de proponer cambios.

### Puerta B — Aprobar arquitectura y tratamiento del historial

Se propone una integración **aditiva**: conservar `esart` y `esart_ref` intactos y
crear el contrato UUID aprobado en `public`, que actualmente no tiene tablas.
La separación evita colisiones físicas, pero no elimina las equivalencias de
negocio: debe aprobarse quién será dueño de cada catálogo y cómo se relacionarán
los datos heredados. No se debe añadir `esart` al `search_path` para que los modelos
UUID resuelvan accidentalmente a tablas BIGINT.

Esta propuesta **no convierte automáticamente** las 42 tablas ni desplaza sus FK.
Si se pretende unificar también sus datos y eliminar duplicidad lógica, hace falta
un proyecto de homologación por entidad y un mapa BIGINT/UUID, sin pérdida de datos.
No se efectuarán eliminaciones o conversiones implícitas.

Como las revisiones históricas rechazan el destino, se necesita una decisión
explícita sobre el procedimiento de instalación. La ruta recomendada para mantener
los archivos históricos intactos es:

1. Preparar un instalador de integración específico, revisable y acotado a los
   objetos nuevos de `public`, derivado del DDL congelado de `0001` y `0002`.
   No monkeypatch de guardas ni ejecución automática de SQL heredado.
2. Probarlo primero sobre una restauración independiente del respaldo, preservando
   las tablas heredadas y sus huellas. Esa restauración no es ninguna base existente.
3. Comprobar igualdad física completa con el contrato `0001` y, después, `0002`:
   columnas, tipos, PK, FK, índices funcionales, CHECK, defaults, identidades,
   funciones, triggers y permisos de auditoría. Los modelos por sí solos no
   describen todos los objetos de la migración.
4. Solo tras esa equivalencia, aprobar y registrar una **adopción de baseline**
   en Alembic, con evidencia y trazabilidad del instalador. Si se usa `stamp`,
   documentar que registra una adopción verificada, no una ejecución histórica
   inexistente. Nunca usarlo antes de construir y verificar el esquema.

Esto requiere aprobación expresa de la instalación aditiva y de la adopción de
baseline. No se presenta como un `upgrade` directo. Si se exige ejecutar las
revisiones originales literalmente en `esart_db`, deberá aprobarse otra estrategia
para sus guardas y su historial antes de implementarla. No se modifican en esta fase.

El futuro instalador debe verificar identidad y ausencia de todos sus objetos de
destino, rechazar conflictos y confirmar su DDL en transacción. Ninguna operación
debe eliminar tablas, esquemas o filas existentes ni usar limpieza destructiva.

### Puerta C — Seeds adaptados, sin copiar identificadores

Reutilizar los datos aprobados como **referencia**, sin conectarse a las bases de
pruebas para modificarlas ni reutilizar sus UUID:

- Roles: 2 códigos, respetando el CHECK y contrastando los registros heredados.
- Permisos: 36 códigos, sin conceder acceso por el mero hecho de insertarlos.
- Tipos de unidad: 9 códigos, UUID generados en `esart_db`.
- Unidades: resolver por código validado; insertar superiores antes que dependientes.
  Generar UUID nuevos solo para códigos ausentes en el destino contractual. Si un
  código existente tiene otro nombre o superior, detenerse: no sobrescribirlo.
- Clasificación: resolver los UUID principales por código y asignar las 39
  correspondencias de la matriz; FUTOM debe permanecer NULL. No reutilizar el script
  de fase 4 con sus UUID y snapshot de pruebas. Su excepción de fecha requerirá
  aprobación para la base principal y seguirá usando el trigger, sin fechas manuales.
- Cargos: hay cinco referencias académicas en el repositorio; el modelo exige códigos
  que el catálogo heredado no tiene. Debe aprobarse una matriz nombre/código antes
  de preparar inserciones. No inventarlos en un seed ni importar flags como requisitos.
- Cursos: existen 14 referencias en el repositorio. Conservar sus códigos y nombres;
  acordar la conservación de modalidad/tipo/duración, que no tienen columnas
  equivalentes en el modelo UUID. No convertir esos atributos a conceptos distintos.

No se confirma que los cinco cargos o catorce cursos estén actualmente cargados:
su consulta está bloqueada. No se ejecutarán los scripts heredados, algunos de
los cuales importan modelos de otro proyecto o incluyen conexiones de ejemplo.
Tampoco se crearán administradores con contraseña predeterminada ni se trasladarán
usuarios, hashes o roles sin una correspondencia aprobada.

Cada seed nuevo debe tener preflight específico para `esart_db`, parámetros ligados,
claves naturales verificadas, inserción idempotente y conteos confirmados después
del commit. En una segunda ejecución no debe insertar, reclasificar ni disparar
triggers de fecha para filas ya correctas. No cargar estados de material de VULCANO.

### Puerta D — Validación y activación posteriores

Antes de cambiar la conexión operativa, validar la instalación y los seeds sobre
la restauración independiente y presentar los resultados. Después de una nueva
autorización, aplicarlos a la principal con respaldo vigente y repetir las
verificaciones de integridad, preservación e idempotencia.

El plan de recuperación conserva los esquemas heredados sin alterarlos. Ante un
fallo de instalación transaccional, hacer rollback de esa transacción. Después de
confirmar cambios, detener la activación y preparar una recuperación aprobada en
destino independiente; no ejecutar un downgrade o una limpieza destructiva de la
principal como supuesto mecanismo automático de reversión.

## 6. Diagnóstico de conexión, API y Angular — sin implementación

### FastAPI

- La URL seleccionada explícitamente desde `backend/.env` nombra `esart_db`.
  Eso no implica que el proceso operativo pueda arrancar o consultar sus datos.
- `aplicacion.configuracion.Configuracion` y la configuración de conexión buscan
  por defecto `.env` en la raíz del repositorio. Ese archivo no existe; el de
  `backend` sí existe. La carga por defecto falla por variables requeridas ausentes.
- Al seleccionar expresamente `backend/.env`, la configuración completa rechaza
  una clave JWT que conserva un marcador de ejemplo. No se mostró ni cambió su valor.
  La validación se detiene allí; no se certifican como válidos los secretos posteriores.
- Los modelos no fijan esquema. El `search_path` actual resuelve a `public`, donde
  faltan las 23 tablas. Cambiar solo la URL o el `search_path` no resuelve la estructura.
- La aplicación registra solamente `/api/salud`. No están implementados los endpoints
  de unidades o catálogos. Un `SELECT 1` satisfactorio no certifica su integración.
- Existe la infraestructura de permisos por componente. Los futuros endpoints deben
  reutilizarla y exigir identidad autenticada; no convertir el catálogo en un acceso
  público para evitar la configuración de autenticación.
- Las pruebas actuales usan configuración aislada y dependencias sustituidas. Deben
  seguir separadas de la principal. Los endpoints reales no se probarán haciendo
  escrituras de prueba sobre ella.

Después de autorización: unificar de forma explícita la selección de configuración,
provisionar secretos válidos fuera del código, conservar la conexión principal y
separar la de pruebas; implementar las rutas contractuales y las pruebas de permisos.
No se modificó ninguno de esos componentes en este diagnóstico.

### Angular

La aplicación conserva la estructura inicial: rutas vacías, sin servicio de unidades,
sin proveedor `HttpClient` y sin proxy de API configurado. No hay un consumo actual
de `/api/catalogos/unidades` que se pueda redirigir o dar por validado.

En las fases posteriores se propone conservar la arquitectura standalone e incorporar:

- Un servicio que consuma rutas relativas `/api`, sin conexión directa a PostgreSQL.
- Un DTO de unidad con código, nombre, tipo opcional y superior, y un contrato
  aprobado para filtros por código, nombre y tipo. Si cambia el contrato API,
  someter la ampliación a revisión.
- Listado y jerarquía con los 40 códigos esperados; FUTOM debe mostrarse como
  pendiente de clasificación. Si hubiera otras unidades legítimas existentes,
  conservarlas y distinguir ese conjunto, sin borrarlas para forzar un total de 40.
- Estados de carga/error/vacío y controles de acceso existentes. Definir el proxy de
  desarrollo o despliegue bajo un mismo origen; no resolverlo con credenciales en Angular.

No se editaron servicios, componentes, rutas, estilos ni configuración Angular.

## 7. Riesgos y decisiones antes de autorizar cambios

| Prioridad | Hallazgo | Condición para continuar |
|---|---|---|
| Bloqueante | No hay lectura de las 42 tablas ni respaldo válido | Respaldo administrativo completo, restauración independiente e inspección de datos |
| Bloqueante | Sin Alembic; 23 tablas contractuales ausentes en `public` | Aprobar instalación y registro de baseline verificable; no marcar `head` sin DDL |
| Bloqueante | Guardas de `0001` y `0002` impiden un upgrade directo | Aprobar procedimiento específico sin alterar el historial de forma implícita |
| Alta | 14 homónimos BIGINT, usuarios multirrol y stubs sin códigos | Matrices de correspondencia y límites entre contextos; no cast ni copia de IDs |
| Alta | Datos/duplicados no verificables y campos académicos sin equivalencia | Inspección con permisos y decisiones de mapeo documentadas |
| Alta | Selección de `.env` incompatible y marcador JWT de ejemplo | Configuración y secretos válidos, solo en la fase autorizada |
| Alta | No existen endpoints ni servicios Angular de unidades | Implementación y pruebas en fases 4/5, sin saltar autenticación |

Se solicita resolver primero el respaldo y la inspección de datos; no basta una
aprobación general de migración mientras esos puntos sigan pendientes.

## 8. Validaciones realizadas en el repositorio

- Python 3.12 y `pip check`: dependencias consistentes.
- Suite backend: **96 pruebas aprobadas, 2 integraciones omitidas por defecto**.
  No ejecutó pruebas con escrituras contra la principal ni las bases existentes.
- Ruff de las nuevas herramientas Python y sus pruebas: sin errores.
- Ruff global: **50 incidencias previas** (46 E501 y 4 I001): 43 en `initial_data.py`,
  6 en `tipos_cargo_artillero.py` y 1 en `generar_hash.py`. No se corrigieron archivos
  ajenos al diagnóstico para aparentar un estado global limpio.
- No se ejecutaron build o pruebas de integración Angular: pertenecen a fases posteriores.

Herramientas preparadas:
[diagnosticar_integracion.py](../backend/herramientas/diagnosticar_integracion.py),
[respaldar_base_principal.ps1](../backend/herramientas/respaldar_base_principal.ps1) y
[pruebas del diagnóstico](../backend/pruebas/test_diagnostico_integracion.py).

**No se ejecutaron las fases 3–6 ni se cambió la conexión operativa.** Las bases
`esart_hu03_pruebas` y `esart_hu04_fase3_temporal` no se consultaron ni modificaron
durante este procedimiento. Se detiene la integración hasta completar los requisitos
pendientes y obtener autorización expresa sobre el plan concreto.

## Anexo A. Inventario de las 42 tablas existentes

Todas son propiedad de postgres. Las filas figuran como no verificadas porque la
cuenta disponible no tiene lectura; no se sustituye ese dato por una estimacion.

| Tabla | Columnas | PK | FK | UNIQUE | CHECK | Indices | Filas |
|---|---:|---|---:|---:|---:|---:|---|
| esart.alertas_academicas | 9 | (id) | 3 | 0 | 0 | 4 | No verificadas |
| esart.alertas_certificacion | 8 | (id) | 3 | 0 | 1 | 4 | No verificadas |
| esart.alumnos_activos | 8 | (id) | 3 | 0 | 1 | 5 | No verificadas |
| esart.artillero_cargos | 8 | (id) | 3 | 0 | 1 | 3 | No verificadas |
| esart.artillero_certificaciones | 10 | (id) | 1 | 0 | 2 | 4 | No verificadas |
| esart.artillero_cursos | 10 | (id) | 2 | 0 | 2 | 3 | No verificadas |
| esart.artillero_disparos | 10 | (id) | 3 | 0 | 1 | 3 | No verificadas |
| esart.certificados_reentrenamiento | 15 | (id) | 3 | 2 | 0 | 5 | No verificadas |
| esart.comite_movil_instructores | 6 | (id) | 2 | 0 | 0 | 4 | No verificadas |
| esart.comites_moviles | 7 | (id) | 1 | 1 | 0 | 2 | No verificadas |
| esart.componentes | 9 | (id) | 1 | 1 | 0 | 3 | No verificadas |
| esart.consejos_academicos | 9 | (id) | 3 | 0 | 0 | 3 | No verificadas |
| esart.cursos | 12 | (id) | 4 | 1 | 2 | 2 | No verificadas |
| esart.cursos_instructores | 4 | (id) | 2 | 0 | 0 | 2 | No verificadas |
| esart.diplomas | 7 | (id) | 3 | 2 | 0 | 4 | No verificadas |
| esart.doctrina_documentos | 10 | (id) | 1 | 0 | 0 | 3 | No verificadas |
| esart.egresados_curso | 19 | (id) | 5 | 0 | 4 | 5 | No verificadas |
| esart.especialidades_instructor | 3 | (id) | 0 | 1 | 0 | 2 | No verificadas |
| esart.habilitaciones | 9 | (id) | 3 | 0 | 3 | 4 | No verificadas |
| esart.hoja_vida_artillero | 5 | (id) | 1 | 1 | 0 | 2 | No verificadas |
| esart.inscripciones_curso | 8 | (id) | 2 | 0 | 2 | 5 | No verificadas |
| esart.instructores | 5 | (id) | 1 | 1 | 0 | 2 | No verificadas |
| esart.instructores_especialidades | 5 | (id) | 2 | 0 | 0 | 2 | No verificadas |
| esart.malla_curricular | 6 | (id) | 2 | 0 | 1 | 2 | No verificadas |
| esart.materias | 5 | (id) | 0 | 1 | 0 | 2 | No verificadas |
| esart.notas_finales_egresado | 6 | (id) | 2 | 0 | 2 | 4 | No verificadas |
| esart.notas_materia | 8 | (id) | 2 | 0 | 2 | 4 | No verificadas |
| esart.operadores_sistema | 8 | (id) | 3 | 0 | 0 | 5 | No verificadas |
| esart.participantes_reentrenamiento | 6 | (id) | 2 | 0 | 1 | 5 | No verificadas |
| esart.personal_militar | 12 | (id) | 1 | 1 | 0 | 4 | No verificadas |
| esart.reentrenamientos | 16 | (id) | 3 | 1 | 2 | 6 | No verificadas |
| esart.rol_permisos | 8 | (rol_id, componente_id) | 2 | 0 | 1 | 2 | No verificadas |
| esart.roles | 6 | (id) | 0 | 1 | 1 | 2 | No verificadas |
| esart.semestres_academicos | 7 | (id) | 0 | 0 | 2 | 2 | No verificadas |
| esart.tipos_cargo | 6 | (id) | 0 | 1 | 0 | 2 | No verificadas |
| esart.tipos_curso | 7 | (id) | 0 | 1 | 1 | 3 | No verificadas |
| esart.usuario_permisos | 9 | (usuario_id, componente_id) | 3 | 0 | 1 | 2 | No verificadas |
| esart.usuario_roles | 4 | (usuario_id, rol_id) | 3 | 0 | 0 | 2 | No verificadas |
| esart_ref.sistemas_artilleria | 1 | (id) | 0 | 0 | 0 | 1 | No verificadas |
| esart_ref.sistemas_en_operacion | 1 | (id) | 0 | 0 | 0 | 1 | No verificadas |
| esart_ref.unidades_militares | 1 | (id) | 0 | 0 | 0 | 1 | No verificadas |
| esart_ref.usuarios | 9 | (id) | 0 | 0 | 1 | 3 | No verificadas |

## Anexo B. Diferencias de columnas en los 23 destinos contractuales

Las 23 tablas esperadas estan ausentes en public. La siguiente tabla compara sus
columnas con las tablas homonimas de otros esquemas; esas tablas no son destinos
intercambiables. Los tipos, defaults, nullabilidad y FK completos estan en el JSON.

| Destino esperado | Homonimo existente | PK del homonimo | Columnas contractuales ausentes en el homonimo | Columnas heredadas adicionales |
|---|---|---|---|---|
| public.tipos_unidad | Ninguno | ? | Tabla completa pendiente | ? |
| public.unidades_militares | esart_ref.unidades_militares | PRIMARY KEY (id); id bigint | activa, codigo, fecha_actualizacion, fecha_creacion, nombre, sigla, tipo_unidad_id, unidad_superior_id | Ninguna por nombre |
| public.personal_militar | esart.personal_militar | PRIMARY KEY (id); id bigint | arma, estado_servicio, fecha_actualizacion, fecha_creacion, numero_documento, primer_apellido, primer_nombre, segundo_apellido, segundo_nombre, unidad_militar_id | activo, actualizado_en, apellidos, creado_en, documento_identidad, especialidad_actual, genero, nombres, unidad_actual_id |
| public.hoja_vida_artillero | esart.hoja_vida_artillero | PRIMARY KEY (id); id bigint | especialidad, fecha_actualizacion, fecha_creacion, fecha_ingreso_arma, personal_militar_id | actualizado_en, artillero_id, creado_en |
| public.roles | esart.roles | PRIMARY KEY (id); id bigint | fecha_actualizacion, fecha_creacion | creado_en, descripcion |
| public.permisos | Ninguno | ? | Tabla completa pendiente | ? |
| public.roles_permisos | Ninguno | ? | Tabla completa pendiente | ? |
| public.usuarios | esart_ref.usuarios | PRIMARY KEY (id); id bigint | bloqueado_hasta, fecha_actualizacion, fecha_creacion, fecha_ultimo_acceso, hash_contrasena, intentos_fallidos_consecutivos, nombre_completo, nombre_usuario, rol_id | actualizado_en, contrasena_hash, creado_en, documento_identidad, requiere_cambio_contrasena, ultimo_acceso_en, usuario |
| public.intentos_inicio_sesion | Ninguno | ? | Tabla completa pendiente | ? |
| public.sesiones_usuario | Ninguno | ? | Tabla completa pendiente | ? |
| public.importaciones_excel | Ninguno | ? | Tabla completa pendiente | ? |
| public.auditoria_eventos | Ninguno | ? | Tabla completa pendiente | ? |
| public.tipos_curso | esart.tipos_curso | PRIMARY KEY (id); id bigint | descripcion, fecha_actualizacion, fecha_creacion, nota_minima_aprobacion, tipo_sistema, vigencia_meses | duracion_semanas, modalidad, tipo |
| public.artillero_cursos | esart.artillero_cursos | PRIMARY KEY (id); id bigint | estado, fecha_actualizacion, fecha_creacion, hoja_vida_artillero_id, importacion_excel_id, nota_final, numero_acta, numero_cohorte | aprobado, creado_en, hoja_vida_id, horas, nombre |
| public.tipos_certificacion | Ninguno | ? | Tabla completa pendiente | ? |
| public.artillero_certificaciones | esart.artillero_certificaciones | PRIMARY KEY (id); id bigint | estado, fecha_actualizacion, fecha_creacion, fecha_expedicion, hoja_vida_artillero_id, importacion_excel_id, numero_certificado, tipo_certificacion_id | activo, archivo_url, creado_en, entidad, fecha_baja, fecha_emision, hoja_vida_id, nombre |
| public.sistemas_artilleria | esart_ref.sistemas_artilleria | PRIMARY KEY (id); id bigint | activo, calibre_milimetros, codigo, fecha_actualizacion, fecha_creacion, nombre, tipo_sistema, verificacion_habilitada | Ninguna por nombre |
| public.requisitos_habilitacion | Ninguno | ? | Tabla completa pendiente | ? |
| public.tipos_cargo | esart.tipos_cargo | PRIMARY KEY (id); id bigint | codigo, fecha_actualizacion, fecha_creacion | creado_en, cuenta_para_coofu |
| public.artillero_cargos | esart.artillero_cargos | PRIMARY KEY (id); id bigint | fecha_actualizacion, fecha_creacion, hoja_vida_artillero_id, numero_resolucion, observaciones, unidad_militar_id | creado_en, descripcion, hoja_vida_id, unidad_id |
| public.componentes | esart.componentes | PRIMARY KEY (id); id bigint | fecha_actualizacion, fecha_creacion | creado_en |
| public.rol_permisos | esart.rol_permisos | PRIMARY KEY (rol_id, componente_id);  | fecha_actualizacion, fecha_creacion | actualizado_en |
| public.usuario_permisos | esart.usuario_permisos | PRIMARY KEY (usuario_id, componente_id);  | fecha_actualizacion, fecha_creacion | actualizado_en |

## Anexo C. Secuencias existentes

| Esquema | Secuencia | Tipo | Incremento | Ciclica |
|---|---|---|---:|---|
| esart | alertas_academicas_id_seq | bigint | 1 | No |
| esart | alertas_certificacion_id_seq | bigint | 1 | No |
| esart | alumnos_activos_id_seq | bigint | 1 | No |
| esart | artillero_cargos_id_seq | bigint | 1 | No |
| esart | artillero_certificaciones_id_seq | bigint | 1 | No |
| esart | artillero_cursos_id_seq | bigint | 1 | No |
| esart | artillero_disparos_id_seq | bigint | 1 | No |
| esart | certificados_reentrenamiento_id_seq | bigint | 1 | No |
| esart | comite_movil_instructores_id_seq | bigint | 1 | No |
| esart | comites_moviles_id_seq | bigint | 1 | No |
| esart | componentes_id_seq | bigint | 1 | No |
| esart | consejos_academicos_id_seq | bigint | 1 | No |
| esart | cursos_id_seq | bigint | 1 | No |
| esart | cursos_instructores_id_seq | bigint | 1 | No |
| esart | diplomas_id_seq | bigint | 1 | No |
| esart | doctrina_documentos_id_seq | bigint | 1 | No |
| esart | egresados_curso_id_seq | bigint | 1 | No |
| esart | especialidades_instructor_id_seq | bigint | 1 | No |
| esart | habilitaciones_id_seq | bigint | 1 | No |
| esart | hoja_vida_artillero_id_seq | bigint | 1 | No |
| esart | inscripciones_curso_id_seq | bigint | 1 | No |
| esart | instructores_especialidades_id_seq | bigint | 1 | No |
| esart | instructores_id_seq | bigint | 1 | No |
| esart | malla_curricular_id_seq | bigint | 1 | No |
| esart | materias_id_seq | bigint | 1 | No |
| esart | notas_finales_egresado_id_seq | bigint | 1 | No |
| esart | notas_materia_id_seq | bigint | 1 | No |
| esart | operadores_sistema_id_seq | bigint | 1 | No |
| esart | participantes_reentrenamiento_id_seq | bigint | 1 | No |
| esart | personal_militar_id_seq | bigint | 1 | No |
| esart | reentrenamientos_id_seq | bigint | 1 | No |
| esart | roles_id_seq | bigint | 1 | No |
| esart | semestres_academicos_id_seq | bigint | 1 | No |
| esart | tipos_cargo_id_seq | bigint | 1 | No |
| esart | tipos_curso_id_seq | bigint | 1 | No |
| esart_ref | sistemas_artilleria_id_seq | bigint | 1 | No |
| esart_ref | sistemas_en_operacion_id_seq | bigint | 1 | No |
| esart_ref | unidades_militares_id_seq | bigint | 1 | No |
| esart_ref | usuarios_id_seq | bigint | 1 | No |

Los valores efectivos deben cotejarse con los datos en la inspeccion administrativa.
No se avanzo ni reajusto ninguna secuencia.
