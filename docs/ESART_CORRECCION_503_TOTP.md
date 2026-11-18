# Revisión de permisos y corrección de QR/TOTP

## Causa exacta y estado

La revisión real de esart_db, como esart_aplicacion y en transacciones READ ONLY, confirmó tres bloqueos sucesivos del código anterior:

1. La configuración efectiva tenía TOTP_HABILITADO=false y carecía de TOTP_CLAVE_CIFRADO. Después de verificar la contraseña, /api/auth/login llama TotpService.preparar(), que comienza por clave(). Allí se producía inmediatamente HTTP 503, TOTP_NO_DISPONIBLE, «Servicio de autenticador no disponible.». No llegaba a consultar permisos.
2. Corregida la configuración, faltaban permisos en desafíos, recuperación, políticas y auditoría. Tener USAGE del esquema y SELECT/INSERT/UPDATE de usuario_totp no es suficiente.
3. Aunque se concedieran esos permisos, preparar() exigía SELECT de autorizaciones, cinco FK por nombre, una FK compuesta y cuatro triggers de operaciones sensibles. Esos objetos no participan en la verificación de contraseña/QR/TOTP. Esa comprobación introducía otro 503 y obligaba a modificar estructura para habilitar el login.

Se corrigió el código para que el login compruebe sus operaciones reales y falle con TOTP_PERMISOS_FALTANTES cuando falta alguna. Los detalles de los objetos se registran en el backend, sin secretos. La verificación de integridad y permisos de autorizaciones se conserva exclusivamente en AutorizacionAccionesService; no se conceden privilegios sobre esa tabla.

**Actualización posterior a los GRANT:** el propietario confirmó su ejecución y la revisión real devuelve permisos_faltantes_login vacío. La nueva comprobación encontró que faltan las políticas LOGIN_TOTP y DESBLOQUEO_TOTP. El incidente sigue abierto hasta completar esas filas y comprobar el recorrido real; ver [ESART_PRUEBAS_REALES_TOTP.md](ESART_PRUEBAS_REALES_TOTP.md). No se ejecutaron GRANT, migraciones ni DDL desde el agente.

## Configuración de cifrado corregida

Se comprobó que usuario_totp no contenía registros antes de provisionar la clave. Se generaron 32 bytes criptográficamente aleatorios, codificados en Base64 estándar, y se guardaron en backend/.env, que está excluido de Git. Se activó TOTP_HABILITADO. No se mostró ni se guardó la clave en documentación o resultados.

La herramienta configurar_totp_local conserva una clave válida existente, rechaza configuraciones duplicadas y nunca genera una clave nueva si hay factores guardados y falta la clave original. Solo admite desarrollo local y realiza consultas READ ONLY; únicamente escribe el archivo de configuración. No debe rotarse esa clave al reiniciar.

El diagnóstico posterior confirma totp_habilitado=true, clave_presente=true y clave_base64_32_bytes=true. El bloqueo actual es TOTP_PERMISOS_FALTANTES, no la generación del secreto ni una contraseña incorrecta. Los secretos TOTP siguen generándose mediante PyOTP y cifrándose con AES-GCM, nonce aleatorio y contexto ligado al usuario.

## Operaciones SQL y privilegios mínimos

| Tabla | Operaciones reales del flujo | Privilegios adicionales |
|---|---|---|
| usuario_totp | SELECT con bloqueo de fila; INSERT de pendiente; UPDATE de secreto/estado/fechas/último intervalo | Ninguno: los existentes bastan. |
| politicas_accion | SELECT de LOGIN_TOTP y DESBLOQUEO_TOTP | SELECT; nunca INSERT/UPDATE al backend. |
| desafios | INSERT del desafío; SELECT FOR UPDATE; UPDATE de estado, intentos, verificado_en y consumido_en | SELECT, INSERT y UPDATE de esas cuatro columnas. |
| totp_recuperacion | INSERT de hashes; SELECT FOR UPDATE al consumir; UPDATE de usado_en/revocado_en | SELECT, INSERT y UPDATE de esas dos columnas. |
| auditoria | INSERT de evento; RETURNING id, fecha_evento generado por SQLAlchemy | INSERT y SELECT solo de id/fecha_evento. |
| auditoria_cambios | INSERT de cambio; RETURNING id, creado_en | INSERT y SELECT solo de id/creado_en. |
| autorizaciones | Ninguna en login, vinculación QR o validación de factor | Ninguno. Permanece fuera del archivo de GRANT. |

Se mantienen las consultas/escrituras existentes en esart_ref.usuarios, sesiones, roles y presupuestos de acceso. El control de contraseñas/CAPTCHA ocurre antes del TOTP y no se sustituye. No se añaden permisos de administrador, DELETE, TRUNCATE, ALL TABLES ni ALL SEQUENCES.

El archivo revisable es [ESART_TOTP_GRANTS_MINIMOS.sql](ESART_TOTP_GRANTS_MINIMOS.sql). Debe ejecutarlo el propietario en esart_db. No cambia estructura y termina mostrando las dos políticas requeridas. Si faltan, el archivo separado [ESART_TOTP_POLITICAS_MINIMAS.sql](ESART_TOTP_POLITICAS_MINIMAS.sql) propone únicamente esas dos filas, sin reemplazar políticas existentes ni conceder INSERT de políticas al backend. Su ejecución queda sujeta a revisión del propietario; todavía no se pudo leer su contenido con el rol de aplicación.

## Secuencias: corrección del diagnóstico anterior

Se consultaron pg_attribute.attidentity, pg_get_serial_sequence y los valores por defecto, sin llamar nextval, currval ni setval. Los cinco bigint id de seguridad son GENERATED ALWAYS AS IDENTITY (attidentity='a'); los id de desafios y autorizaciones son UUID generados por Python. El ORM inserta sin asignar los identity y usa RETURNING para obtenerlos.

La ausencia de USAGE sobre esas secuencias no es un bloqueo de ese INSERT identity. No se incluye ningún GRANT de secuencia en la propuesta mínima. Un id serial con DEFAULT nextval sí necesita USAGE o UPDATE de su secuencia; el diagnóstico distingue los dos casos. Esta distinción está respaldada por el [ejecutor de PostgreSQL para identity](https://doxygen.postgresql.org/execExprInterp_8c_source.html), que utiliza nextval_internal con comprobación directa de permisos desactivada, y la [documentación de identity](https://www.postgresql.org/docs/18/ddl-identity-columns.html). RETURNING sí exige SELECT de las columnas devueltas, según [INSERT de PostgreSQL](https://www.postgresql.org/docs/18/sql-insert.html).

Esto corrige la recomendación anterior de conceder USAGE/SELECT indiscriminadamente a las secuencias de seguridad.

## Prueba real preparada

El comando desde backend es `..\.venv\Scripts\python.exe -m herramientas.probar_totp_desarrollo --ejecutar`. No se ha ejecutado mientras se esperan los GRANT. Primero verifica desarrollo local, nombre/rol de la base, permisos y políticas. Si falta algo, termina antes de crear una cuenta.

Cuando esté listo, crea una cuenta exclusiva mfa.validacion.<aleatorio> con el rol USUARIO existente y una contraseña aleatoria que no imprime. Arranca FastAPI con aplicacion.principal real, Angular con proxy local y Chrome; no usa dobles HTTP, inyección de Angular ni la aplicación de captura CAPTCHA del laboratorio. Comprueba vinculación inicial 202 sin sesión, QR local, código TOTP real, confirmación, sesión autenticada, logout y nuevo login 202 → TOTP → 200. Las capturas se toman sin QR, clave manual ni recuperación visibles. Al terminar desactiva exclusivamente la cuenta creada y revoca sus sesiones/factor; conserva auditoría y evidencia. No modifica cuentas existentes, crea roles ni cambia estructura.

La herramienta de navegador no equivale a haber escaneado con un teléfono físico; la validación automatizada calcula el TOTP de la URI real de vinculación, con una implementación independiente en Node.

## Evidencia y resultados disponibles

- [ESART_TOTP_REVISION_PERMISOS_REAL.json](ESART_TOTP_REVISION_PERMISOS_REAL.json): metadatos reales, permisos efectivos, identidad/secuencias y configuración sin claves. Preparación actual: HTTP 503 TOTP_PERMISOS_FALTANTES.
- Backend: 221 pruebas aprobadas, 64 omitidas y seis subtests aprobados. Las nuevas regresiones verifican permisos faltantes, independencia del login respecto de autorizaciones y diferencia entre serial e identity. Las omitidas requieren entornos explícitos.
- Angular: 71 pruebas aprobadas. En esta revisión no se modifican el diseño del CAPTCHA, los umbrales 3/7, las tres horas de bloqueo ni VentanaBloqueo.
- Pendiente: confirmación de GRANT, lectura de políticas, ejecución del recorrido real y registro de sus resultados. Hasta obtener evidencia 202 → vinculación/TOTP → 200 con sesión válida, el incidente sigue abierto.

Archivos de código ajustados: servicios/totp.py, requisitos_totp.py y autorizacion_acciones.py; herramientas/diagnosticar_totp.py, configurar_totp_local.py y probar_totp_desarrollo.py; pruebas/test_totp_unidad.py y conftest.py. La configuración de pruebas fuerza TOTP deshabilitado por defecto para no depender de secretos de backend/.env; cada prueba TOTP configura su clave aislada. No se realizaron commits ni push.
