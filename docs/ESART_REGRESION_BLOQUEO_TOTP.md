# Bloqueo de cuentas y separación de TOTP

Fecha: 16 de noviembre de 2026.

## Diagnóstico antes de la corrección

Se revisaron los dos prefijos HTTP de login, el servicio de autenticación, bcrypt, el control PostgreSQL, CAPTCHA, TOTP, la dependencia de sesión y `InicioSesion`. `/api/auth/login` y `/api/v1/auth/login` utilizan el mismo servicio; no se encontró una ruta alternativa de login que omita CAPTCHA o bloqueo.

La inspección de solo lectura confirmó conexión local a `esart_db` como `esart_aplicacion`. En la configuración cargada por esta sesión, `totp_habilitado=false` y no hay clave TOTP configurada. El rol no tiene USAGE del esquema seguridad ni acceso a la revisión Alembic; no se ampliaron sus permisos para diagnosticar.

La consulta agregada de los cien últimos registros de intentos devolvió 36 `CAPTCHA_INVALIDO`, 16 `CREDENCIALES_INVALIDAS`, 5 `BLOQUEO_VIGENTE` y 8 exitosos/sin motivo. Los contadores de usuarios agrupados mostraron una cuenta con 0 y otra con 3. No se consultaron ni publicaron nombres, contraseñas, hashes, IP históricas ni datos personales para este informe.

Esto explica el síntoma observable del contador detenido en tres: desde el cuarto envío el CAPTCHA se evalúa **antes** de bcrypt. Si falta, expira, se reutiliza o no coincide, no se comprueba la contraseña; por tanto ese envío no es otro fallo comprobado de contraseña. Esta separación se introdujo expresamente con el encargo TOTP anterior y se mantiene conforme al requisito actual. No se permite probar contraseñas ilimitadamente ignorando CAPTCHA para contar esos envíos. Hay auditoría y presupuesto por IP para rechazos CAPTCHA.

Se detectaron además dos defectos de acoplamiento introducidos por TOTP:

1. `TotpService.preparar()` se ejecutaba al entrar al login, antes de controlar contraseña/bloqueo. Al habilitar TOTP con clave, esquema o permisos incompletos, devolvía 503 antes de registrar fallos. No puede atribuirse ese defecto a la configuración local deshabilitada observada; es una regresión condicional real del código.
2. La escritura adicional en `seguridad.auditoria` estaba en la misma transacción que contador y auditoría original, antes de commit. Una excepción SQL en esa copia hacía fallar la petición y el cierre de sesión descartaba el incremento. La dependencia SQLAlchemy no hace commit automático; no había un reinicio espontáneo del contador.

No se afirma haber identificado el entorno exacto del proceso servido al navegador si utiliza otras variables de entorno. Los resultados de lectura anteriores corresponden a la configuración local del proyecto. Las pruebas siguientes verifican las rutas reales del código contra otro clúster.

## Cambios

- `backend/aplicacion/servicios/autenticacion.py`: los controles persistentes existentes se ejecutan primero; la disponibilidad TOTP se exige después de contraseña válida y rol activo, antes de obtener factor o emitir sesión/JWT. TOTP no se omite cuando falla: credenciales correctas con servicio TOTP no disponible siguen recibiendo 503 y ningún JWT.
- `backend/aplicacion/servicios/seguridad_login.py`: la auditoría original de `esart.intentos_inicio_sesion` y `esart.auditoria_acceso` sigue siendo obligatoria. La copia adicional TOTP se escribe y fuerza dentro de un SAVEPOINT. Un error DBAPI revierte esa copia, registra un error operativo sin datos sensibles y permite confirmar contador/bloqueo junto a la auditoría principal. No se silencian fallos de la auditoría principal. Una caída de la base que impida el commit no se considera un bloqueo persistido.
- El rechazo CAPTCHA tiene código público `CAPTCHA_INVALIDO`, HTTP 401, mensaje explícito de que la contraseña no se comprobó y `captcha_validado=false`. No expone contador ni existencia de cuenta. Los fallos de contraseña mantienen `CREDENCIALES_INVALIDAS`; los bloqueos mantienen 423 `CUENTA_BLOQUEADA`.
- `frontend/esart/src/app/paginas/inicio-sesion/inicio-sesion.ts`: no sustituye el mensaje CAPTCHA específico por el mensaje ambiguo de credenciales. Se conservan el modal y el reloj institucional existente, alimentados por fecha/hora del servidor, y la restauración por comprobante después de recargar.
- Pruebas: `backend/pruebas/test_totp_pg.py`, `test_captcha_local_pg.py` y `frontend/esart/src/app/paginas/inicio-sesion/inicio-sesion.spec.ts`.

No se modifican tablas, migraciones, permisos, usuarios, contraseñas, QR, roles, políticas sensibles, algoritmo TOTP ni duración JWT.

## Reglas conservadas

| Situación | Resultado |
|---|---|
| Contraseña comprobada incorrecta 1–3 | Incremento persistente; 401. El tercer fallo informa CAPTCHA obligatorio para el próximo envío. |
| Envío desde el cuarto sin CAPTCHA válido | 401 CAPTCHA_INVALIDO; audita y consume cuota IP; no verifica ni suma contraseña. |
| CAPTCHA válido + contraseña incorrecta 4–6 | Incremento persistente; 401. |
| CAPTCHA válido + séptima contraseña incorrecta | Contador 7, bloqueado_hasta = reloj PostgreSQL + 3 horas; 423. |
| Cuenta bloqueada, incluso contraseña correcta | 423 antes de comprobar contraseña; no prolonga el plazo. |
| Expiración del bloqueo | Limpia bloqueo/contador bajo bloqueo de fila y audita vencimiento; la próxima contraseña incorrecta vuelve a contar como 1. |
| Contraseña válida con factor activo | Desafío TOTP 202; no reinicia contador ni emite JWT todavía. |
| Código TOTP incorrecto | Incrementa intentos del desafío y aplica sus cuotas; no cambia el contador de contraseñas. |
| Login completo correcto | Reinicia contador y emite la sesión existente. |
| Desbloqueo anticipado TOTP | Solo factor previamente ACTIVO; limpia bloqueo/contador sin emitir JWT. |

Los bloqueos de fila y actualizaciones persistentes existentes se mantienen para serializar intentos concurrentes. Cambiar de proceso o crear otro pool no restablece el estado PostgreSQL. Las cabeceras/IP y el comprobante público no se convierten en prueba de titularidad ni habilitan consulta arbitraria de históricos.

## Pruebas

El ejecutor `herramientas.probar_seguridad_aislada` crea un clúster nuevo marcado, puerto distinto del operativo y cuentas `hu06.*`. Comprueba el directorio de datos antes de preparar el esquema y lo detiene al finalizar. No modifica la base principal ni sus cuentas.

Las pruebas nuevas fuerzan indisponibilidad TOTP o un error SQL real de división por cero dentro de su auditoría. Usan los endpoints HTTP y CAPTCHA real generado, comprueban cada contador del 1 al 7 desde otra sesión PostgreSQL, la respuesta 423 con contraseña correcta, el plazo de tres horas y la auditoría original confirmada. Otra prueba inicia un intérprete nuevo con otra aplicación FastAPI/pool y comprueba que la misma cuenta continúa bloqueada. También se comprueba que un desafío TOTP pendiente y un código incorrecto no reinicien ni incrementen el contador de contraseñas.

Las regresiones existentes verifican CAPTCHA ausente/incorrecto sin ejecutar bcrypt, concurrencia desde varias IP, vencimiento exacto, desbloqueo TOTP activo, límites IP y consulta del bloqueo al recargar. Los recorridos Chrome comprueban modal público, CAPTCHA desde el cuarto, séptimo fallo, recarga, QR y login de dos factores sin interceptar las respuestas HTTP.

Resultados finales:

- PostgreSQL aislado: **45 pruebas aprobadas**, incluidas las cuatro nuevas regresiones (dos variantes de avería TOTP, separación de contadores y proceso nuevo). Evidencia en `backend/respaldos/hu06_7f1e79bc6ebb4753957516ab9658951e/resultado.json`. Clúster detenido al terminar.
- Backend general: **196 aprobadas, 60 omitidas** sin sus entornos explícitos. Las pruebas PostgreSQL omitidas en ese comando sí se ejecutan por separado en el laboratorio; no sumar los resultados como casos distintos.
- Angular: **60 pruebas aprobadas en 10 archivos** en la ejecución de esta entrega.
- Ruff sin errores. Build Angular aprobado; se mantiene el aviso CommonJS de qrcode, sin errores de compilación.
- Navegador público: séptimo fallo, 423, modal, recarga y recuperación de bloqueo, sin sesión administrativa ni interceptar HTTP. Evidencia en `navegador_publico/resultado.json` dentro del directorio aislado.
- Navegador TOTP: QR local válido y retirado al activar; login primer factor 202 sin JWT, segundo factor 200, sesión 200 y logout 204. Evidencia en `navegador_totp/resultado.json`.
- Desbloqueo TOTP en Chrome: séptimo fallo 423, desafío 202, confirmación 200 sin JWT y login nuevamente habilitado. Evidencia en `navegador_desbloqueo/resultado.json`.

TOTP y QR continúan funcionando en el entorno aislado. Esto no acredita que estén habilitados en la configuración principal: la lectura local encontró TOTP deshabilitado y sin clave, y no se cambió esa configuración.

## Comprobación operativa posterior

No provocar siete fallos en una cuenta real para validar. Para una reproducción autorizada, usar una cuenta aislada y resolver correctamente un CAPTCHA nuevo, asociado al mismo nombre de usuario, en cada envío desde el cuarto. Si la respuesta es CAPTCHA_INVALIDO, resolver ese rechazo; no interpretarlo como otra contraseña comprobada. Si aparece 503, revisar su código y la configuración TOTP, sin deshabilitar controles para obtener un JWT.

No se requiere migración ni modificación de registros existentes para aplicar estos cambios de código. La habilitación operativa de TOTP continúa sujeta a los requisitos administrativos documentados en `ESART_TOTP_IMPLEMENTACION.md`.
