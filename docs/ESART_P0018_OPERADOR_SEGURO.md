# Procedimiento local para preparar P0014→P0018

Este runbook no ejecuta migraciones ni cambia `esart_db`. Las credenciales se capturan interactivamente y permanecen en memoria de proceso; nunca pegarlas en el repositorio, terminal como literal, informes o chat.

## Hallazgos de configuración

- `backend/.env` contiene solo la variable `URL_BASE_DATOS` entre las variables de base de datos; es la conexión de `esart_aplicacion` y no se debe modificar al rotar la credencial de `postgres`.
- La conexión de migración se lee de `ESART_MIGRACIONES_URL` y la de respaldo de `ESART_RESPALDO_URL`, solo desde el entorno del proceso. No deben guardarse en `.env`.
- No se encontraron otras variables de conexión superusuario en `backend/.env`. La contraseña expuesta sigue activa hasta que el operador la rote localmente.
- Se usará `postgres` únicamente para rotar su propia contraseña y aprovisionar roles. No se usará para FastAPI, pg_dump ni Alembic.

## 1. Rotar contraseña expuesta

Desde una consola local interactiva:

```powershell
psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W
```

En el prompt de `psql`:

```text
\password postgres
\q
```

`\password` solicita el secreto sin imprimirlo. Actualiza únicamente el gestor seguro usado por el operador para el rol `postgres`; no cambies `URL_BASE_DATOS` ni contraseñas de usuarios ESART. La contraseña de aplicación es independiente.

## 2. Aprovisionar respaldo y migrador

El SQL preparado está en `backend/migraciones_principal/preparar_roles_firma.sql`. Ejecutarlo interactivamente una sola vez, después de la rotación:

```powershell
psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W -v ON_ERROR_STOP=1 -f backend/migraciones_principal/preparar_roles_firma.sql
```

Las dos contraseñas se solicitan interactivamente con `\password` y no se guardan en el archivo. `esart_respaldo` recibe `pg_read_all_data` para que el respaldo completo lea tablas y secuencias, además de CONNECT a `esart_db`; no obtiene escritura, DDL ni privilegios de login superusuario. `esart_migrador` no recibe grants sobre `esart_db`; será propietario solo de la copia restaurada.

No se crea un login administrativo adicional: ya existe el rol administrativo `postgres`, y añadir una cuenta con `CREATEROLE`/`CREATEDB` ampliaría privilegios sin ser necesario para la validación. `postgres` no será el migrador.

## 3. Crear respaldo cuando el rol esté aprovisionado

Desde PowerShell, capture el rol separado con `Get-Credential`. El siguiente bloque construye la URL dentro del proceso; no muestra ni persiste la contraseña:

```powershell
$credencialRespaldo = Get-Credential -UserName 'esart_respaldo'
$secretoRespaldo = [System.Net.NetworkCredential]::new('', $credencialRespaldo.Password).Password
$usuarioUrl = [uri]::EscapeDataString($credencialRespaldo.UserName)
$claveUrl = [uri]::EscapeDataString($secretoRespaldo)
$env:ESART_RESPALDO_URL = "postgresql+asyncpg://$usuarioUrl`:$claveUrl@127.0.0.1:5432/esart_db"
Push-Location backend
..\.venv\Scripts\python.exe -m herramientas.respaldo_previo_firma_documental
$resultadoRespaldo = $LASTEXITCODE
Pop-Location
Remove-Item Env:ESART_RESPALDO_URL -ErrorAction SilentlyContinue
Remove-Variable credencialRespaldo,secretoRespaldo,usuarioUrl,claveUrl -ErrorAction SilentlyContinue
if ($resultadoRespaldo -ne 0) { throw 'Falló la generación o verificación del respaldo.' }
```

El programa valida host/base/rol, produce custom dump privado, verifica `pg_restore --list` e imprime la ruta, tamaño y SHA-256. Verificar que `backend/respaldos/p0018_privado` siga protegido por ACL. Un `--list` correcto solo prueba legibilidad del archivo, no restauración.

## 4. Restaurar la copia de ensayo

Use el dump recién generado. Mantenga el nombre reservado que admite la guarda local:

```powershell
$credencialAdmin = Get-Credential -UserName 'postgres'
$claveAdmin = [System.Net.NetworkCredential]::new('', $credencialAdmin.Password).Password
$env:PGPASSWORD = $claveAdmin
createdb.exe --host=127.0.0.1 --port=5432 --username=postgres --owner=esart_migrador --maintenance-db=postgres esart_db_p0018_restore_test
Remove-Item Env:PGPASSWORD

$credencialMigrador = Get-Credential -UserName 'esart_migrador'
$claveMigrador = [System.Net.NetworkCredential]::new('', $credencialMigrador.Password).Password
$env:PGPASSWORD = $claveMigrador
pg_restore.exe --host=127.0.0.1 --port=5432 --username=esart_migrador --dbname=esart_db_p0018_restore_test --no-owner --no-privileges --exit-on-error <RUTA_DUMP_VERIFICADO>
Remove-Item Env:PGPASSWORD
Remove-Variable credencialAdmin,claveAdmin,credencialMigrador,claveMigrador -ErrorAction SilentlyContinue
```

Los comandos deben ejecutarse desde la carpeta que contiene los binarios PostgreSQL 18, o sustituir `createdb.exe`/`pg_restore.exe` por sus rutas locales aprobadas. `<RUTA_DUMP_VERIFICADO>` es un marcador: reemplazarlo localmente por la ruta del archivo, sin pegar credenciales. La base de ensayo queda separada dentro del clúster local y con tablas propiedad de `esart_migrador`; `--no-privileges` evita ACL de origen referidas a roles ausentes. Comparar por separado la matriz de grants original con los grants que recrean p0016/p0018.

Ejecute los conteos exactos de las 21 tablas y la revisión inicial con `psql` conectado a la copia como `esart_migrador`, usando el SQL de solo lectura `docs/ESART_P0018_CONTEOS_EXACTOS_SOLO_LECTURA.sql`. La herramienta `backend/herramientas/verificar_respaldo_aislado.py` puede crear además un clúster PostgreSQL temporal con puerto aleatorio y comprobar claves foráneas e índices; todavía requiere preparar `archivo_verificado.json` y no aplica migraciones.

## 5. Estado de migraciones y límites

- La revisión instalada reportada es p0014. El marcador debe confirmarse otra vez en la copia antes de migrar.
- p0015/p0017 requieren ownership de `esart.auditoria_eventos` para sustituir su CHECK. La restauración `--no-owner` como `esart_migrador` le da ownership solo en la copia.
- p0016 puede insertar filas académicas derivadas y debe compararse antes/después.
- p0018 sigue bloqueada por las cinco tablas legadas. No se eliminó la guarda y no se ha escrito una migración conciliatoria final: la cuenta de aplicación no puede leer datos ni conteos exactos para validar las correspondencias de identidad, documento, solicitud, consentimiento, firma y evidencia.
- No ejecutes `alembic upgrade` todavía. Primero hay que disponer del dump restaurado, conteos exactos, relaciones y valores de estados/tipos; cerrar la matriz definitiva; implementar una migración aditiva y probarla en la copia. No usar `stamp`, editar `alembic_version` ni migrar `esart_db` sin autorización expresa posterior.
