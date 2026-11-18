# Integración de cuentas, QR y TOTP obligatorio

> Actualización de permisos y HTTP 503: consultar [ESART_CORRECCION_503_TOTP.md](ESART_CORRECCION_503_TOTP.md). La clave local ya está provisionada. El login comprueba ahora solo sus permisos SQL reales; las FK/triggers y permisos de autorizaciones se verifican exclusivamente en el servicio de operaciones sensibles. La propuesta de GRANT actual no requiere cambios de estructura ni acceso a autorizaciones.

## Diagnóstico de la implementación

Antes de esta entrega, las cuentas con factor ACTIVO ya recibían un desafío LOGIN sin JWT. Las cuentas sin factor podían entrar con contraseña y abrir /totp después: esa secuencia no cumplía la vinculación inicial obligatoria. Existían cifrado AES-GCM ligado al usuario, protección de reutilización, límites separados, recuperación, auditoría y desbloqueo TOTP. Se reutilizan esos servicios y componentes.

El 16 de noviembre de 2026 se consultó la base real esart_db como esart_aplicacion, dentro de una transacción READ ONLY. [ESART_TOTP_ESTRUCTURA_REAL.json](ESART_TOTP_ESTRUCTURA_REAL.json) contiene únicamente metadatos, restricciones y permisos; no contiene usuarios, secretos, códigos ni credenciales de conexión. El diagnóstico se reproduce desde backend con `..\.venv\Scripts\python.exe -m herramientas.diagnosticar_totp`.

Las siete tablas existen y permiten representar el flujo sin agregar tablas ni columnas. La cuenta de aplicación solo tiene SELECT/INSERT/UPDATE en usuario_totp; no tiene SELECT/INSERT sobre desafíos, recuperación o auditoría, ni SELECT sobre políticas. Tampoco tiene USAGE sobre las secuencias. Faltan las cinco FK de usuario, la relación compuesta de autorización y los cuatro triggers de auditoría exigidos por preparar(). No se consultaron valores de políticas porque el rol carece de acceso.

**El despliegue actual no está habilitado para operar este flujo.** El código devuelve 503 después de verificar credenciales si la clave/configuración o la integración de seguridad no están disponibles. No omite factores para conseguir un login exitoso. No se alteraron permisos, tablas, restricciones, políticas, cuentas ni configuración protegida de esart_db.

## Flujo implementado

1. InicioSesion envía usuario, contraseña y CAPTCHA cuando corresponde al endpoint existente /api/auth/login.
2. FastAPI conserva contraseña, estado activo, roles y bloqueo persistente. Después exige disponibilidad de TOTP para todas las cuentas.
3. Si el factor está ACTIVO, crea un desafío LOGIN. Si está ausente, pendiente o revocado, crea un desafío VINCULACION. Ambos responden 202 sin crear SesionUsuario ni JWT. La respuesta indica configuracion_requerida, identificador y expiración; nunca contiene el secreto.
4. Angular reutiliza Totp en CONFIGURAR para VINCULACION, o LOGIN para un factor activo. El componente incrustado no redirige al inicio al cancelar.
5. En la vinculación inicial, Angular solicita /auth/totp/login/configurar con el ID. La cookie HttpOnly es la prueba reciente de contraseña y está firmada para ese ID, propósito y contexto. El backend verifica cuenta no bloqueada, vigencia y estado del desafío. La cuenta se obtiene del desafío, nunca de un usuario_id enviado por el cliente.
6. El servicio genera o recupera la configuración pendiente cifrada y devuelve su URI otpauth. Angular genera el QR localmente con qrcode. La vigencia visible es el mínimo entre la configuración pendiente y el desafío de login; solicitar de nuevo el QR no prolonga el desafío ni reemplaza un factor activo.
7. Angular envía seis dígitos a /auth/totp/login/vincular. FastAPI valida el desafío y un código real, activa el factor, registra recuperación/auditoría y consume el desafío. **Esas operaciones y la creación de sesión se confirman en una sola transacción**, dentro de finalizar_login. Un fallo antes del commit no deja el factor activado sin completar la operación.
8. Solo entonces se escriben las cookies JWT/CSRF existentes y SesionService registra el usuario público. Se retiran QR y clave manual. Se muestran los códigos de recuperación una vez; confirmar su guardado completa el evento del componente y permite navegar al destino solicitado.
9. En nuevos accesos, LOGIN pide solo el código temporal o recuperación: no entrega QR ni secreto. /auth/totp/login/confirmar conserva su propósito y no acepta un desafío VINCULACION.

El desafío inicial usa la política LOGIN_TOTP existente, con su vigencia configurada y un máximo de cinco códigos fallidos. Se almacena el propósito en recurso_tipo y la huella del vínculo en operacion_hash. No se requiere una política o columna nueva. El contador TOTP no altera el contador de contraseñas.

## Endpoints

Todos los endpoints también están disponibles bajo /api/v1. Los cuerpos rechazan campos adicionales.

| Endpoint bajo /api | Contexto y resultado |
|---|---|
| POST /auth/login | Contraseña/CAPTCHA. 202 con totp_requerido y configuracion_requerida; nunca sesión completa. |
| POST /auth/totp/login/configurar | Nuevo. `{desafio_id}` y cookie esart_totp_login ligada a VINCULACION. URI otpauth y expiración. |
| POST /auth/totp/login/vincular | Nuevo. `{desafio_id,codigo}` y misma cookie. Activa/consume/crea sesión conjuntamente y entrega recuperación una vez. |
| POST /auth/totp/login/confirmar | Reutilizado. Desafío LOGIN, cookie y código TOTP o recuperación. |
| GET /auth/yo | Reutilizado. Exige sesión completa y factor ACTIVO; deniega sesiones anteriores a la activación del factor. |
| GET /auth/totp/estado | Reutilizado. Consulta autenticada sin secretos. |
| POST /auth/totp/configurar, /confirmar | Conservados con sesión y CSRF; no sirven como atajo durante el primer login. |
| POST /auth/totp/desactivar | Reutilizado. Sesión, CSRF, contraseña y TOTP; revoca también las sesiones. |
| POST /auth/totp/recuperacion/renovar, /revocar | Conservados. Recuperación con límites, contraseña y segundo comprobante válido. |
| POST /auth/desbloqueo/solicitar, /confirmar | Conservados. Desbloquear no crea sesión. |

Se conserva el JWT de sesión HttpOnly con sus permisos actuales. No existe un contrato de refresh token en ESART y no se añade uno ficticio.

## Relación con PostgreSQL y permisos

| Tabla existente | Uso de las columnas existentes | Permisos de aplicación necesarios |
|---|---|---|
| usuario_totp | usuario_id único, secreto_cifrado, estado, expiración, activación/revocación y último intervalo | SELECT/INSERT; UPDATE de las columnas del factor |
| desafios | usuario_id, politica_id, recurso_tipo, operacion_hash, estado, intentos, expiración y consumo | SELECT/INSERT; UPDATE de estado, intentos y fechas de consumo |
| totp_recuperacion | usuario_id, codigo_hash, usado_en, revocado_en | SELECT/INSERT; UPDATE de consumo/revocación |
| politicas_accion | LOGIN_TOTP y DESBLOQUEO_TOTP con vigencia y estado | SELECT |
| auditoria, auditoria_cambios | Eventos y transición del factor sin valores secretos | SELECT/INSERT; nunca UPDATE/DELETE/TRUNCATE |
| autorizaciones | Integración de operaciones sensibles existente | SELECT/INSERT; UPDATE limitado a resultado/consumo |

También se requiere USAGE del esquema y las secuencias de inserción, junto con los permisos ya existentes sobre sesiones, usuarios y presupuestos de intentos. La revisión p0005_integracion_totp, ya presente antes de esta entrega, propone relaciones, políticas, triggers y grants; **no se ejecutó ni se modificó**. Su aplicación necesita autorización, revisión de huérfanos y respaldo restaurable. No debe ejecutarse seguridad.sql sobre estas tablas existentes.

## Seguridad y finalidad del factor

El factor activo representa el autenticador de una cuenta; el desbloqueo existente utiliza ese mismo factor. Se conserva expresamente tras revisar su alcance: DESBLOQUEO solo elimina el bloqueo y nunca emite JWT; el login posterior sigue exigiendo contraseña y un código nuevo. Las cookies y desafíos tienen propósitos distintos y el último intervalo aceptado se comparte para impedir reutilización entre vinculación, login, desbloqueo y operaciones. No se copia ni convierte un secreto de desbloqueo en un registro nuevo. Si se requieren dispositivos distintos por finalidad, hará falta diseñar su registro y persistencia con autorización de esquema.

El QR es exclusivamente de vinculación RFC 6238; escanearlo no acredita el código y no concede acceso. No se implementa aprobación móvil simulada. Secretos cifrados, contraseñas y códigos no se registran. El nonce se excluye del repr del desafío. Los endpoints de seguridad llevan no-store y el QR/clave se limpian tras confirmar, expirar, cerrar o destruir el componente.

Cerrar o recargar antes de verificar no crea sesión. Un JWT anterior al alta del factor tampoco permite entrar. Deshabilitar TOTP o perder su configuración no degrada el acceso a contraseña sola. CAPTCHA conserva su diseño y umbrales; bloqueo conserva siete fallos, tres horas y HTTP 423. El código de desbloqueo existente no se cambió.

El interceptor Angular trata un 401 de los endpoints de login TOTP como error del proceso de autenticación; lo muestra en el modal sin inventar una expiración de sesión completa.

## Archivos de esta entrega

- Angular: paginas/totp/totp.ts, totp.html y totp.spec.ts; paginas/inicio-sesion/inicio-sesion.html y su spec; nucleo/modelos/sesion.ts; servicios/sesion.service.ts y totp.service.ts; interceptores/sesion-expirada.interceptor.ts y su spec. totp.css y VentanaBloqueo fueron revisados y no necesitaron cambios.
- FastAPI: servicios/autenticacion.py y totp.py; rutas/totp.py. Se reutilizan los routers, protección JWT, CAPTCHA y permisos existentes.
- Diagnóstico/pruebas: herramientas/diagnosticar_totp.py y navegador_totp.mjs; pruebas/test_totp_unidad.py, test_totp_pg.py, test_seguridad_login_pg.py, test_captcha_local_pg.py, soporte_mfa.py y configuración del laboratorio en conftest.py. El soporte de pruebas completa factores mediante servicios/HTTP reales; no añade atajos al backend.

## Validación y límites

- Backend: 215 pruebas aprobadas, 64 omitidas y seis subtests aprobados. Incluye generación TOTP real, ausencia de sesión tras contraseña, desafío de otra finalidad, cookie ajena, expiración, consumo, límite, registro previo activo, rechazo de sesiones anteriores y commit diferido hasta finalizar la sesión.
- Angular: 71 pruebas aprobadas en diez archivos. Incluye primer login CONFIGURAR sin sesión, QR y retirada al confirmar, ausencia de navegación prematura, cancelación y errores del segundo factor sin redirección de sesión expirada.
- Producción: build aprobado; persisten avisos de presupuesto CSS del componente y dependencia CommonJS qrcode. Sin dependencias nuevas ni servicios de pago.
- Ruff y comprobación de sintaxis del recorrido navegador: aprobados.
- PostgreSQL real: diagnóstico de solo lectura ejecutado. No se crearon cuentas ni se realizaron intentos de login sobre usuarios reales.
- Integración PostgreSQL y navegador completo: pruebas actualizadas y pendientes de ejecución en el clúster aislado previamente preparado. No se lanzó el aprovisionador porque ejecuta migraciones y la solicitud prohíbe hacerlo automáticamente. Los resultados anteriores de laboratorio no acreditan el flujo nuevo. El escaneo con una aplicación física también queda pendiente; no se afirma haberlo realizado.

Para habilitar el flujo en esart_db falta autorizar y aplicar los ajustes de integridad/permisos revisados, provisionar la clave externa y configuración protegida, y validar con cuentas autorizadas. Hasta entonces la respuesta 503 evita conceder una sesión incompleta. No se realizaron commits ni push.
