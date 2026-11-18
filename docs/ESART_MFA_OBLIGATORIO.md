# Autenticación multifactor y vinculación inicial obligatorias

> La revisión vigente de permisos, cifrado y causa del 503 se encuentra en [ESART_CORRECCION_503_TOTP.md](ESART_CORRECCION_503_TOTP.md). El incidente permanece pendiente de verificar el recorrido real después de que el propietario aplique los GRANT mínimos.

El login existente comprueba contraseña, CAPTCHA y bloqueo antes de consultar el factor. Una cuenta con TOTP ACTIVO recibe HTTP 202 y un desafío temporal ligado a una cookie HttpOnly del navegador, sin crear una sesión ni emitir JWT. Solo la confirmación válida consume el desafío y crea la sesión con los permisos actuales. Cerrar el modal o recargar exige volver a iniciar el proceso; las rutas HTTP protegidas siguen requiriendo una sesión completa.

La nueva política exige vinculación a todas las cuentas. Sin factor activo, el login responde 202 con configuracion_requerida=true y un desafío VINCULACION limitado a ese navegador. Los endpoints /auth/totp/login/configurar y /auth/totp/login/vincular permiten obtener QR y confirmar el primer código sin conceder acceso a módulos. Activación, consumo del desafío y creación de sesión se confirman juntos. Deshabilitar TOTP devuelve indisponibilidad después de comprobar contraseña, también para cuentas sin factor. El flujo actualizado y el diagnóstico real están en [ESART_INTEGRACION_CUENTAS_TOTP.md](ESART_INTEGRACION_CUENTAS_TOTP.md).

## Registro, recuperación y revocación

Se reutilizan Totp, TotpService, SesionService, InicioSesion y VentanaBloqueo. El QR de registro contiene una URI otpauth para aplicaciones RFC 6238. Escanearlo no activa el factor: FastAPI exige un código válido. El secreto permanece cifrado con AES-GCM y asociado al usuario.

Al activar se generan diez códigos aleatorios de recuperación de 128 bits. Se entregan una sola vez, con Cache-Control: no-store, y el componente espera que el usuario confirme su guardado antes de emitir completado. Solo se conservan en memoria mientras se muestran; cerrar o destruir el componente los borra. En la tabla existente seguridad.totp_recuperacion se guardan HMAC con separación de dominio y usuario, nunca códigos en claro.

- POST /api/auth/totp/recuperacion/renovar exige sesión, CSRF, contraseña actual y un TOTP nuevo. Revoca todos los códigos anteriores y entrega otro lote una sola vez. Permite obtener códigos a cuentas vinculadas antes de esta entrega.
- POST /api/auth/totp/login/confirmar admite recuperacion=true y un código de recuperación de 32 caracteres hexadecimales. Requiere el desafío obtenido después de contraseña y la cookie del mismo navegador; conserva caducidad y límites de intentos. El código se consume en la misma transacción que crea la sesión. Los bloqueos de filas serializan usos concurrentes.
- Tras recuperar acceso, CONFIGURAR AUTENTICADOR permite revocar el dispositivo perdido con contraseña y otro código sin usar. POST /api/auth/totp/recuperacion/revocar exige sesión y CSRF. Revoca factor, códigos restantes, desafíos pendientes y todas las sesiones. El siguiente login exige vincular el reemplazo antes de emitir otra sesión.
- La revocación normal mantiene contraseña más TOTP y también revoca las sesiones.

La recuperación no cambia el desbloqueo TOTP existente ni permite saltarse una cuenta bloqueada. Sin dispositivo y sin códigos disponibles se requiere un procedimiento administrativo de verificación de identidad; no se implementa una puerta pública de recuperación.

Los intentos del segundo factor usan presupuestos separados de los de contraseña. Se mantienen CAPTCHA tras tres fallos, bloqueo al séptimo, duración de tres horas y HTTP 423. Auditoría registra emisión, validación y recuperación sin códigos ni secretos.

## Aprobación QR: fase 2

No existe un cliente móvil ESART vinculado capaz de firmar desafíos; por eso no se ofrece aprobación QR en el login. El QR de vinculación TOTP no es un método de aprobación de sesión.

La fase 2 requiere registrar una clave pública del dispositivo tras reautenticación y segundo factor, identificación y revocación de dispositivos, almacenamiento seguro de la clave privada móvil y firma de un desafío aleatorio breve. La firma debe cubrir identificador de desafío, usuario, origen, propósito LOGIN, expiración y vínculo con el navegador. El backend debe verificar firma, dispositivo activo, vigencia y consumo atómico. La entrega del resultado debe requerir la cookie del navegador que inició el desafío, mediante consulta autenticada o canal equivalente. El QR contendrá solo un identificador opaco de un solo uso, sin secreto TOTP ni JWT. Escanear sin aprobación criptográfica no concede acceso.

## Verificación y despliegue

No se cambió el esquema PostgreSQL ni se ejecutaron migraciones. Se reutilizan las tablas y permisos existentes. No se agregan refresh tokens: se conserva el contrato JWT de sesión HttpOnly actual; introducir refresh requeriría diseñar su ciclo de revocación y persistencia.

Se añaden pruebas unitarias de generación y hashes, consumo y rechazo, interfaz de recuperación y limpieza. Las pruebas de integración PostgreSQL incluyen recuperación concurrente, reutilización de código, revocación de sesiones y servicio deshabilitado; requieren el clúster aislado explícito y no se ejecutan contra la base principal. La herramienta de navegador confirma el guardado antes de capturar la pantalla para no guardar los códigos en una imagen.

Validación anterior a la vinculación inicial obligatoria: backend 200 pruebas aprobadas, 62 omitidas y 6 subtests aprobados; Angular 65 pruebas aprobadas. Los resultados actuales se consignan en ESART_INTEGRACION_CUENTAS_TOTP.md. Las pruebas PostgreSQL y el recorrido de navegador real quedan pendientes de ejecutar en su entorno aislado autorizado; estos resultados no acreditan un despliegue operativo en la base principal.
