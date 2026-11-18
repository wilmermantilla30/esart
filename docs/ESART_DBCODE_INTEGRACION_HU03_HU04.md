# Integración HU-03/HU-04 desde DBCode

> **Paquete histórico superado por la estructura BIGINT cargada posteriormente. No ejecutar estos scripts en la principal actual.** Consultar [ESART_CORRECCION_INTEGRAL.md](ESART_CORRECCION_INTEGRAL.md) y la auditoría actual de persistencia.

Estado: SQL preparado para revisión y ejecución manual. **Este paquete no se ha ejecutado en PostgreSQL. No se declara desplegada la integración.**

## Archivos que se ejecutan

1. `backend/sql/dbcode/01_integrar_esart_db.sql`: integración transaccional y seeds.
2. `backend/sql/dbcode/02_verificar_esart_db.sql`: comprobaciones de solo lectura.

Son SQL PostgreSQL completos, sin comandos de psql ni credenciales. No ejecutar por separado las plantillas ni `_ddl_generado.sql`. Los JSON, el generador y la evidencia de análisis estático son material de revisión; no requieren conexión.

## Ejecución precisa en DBCode

1. Seleccionar la conexión administrativa ya disponible: base **esart_db**, usuario **postgres**, PostgreSQL 18. No cambiar la conexión permanente de FastAPI. El respaldo `D:\2026\esart\respaldos\esart_db_pre_hu04.backup` ya tiene restauración validada; conservarlo. Su evidencia está en `docs/ESART_RESPALDO_VERIFICACION.json`.
2. Guardar trabajo pendiente y cerrar cualquier transacción anterior de esta sesión. Ejecutar durante una ventana sin escrituras de la aplicación: el instalador bloquea escrituras sobre las tablas institucionales; las lecturas ordinarias continúan. Un conflicto de bloqueo aborta a los diez segundos.
3. Abrir el archivo **01** y ejecutar **todo el archivo**, en una misma sesión. Usar la opción de ejecutar script completo de DBCode, con autocommit habilitado para la sesión: el archivo administra su propio `BEGIN`/`COMMIT`. No seleccionar fragmentos ni ejecutar cada sentencia en conexiones diferentes. La identidad y la estructura se comprueban dentro de la transacción antes del DDL.
4. Ante cualquier `ERROR`, detenerse y ejecutar `ROLLBACK;` en esa sesión. No omitir validaciones, corregir datos a ciegas ni registrar manualmente el historial. La respuesta final debe ser **COMMIT**, no ROLLBACK. Los NOTICE y conteos anteriores a COMMIT son provisionales.
5. Tras COMMIT, ejecutar **02 completo**. Guardar los resultados: catálogos, 40 unidades, 39 clasificadas, FUTOM pendiente, árbol, seis huellas de filas, estado de la secuencia y lectura como `esart_aplicacion`. Cualquier error implica que no se puede certificar el despliegue.
6. Repetir **01 completo** y luego **02 completo**. El segundo instalador debe informar **cero inserciones en los seis catálogos**. Comparar las seis huellas y el estado de la secuencia con la primera verificación: deben permanecer iguales, incluidas las fechas, sin escrituras externas. La fecha del registro de integración tampoco se actualiza.
7. Conservar salidas y errores, si los hay, como evidencia. No ejecutar reversión ni borrar objetos para solventar conflictos.

Las operaciones DDL y los datos están en una transacción. PostgreSQL no revierte los avances de secuencias: un error posterior a una inserción podría dejar huecos, sin pérdida de filas ni renumeración. El script nunca ejecuta `setval` ni reajusta identificadores.

## Diagnóstico y adaptación

El inventario disponible identifica 42 tablas, 322 columnas originales, 75 FK y cinco referencias directas al identificador BIGINT de `esart_ref.unidades_militares`: `personal_militar.unidad_actual_id`, `artillero_cargos.unidad_id`, `artillero_disparos.unidad_id`, `egresados_curso.unidad_destino_id` y `reentrenamientos.unidad_id`. Existen veinte tablas dependientes transitivas. No se cambian esos identificadores, tipos ni acciones referenciales.

El SQL verifica nuevamente columnas, nulabilidad, identidades, valores predeterminados, restricciones, índices, vistas y triggers originales. Busca entidades homónimas en otros esquemas, historial Alembic desconocido, secuencias atrasadas y referencias incompatibles. Conserva en memoria temporal todas las filas iniciales y comprueba que sus valores originales sigan intactos antes de confirmar. No muestra datos personales ni contraseñas.

**Si la tabla original de unidades contiene registros antes de la primera instalación, el script aborta.** Una fila con solo `id` no permite deducir su correspondencia institucional; es necesaria una conciliación explícita. Tampoco adopta instalaciones parciales ni sobrescribe catálogos de igual código con otros valores. No elimina unidades excedentes para alcanzar cuarenta.

La tabla canónica sigue siendo `esart_ref.unidades_militares`, con PK BIGINT e identidad originales. `unidad_superior_id` es BIGINT; `tipo_unidad_id` es UUID opcional. `uuid_publico` es un identificador externo nuevo y único, generado en la principal. Los UUID de tipos y demás entidades nuevas también se generan localmente; los JSON de semillas no contienen identificadores de pruebas. Los superiores se resuelven por código y se insertan antes que sus dependientes.

Las columnas añadidas a tablas heredadas son opcionales y sin valores predeterminados para conservar registros existentes sin inventar información. Las tablas nuevas mantienen las restricciones de los modelos adaptadas a las claves reales. Este esquema es una adaptación compatible, no una copia literal del esquema UUID de pruebas. Los CHECK permiten NULL en campos nuevos opcionales; no equivalen a declarar todos los campos del modelo histórico NOT NULL.

`esart.rol_permisos` conserva la autorización heredada por componente. `esart.roles_permisos` relaciona roles con el catálogo granular `esart.permisos`, una relación distinta. No se migran ni inventan concesiones entre ambos sistemas; deben conciliarse al adaptar la autenticación.

## Datos e idempotencia

| Catálogo | Referencias aprobadas | Inserciones esperadas si coincide con el respaldo |
|---|---:|---:|
| Tipos de cargo | 5 | 0 |
| Tipos de curso | 14 | 0 |
| Roles | 2 | 0 |
| Permisos | 36 | 36 |
| Tipos de unidad | 9 | 9 |
| Unidades militares | 40 | 40 |

Los conteos reales del instalador prevalecen sobre esta expectativa. Los cargos, cursos y roles existentes se reconocen por sus claves naturales y se conservan íntegros. Los códigos de cargo nuevos quedan NULL: no existen códigos aprobados que permitan inventarlos. La validación requiere todas las referencias aprobadas; pueden conservarse referencias ajenas compatibles en catálogos, pero la condición específica de unidades exige exactamente 40.

La matriz incluida clasifica 39 unidades; FUTOM conserva `tipo_unidad_id = NULL`. Se verifican códigos, nombres, tipos y cada superior, unicidad, ausencia de ciclos, todas las FK institucionales y validez de restricciones e índices. No se crean estados operacionales ni logísticos de VULCANO, administradores ni contraseñas predeterminadas. Certificaciones y requisitos de habilitación no se pueblan sin referencias aprobadas.

Los registros coincidentes se omiten antes de cualquier INSERT o consumo de secuencia; no se actualizan fechas ni se usa un UPSERT que active triggers. El registro de instalación se inserta solo una vez.

## Alembic y trazabilidad

No se modifican `0001` ni `0002`, no se ejecutan en esta base y **no se escribe `alembic_version` ni se hace stamp**. Sus supuestos de esquema vacío/UUID no coinciden con la principal heredada. Si existe cualquier tabla `alembic_version`, se aborta para revisar su historia real.

La instalación manual queda en `esart.integraciones_control`, con versión `dbcode_hu03_hu04_v1`, manifiesto SHA-256, operador, fecha, inserciones y huella estructural. Las repeticiones comparan esa estructura antes de actuar. Este registro no sustituye una revisión Alembic: antes de futuras migraciones deberá prepararse una línea de base adaptada que compruebe realmente los efectos de esta instalación. No usar `alembic upgrade head` ni `alembic stamp 0002` como atajo.

## FastAPI y permisos

El instalador concede permisos específicos sobre las estructuras gestionadas a `esart_aplicacion`, sin cambiar privilegios globales ni la cuenta del backend. Auditoría permite SELECT/INSERT y bloquea modificaciones y borrados. Se añaden funciones y triggers de fecha que solo cambian la fecha al cambiar otros valores; no alteran filas durante la carga. Las secuencias gestionadas reciben USAGE/SELECT.

Ambos archivos usan `SET LOCAL ROLE esart_aplicacion` para consultar efectivamente la vista con los permisos de la cuenta operativa, dentro de la conexión administrativa. Esto comprueba autorización SQL, **no prueba la contraseña, la configuración de FastAPI ni una petición HTTP**.

La vista `esart.v_unidades_api`, con `security_invoker`, expone UUID público como `id`, código, nombre, sigla, activa, tipo, superior y `clasificacion_pendiente`. Consulta de integración recomendada para el repositorio del endpoint:

```sql
SELECT * FROM esart.v_unidades_api ORDER BY codigo;
```

Los modelos actuales todavía requieren configuración de esquemas, tipos BIGINT internos y alias de columnas heredadas. El detalle está en `backend/sql/dbcode/resumen_revision.json`, clave `alias_orm_requeridos`. La vista facilita la consulta de unidades sin duplicarlas, pero no sustituye esas adaptaciones para escrituras.

**Este entregable no cambia la conexión operativa, los endpoints ni Angular.** El diagnóstico previo encontró solo el endpoint de salud registrado y rutas Angular sin integración de unidades. Después de ejecutar y verificar el SQL, queda validar/adaptar la configuración del backend a esart_db, la consulta real autenticada y el consumo Angular. No se considera terminada la integración de la interfaz por ejecutar SQL ni por obtener un SELECT correcto.

## Validación realizada antes de la entrega

Se generaron los archivos sin conexión a PostgreSQL. Se verifican los datos aprobados, el orden jerárquico, la ausencia de IDs trasladados, la reproducción exacta del paquete y las protecciones transaccionales mediante pruebas automatizadas. `validacion_estatica.json` registra las huellas y el análisis sintáctico PostgreSQL de los SQL; no constituye una ejecución ni valida contra el catálogo vivo.

El operador debe completar las verificaciones reales mediante DBCode. Hasta entonces las inserciones, permisos efectivos en la principal y compatibilidad de sus datos se consideran **pendientes de ejecución**.

Resultados locales: **106 pruebas aprobadas, 2 omitidas** con Python de `backend/.venv`; Ruff sin errores en `herramientas/generar_sql_dbcode.py` y `pruebas/test_sql_dbcode.py`. El análisis sintáctico final aceptó las 81 sentencias del instalador, las 20 de verificación y los cuerpos de las dos funciones persistentes. Es validación estática con analizador PostgreSQL 18.6, no ejecución contra el servidor 18.7. El repositorio mantiene incidencias Ruff preexistentes fuera de estos archivos; no se declara Ruff global limpio.

## Inventario exacto de cambios propuestos

Se conservan las 42 tablas originales. Se proponen nueve tablas funcionales nuevas y una de control, 54 columnas adicionales en catorce tablas existentes y una vista.

### Tablas nuevas

- `esart.tipos_unidad`: `id UUID DEFAULT gen_random_uuid() NOT NULL`; `codigo VARCHAR(20) NOT NULL`; `nombre VARCHAR(200) NOT NULL`; `activo BOOLEAN DEFAULT true NOT NULL`; `fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`.
- `esart.permisos`: `id UUID DEFAULT gen_random_uuid() NOT NULL`; `codigo VARCHAR(50) NOT NULL`; `descripcion VARCHAR(200) NOT NULL`; `fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`.
- `esart.roles_permisos`: `rol_id BIGINT NOT NULL`; `permiso_id UUID NOT NULL`; `fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`.
- `esart.intentos_inicio_sesion`: `id BIGINT GENERATED ALWAYS AS IDENTITY`; `nombre_usuario_intentado VARCHAR(60) NOT NULL`; `usuario_id BIGINT`; `direccion_ip INET`; `exitoso BOOLEAN NOT NULL`; `motivo_fallo VARCHAR(40)`; `fecha TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`.
- `esart.sesiones_usuario`: `id UUID NOT NULL`; `usuario_id BIGINT NOT NULL`; `fecha_inicio TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `fecha_ultima_actividad TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `direccion_ip INET`; `agente_usuario VARCHAR(300)`; `revocada BOOLEAN DEFAULT false NOT NULL`; `fecha_revocacion TIMESTAMP WITH TIME ZONE`.
- `esart.importaciones_excel`: `id UUID DEFAULT gen_random_uuid() NOT NULL`; `usuario_id BIGINT NOT NULL`; `nombre_archivo VARCHAR(255) NOT NULL`; `hash_sha256_archivo CHAR(64) NOT NULL`; `fecha TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `filas_totales INTEGER DEFAULT 0 NOT NULL`; `filas_validas INTEGER DEFAULT 0 NOT NULL`; `filas_rechazadas INTEGER DEFAULT 0 NOT NULL`; `estado VARCHAR(20) NOT NULL`; `errores JSONB`; `fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`.
- `esart.auditoria_eventos`: `id BIGINT GENERATED ALWAYS AS IDENTITY`; `fecha TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `usuario_id BIGINT`; `nombre_usuario VARCHAR(60)`; `accion VARCHAR(40) NOT NULL`; `numero_documento_consultado VARCHAR(10)`; `resultado VARCHAR(20)`; `direccion_ip INET`; `agente_usuario VARCHAR(300)`; `detalle JSONB`.
- `esart.tipos_certificacion`: `id UUID DEFAULT gen_random_uuid() NOT NULL`; `codigo VARCHAR(30) NOT NULL`; `nombre VARCHAR(200) NOT NULL`; `entidad_emisora VARCHAR(200)`; `tipo_sistema VARCHAR(50)`; `activo BOOLEAN DEFAULT true NOT NULL`; `fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`.
- `esart.requisitos_habilitacion`: `id UUID DEFAULT gen_random_uuid() NOT NULL`; `sistema_artilleria_id BIGINT`; `tipo_requisito VARCHAR(20) NOT NULL`; `tipo_curso_id BIGINT`; `tipo_certificacion_id UUID`; `descripcion VARCHAR(300) NOT NULL`; `activo BOOLEAN DEFAULT true NOT NULL`; `fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`; `fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`.
- `esart.integraciones_control`: `version TEXT PK`, `huella_manifiesto CHAR(64) NOT NULL`, `aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now()`, `operador TEXT NOT NULL`, `metodo TEXT NOT NULL CHECK`, `estructura JSONB NOT NULL`, `resumen JSONB NOT NULL`. Registro manual de la instalación.

### Columnas añadidas a tablas existentes

| Tabla | Columna | Tipo |
|---|---|---|
| `esart_ref.unidades_militares` | `codigo` | `VARCHAR(20)` |
| `esart_ref.unidades_militares` | `nombre` | `VARCHAR(200)` |
| `esart_ref.unidades_militares` | `sigla` | `VARCHAR(30)` |
| `esart_ref.unidades_militares` | `unidad_superior_id` | `BIGINT` |
| `esart_ref.unidades_militares` | `activa` | `BOOLEAN` |
| `esart_ref.unidades_militares` | `fecha_creacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart_ref.unidades_militares` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart_ref.unidades_militares` | `tipo_unidad_id` | `UUID` |
| `esart_ref.unidades_militares` | `uuid_publico` | `UUID` |
| `esart.personal_militar` | `primer_nombre` | `VARCHAR(60)` |
| `esart.personal_militar` | `segundo_nombre` | `VARCHAR(60)` |
| `esart.personal_militar` | `primer_apellido` | `VARCHAR(60)` |
| `esart.personal_militar` | `segundo_apellido` | `VARCHAR(60)` |
| `esart.personal_militar` | `arma` | `VARCHAR(40)` |
| `esart.personal_militar` | `estado_servicio` | `VARCHAR(20)` |
| `esart.hoja_vida_artillero` | `especialidad` | `VARCHAR(100)` |
| `esart.hoja_vida_artillero` | `fecha_ingreso_arma` | `DATE` |
| `esart.roles` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart_ref.usuarios` | `nombre_completo` | `VARCHAR(200)` |
| `esart_ref.usuarios` | `rol_id` | `BIGINT` |
| `esart_ref.usuarios` | `intentos_fallidos_consecutivos` | `INTEGER` |
| `esart_ref.usuarios` | `bloqueado_hasta` | `TIMESTAMP WITH TIME ZONE` |
| `esart.tipos_curso` | `descripcion` | `TEXT` |
| `esart.tipos_curso` | `tipo_sistema` | `VARCHAR(50)` |
| `esart.tipos_curso` | `vigencia_meses` | `INTEGER` |
| `esart.tipos_curso` | `nota_minima_aprobacion` | `NUMERIC(4, 2)` |
| `esart.tipos_curso` | `fecha_creacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.tipos_curso` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.artillero_cursos` | `numero_cohorte` | `VARCHAR(30)` |
| `esart.artillero_cursos` | `estado` | `VARCHAR(20)` |
| `esart.artillero_cursos` | `nota_final` | `NUMERIC(4, 2)` |
| `esart.artillero_cursos` | `numero_acta` | `VARCHAR(50)` |
| `esart.artillero_cursos` | `importacion_excel_id` | `UUID` |
| `esart.artillero_cursos` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.artillero_certificaciones` | `tipo_certificacion_id` | `UUID` |
| `esart.artillero_certificaciones` | `numero_certificado` | `VARCHAR(50)` |
| `esart.artillero_certificaciones` | `estado` | `VARCHAR(20)` |
| `esart.artillero_certificaciones` | `importacion_excel_id` | `UUID` |
| `esart.artillero_certificaciones` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart_ref.sistemas_artilleria` | `codigo` | `VARCHAR(30)` |
| `esart_ref.sistemas_artilleria` | `nombre` | `VARCHAR(200)` |
| `esart_ref.sistemas_artilleria` | `tipo_sistema` | `VARCHAR(50)` |
| `esart_ref.sistemas_artilleria` | `calibre_milimetros` | `NUMERIC(6, 2)` |
| `esart_ref.sistemas_artilleria` | `verificacion_habilitada` | `BOOLEAN` |
| `esart_ref.sistemas_artilleria` | `activo` | `BOOLEAN` |
| `esart_ref.sistemas_artilleria` | `fecha_creacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart_ref.sistemas_artilleria` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.tipos_cargo` | `codigo` | `VARCHAR(30)` |
| `esart.tipos_cargo` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.artillero_cargos` | `numero_resolucion` | `VARCHAR(50)` |
| `esart.artillero_cargos` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.componentes` | `fecha_actualizacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.rol_permisos` | `fecha_creacion` | `TIMESTAMP WITH TIME ZONE` |
| `esart.usuario_permisos` | `fecha_creacion` | `TIMESTAMP WITH TIME ZONE` |

### Objetos auxiliares

Vista `esart.v_unidades_api`; funciones `esart.actualizar_fecha_hu0304` y `esart.inmutabilidad_auditoria_hu0304`; veinte triggers de fecha y dos de inmutabilidad de auditoría. Las restricciones e índices adicionales se detallan en el SQL y su manifiesto; se conservan las PK, FK e índices originales. Las tablas temporales del instalador desaparecen al cerrar la transacción.

### Integridad del paquete

Manifiesto SHA-256: `b039ade13bfe7f3420b19804ae47d2bfa83d7059c005f5adf6b37f1c171b8c89`.

- `01_integrar_esart_db.sql`: `8e5d8f31fb654c59326917166930987c9f973738cc6c9fcd239367c99bdddda4`.
- `02_verificar_esart_db.sql`: `51af87053a0893b5d64b743c660f5149b2be7c68c75b6e1085424ee2772197d3`.
