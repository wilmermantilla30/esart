# Preparación de Alembic en esart_db

## Estado comprobado el 20 de noviembre de 2026

El intento de solo lectura a `127.0.0.1:5432/esart_db` como `esart_migrador` recibió `fe_sendauth: no password supplied`. La sesión de ejecución carece de `ESART_MIGRACIONES_URL`. No se confirmó la revisión activa, el catálogo ni la titularidad real de los objetos. Ninguna migración se ejecutó. Los resultados de la copia de ensayo no se pueden trasladar a la base real.

La cadena local después de p0014 es p0015 → p0016 → p0017 → p0018 → p0019. p0017 modifica el CHECK de acciones de auditoría y actualiza la política administrativa de restablecimiento TOTP. p0018 crea objetos ausentes o adopta los compatibles, valida los controles heredados y compara conteos y SHA-256 de los registros de firma previamente presentes, incluidos documentos, versiones, firmas y auditoría. p0019 aplica concesiones a la API. Las 13 pruebas locales de persistencia y revisión pasaron. No se crearon bases temporales.

El entorno Alembic admite `esart_db` de desarrollo local como `esart_migrador` sin superusuario. Su ejecutor toma la URL de `ESART_MIGRACIONES_URL` y abre una transacción. La herramienta de conciliación de ensayo mantiene su guarda para las escrituras. Su modo de auditoría admite la base real, imprime la revisión y las revisiones pendientes bajo una transacción de solo lectura y compara el catálogo relevante si p0018 está pendiente. Las diferencias de p0015 a p0017, si aún están pendientes, requieren revisión específica del catálogo antes de elegir el comando.

## Respaldo

`esart_db_pre_alembic.dump` es del 15 de noviembre de 2026, tiene 153402 bytes y SHA-256 `7488EDAF5152B8603809F5FA8B5996D13C97B576A77E4D705B07BCA0511511FC`. El encabezado declara `esart_db`. Se leyó el archivo completo con `pg_restore --exit-on-error --file=NUL`, sin conectar a una base. Su catálogo carece de las tablas documentales, firmas, auditoría de firma y revisión Alembic. Los otros dos `.dump` localizados tienen cero bytes. No hay evidencia local de un respaldo actual restaurado.

Para preparar un respaldo actual, usar el rol existente `esart_respaldo`, su URL efímera `ESART_RESPALDO_URL` y el destino privado con ACL revisadas que usa la herramienta del repositorio. Desde `backend`:

```powershell
& '.\.venv\Scripts\python.exe' -m herramientas.respaldo_previo_firma_documental
```

Registrar ruta, tamaño y SHA-256. Verificar que el catálogo del volcado contenga la revisión y cada tabla de firma presente en el origen. Verificar lectura completa con `pg_restore --exit-on-error --file=NUL`. La restauración de prueba requiere un entorno de recuperación aislado autorizado y ya disponible, comprobación de revisión y comparación de conteos y huellas. Registrar por separado los roles y ACL necesarios para recuperar el servicio y, si hay PDF fuera de PostgreSQL, el respaldo del almacén privado correspondiente. Nunca restaurar el respaldo sobre la base operativa para comprobarlo.

## Ejecución futura

1. Confirmar identidad, revisión y diferencias sobre la base real. Asegurar que el rol migrador puede alterar los objetos pertinentes sin elevarlo a superusuario. Confirmar el respaldo y su recuperación.
2. Coordinar una ventana sin escrituras de la aplicación. Aplicar únicamente la revisión inmediatamente posterior a la registrada. Si la revisión es `p0017_restablecer_totp_admin`, el destino explícito es `p0018_firma_documental`.
3. Con p0018, Alembic ejecuta DDL, validación de catálogo, comparación de huellas de las columnas preexistentes y actualización de la revisión dentro de una transacción. Un error se propaga y revierte los cambios transaccionales. Después del commit, comprobar la revisión, los OID y la evidencia de integridad. Mantener bloqueado el downgrade de p0018 y usar el respaldo verificado si se necesita recuperar un cambio ya confirmado.

No se ha identificado ningún objeto que requiera eliminarse. Una reconstrucción requeriría un inventario de los objetos y una confirmación específica.

## Actualización directa a p0019

El único head local es `p0019_firma_movil`. Desde una terminal interactiva en `backend`, el siguiente ejecutor verifica el destino, muestra la revisión activa y la lista de pendientes, y usa Alembic hasta p0019 cuando el tramo está permitido. Solicita la contraseña sin eco si no recibe la URL migradora. Verifica la revisión final y el catálogo de firma antes del commit.

```powershell
& '.\.venv\Scripts\python.exe' -m herramientas.actualizar_esart_db
```

Si p0015 o p0017 están pendientes, el ejecutor se detiene antes de sustituir el CHECK `esart.auditoria_eventos.ck_auditoria_eventos_ck_auditoria_eventos_accion` y señala que hace falta confirmación específica. También se detiene ante una revisión desconocida, una discrepancia de catálogo o un error de migración. En esta sesión la autenticación siguió bloqueada por falta de credencial y no se ejecutó ninguna revisión.
