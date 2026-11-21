# Preparación y validación de p0018

## Estado verificado

- PostgreSQL: `esart_db`, servidor local `127.0.0.1`, entorno configurado `desarrollo`.
- Cuentas de login: `esart_aplicacion` (no superusuario) y `postgres` (superusuario). No existe `esart_migrador` ni `esart_respaldo`.
- `esart_aplicacion` es dueño de la base, pero no puede leer `esart.alembic_version`; las tablas core y Alembic pertenecen a `postgres`. No fue posible leer la revisión aplicada sin usar la cuenta superusuario.
- La historia local de Alembic está conectada: p0018 depende de p0017 y p0017 de p0016; la historia completa tiene un merge p0010 y `p0018_firma_documental` es el único head. Esto valida el grafo de archivos, no la revisión instalada en PostgreSQL.
- El script anterior guardaba `ESART_MIGRACIONES_URL` en `backend/.env` con la cuenta superusuario. Esa línea ya se retiró; `URL_BASE_DATOS` de `esart_aplicacion` se conservó. Alembic lee la URL migradora solo del entorno del proceso. Las otras referencias del repositorio son nombres de variable o instrucciones, no copias de la credencial.
- La ruta privada predeterminada existe ahora en `backend/almacen_privado/documentos`. Herencia NTFS desactivada; ACL limitada a la cuenta de desarrollo, SYSTEM y Administradores. La carpeta está excluida de Git. La persistencia sigue desactivada (`DOCUMENTOS_PERSISTENCIA_HABILITADA=false`) hasta instalar las tablas.
- Había un dump antiguo (`backend/respaldos/esart_db_pre_alembic.dump`); `pg_restore --list` lo pudo leer, pero no es un respaldo previo a p0018 y no se restauró. Su directorio padre hereda ACL amplias. Se creó `backend/respaldos/p0018_privado` con herencia desactivada y acceso limitado a la cuenta de desarrollo, SYSTEM y Administradores; la nueva herramienta falla si esa ruta no existe.

## Revisión SQL de p0018

La revisión solo crea objetos nuevos en `esart_firma`, añade un componente y sus filas de permisos, y concede acceso a la API sobre las tablas nuevas. Conserva `esart_ref.usuarios`, `esart.personal_militar`, `esart.cursos` y `esart.auditoria_eventos` mediante referencias; no altera la restricción de auditoría core. `upgrade` no ejecuta operaciones `DROP`, `TRUNCATE`, `DELETE` ni `UPDATE`; la palabra `DELETE` aparece solo al revocar ese privilegio en las tablas recién creadas de `esart_firma`. No modifica datos académicos. El `downgrade` es local, protegido y se niega si hay documentos, evidencias o permisos de firma personalizados.

La guarda de Alembic y la de p0018 exigen `ENTORNO=desarrollo`, servidor local, usuario `esart_migrador` no-superusuario y base `esart_db`. Para probar una copia se permite únicamente el nombre exacto `esart_db_p0018_restore_test` con `ESART_VALIDAR_P0018_COPIA=1`.

## Rotación y referencias a la credencial

La contraseña que apareció en una salida de error debe considerarse expuesta. No está repetida en este informe. La URL superusuario ya se eliminó de `backend/.env`, pero la contraseña de PostgreSQL no se ha rotado. No guardes credenciales migradoras ahí. La URL de Alembic se entrega solo al proceso que ejecuta la operación. La URL de aplicación `URL_BASE_DATOS` pertenece a `esart_aplicacion` y no se cambió.

Abre una sesión interactiva de `psql`:

```powershell
psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres -W
```

Dentro del indicador de `psql`, rota la clave sin eco y sal:

```text
\password postgres
\q
```

`psql` solicita la clave sin mostrarla. Actualiza también su registro en el gestor de secretos local. No uses esa cuenta para `alembic upgrade`.

## Roles mínimos preparados

`backend/migraciones_principal/preparar_roles_firma.sql` crea dos roles sin privilegios de superusuario: `esart_migrador` para p0018 y `esart_respaldo` de solo lectura para `pg_dump`. La cuenta migradora solo recibe `CREATE` en `esart_db`, uso de esquemas core, referencias a las tres tablas padre, lectura/inserción de los catálogos que p0018 modifica y DML limitado a `esart.alembic_version`. No recibe `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS` ni pertenencia a `postgres`.

Ejecuta el SQL después de rotar la cuenta, interactivamente para que `\\password` solicite las claves:

```powershell
psql -X -h 127.0.0.1 -p 5432 -U postgres -d esart_db -W -v ON_ERROR_STOP=1 -f backend/migraciones_principal/preparar_roles_firma.sql
```

Este paso crea roles y concede privilegios; no ejecuta Alembic. Requiere autorización operativa por separado.

### Compatibilidad con revisiones anteriores

El SQL anterior solo otorga permisos para p0018. Si `alembic_version` indica p0016, p0016 aún requiere lecturas/escrituras sobre `esart.hoja_vida_artillero`, `esart.cursos`, `esart.tipos_curso` y `esart.artillero_cursos`, además de `GRANT OPTION` para otorgar permisos a `esart_aplicacion`. p0017 requiere cambiar el `CHECK` de `esart.auditoria_eventos`; PostgreSQL no ofrece `GRANT ALTER`, así que su ejecutor debe ser dueño de esa tabla. También necesita leer/escribir `seguridad.politicas_accion`.

Las tablas existentes son propiedad de `postgres`. No concedas membresía a `postgres` ni ejecutes la cadena sin determinar primero la revisión instalada. En una copia restaurada con `pg_restore --no-owner`, los objetos quedan creados por quien restaura y la cuenta migradora puede ejecutar las revisiones pendientes en ese entorno aislado. Para la base operativa de desarrollo, resuelve cualquier p0016/p0017 pendiente mediante un procedimiento de propiedad aprobado; p0018 por sí sola sí se diseñó para `esart_migrador`.

## Respaldo y prueba aislada

No hay respaldo nuevo previo a p0018. El dump antiguo es legible por `pg_restore`, pero no se restauró. La única URL de migraciones que estaba en `.env` apuntaba a la cuenta superusuario; ya se retiró. La herramienta nueva requiere `ESART_RESPALDO_URL` para una cuenta de respaldo separada. No se intentó restauración ni se ejecutó migración.

Después de preparar los dos roles, abre PowerShell y captura la clave de `esart_respaldo` con `Get-Credential` (el valor no se escribe en el comando):

```powershell
$c = Get-Credential -UserName 'esart_respaldo'
$p = (New-Object System.Net.NetworkCredential('', $c.Password)).Password
$env:ESART_RESPALDO_URL = 'postgresql+asyncpg://' + [uri]::EscapeDataString($c.UserName) + ':' + [uri]::EscapeDataString($p) + '@127.0.0.1:5432/esart_db'
Push-Location backend
..\.venv\Scripts\python.exe -m herramientas.respaldo_previo_firma_documental
Pop-Location
Remove-Item Env:ESART_RESPALDO_URL
Remove-Variable c,p
```

La herramienta verifica entorno, base, host, rol no-superusuario, crea un dump custom, comprueba que `pg_restore --list` pueda leerlo y reporta tamaño y SHA-256. Ese listado comprueba el archivo, no una restauración completa.

Para restaurarlo aisladamente, después de obtener el respaldo, usa la cuenta administrativa recién rotada solo para crear la base vacía (nunca para Alembic):

```powershell
createdb -h 127.0.0.1 -p 5432 -U postgres -O esart_migrador esart_db_p0018_restore_test
pg_restore --exit-on-error --no-owner -h 127.0.0.1 -p 5432 -U esart_migrador -d esart_db_p0018_restore_test backend/respaldos/p0018_privado/<dump-verificado>.dump
```

Verifica el `alembic_version` restaurado:

```powershell
psql -X -h 127.0.0.1 -p 5432 -U esart_migrador -d esart_db_p0018_restore_test -W -c 'SELECT version_num FROM esart.alembic_version'
```

Para aplicar la revisión en la copia, captura la clave en memoria (sin guardarla en `.env`) y ejecuta desde `backend`:

```powershell
$c = Get-Credential -UserName 'esart_migrador'
$p = (New-Object System.Net.NetworkCredential('', $c.Password)).Password
$env:ESART_MIGRACIONES_URL = 'postgresql+asyncpg://' + [uri]::EscapeDataString($c.UserName) + ':' + [uri]::EscapeDataString($p) + '@127.0.0.1:5432/esart_db_p0018_restore_test'
$env:ESART_VALIDAR_P0018_COPIA = '1'
Push-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade p0018_firma_documental
Pop-Location
Remove-Item Env:ESART_MIGRACIONES_URL,Env:ESART_VALIDAR_P0018_COPIA
Remove-Variable c,p
```

Luego comprueba tablas, claves foráneas, triggers y revisión `p0018_firma_documental` antes de considerar la base de desarrollo original. Si la revisión restaurada no es p0017, no continúes con la base original hasta resolver permisos de las revisiones pendientes.

Tras la prueba de copia, el comando exacto para la base de desarrollo original será el mismo bloque con la URL terminada en `/esart_db`, quitando `ESART_VALIDAR_P0018_COPIA`. Ejecútalo solo con autorización expresa posterior al respaldo y a la validación aislada.

## Bloqueos pendientes

1. Rotar la credencial expuesta; su URL ya se eliminó de `backend/.env`.
2. Autorizar la creación de `esart_migrador` y `esart_respaldo` con el SQL preparado.
3. Crear y verificar respaldo completo y restaurarlo en la base aislada.
4. Leer la revisión aplicada. Si p0017 aún está pendiente, sus cambios sobre tablas propiedad de `postgres` no caben en los permisos mínimos de p0018; no se debe intentar la actualización hasta resolverlo sin ejecutar Alembic como `postgres`.
5. Ejecutar p0018 en la copia restaurada con `esart_migrador`; revisar el resultado.
6. Solo después del respaldo verificado, de la prueba aislada y de autorización expresa se podrá ejecutar p0018 en `esart_db`.

No se modificó producción, no se cambió ninguna contraseña, no se creó ningún rol SQL y no se ejecutó p0018. Se quitó `ESART_MIGRACIONES_URL` del archivo local, sin alterar la URL de la aplicación.

La consulta de `alembic_version` fue denegada para `esart_aplicacion`; por eso la revisión instalada sigue sin confirmar. `alembic heads/history` valida únicamente el grafo local de archivos.

## Pruebas de esta preparación

- Almacenamiento privado y generadores PDF: 13 aprobadas, 2 omitidas.
- Reglas utilitarias de verificación académica: 11 aprobadas.
- Ruff y compilación Python: correctos.
- `alembic heads/history`: head p0018 y cadena p0017 → p0016 comprobados en el repositorio.
- Dump antiguo: legible por `pg_restore --list`; no restaurado y no aceptado como respaldo p0018.
- No hubo respaldo nuevo, prueba de restauración, aplicación Alembic ni escritura en PostgreSQL.
