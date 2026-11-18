# PostgreSQL de ESART: instalación, población y verificación

## Reglas y requisitos

Solo esart_db es operativa. esart y esart_ref son esquemas internos. PostgreSQL 18, herramientas psql/pg_dump/pg_restore compatibles y roles separados: esart_aplicacion para ejecución; propietario/operador para cambios estructurales. Los scripts SQL deben ejecutarse completos y con detención ante errores. Esta guía no autoriza ejecutar cambios ni modifica bases.

Antes de intervenir: comprobar destino/usuario, inventariar objetos y datos, respaldo completo, prueba de recuperabilidad documentada y aprobación del procedimiento. No borrar tablas, reiniciar secuencias, convertir BIGINT a UUID, copiar IDs de pruebas o forzar conteos. Conservar registros ajenos. Un conflicto exige revisión, no omitir restricciones.

## Escenario A — Instalación existente

1. Configurar backend/.env de forma local según el [README](../README.md), conservando esart_db y esart_aplicacion.
2. Ejecutar únicamente el verificador de lectura desde backend:

```powershell
.venv/Scripts/python.exe -m herramientas.verificar_persistencia_principal
```

Comprueba identidad, estructura frente a la fotografía p0001, cuatro catálogos, clasificación y FUTOM; no registra una revisión. Escribe evidencia JSON en disco. Ante cambios estructurales posteriores legítimos podría requerir actualizar el verificador mediante revisión; no alterar la base para satisfacer un snapshot antiguo.

3. Consultar metadatos, conteos e integridad mediante el SQL al final de esta guía. No volver a poblar tablas porque una interfaz vacía no las muestre.
4. Revisar revisión Alembic real con cuenta que pueda leer su historial. Si ya está p0001_real, no volver a adoptarla ni usar stamp.
5. La consulta real de esta tarea dio 40/9/5/14, 39 clasificadas y FUTOM pendiente. SELECT de personal y alembic_version está restringido para la cuenta operativa: solicitar al propietario esa comprobación puntual, no permisos administrativos generales.

## Alembic: dos historiales, una base operativa

| Configuración | Directorio | Contrato | Uso |
|---|---|---|---|
| backend/alembic.ini | migraciones_principal | BIGINT, esart/esart_ref, único head p0001_real | Principal |
| backend/alembic_historico.ini | migraciones/versions | UUID, public, 0001→0002 | Historia de pruebas; su env rechaza esart_db |

`p0001_real` valida y adopta objetos existentes mediante una fotografía congelada. No crea las 43 tablas, no ejecuta los seeds y no representa la aplicación de 0001/0002. La creación/escritura de su tabla de versión es un cambio de base que exige autorización. No usar stamp para simular equivalencia.

El operador reportó previamente **p0001_real (head)** en esart_db. En esta tarea se observó esart.alembic_version pero esart_aplicacion no puede leerla. `heads` solo enumera el código local; no prueba la revisión de la base.

Desde backend, comandos de inspección sin migrar:

```powershell
.venv/Scripts/python.exe -m alembic history --verbose
.venv/Scripts/python.exe -m alembic heads
```

`current -v` requiere que el proceso disponga de ESART_MIGRACIONES_URL: el env principal no lee la cuenta de migraciones desde el .env ni usa silenciosamente la del backend. Para una inspección local autorizada, introducir la URL administrativa protegida sin eco y solo durante el proceso:

```powershell
$conexionProtegida = Read-Host 'URL administrativa asyncpg de esart_db' -AsSecureString
try {
    $env:ESART_MIGRACIONES_URL = [System.Net.NetworkCredential]::new('', $conexionProtegida).Password
    .venv/Scripts/python.exe -m alembic current -v
} finally {
    Remove-Item Env:ESART_MIGRACIONES_URL -ErrorAction SilentlyContinue
    $conexionProtegida.Dispose()
}
```

Usar un perfil/proceso local confiable. No copiar el secreto en scripts, historial de shell, Git, capturas o informes; preferir el gestor local de secretos del equipo. El backend permanece con esart_aplicacion. Si falta acceso, comprobar por DBCode del propietario con el SQL de lectura; no crear conexiones ni roles improvisados.

No ejecutar upgrade, downgrade, stamp ni revision --autogenerate durante una recepción o documentación. La autogeneración está bloqueada en env.py hasta conciliar su alcance; el modo offline también se rechaza. Los cambios futuros serán revisiones manuales compatibles en la línea principal, con comprobaciones y aprobación.

## Escenario B — Base nueva y vacía

**INSTALACIÓN DESDE CERO NO DISPONIBLE TODAVÍA.**

El código contiene piezas de referencia, no una cadena inicial probada:

1. esart_vulcano_postgresql.sql crea estructuras académicas y referencias incompletas.
2. esart_seguridad_roles_permisos.sql amplía usuarios, roles y malla de permisos.
3. ESART_CARGAR_ESART_DB.sql amplía unidades, crea tipos y carga referencias.
4. p0001_real adopta el resultado esperado; no ejecuta las piezas anteriores.

Esta secuencia es una dependencia inferida del código, **no un procedimiento de instalación autorizado ni validado de extremo a extremo**. IF NOT EXISTS no corrige objetos incompletos. No se ha comprobado que esa combinación reproduzca exactamente las 43 tablas, restricciones, índices, privilegios y datos del snapshot.

Falta una migración inicial reproducible de la línea principal —incluidos esquemas, identidades, restricciones e índices—, seeds operativos BIGINT de catálogos separados del DDL, provisión mínima de privilegios revisada, conciliación de autorización granular y pruebas completas de instalación/restauración. También falta el flujo seguro de alta de usuarios, sin administradores predeterminados.

Hasta disponer de ello, un entorno equivalente requiere una instalación existente o un respaldo autorizado por canales privados. No incluir ese respaldo en Git. No crear bases alternativas ni restaurar encima de esart_db existente. Una instalación limpia requiere procedimiento específico aprobado por el propietario.

## Escenario C — Esquema creado, catálogos vacíos

Primero ejecutar los conteos y revisar columnas/índices únicos. Un count que falla por permisos no significa tabla vacía. Separar vacío de parcial o incompatible. No inferir el estado desde Angular.

No hay actualmente un seed BIGINT completo validado y autorizado para poblar todos los catálogos desde este escenario. Los SQL académicos tienen semántica insertiva por nombre/código comprobable por revisión; el cargador de unidades combina DDL/DML y rellena padres NULL. Los ejecutores Python heredados importan app.*, ausente aquí. Los seeds de backend/seeds apuntan explícitamente a bases históricas y no se deben reutilizar cambiando la URL.

Procedimiento pendiente: conciliar referencias por código/nombre, generar plan de inserciones por catálogo, revisar discrepancias, resolver superiores/tipos por claves reales, aprobar y probar el cargador operativo, ejecutar transacción e informe y repetir para demostrar idempotencia de filas/fechas. No ejecutar ahora los cargadores solo por estar disponibles. El inventario especifica los comandos técnicos y su estado de bloqueo.

## Escenario D — Otro desarrollador

Seguir [guía de entrega](ESART_ENTREGA_OTRO_DESARROLLADOR.md). Un clon proporciona código, referencias institucionales y snapshots de metadatos, no una copia física del PostgreSQL local. Los datos de negocio, usuarios, documentos y evidencias privadas requieren fuentes autorizadas o respaldo. El clon y pip/npm no crean tablas.

## Respaldos y restaurabilidad

El respaldo local backend/respaldos/esart_db_pre_alembic.dump tiene una evidencia previa de índice legible y decodificación completa. Eso no demuestra restauración correcta. El respaldo anterior esart_db_pre_hu04.backup tenía otra huella y otra verificación: no intercambiar sus certificaciones. No distribuir archivos reales ni rutas personales como requisito del proyecto.

`herramientas/respaldar_base_principal.ps1` genera custom dump y evidencia sin alterar la base; requiere una cuenta con lectura suficiente. `verificar_respaldo_aislado.py` crea un clúster aislado para pruebas: está fuera del procedimiento autorizado actual y no debe ejecutarse automáticamente. Una futura prueba de recuperación exige autorización separada y nunca destino esart_db existente. Conservación de respaldos y política de secretos deben acordarse fuera de Git.

## Consultas de solo lectura

Ejecutar con cuenta autorizada. No conceder permisos adicionales para ocultar errores. En DBCode o psql, cada bloque es de lectura; no contiene cargas ni migraciones.

```sql
SELECT current_database() AS base, current_user AS usuario;
SELECT nspname AS esquema FROM pg_namespace
WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema' ORDER BY 1;
SELECT n.nspname AS esquema,c.relname AS tabla
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p') AND n.nspname IN ('esart','esart_ref','public')
ORDER BY 1,2;

SELECT 'unidades' catalogo,count(*) total FROM esart_ref.unidades_militares
UNION ALL SELECT 'tipos_unidad',count(*) FROM esart.tipos_unidad
UNION ALL SELECT 'cargos',count(*) FROM esart.tipos_cargo
UNION ALL SELECT 'cursos',count(*) FROM esart.tipos_curso;
-- Personal: solo propietario/cuenta con SELECT autorizado.
SELECT count(*) AS personal FROM esart.personal_militar;

SELECT count(*) AS unidades,count(tipo_unidad_id) AS clasificadas,
       count(*) FILTER(WHERE tipo_unidad_id IS NULL) AS pendientes
FROM esart_ref.unidades_militares;
SELECT id,codigo,nombre,tipo_unidad_id FROM esart_ref.unidades_militares
WHERE tipo_unidad_id IS NULL ORDER BY codigo;
SELECT codigo,tipo_unidad_id FROM esart_ref.unidades_militares WHERE codigo='FUTOM';

-- Cero filas en cada detección de huérfanos o códigos duplicados.
SELECT u.codigo FROM esart_ref.unidades_militares u
LEFT JOIN esart.tipos_unidad t ON t.id=u.tipo_unidad_id
WHERE u.tipo_unidad_id IS NOT NULL AND t.id IS NULL;
SELECT u.codigo FROM esart_ref.unidades_militares u
LEFT JOIN esart_ref.unidades_militares p ON p.id=u.unidad_padre_id
WHERE u.unidad_padre_id IS NOT NULL AND p.id IS NULL;
SELECT codigo,count(*) FROM esart_ref.unidades_militares GROUP BY codigo HAVING count(*)>1;

WITH RECURSIVE j AS (
 SELECT id,unidad_padre_id,ARRAY[id] camino,false ciclo FROM esart_ref.unidades_militares
 UNION ALL
 SELECT p.id,p.unidad_padre_id,j.camino||p.id,p.id=ANY(j.camino)
 FROM j JOIN esart_ref.unidades_militares p ON p.id=j.unidad_padre_id WHERE NOT j.ciclo
)
SELECT * FROM j WHERE ciclo;

SELECT n.nspname esquema,t.relname tabla,c.conname,pg_get_constraintdef(c.oid) definicion,
       c.convalidated FROM pg_constraint c
JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname IN ('esart','esart_ref') ORDER BY 1,2,3;
SELECT sn.nspname esquema,sc.relname tabla,c.conname,
       dn.nspname destino_esquema,dc.relname destino_tabla
FROM pg_constraint c JOIN pg_class sc ON sc.oid=c.conrelid
JOIN pg_namespace sn ON sn.oid=sc.relnamespace
JOIN pg_class dc ON dc.oid=c.confrelid JOIN pg_namespace dn ON dn.oid=dc.relnamespace
WHERE c.contype='f' AND dn.nspname='esart_ref' AND dc.relname='unidades_militares';

-- Localizar historial antes de consultarlo, sin crearlo si falta.
SELECT n.nspname esquema,c.relname FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='alembic_version';
-- Solo si existe y el operador tiene SELECT:
SELECT version_num FROM esart.alembic_version;
```

Resultado esperado de referencia: 40 unidades, 39 clasificadas, FUTOM NULL; catálogos 9/5/14; sin huérfanos ni ciclos. Una diferencia se informa y analiza: no se corrige automáticamente.
