# Conciliación p0018 en esart_ensayo

## CHECK documentales y función de autenticación

La auditoría real reportada confirmó las 21 tablas heredadas y los permisos. En `documentos`, la referencia construye un arreglo de literales `varchar` y convierte el arreglo a `text[]`. La variante reportada convierte cada literal individualmente a `text` y construye el mismo `text[]`. PostgreSQL 18.7 compara ambos arreglos como idénticos, incluidos sus elementos y orden. Las dos expresiones aplican el mismo operador `=` mediante `ANY` al mismo valor de columna convertido a `text`; por lo tanto dan el mismo resultado para cualquier valor. Si la columna es NULL, ambas expresiones dan NULL. Las columnas tienen además `NOT NULL`.

La excepción del validador exige la tabla `documentos`, el nombre de uno de los dos CHECK, el predicado alternativo exacto y que la restricción esté validada y aplicada. Las definiciones de los demás CHECK permanecen bajo comparación exacta.

La función de p0018 es PL/pgSQL, sin argumentos, retorna `trigger`, es VOLATILE y PARALLEL UNSAFE, usa SECURITY INVOKER y carece de ajustes de configuración propios como `search_path`. Su cuerpo lanza una excepción P0001 de forma incondicional. Se admite la misma instrucción con otro mensaje literal y, opcionalmente, con `TG_TABLE_NAME` como único argumento de formato. La gramática excluye ramas, SQL dinámico, retornos y manejadores de excepciones. Las definiciones que se aparten de estos límites se rechazan. Los tres triggers auditados deben seguir habilitados y cubrir INSERT y UPDATE.

La sesión del agente recibió `fe_sendauth: no password supplied` antes de autenticar contra la copia real. Por eso siguen sin verificarse su código PL/pgSQL exacto, propietario y ACL. El comando `--solo-auditar` imprime la definición canónica real, el propietario, la ACL y los permisos efectivos EXECUTE del migrador y de la API, sin invocar la función. Si la auditoría sigue rechazándola, conservar su definición y revisar el conflicto antes de autorizar cualquier intervención.

**Resultados.** Pasaron 9 casos distintos de integración en PostgreSQL 18.7 y 13 pruebas locales, con cero fallos en las ejecuciones finales. Los cinco casos específicos se repitieron comprobando los OID de las 23 tablas. La adopción conservó los CHECK, los triggers y la función, además de los conteos y SHA-256 de los documentos, las versiones y la auditoría. Se comprobó el rechazo de INSERT y UPDATE en una tabla temporal del laboratorio. Los casos negativos rechazaron un estado adicional, una función que permitía UPDATE y variantes con SECURITY DEFINER o con `search_path` propio. El primer intento de prueba detectó una aserción de catálogo demasiado estricta, que se corrigió para comparar la identidad de los objetos preexistentes aunque la migración agregue otros. No se aplicaron p0018 ni p0019 en la copia real.

## Auditoría integral y adopción de objetos preexistentes

El operador reportó 15 tablas heredadas compatibles y seis con diferencias. La salida reportada identifica las tablas y los nombres de los tres triggers. Aún falta obtener del servidor real la definición de cada columna, el estado de los triggers, los atributos de la función y el contexto de permisos. Esta sesión recibió de nuevo `fe_sendauth: no password supplied`. Los valores de la tabla siguiente son las transformaciones previstas por p0018 y las referencias verificadas en el laboratorio.

| Tabla | Diferencia reportada | Estructura que p0018 puede adoptar |
| --- | --- | --- |
| `identidades` | Columnas, tipos o nulabilidad | `usuario_id bigint NULL`, sin default. FK a `esart_ref.usuarios(id)` con `ON DELETE RESTRICT` e índice único parcial si ya existen con sus definiciones exactas. |
| `evidencias` | Columnas, tipos o nulabilidad | `documento_id uuid NULL`, sin default. FK a `documentos(id)` con `ON DELETE RESTRICT` e índice parcial si son compatibles. |
| `solicitudes_firma` | Columnas, tipos o nulabilidad | `documento_id uuid NULL` y `documento_version_id uuid NULL`, ambos sin default. `certificado_id` y `version_id` pueden admitir NULL. Se valida la FK compuesta, el CHECK que exige un solo objeto y el índice único parcial. |
| `sesiones_firma` | `trg_autenticacion_heredada` adicional | Trigger habilitado en modo ordinario, por fila y antes de INSERT o UPDATE. Debe invocar la función de p0018 con el cuerpo esperado. |
| `totp_factores` | `trg_autenticacion_heredada` adicional | Misma definición esperada, sobre su propia tabla. |
| `totp_recuperacion` | `trg_autenticacion_heredada` adicional | Misma definición esperada, sobre su propia tabla. |

La auditoría contrasta las 21 tablas heredadas con el JSON original y con los cambios permitidos por p0018. Para las dos documentales usa un catálogo de referencia generado por PostgreSQL 18 a partir del DDL de la revisión. La comparación identifica columnas adicionales o ausentes y diferencias de tipo, nulabilidad y defaults. También verifica secuencias propias, restricciones, claves foráneas, índices, disparadores y funciones. Para la función que rechaza la autenticación heredada compara el cuerpo y atributos de seguridad, sin ejecutarla. Para la función de inmutabilidad heredada, el inventario solo permite confirmar su firma y su asociación con los triggers. La auditoría imprime propiedad, ACL de tablas, columnas y secuencias, permisos efectivos del migrador y extensiones instaladas. Los permisos y extensiones no figuran en el JSON original, por lo que se informan como contexto operativo.

La migración conserva objetos compatibles y crea únicamente los objetos de p0018 que falten. Sus huellas incluyen las columnas preexistentes que se adopten y el ejecutor comprueba además los OID de las 23 tablas. Cualquier discrepancia revierte la transacción. La copia real sigue pendiente de auditoría y de autorización para aplicar p0018. p0019 queda fuera.

**Resultados de la conciliación integral.** Pasaron 19 casos distintos de integración en PostgreSQL 18.7 y 13 pruebas locales, con cero fallos. La primera ejecución cubrió 17 casos. Se repitieron los dos casos de las seis diferencias junto con dos nuevos casos de adopción parcial y rechazo de función incompatible. Se comprobó que las tres extensiones y los tres triggers compatibles conservan sus OID, que las tres discrepancias de columna y las tres definiciones de trigger incompatibles se identifican en una sola auditoría, y que la huella de los documentos, versiones, auditoría e identidad enlazada permanece igual. También se comprobó la creación de los objetos faltantes en el caso parcial y el rechazo de una función de seguridad que devuelve `NEW`. Ruff pasó. Pytest mantuvo la advertencia de deprecación de `pytest-asyncio`.

**Auditoría de solo lectura**

```powershell
& 'D:\2026\esart\esart\esart\backend\.venv\Scripts\python.exe' 'D:\2026\esart\esart\esart\backend\herramientas\aplicar_p0018_ensayo.py' --solo-auditar
```

**Aplicación de p0018 después de validar la auditoría y obtener autorización**

```powershell
& 'D:\2026\esart\esart\esart\backend\.venv\Scripts\python.exe' 'D:\2026\esart\esart\esart\backend\herramientas\aplicar_p0018_ensayo.py'
```

## Diagnóstico y cambios

### CHECK de firma preexistente

En la copia real, p0018 abortó en p0017 al detectar `ck_desafios_solo_firma`. El inventario conserva `desafios_autenticacion_proposito_check`, que admite LOGIN, FIRMAR, RECUPERAR_MFA y CAMBIAR_MFA. El CHECK reportado es un objeto adicional al inventario y coincide con el CHECK que p0018 agrega para restringir el propósito a FIRMAR. PostgreSQL 18 muestra el literal con `::text` porque la columna tiene tipo `text`.

El validador admite únicamente ese CHECK adicional en `desafios_autenticacion`, con el nombre y la definición canónica exactos y en estado validado y aplicado. Si ya existe y es compatible, p0018 lo conserva y omite su creación. Las restricciones heredadas siguen siendo obligatorias. Una definición más permisiva, un CHECK sin validar o cualquier otra diferencia se rechazan sin modificar la tabla.

La auditoría de solo lectura compara el catálogo de las 21 tablas con el inventario, informa discrepancias por tabla y prescinde de Alembic. Desde una terminal interactiva con la credencial del migrador:

```powershell
& 'D:\2026\esart\esart\esart\backend\.venv\Scripts\python.exe' 'D:\2026\esart\esart\esart\backend\herramientas\aplicar_p0018_ensayo.py' --solo-auditar
```

El intento contra la copia real recibió `fe_sendauth: no password supplied` en la sesión del agente. La auditoría de la copia queda pendiente. En esta corrección, las ejecuciones de p0018 se limitan al laboratorio y p0019 queda fuera.

Resultados de esta corrección: 15 pruebas de integración aprobadas y 0 fallidas en PostgreSQL 18.7, y 13 pruebas locales aprobadas. La regresión positiva verificó las 21 tablas mediante la auditoría y conservó el OID y la definición del CHECK, además de los OID, los conteos y las huellas de los documentos, versiones y auditoría. Se rechazaron el CHECK que admite LOGIN, el CHECK sin validar y la ausencia de la restricción heredada. También pasaron el preflight y los diez casos de divergencia de catálogo. Ruff y el formato pasaron. Pytest mantuvo la advertencia de deprecación de `pytest-asyncio`.

La revisión de partida reportada es `p0017_restablecer_totp_admin`. El JSON describe las 21 tablas heredadas y la copia reportada tiene otras dos, `documentos` y `versiones_documento`, con 3 y 4 filas respectivamente. La versión anterior rechazaba ambas tablas por nombre y su guarda interna rechazaba `esart_ensayo`, aunque `env.py` ya admitía la copia con la bandera de validación.

| Grupo | Decisión de p0018 |
| --- | --- |
| 21 tablas del inventario | Valida los objetos existentes. Crea el conjunto a partir del JSON si el esquema está ausente. Un esquema existente incompleto falla. |
| `documentos` y `versiones_documento` | Adopta cada tabla compatible por catálogo y crea cada tabla ausente en orden de dependencia. Una versión incompatible impide toda la conciliación. |
| Identidades, evidencias, solicitudes y autenticación heredada | Adopta las extensiones exactas de p0018 y aplica las que falten. Los objetos incompatibles requieren revisión. |
| Malla y permisos | Mantiene el comportamiento previsto por p0018, incluido el componente especial existente compatible. Conserva la cadena de revisiones y las concesiones de p0019. |

La comparación valida nombres, orden de columnas, tipos, nulabilidad, defaults, secuencias propias, restricciones y claves foráneas completas, índices y disparadores. Comprueba además que los objetos estén activos y rechaza tablas con herencia, particionado, reglas o seguridad por fila. El JSON identifica las secuencias heredadas sin distinguir SERIAL de IDENTITY e identifica la función de inmutabilidad por su firma, sin registrar su cuerpo. La migración conserva esa función, verifica su firma y verifica que los disparadores esperados la invoquen.

Las definiciones canónicas documentales se obtuvieron del catálogo de PostgreSQL 18 en el laboratorio y están versionadas junto a la migración. La auditoría y la validación usan esa misma referencia sin crear un esquema temporal. La migración bloquea las tablas de firma durante la validación y el cambio para estabilizar los objetos y los datos comparados.

En la misma transacción compara conteos y huellas SHA-256 de las columnas originales de cada tabla previamente presente, incluida la auditoría. El cálculo incluye UUID, referencias, datos emitidos y hashes de las versiones. Una discrepancia revierte la transacción. El downgrade de p0018 queda bloqueado para cualquier estado porque la revisión carece de un registro fiable de procedencia de objetos y concesiones.

## Evidencia del laboratorio

Las pruebas locales de persistencia y de la cadena de Alembic dieron 13 aprobadas. La integración usó PostgreSQL 18.7 en clústeres efímeros. Cada conexión migradora se configuró para `esart_ensayo` en `127.0.0.1`, con puerto asignado al laboratorio y el usuario `esart_migrador`. La suite comprueba también esa identidad y la ausencia de privilegios de superusuario en el servidor.

| Grupo | Aprobadas | Fallidas | Comprobaciones |
| --- | ---: | ---: | --- |
| Conciliación y reversión | 4 | 0 | Instalación nueva, esquema heredado sin tablas documentales, adopción parcial y adopción completa. Guarda de copia, restricciones, FK, índices, triggers, permisos de p0018 y p0019 y reversión bloqueada. |
| Estructuras incompatibles | 10 | 0 | Columna adicional, tipo, nulabilidad, default, CHECK, FK diferible, índice adicional, trigger deshabilitado, default heredado y extensión parcial. Cada discrepancia conservó la revisión p0017 y los datos previos. |
| Total de integración | 14 | 0 | Los cuatro escenarios de conciliación se repitieron con aserciones explícitas adicionales de identidad, catálogo y permisos. |

El primer intento se detuvo antes de ejecutar casos porque `pg_ctl` no pudo crear un token restringido en el sandbox de Windows (error 87). Los resultados de la tabla se obtuvieron al ejecutar el laboratorio fuera del sandbox con la aprobación correspondiente.

En la verificación previa de solo lectura se repitieron las 14 pruebas de integración y las 13 de persistencia y cadena de Alembic, con 27 aprobadas y 0 fallidas. Una prueba adicional ejecutó el preflight mediante `psql` en otro clúster efímero, confirmó el modo de solo lectura e inspeccionó los 23 conteos y SHA-256. En total, 28 comprobaciones aprobadas. Pytest emitió una advertencia de deprecación de `pytest-asyncio` por `asyncio_default_fixture_loop_scope` sin definir.

En la ejecución con verificaciones explícitas de catálogo, identidad y permisos se obtuvieron los mismos valores antes de p0018 y después de ejecutarla. La prueba comprobó de nuevo las huellas después del intento de reversión.

| Tabla | OID | Filas | SHA-256 antes y después |
| --- | ---: | ---: | --- |
| `documentos` | 17015 | 3 | `5835d670a84f46a4035c9444da58d91059935c26d831c8cd9719f005dc06b8c4` |
| `versiones_documento` | 17055 | 4 | `1eb507a114163f033d7a7b7528159caa60852a200b4fee447d5bf9ab907f92bd` |
| `auditoria_eventos` | 16467 | 1 | `5ecbfef927e3b1d45446957e1cfd4e63e04f151f8ebd83f846141d973d5112dc` |

Los OID y huellas corresponden a datos sintéticos. En la sesión del agente `ESART_MIGRACIONES_URL` estaba sin definir. La validación de identidad y las huellas de la copia real quedan pendientes de comprobar con la URL migradora de la copia y la autorización correspondiente. `esart_db` y la copia real quedaron fuera del laboratorio.

## Verificación de solo lectura de la copia real

El intento de conexión a `127.0.0.1:5432/esart_ensayo` como `esart_migrador` llegó al servidor y recibió `fe_sendauth: no password supplied`. La URL migradora tampoco está definida en los ámbitos de proceso, usuario y máquina de la sesión. PostgreSQL no abrió una sesión autenticada. Quedan pendientes la identidad efectiva, la revisión, los conteos de las 23 tablas y sus huellas reales.

Con la credencial habilitada mediante `pgpass`, desde `backend` se puede ejecutar el preflight. El script valida la identidad y la revisión antes de leer las tablas y obtiene los 23 conteos y SHA-256 en una sola instantánea de solo lectura. Mantener el puerto de la copia si difiere de 5432.

```powershell
$env:PGOPTIONS = '-c default_transaction_read_only=on'
$env:PGCONNECT_TIMEOUT = '5'
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -X -w --csv -h 127.0.0.1 -p 5432 -U esart_migrador -d esart_ensayo -f herramientas/preflight_p0018_ensayo.sql
Remove-Item Env:PGOPTIONS, Env:PGCONNECT_TIMEOUT
```

## Comandos tras la autorización

La aplicación quedó autorizada para la copia real, sujeta a verificar el destino y la integridad. La sesión independiente volvió a recibir `fe_sendauth: no password supplied` antes de abrir una sesión. Por tanto, en esta ejecución no se aplicó ninguna revisión. Se repitieron las 13 pruebas locales y el análisis estático sin montar nuevas bases ni roles. Los resultados de integración previos corresponden a la misma lógica de p0018.

Desde la terminal interactiva del operador, el siguiente comando usa la URL migradora existente o solicita la contraseña sin eco. Ejecuta exclusivamente p0018 y compara OID, conteos y huellas de las columnas preexistentes de las 23 tablas dentro de la misma transacción. También comprueba la revisión y las columnas que requiere p0019. El informe de huellas se imprime después del commit.

```powershell
& 'D:\2026\esart\esart\esart\backend\.venv\Scripts\python.exe' 'D:\2026\esart\esart\esart\backend\herramientas\aplicar_p0018_ensayo.py'
```

Desde `backend`, para el laboratorio. `PG_BIN` puede indicar la carpeta `bin` de PostgreSQL 18 si difiere de la ruta estándar en Windows.

```powershell
$env:ESART_EJECUTAR_INTEGRACION_P0018 = '1'
.venv\Scripts\python.exe -m pytest -s pruebas/test_p0018_postgresql.py
Remove-Item Env:ESART_EJECUTAR_INTEGRACION_P0018
```

Para la copia del operador, cargar `ESART_MIGRACIONES_URL` mediante el mecanismo habitual de secretos y usar la configuración local de desarrollo existente. El siguiente bloque verifica que la URL sea de `esart_migrador` en `esart_ensayo` local antes de invocar Alembic. Ejecutar primero las consultas de evidencia y comprobar la revisión inicial. El SQL manual histórico de p0018/p0019 antecede a esta conciliación.

```powershell
$env:ESART_VALIDAR_P0018_COPIA = '1'
.venv\Scripts\python.exe -c "import os; from sqlalchemy.engine import make_url; u = make_url(os.environ['ESART_MIGRACIONES_URL']); raise SystemExit(0 if (u.drivername == 'postgresql+asyncpg' and u.username == 'esart_migrador' and u.database == 'esart_ensayo' and u.host in ('127.0.0.1', 'localhost', '::1') and not u.query) else 'Se requiere la URL directa de esart_migrador a esart_ensayo local')"
if ($LASTEXITCODE -ne 0) { throw 'Destino de migración inválido' }
.venv\Scripts\python.exe -m alembic upgrade p0018_firma_documental
if ($LASTEXITCODE -ne 0) { throw 'Falló p0018' }
Remove-Item Env:ESART_VALIDAR_P0018_COPIA
```

Ejecutar esta consulta de evidencia en la copia antes y después, con `psql -h 127.0.0.1 -p PUERTO -U esart_migrador -d esart_ensayo -X -v ON_ERROR_STOP=1`, usando el puerto de la URL migradora. Comparar los resultados bajo una ventana sin escrituras de la aplicación. En la copia descrita, los tres OID, conteos y huellas deben conservarse, mientras cambia la revisión.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL TIME ZONE 'UTC';
SELECT current_database(), current_user, host(inet_server_addr()) AS servidor,
       rolsuper, version_num,
       has_database_privilege(current_user, current_database(), 'CREATE') AS puede_crear_esquema
FROM esart.alembic_version
JOIN pg_roles ON rolname = current_user;

WITH filas AS (
    SELECT 'documentos' AS tabla, id::text AS id, to_jsonb(d)::text AS datos
    FROM esart_firma.documentos d
    UNION ALL
    SELECT 'versiones_documento', id::text, to_jsonb(v)::text
    FROM esart_firma.versiones_documento v
    UNION ALL
    SELECT 'auditoria_eventos', id::text, to_jsonb(a)::text
    FROM esart_firma.auditoria_eventos a
), tablas(tabla) AS (
    VALUES ('documentos'), ('versiones_documento'), ('auditoria_eventos')
)
SELECT t.tabla, to_regclass('esart_firma.' || t.tabla)::oid AS oid, count(f.id) AS filas,
       encode(sha256(convert_to(
           coalesce(string_agg(f.datos, E'\n' ORDER BY f.id COLLATE "C"), ''), 'UTF8')), 'hex') AS sha256
FROM tablas t LEFT JOIN filas f USING (tabla)
GROUP BY t.tabla
ORDER BY t.tabla;
COMMIT;
```
