# ESART: comandos para ejecución personal del operador

16 de noviembre de 2026. **Ningún comando de respaldo, creación o restauración de este documento se ha ejecutado.** Ejecutar por bloques revisando cada salida, no pegar el documento completo como un script. Las contraseñas se introducen exclusivamente en el prompt nativo local, nunca en el chat ni en argumentos/variables de los comandos.

## Destinos propuestos

- Origen: 127.0.0.1:5432/esart_db, propietario postgres.
- Respaldo: D:\RespaldosPrivados\ESART, fuera del repositorio. El operador debe verificar ACL privadas y espacio suficiente antes de usarlo; el procedimiento no concede permisos de archivos automáticamente.
- Destino preferido: **otra instancia PostgreSQL 18** local, puerto propuesto 55432, base nueva **esart_restauracion_pruebas**, almacenamiento propio. El puerto/instancia deben existir y estar confirmados; no se provisionan automáticamente aquí. Configurar la instancia aislada sin jobs, integraciones externas ni acceso de clientes reales.

No usar una base con el mismo nombre en el clúster principal, --clean ni --create al restaurar este ensayo. El nombre distinto sirve para validar restauración sin migraciones. env.py exige esart_db: **no ejecutar Alembic contra esart_restauracion_pruebas ni modificar env.py para forzarlo**. Un ensayo futuro de migraciones necesitará una instancia separada con esart_db y autorización independiente.

Una base distinta en el mismo clúster comparte roles, recursos, tablespaces y extensiones disponibles; ofrece menor aislamiento y puede producir carga en producción. Por ello aquí se fija 55432 distinto de 5432 y se rechaza el destino del origen. Confirmar también instancia/directorio de datos, no solo el puerto. Ningún diseño protege de comandos ejecutados con parámetros equivocados: revisar identidad en cada paso.

## 1. Variables y comprobaciones locales

```powershell
$pgEsart = 'C:\Program Files\PostgreSQL\18\bin'
$origenHostEsart = '127.0.0.1'
$origenPuertoEsart = 5432
$destinoHostEsart = '127.0.0.1'
$destinoPuertoEsart = 55432
$destinoBaseEsart = 'esart_restauracion_pruebas'
$raizRespaldoEsart = 'D:\RespaldosPrivados\ESART'
& "$pgEsart\pg_dump.exe" --version
& "$pgEsart\pg_restore.exe" --version
# Antes de crear archivos: revisar ACL del directorio privado ya preparado.
Get-Acl -LiteralPath $raizRespaldoEsart | Format-List
```

No continuar si el directorio no existe o su acceso no está restringido. Asegurar las claves originales AES TOTP/JWT en el gestor seguro, por separado del dump. El respaldo contiene hashes, secretos cifrados y datos personales: no guardarlo en Git ni enviar su contenido por chat.

## 2. Identificar origen, detener escritores y capturar evidencia

El operador detiene FastAPI y todos los demás escritores mediante su mecanismo habitual. No se matan sesiones automáticamente ni se cambian privilegios. Conservar la ventana sin escritores hasta finalizar el baseline y el dump.

```powershell
& "$pgEsart\psql.exe" -X --host=$origenHostEsart --port=$origenPuertoEsart --username=postgres --password --dbname=esart_db --set=ON_ERROR_STOP=1 --command="BEGIN READ ONLY; SELECT current_database(),current_user,inet_server_addr(),inet_server_port(),pg_postmaster_start_time(),current_setting('data_directory'),current_setting('transaction_read_only'); ROLLBACK;"
if ($LASTEXITCODE -ne 0) { throw 'No se pudo identificar el origen.' }
```

Verificar personalmente que es la instancia esperada. Tras revisar la ubicación privada, crear subdirectorio único y ejecutar SQL **solo lectura**:

```powershell
$carpetaRespaldoEsart = Join-Path $raizRespaldoEsart ('pre_p0010_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $carpetaRespaldoEsart -ErrorAction Stop | Out-Null
$repoEsart = 'D:\2026\esart\esart\esart'
& "$pgEsart\psql.exe" -X --host=$origenHostEsart --port=$origenPuertoEsart --username=postgres --password --dbname=esart_db --set=ON_ERROR_STOP=1 --file=(Join-Path $repoEsart 'docs\ESART_ALEMBIC_PREFLIGHT_PROPIETARIO.sql') --output=(Join-Path $carpetaRespaldoEsart 'preflight_origen.txt')
if ($LASTEXITCODE -ne 0) { throw 'Preflight incompleto; detener procedimiento.' }
& "$pgEsart\psql.exe" -X --host=$origenHostEsart --port=$origenPuertoEsart --username=postgres --password --dbname=esart_db --set=ON_ERROR_STOP=1 --file=(Join-Path $repoEsart 'docs\ESART_ALEMBIC_IMPACTO_HU10_SOLO_LECTURA.sql') --output=(Join-Path $carpetaRespaldoEsart 'impacto_hu10.txt')
if ($LASTEXITCODE -ne 0) { throw 'Comparación HU-10 incompleta.' }
```

Conservar también horas de inicio/fin. Confirmar p0004 y seis conteos cero. Investigar cualquier reaparición del huérfano 1→0; no corregirlo mediante borrados. El archivo de preflight no impide por sí mismo que otro cliente escriba: la detención de escritores es operativa.

## 3. Respaldo maestro completo

```powershell
$archivoDumpEsart = Join-Path $carpetaRespaldoEsart 'esart_db.dump'
& "$pgEsart\pg_dump.exe" --host=$origenHostEsart --port=$origenPuertoEsart --username=postgres --password --dbname=esart_db --format=custom --create --verbose --file=$archivoDumpEsart 2> (Join-Path $carpetaRespaldoEsart 'pg_dump.log')
if ($LASTEXITCODE -ne 0) { throw 'Dump completo fallido; no aceptar respaldo.' }
& "$pgEsart\pg_dumpall.exe" --host=$origenHostEsart --port=$origenPuertoEsart --username=postgres --password -l esart_db --globals-only --no-role-passwords --file=(Join-Path $carpetaRespaldoEsart 'globals_sin_passwords.sql') 2> (Join-Path $carpetaRespaldoEsart 'globals.log')
if ($LASTEXITCODE -ne 0) { throw 'Globales incompletos.' }
& "$pgEsart\pg_restore.exe" --list $archivoDumpEsart | Set-Content -Encoding UTF8 (Join-Path $carpetaRespaldoEsart 'contenido.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo leer el archivo.' }
Get-FileHash -Algorithm SHA256 -LiteralPath $archivoDumpEsart | Format-List | Out-File (Join-Path $carpetaRespaldoEsart 'sha256_dump.txt')
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $carpetaRespaldoEsart 'globals_sin_passwords.sql') | Format-List | Out-File (Join-Path $carpetaRespaldoEsart 'sha256_globals.txt')
```

No hay filtros: incluye estructura, datos, secuencias, funciones, triggers, índices, restricciones, ownership y ACL de la base; globales aparte. Extensiones requieren sus binarios compatibles en el destino. Configuración del servicio, binarios de extensiones, archivos externos y claves no se recuperan mediante pg_dump. Globales excluye contraseñas de roles: recuperarlas por el gestor seguro. No ejecutar globals_sin_passwords.sql durante esta fase: reproduciría roles/membresías/tablespaces y requiere revisión/autorización. No aceptar un fallback --schema-only.

## 4. Inspección del destino, antes de crear nada

Los bloques siguientes quedan preparados para ejecución posterior del operador. No se han ejecutado aquí. Revisar el TOC y las funciones/extensiones del respaldo antes de restaurar; restaurar un dump ejecuta código del origen. Confirmar que funciones, políticas o referencias externas no apuntan al servicio original.

```powershell
if ($destinoBaseEsart -ne 'esart_restauracion_pruebas') { throw 'Nombre de destino no aprobado.' }
if ($destinoHostEsart -eq $origenHostEsart -and $destinoPuertoEsart -eq $origenPuertoEsart) { throw 'Se requiere instancia separada para este procedimiento.' }
& "$pgEsart\psql.exe" -X --host=$destinoHostEsart --port=$destinoPuertoEsart --username=postgres --password --dbname=postgres --set=ON_ERROR_STOP=1 --command="BEGIN READ ONLY; SELECT current_database(),current_user,inet_server_addr(),inet_server_port(),pg_postmaster_start_time(),current_setting('data_directory'); SELECT datname FROM pg_database WHERE datname IN ('esart_db','esart_restauracion_pruebas'); ROLLBACK;"
if ($LASTEXITCODE -ne 0) { throw 'Destino aislado no disponible o no identificado.' }
```

**Pausa de revisión del operador:** directorio de datos e instancia distintos; esart_restauracion_pruebas no existe; no hay conexiones de la aplicación al destino. Si ya existe la base de prueba, detenerse, no borrarla ni sobrescribirla. Comprobar tablespaces: el ensayo siguiente usa --no-tablespaces para impedir restaurar rutas de almacenamiento del origen; esa omisión se registra como límite del ensayo.

## 5. Creación y restauración de ensayo sin aplicar ACL

Solo cuando el operador decida ejecutar la creación y restauración preparadas, después de la inspección anterior:

```powershell
& "$pgEsart\createdb.exe" --host=$destinoHostEsart --port=$destinoPuertoEsart --username=postgres --password --maintenance-db=postgres --template=template0 --owner=postgres $destinoBaseEsart
if ($LASTEXITCODE -ne 0) { throw 'No se creó el destino vacío; no restaurar.' }
& "$pgEsart\pg_restore.exe" --host=$destinoHostEsart --port=$destinoPuertoEsart --username=postgres --password --dbname=$destinoBaseEsart --exit-on-error --single-transaction --no-owner --no-privileges --no-tablespaces --verbose $archivoDumpEsart 2> (Join-Path $carpetaRespaldoEsart 'pg_restore_ensayo.log')
if ($LASTEXITCODE -ne 0) { throw 'Restauración fallida; conservar logs y no reintentar sobre destino parcial.' }
```

Sin --create: se restaura en la base de prueba indicada, no en el nombre original guardado en el archivo. Por eso aquí sí se puede usar --single-transaction. Se omiten ownership/ACL/tablespaces explícitos del archivo; los objetos nuevos pertenecen al restaurador. Antes de createdb, comparar encoding, LC_COLLATE, LC_CTYPE y proveedor de locale de origen con la instancia de prueba; si difieren, fijar los parámetros equivalentes soportados en createdb antes de ejecutar, no aceptar silenciosamente los defaults. Hay que confirmar que event triggers del destino y funciones/extensiones del archivo no ejecutan cambios de permisos ni efectos externos: --no-privileges omite ACL del dump, no inspecciona código arbitrario.

Esta prueba puede demostrar restauración de datos/esquema, **no recuperación fiel de ACL, tablespaces y ownership de objetos con propietarios distintos**. Aunque el catálogo inspeccionado muestra postgres como propietario de las tablas, no se presupone para todos los objetos de la base. Una recuperación completa con ACL exige autorización posterior para reproducir privilegios en el destino aislado; no quitar --no-privileges sin esa autorización. No ejecutar migraciones en ninguna de las dos bases.

## 6. Verificación de integridad de la copia

```powershell
& "$pgEsart\psql.exe" -X --host=$destinoHostEsart --port=$destinoPuertoEsart --username=postgres --password --dbname=$destinoBaseEsart --set=ON_ERROR_STOP=1 --file=(Join-Path $repoEsart 'docs\ESART_ALEMBIC_PREFLIGHT_PROPIETARIO.sql') --output=(Join-Path $carpetaRespaldoEsart 'preflight_copia.txt')
if ($LASTEXITCODE -ne 0) { throw 'Verificación de copia incompleta.' }
& "$pgEsart\psql.exe" -X --host=$origenHostEsart --port=$origenPuertoEsart --username=postgres --password --dbname=esart_db --set=ON_ERROR_STOP=1 --file=(Join-Path $repoEsart 'docs\ESART_RESTAURACION_CONTEOS_PSQL.sql') --output=(Join-Path $carpetaRespaldoEsart 'conteos_origen.txt')
if ($LASTEXITCODE -ne 0) { throw 'Conteos de origen incompletos.' }
& "$pgEsart\psql.exe" -X --host=$destinoHostEsart --port=$destinoPuertoEsart --username=postgres --password --dbname=$destinoBaseEsart --set=ON_ERROR_STOP=1 --file=(Join-Path $repoEsart 'docs\ESART_RESTAURACION_CONTEOS_PSQL.sql') --output=(Join-Path $carpetaRespaldoEsart 'conteos_copia.txt')
if ($LASTEXITCODE -ne 0) { throw 'Conteos de copia incompletos.' }
```

Este SQL no invoca env.py ni exige nombre esart_db: su primera salida debe mostrar esart_restauracion_pruebas y el puerto aislado. Verificar que el original sigue siendo esart_db:5432 y p0004, sin ejecutar escrituras de prueba en él.

Comparar con preflight_origen.txt: versión p0004, cinco huérfanos y contexto cero, definiciones y validación de restricciones, triggers, políticas, huella de contadores/bloqueos, conteos CAPTCHA/factores y secuencias. Añadir conteos exactos de **todas** las tablas del archivo, no estimaciones. Igualar TimeZone y DateStyle en ambas sesiones al comparar huellas que incluyen timestamps. Comparar también índices y funciones; no basta el código de salida. Registrar excepciones esperadas de ACL/ownership/tablespaces omitidos. Validar acceso a claves originales para descifrado TOTP mediante procedimiento controlado sin imprimirlas ni modificar factores.

No marcar restauración completa como APROBADA hasta completar esas verificaciones y el ensayo de ACL autorizado. No conectar Angular/FastAPI productivos a la copia, no iniciar pruebas de login contra el original durante la comparación. La prueba de restauración no autoriza p0010.

## Recuperación y criterios de parada

Si falla dump/restore/comparación: conservar archivos/logs, detener el procedimiento, no eliminar bases ni restaurar encima de un destino existente. No hacer downgrade ni stamp. El original no se usa como destino en los comandos de restauración: host/puerto/base son explícitos y distintos. El aislamiento y la revisión de código del dump reducen riesgos de efectos externos, pero no se ha demostrado mediante una ejecución real todavía.

Para aprobación posterior faltan: evidencia completa y estable de preflight, impacto real de UPSERT/malla aceptado, privilegios TOTP acordados, respaldo verificado y alcance de recuperación aceptado, ventana/RPO/límites definidos y autorización independiente de ensayo de migraciones y de producción. No se ha efectuado commit/push ni eliminado el stash.
