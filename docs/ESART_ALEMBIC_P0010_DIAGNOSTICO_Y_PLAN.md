# Alembic ESART: diagnóstico previo y plan sujeto a aprobación

Fecha: 16 de noviembre de 2026. **No se ha autorizado ni ejecutado la actualización.**

## Dictamen

El grafo local es válido y tiene una cabeza, p0010_merge_hu10_totp. Las siete tablas TOTP existentes son estructuralmente compatibles con los cambios previstos, pero **la compatibilidad de todos los datos y el historial aplicado no están completamente verificados** con el rol de aplicación. No recomiendo aprobar todavía `upgrade head` tal como está: faltan el preflight del propietario, una decisión explícita sobre la ampliación de privilegios TOTP y una restauración/actualización de ensayo sobre una copia aislada.

No se modificaron migraciones, env.py, configuración protegida ni datos de PostgreSQL. Solo se añadieron documentación y una herramienta de inventario de solo lectura. No se usaron upgrade, stamp, autogenerate, SQL offline, commit ni push. Tampoco se ejecutó un respaldo o una restauración: sus comandos se incluyen para revisión y posterior aprobación.

## Evidencia real y límites

La transacción de diagnóstico fue REPEATABLE READ, READ ONLY y terminó con ROLLBACK. La conexión real es 127.0.0.1:5432/esart_db, PostgreSQL 18.7, como esart_aplicacion. Los objetos examinados pertenecen a postgres. La evidencia está en [ESART_ALEMBIC_P0010_CATALOGO.json](ESART_ALEMBIC_P0010_CATALOGO.json); contiene catálogo, permisos y conteos agregados, nunca contraseñas, claves, secretos ni códigos.

Observado:

- Existen las siete tablas seguridad.usuario_totp, totp_recuperacion, desafios, autorizaciones, politicas_accion, auditoria y auditoria_cambios.
- Los usuario_id son bigint y esart_ref.usuarios.id es bigint. desafios/autorizaciones usan UUID; politica_id es bigint y operacion_hash es varchar(64) en ambos lados. Las PK, UNIQUE y relaciones originales constan en el inventario.
- usuario_totp y las otras tablas con identificador numérico usan GENERATED ALWAYS AS IDENTITY. Los nombres de secuencia previstos por TOTP coinciden con el inventario anterior. La migración no sustituye estas columnas ni sus secretos cifrados.
- No existen las cinco FK de usuarios propuestas, uq_desafio_contexto, fk_autorizacion_contexto, la función TOTP ni sus cuatro triggers. Su creación no colisiona con esos nombres en el catálogo observado.
- Conteos de huérfanos de usuario: usuario_totp=0, totp_recuperacion=0 y desafios=0. **Auditoria y autorizaciones quedan pendientes del propietario**, porque el rol actual no puede leer sus usuario_id. Tampoco pudo comprobarse la coincidencia compuesta de las autorizaciones.
- LOGIN_TOTP y DESBLOQUEO_TOTP existen, activas, requieren TOTP y duran 120 segundos. Las siete políticas de CURSOS/PERSONAL también existen; su permiso_requerido es NULL.
- Existen componentes, rol_permisos y usuario_permisos, pero la aplicación no puede leerlos todavía. No se afirma que estén vacíos.
- No aparecen parametros_habilitacion ni auditoria_eventos como tablas en el catálogo consultado. No existen las funciones/triggers de auditoría examinados.
- requiere_cambio_contrasena existe, pero la aplicación no puede actualizar esa columna, contrasena_hash, activo ni actualizado_en. Sí conserva los permisos de columnas de último acceso, intentos y bloqueo.
- esart.alembic_version existe, pero el rol de aplicación no tiene SELECT. **No se pudo confirmar su contenido.** La presencia de una columna no demuestra que p0009 ni sus antecesoras estén registradas/aplicadas.

El operador debe ejecutar [ESART_ALEMBIC_PREFLIGHT_PROPIETARIO.sql](ESART_ALEMBIC_PREFLIGHT_PROPIETARIO.sql) con su conexión autorizada y entregar los resultados sin credenciales. No se pide conceder lectura del historial ni de secretos al backend.

## Configuración Alembic

- backend/alembic.ini apunta exclusivamente a migraciones_principal. El historial UUID antiguo tiene otra configuración y no debe mezclarse con esart_db.
- env.py requiere ESART_MIGRACIONES_URL, sin fallback a la cuenta FastAPI. Verifica current_database()='esart_db', pero **no comprueba por sí solo host, puerto ni que el usuario sea propietario**. Estos se verifican en el preflight.
- El modo --sql está expresamente rechazado. No se propone sortearlo ni convertir el catálogo real en un SQL offline incompleto. Autogenerate también se rechaza.
- Incluso invocaciones que carguen env.py para consultar el estado ejecutan CREATE SCHEMA IF NOT EXISTS esart. Por eso aquí no se ejecutó `alembic current` como supuesto diagnóstico de solo lectura: se intentó leer directamente la tabla de versiones con comprobación previa de permisos.
- El mensaje de error del modo offline menciona stamp, pero el archivo **no constituye un bloqueo explícito de todas las invocaciones online de stamp**. La prohibición de usarlo se mantiene en este procedimiento.
- El modo normal abre una transacción externa con motor.begin(); env.py ejecuta las migraciones dentro de ella. No hay autocommit_block ni COMMIT explícitos en estas revisiones. Se espera una transacción conjunta de DDL/DML/versión; no una confirmación por revisión. Esto también se contrastó con MigrationContext.begin_transaction de Alembic 1.14 instalado, que no abre otra transacción si ya hay una externa.
- Un rollback no recupera necesariamente valores consumidos de secuencias. Un salto de identidad no autoriza a ejecutar setval ni implica pérdida de filas. [PostgreSQL: secuencias](https://www.postgresql.org/docs/18/functions-sequence.html).

## Grafo revisado

```text
p0004_captcha_local
 ├─ p0005_componentes_y_malla
 │   └─ p0006_parametros_habilitacion
 │       └─ p0007_auditoria_eventos
 │           └─ p0008_malla_editable
 │               └─ p0009_gestion_usuarios ─┐
 └─ p0005_integracion_totp ─────────────────┴─ p0010_merge_hu10_totp
```

Los dos p0005 tienen revision diferentes: no hay colisión de identificadores. p0010 tiene ambas cabezas como down_revision y upgrade/downgrade vacíos. No cambia por sí misma tablas ni permisos, pero llegar a ella requiere aplicar las revisiones de ambas ramas que falten. **La rama TOTP puede ejecutarse antes o después de parte de la otra rama; no se debe asumir un orden global basado en el nombre del archivo.** El estado inicial real se decide exclusivamente tras leer alembic_version y conciliarlo con el catálogo, nunca mediante stamp.

## Operaciones y riesgos por revisión

| Revisión | Upgrade efectivo | Riesgo y comprobación |
|---|---|---|
| p0004_captcha_local | Crea desafios_captcha, altera referencias de auditoria_acceso y concede acceso CAPTCHA limitado. | Es el punto de referencia pedido, no una revisión que deba repetirse. Si sus objetos existen pero el historial pretende ejecutarla de nuevo, detener la actualización y conciliar el historial. |
| p0005_componentes_y_malla | Inserta roles faltantes; hace UPSERT de componentes; inserta permisos por rol solo si no existen; concede lectura de la malla. | **El UPSERT de componentes sí sobrescribe nombre, ruta, orden, padre y activo**. Puede desactivar módulos de segunda entrega previamente activados o reemplazar rutas personalizadas. No altera permisos ya existentes, pero sí concede los faltantes según la malla: incluye VER_DOCUMENTO_COMPLETO para USUARIO. Requiere aprobación de esa visibilidad y comparación previa de componentes/permisos. |
| p0006_parametros_habilitacion | Crea parametros_habilitacion, FK de actualizado_por_id, cuatro parámetros y grants de lectura académica/edición de valores. | CREATE TABLE no tolera una tabla ya existente. Parametriza cursos SACLI/SACME, 12 meses y alerta de 60 días; validar reglas de habilitación acordadas. No modifica parámetros existentes mediante el INSERT, pero una repetición falla antes en CREATE TABLE. |
| p0007_auditoria_eventos | Crea tabla, índices, CHECK de acciones, función CREATE OR REPLACE, dos triggers y SELECT/INSERT al backend. | Una tabla/índice/trigger ya existente puede hacerla fallar. Revisar si la función del mismo nombre ya tiene otros consumidores antes de reemplazarla. Auditoría HU-11 es dependencia de login/administración: falta de tabla o privilegio puede bloquear esas operaciones. No es una alteración de auditoria_acceso ni de seguridad.auditoria. |
| p0008_malla_editable | GRANT SELECT/INSERT/UPDATE/DELETE de rol_permisos y usuario_permisos a la cuenta de aplicación. | Es necesario para la gestión web, pero amplía capacidad de modificación SQL. La separación por usuario y las protecciones administrativas están en FastAPI; probar 403 de usuarios sin permiso y auditoría de cambios. No modifica politicas_accion ni elimina filas durante upgrade. |
| p0009_gestion_usuarios | Sustituye el CHECK de acciones de auditoria_eventos para agregar cuatro eventos; GRANT UPDATE de contrasena_hash, activo, requiere_cambio_contrasena y actualizado_en. | Depende del nombre exacto ck_auditoria_eventos_ck_auditoria_eventos_accion y de que las filas cumplan la lista. No añade requiere_cambio_contrasena: debe existir y coincidir con la línea base real. No cambia contraseñas ni flags durante upgrade. Los nuevos grants requieren comprobar actor, CSRF, MFA y auditoría en las rutas de gestión. |
| p0005_integracion_totp | Añade cinco FK de usuario, UNIQUE compuesto, FK compuesta, función y cuatro triggers; inserta dos políticas si faltan; concede y revoca privilegios. | Compatibilidad estructural observada, datos parcialmente pendientes y ampliación de privilegios que necesita decisión explícita; detalle siguiente. |
| p0010_merge_hu10_totp | Sin DDL/DML propio; unifica el grafo. | No sanea diferencias manuales ni sustituye revisiones incompletas. No aprobarla como si fuera el único cambio pendiente. |

## Revisión específica TOTP

La revisión no crea/recrea las siete tablas ni modifica secreto_cifrado, codigo_hash, los intervalos aceptados, estados, desafíos ni cuentas existentes. Añade integridad sobre esos datos:

1. Cinco FK usuario_id → esart_ref.usuarios.id, primero NOT VALID y luego VALIDATE en la misma transacción. Auditoria.usuario_id puede ser NULL; los eventos anónimos siguen siendo admisibles. Los no nulos deben corresponder a una cuenta.
2. UNIQUE(id,usuario_id,politica_id,operacion_hash) en desafios, para ser referencia de la FK compuesta. Si id ya es PK, la combinación es necesariamente única; aun así se crea otro índice con coste de espacio y bloqueo.
3. FK compuesta de autorizaciones que exige coincidir con el desafío en actor, política y huella. La FK antigua solo comprobaba desafio_id, de modo que pueden existir inconsistencias antiguas que ahora impidan validar. Se deben corregir mediante un procedimiento autorizado, nunca borrar filas para pasar la migración.
4. Función y cuatro triggers que prohíben UPDATE/DELETE/TRUNCATE de auditoria y auditoria_cambios. No se borra auditoría. Si ya existen esos nombres por cambios manuales, la revisión falla: no usa CREATE OR REPLACE para la función ni IF NOT EXISTS para esas restricciones/triggers.
5. LOGIN_TOTP/DESBLOQUEO_TOTP usan ON CONFLICT(codigo) DO NOTHING. Las filas actuales activas de 120 segundos quedan intactas. Esto tampoco corrige automáticamente una política existente desactivada o modificada.

**Permisos a aprobar antes de ejecutar el archivo actual:**

- Concede SELECT/INSERT y UPDATE(resultado,consumida_en) sobre seguridad.autorizaciones. Esa ampliación no se requiere para login/QR/TOTP y no forma parte de los permisos mínimos previamente autorizados. Sigue pendiente de autorización específica.
- Amplía auditoria/auditoria_cambios desde SELECT de columnas devueltas por RETURNING a SELECT de toda la tabla. Eso permite leer sus metadatos completos, no solo id/fechas.
- Concede USAGE/SELECT sobre cuatro secuencias. La generación identity usada por este flujo no requiere acceso directo a esas secuencias; son privilegios adicionales respecto al mínimo.
- REVOKE UPDATE/DELETE/TRUNCATE retira grants de tabla al rol, pero no es una limpieza exhaustiva de privilegios por columna, heredados o PUBLIC. Los triggers impiden las mutaciones ordinarias; revisar ACL efectivas, no dar por hecho que el REVOKE eliminó todas las vías de concesión.

Decisión requerida: aprobar expresamente la matriz ampliada o revisar la propuesta TOTP para mantener los mínimos y tratar operaciones sensibles por separado. **Esta revisión de diagnóstico no modificó la migración para tomar esa decisión por el operador.** No debe concederse acceso a autorizaciones solo para conseguir que upgrade head termine.

Las FK y las validaciones toman bloqueos; NOT VALID seguido inmediatamente de VALIDATE dentro de una sola transacción no divide el trabajo en ventanas independientes. Deben medirse tiempos en la copia y planificar mantenimiento. [PostgreSQL: ALTER TABLE](https://www.postgresql.org/docs/18/sql-altertable.html).

## CAPTCHA, bloqueo y MFA frente a HU-10

Los upgrades p0005_componentes_y_malla a p0009 no actualizan desafios_captcha, respuesta_hmac, limites_inicio_ip, estados_acceso_anonimos, contadores/bloqueado_hasta de usuarios ni los secretos TOTP. No alteran el diseño Angular, el umbral de siete ni las tres horas; esos controles permanecen en los servicios.

El riesgo es indirecto y operativo: nuevos permisos de malla, falta de auditoria_eventos, CHECK de acciones incompatible o grants incompletos pueden impedir completar la autenticación. Debe desplegarse el código coordinadamente con el esquema aprobado, sin quitar auditoría, aceptar sesiones parciales ni desactivar MFA para evitar errores.

El contrato combinado mantiene: contraseña → CAPTCHA/bloqueo → cambio temporal restringido cuando corresponda → vinculación/validación TOTP → JWT definitivo. El cambio temporal usa un desafío, no una sesión completa. Los CHECK de estados de desafios permiten ese propósito porque recurso_tipo no se limita a LOGIN/DESBLOQUEO. Ninguna de estas revisiones debe reiniciar contraseñas, factores o bloqueos para habilitar HU-10.

## Procedimiento de respaldo propuesto — NO ejecutado

### Condiciones

1. Aprobación del propietario y mantenimiento coordinado: detener API, workers y cualquier escritor antes del respaldo final. Así los estados de autenticación, auditoría, malla y Alembic corresponden al mismo corte sin actividad posterior hasta validar.
2. Confirmar servidor/puerto/base/propietario con el preflight. En el catálogo observado el propietario es postgres; no utilizar esart_aplicacion para backup completo o migraciones, ni cambiar URL_BASE_DATOS de la API a postgres.
3. Usar herramientas PostgreSQL 18 compatibles con el servidor, espacio suficiente y directorio privado fuera del repositorio. El dump contendrá datos personales, hashes de contraseña, secretos cifrados y recuperación: tratarlo como material sensible.
4. Conservar por separado en un gestor/volumen cifrado la configuración y las claves TOTP/JWT originales. Un dump no contiene la clave externa de AES-GCM. La clave JWT también participa en seudónimos de límites/contextos; no regenerarla como parte del respaldo o la migración.

### Comandos PowerShell para que el operador los revise y ejecute tras aprobación

En una terminal dedicada, las opciones --password piden la credencial sin incluirla en la línea de comandos. Sustituir destino/propietario únicamente por valores verificados. No reutilizar esta plantilla contra otra instancia sin repetir el preflight.

```powershell
$pgEsart = 'C:\Program Files\PostgreSQL\18\bin'
$respaldoEsart = Join-Path 'D:\RespaldosPrivados\ESART' ('pre_p0010_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $respaldoEsart -ErrorAction Stop | Out-Null
# El operador debe establecer/verificar ACL privadas del directorio antes de continuar.
$dumpEsart = Join-Path $respaldoEsart 'esart_db.dump'
& "$pgEsart\pg_dump.exe" --host=127.0.0.1 --port=5432 --username=postgres --password --dbname=esart_db --format=custom --create --file=$dumpEsart
if ($LASTEXITCODE -ne 0) { throw 'Respaldo completo fallido; no actualizar.' }
& "$pgEsart\pg_dumpall.exe" --host=127.0.0.1 --port=5432 --username=postgres --password -l esart_db --globals-only --no-role-passwords --file=(Join-Path $respaldoEsart 'globals_sin_passwords.sql')
if ($LASTEXITCODE -ne 0) { throw 'Respaldo de roles/globales fallido; revisar antes de actualizar.' }
& "$pgEsart\pg_restore.exe" --list $dumpEsart | Set-Content -Encoding UTF8 (Join-Path $respaldoEsart 'contenido.txt')
if ($LASTEXITCODE -ne 0) { throw 'Archivo de respaldo no legible; no actualizar.' }
Get-FileHash -Algorithm SHA256 -LiteralPath $dumpEsart | Format-List | Out-File (Join-Path $respaldoEsart 'sha256.txt')
```

No usar --no-owner ni --no-acl para el dump maestro. No sustituir el respaldo completo por --schema-only si falta acceso a datos. La herramienta antigua diagnosticar_integracion usa la conexión configurada de aplicación y admite un fallback estructural: **ese fallback no satisface este requisito de recuperación**. Tampoco se necesita generar un SQL plano con todos los datos en el repositorio.

pg_dump respalda una base; los roles/tablespaces son globales y requieren respaldo aparte. --no-role-passwords evita exportar verificadores de contraseñas de roles: su recuperación debe estar cubierta por el gestor de credenciales, no asumirse incluida. [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html), [pg_dumpall](https://www.postgresql.org/docs/18/app-pg-dumpall.html).

### Demostración de restauración antes de aprobar producción

- Provisionar, con autorización separada, una instancia aislada en otro puerto/directorio. Mantener allí el nombre esart_db porque env.py lo exige; no conectar la prueba a 5432 ni cambiar la base principal.
- Revisar el SQL global antes de restaurarlo: puede contener roles/tablespaces ya existentes o rutas que no son válidas en la copia. No ignorar indiscriminadamente los errores de roles duplicados ni restaurar globals sobre el clúster principal como ensayo.
- Restaurar roles/ownership necesarios con la cuenta autorizada; aprovisionar contraseñas por el canal seguro del operador. Restaurar el archivo completo en el destino limpio: por ejemplo, `pg_restore --create --exit-on-error --dbname=postgres ... esart_db.dump` apuntando **al puerto aislado comprobado**. No combinar --create con --single-transaction.
- Un listado y SHA-256 correctos no prueban una restauración. Verificar tablas, conteos, propietarios, grants, índices, restricciones, auditoría, secuencias y esart.alembic_version en la copia. Las filas TOTP deben descifrarse con la clave original en pruebas controladas, sin imprimirla.
- Ejecutar el upgrade aprobado primero en esa copia y medir duración/bloqueos; después aplicar la matriz funcional descrita abajo. No simular una versión inicial falsa ni usar stamp para forzar el ensayo.

## Plan de ejecución de upgrade head — solo después de aprobar

1. Recibir el historial y preflight del propietario. Si el historial no coincide con el catálogo, parar; no repetir CREATE TABLE ni saltar revisiones para hacerlo encajar.
2. Resolver las decisiones de permisos/datos/componentes anteriores y congelar los archivos exactos revisados mediante un manifiesto de hashes. Si hay que cambiar una propuesta no aplicada, revisarla y volver a ensayar; no editar una revisión que el propietario confirme ya aplicada.
3. Aprobar el ensayo restaurado y un respaldo final restaurable; detener escritores y capturar nuevamente preflight/contadores/grants.
4. Preparar temporalmente ESART_MIGRACIONES_URL con la URI propietaria autorizada. No escribirla en .env de la API ni mostrarla en consola/historial. En PowerShell puede obtenerse con Read-Host -AsSecureString, convertirla solo para el proceso hijo y eliminar la variable al acabar. La URI debe estar correctamente escapada; no se incluye una credencial real en este procedimiento.
5. La operación autorizada será, desde backend, `..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`. No usar --sql, stamp, downgrade ni la configuración histórica.
6. Medir y aprobar antes los límites de espera. El CLI/env.py actual no expone -x para lock_timeout ni garantiza que PGOPTIONS de libpq se aplique a asyncpg. No ejecutar SET en DBCode esperando que afecte a otra conexión. Para límites efectivos, usar la conexión compartida que env.py ya soporta: el operador puede preparar un wrapper revisado que abra create_async_engine con server_settings (lock_timeout, statement_timeout, application_name), engine.begin y conn.run_sync; dentro asignar Config.attributes['connection']=conn y ejecutar command.upgrade(config,'head'). Es la misma operación online, en la misma transacción. Esa variante debe aprobarse/ensayarse antes de usarla, no improvisarse en producción. [Alembic: conexión compartida](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands).
7. Si cualquier revisión falla, detener el procedimiento y conservar el error sin secretos. Verificar en una conexión nueva el historial y los objetos; no reintentar a ciegas. Se espera rollback de la transacción completa, con la salvedad de los valores de secuencia.
8. Tras éxito, ejecutar [ESART_ALEMBIC_POSTFLIGHT_PROPIETARIO.sql](ESART_ALEMBIC_POSTFLIGHT_PROPIETARIO.sql), repetir el inventario de solo lectura y comparar con el baseline antes de abrir tráfico. Esperado: una fila p0010_merge_hu10_totp, integridad validada, triggers habilitados, matriz de privilegios exactamente aprobada, políticas actuales preservadas y contadores/bloqueos sin cambios.

No se incluye un script que se ejecute automáticamente al abrir este documento o arrancar ESART.

## Validación funcional y criterios de aceptación

Primero en la copia restaurada y después en una cuenta de validación autorizada del despliegue, sin bloquear cuentas reales:

| Área | Resultado exigido |
|---|---|
| Contraseña temporal HU-10 | Desafío restringido, cambio válido auditado y continuidad obligatoria a MFA; ningún JWT completo durante el cambio. |
| Alta QR | Factor pendiente cifrado, QR real, código de seis dígitos válido activa; incorrecto/vencido/reutilizado denegado. |
| Login posterior | Contraseña → 202 → TOTP → 200; antes de TOTP no hay cookie JWT ni acceso a rutas protegidas. |
| Bloqueo | CAPTCHA tras el tercer fallo; CAPTCHA incorrecto/vencido no incrementa contraseñas; siete fallos comprobados producen 423 y tres horas; persiste al recargar. CAPTCHA se resuelve por el usuario, sin atajos. |
| Desbloqueo | TOTP válido elimina bloqueo y reinicia contador, sin emitir JWT; login posterior sigue requiriendo factores. |
| Administración | Asociación militar, creación/restablecimiento temporal, cambios de estado y contraseñas; sesiones/contextos revocados según corresponda; auditoría sin credenciales. |
| Permisos | Menú/rutas correctos y denegación HTTP directa a usuarios sin permiso; revisión especial de VER_DOCUMENTO_COMPLETO y de la malla editable. |
| Auditoría | LOGIN_EXITOSO solo después de MFA; tablas de auditoría preservadas e inmutables; acciones nuevas aceptadas por el CHECK. |
| Operaciones sensibles TOTP | No se dan por habilitadas solo por conceder permisos: sin adaptador registrado siguen rechazadas; comprobar finalidad, actor y recurso si se autorizan aparte. |

Como regresión local, después de fijar los archivos aprobados: pytest, pruebas Angular y build. No presentar las pruebas PostgreSQL omitidas por falta de entorno como aprobadas ni ejecutar el aprovisionador de pruebas que aplica migraciones automáticamente sin autorización.

## Recuperación y aprobación requerida

No hay downgrade genérico seguro: p0005 TOTP y p0004 lo rechazan; p0005 malla borra permisos/componentes; p0006 borra parámetros; p0007 borra auditoría; p0009 puede fallar al estrechar el CHECK cuando ya existen eventos nuevos. No se eliminará auditoría para hacer pasar una reversión.

Ante fallo previo al commit: comprobar rollback e historial, diagnosticar y mantener mantenimiento. Ante una reversión posterior a un upgrade confirmado: plan explícito de restauración del respaldo en un destino controlado, con RPO aprobado, preservación de evidencias posteriores y las claves originales; validar antes de volver al servicio. No restaurar automáticamente sobre la base activa ni descartar actividad posterior sin revisión.

Para aprobar faltan: (a) versión real y preflight completo del propietario; (b) cero huérfanos/contextos incompatibles pendientes; (c) aprobación de UPSERT de componentes y malla; (d) decisión sobre grants ampliados TOTP, especialmente autorizaciones; (e) respaldo con restauración y ensayo exitosos; (f) ventana, límites y criterios de recuperación acordados. Hasta entonces, mantener la actualización pendiente.
