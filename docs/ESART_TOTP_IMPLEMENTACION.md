# TOTP ESART: implementación y puesta en servicio

> La política y los resultados de esta entrega inicial son históricos. El flujo vigente exige vinculación antes del primer acceso y está documentado en [ESART_INTEGRACION_CUENTAS_TOTP.md](ESART_INTEGRACION_CUENTAS_TOTP.md), junto con el diagnóstico real de permisos pendientes.

Fecha: 16 de noviembre de 2026. Alcance: segundo factor, vinculación, desbloqueo y autorización centralizada. No se implementaron CRUD de cursos ni personal militar.

## Estado y diagnóstico

Se inspeccionó `esart_db` en modo lectura mediante `esart_aplicacion`. Existen las siete tablas `seguridad.usuario_totp`, `totp_recuperacion`, `politicas_accion`, `desafios`, `autorizaciones`, `auditoria` y `auditoria_cambios`. Sus identificadores de usuario son BIGINT, compatibles con `esart_ref.usuarios.id`. Se mapearon sus columnas existentes con una base ORM separada; no se ejecutó CREATE TABLE en la base principal.

La cuenta de aplicación no dispone de SELECT/INSERT/UPDATE sobre esas tablas. No se pudieron comprobar sus registros de políticas con esa cuenta. Faltan las FK hacia usuarios y las garantías de inmutabilidad de auditoría propuestas en `p0005_integracion_totp`. La existencia de las tablas no significa que el módulo esté desplegado.

**No se aplicaron migraciones, permisos ni cambios de datos en esart_db. No se habilitó TOTP ni se cambió .env.** Las pruebas funcionales usan otro clúster PostgreSQL, con directorio identificado y puerto aleatorio distinto de 5432. Sus usuarios, claves y tablas son exclusivamente de prueba.

El login real utiliza `/api/auth/login`, cookies HttpOnly, CSRF, JWT y sesiones persistidas. No existe un servicio de refresh token: no se añadió uno ficticio. Se conservan la duración máxima del JWT y la expiración por inactividad. Se añadieron alias `/api/v1` para los routers de autenticación y seguridad; el cierre de sesión existente conserva el nombre `cerrar-sesion`.

## Contratos HTTP

Las siguientes rutas también están disponibles bajo `/api/v1`. Los cuerpos rechazan campos adicionales. Los códigos TOTP son cadenas de seis dígitos ASCII, incluidos ceros iniciales. No son números.

| Método y ruta bajo /api | Autorización y resultado |
|---|---|
| POST /auth/login | Contraseña y CAPTCHA existentes. Para un factor ACTIVO responde 202 con `totp_requerido`, `desafio_id`, `expira_en`; no crea sesión ni JWT hasta confirmar. |
| GET /auth/totp/estado | Sesión válida; devuelve estado, sin secreto ni URI. |
| POST /auth/totp/configurar | Sesión + CSRF; `{contrasena}`. Devuelve URI de vinculación y caducidad. Exige contraseña actual, cuenta activa y no bloqueada. |
| POST /auth/totp/confirmar | Sesión + CSRF; `{codigo}`. Activa exclusivamente una vinculación pendiente vigente. |
| POST /auth/totp/desactivar | Sesión + CSRF; `{contrasena,codigo}`. Revoca factor, recuperación y desafíos pendientes asociados. |
| POST /auth/totp/login/confirmar | `{desafio_id,codigo}` + cookie HttpOnly del desafío LOGIN. Solo después del éxito emite la sesión habitual. |
| POST /auth/desbloqueo/solicitar | `{nombre_usuario}`. Respuesta 202 genérica, incluso para cuentas ausentes o sin factor; cookie ligada al propósito DESBLOQUEO. |
| POST /auth/desbloqueo/confirmar | `{desafio_id,codigo}` + cookie del flujo. Solo permite factor previamente ACTIVO. Reinicia bloqueo y contador; **no emite JWT**. |
| POST /seguridad/desafios | Sesión + CSRF; `{codigo_politica,recurso_id,datos}`. Requiere adaptador real, política y permisos. |
| POST /seguridad/desafios/{id}/verificar | Mismo cuerpo + `codigo`; verifica operación y devuelve autorización limitada. |
| POST /seguridad/autorizaciones/{id}/ejecutar | Mismo cuerpo de operación; vuelve a validar permisos y estado, ejecuta y consume autorización atómicamente. |

Las respuestas de autenticación y seguridad llevan `Cache-Control: no-store`. No se devuelven secretos en JWT ni se registran códigos, contraseñas o hashes. La URI solo se entrega al titular autenticado durante vinculación; contiene un secreto y debe tratarse como credencial. Angular genera el QR localmente, sin servicios externos, sin almacenamiento persistente y lo retira al activar.

## Reglas y garantías

- PyOTP: SHA1, seis dígitos, 30 segundos, ventana máxima ±1. El reloj de referencia procede de PostgreSQL.
- AES-256-GCM con nonce aleatorio y AAD ligada al usuario; copiar el cifrado a otro usuario no permite descifrarlo.
- Bloqueo de fila y último intervalo aceptado compartido por los flujos: dos verificaciones concurrentes del mismo intervalo no pueden tener éxito. Si acaba de usarse un código para vincular, debe esperarse al siguiente intervalo para otra operación.
- Vinculación pendiente de diez minutos. Nunca reemplaza silenciosamente un factor activo. Revocar exige contraseña y TOTP válidos.
- Desafíos caducan según política, máximo cinco códigos incorrectos por desafío. Hay presupuesto persistente por IP y contexto de usuario (10 solicitudes por 600 segundos), independiente de crear nuevos desafíos.
- Cookies nonce firmadas, ligadas al identificador, propósito y contexto seudonimizado. Una cookie de otro flujo no sirve. La solicitud de desbloqueo no confirma si una cuenta existe; tampoco basta conocer su nombre para desbloquearla.
- Se conserva CAPTCHA desde el cuarto intento y bloqueo de tres horas al séptimo fallo de credenciales. Conforme al nuevo encargo TOTP, **un CAPTCHA incorrecto sin comprobación fallida de contraseña no incrementa el contador de contraseñas erróneas**; sí se registra y consume presupuesto por IP. Esto sustituye la regla anterior que contaba CAPTCHA inválido como fallo de contraseña.
- Se reutiliza la obtención de IP existente; no se confía indiscriminadamente en cabeceras de proxy.
- La tabla de recuperación queda mapeada y se revoca al desactivar. Esta entrega no añade códigos de emergencia ni una vía pública alternativa de recuperación.
- Los usuarios sin factor activo conservan el login existente. Los usuarios con factor activo requieren TOTP. La obligatoriedad institucional de vincular a todos los usuarios requiere una política posterior explícita; no se inventó una columna para ella.

## Operaciones sensibles: integración obligatoria futura

`AutorizacionAccionesService` y el registro `ADAPTADORES` constituyen el único ejecutor transaccional preparado. En producción el registro está vacío: no existen operaciones académicas implementadas. Por tanto, intentar autorizar una política sin adaptador devuelve 501 `OPERACION_NO_INTEGRADA`; no simula aprobación, eliminación ni cargue.

El SQL de referencia enumera `CURSO_APROBAR`, `CURSO_REPROBAR`, `CURSO_ELIMINAR`, `CURSO_CARGUE_EXCEL`, `CURSO_MODIFICAR_APROBACION`, `PERSONAL_ELIMINAR`, `PERSONAL_CARGUE_EXCEL`. Antes de activarlas, un operador debe verificar los registros reales, su estado, TTL y `permiso_requerido`. Un permiso ausente o incompatible deniega la operación. La migración no otorga permisos académicos ni modifica esas políticas.

Para implementar un recurso real:

1. Registrar un `AdaptadorAccion` por código de política en el arranque del backend, con tipo de recurso y permiso concreto.
2. `permitir` consulta permisos vigentes del actor. No debe confiar en botones, rol remitido por el cliente ni un booleano del cuerpo.
3. `preparar` valida datos, bloquea el recurso real y devuelve una instantánea serializable con `version` verificable. Para Excel debe incluir identificación y hash del archivo/lote validado por el servidor, versión del lote y operaciones previstas. No basta el nombre de archivo del navegador.
4. `ejecutar` aplica exclusivamente esa mutación, devuelve resultado y cambios de una lista explícita de campos auditables; **no hace commit, no abre otra transacción y no realiza efectos externos irreversibles**. Para efectos externos usar un mecanismo transaccional adecuado antes de incorporar el adaptador.
5. Exponer la ejecución únicamente mediante el servicio central. Cualquier otro endpoint que mute el mismo recurso debe exigir el mismo consumo transaccional; no crear una ruta paralela que omita TOTP.
6. Probar llamadas HTTP directas sin autorización, permisos revocados, otro actor/sesión/recurso, cambios de datos o versión, expiración, doble consumo y rollback.

El hash canónico incluye actor, sesión, política, tipo/ID de recurso, datos deseados y estado/versiones del servidor. La verificación y la ejecución recalculan esa huella. La autorización es de un solo uso. La mutación, consumo y auditoría se confirman juntos; un error revierte todo. Esto no protege automáticamente un futuro endpoint que ignore el servicio: la integración backend descrita es obligatoria.

## Despliegue pendiente en la base principal

Antes de habilitar TOTP:

1. Comprobar respaldo restaurable reciente y destino `esart_db`. Ejecutar el diagnóstico de solo lectura adjunto con el operador autorizado. Revisar también columnas y políticas reales: no ejecutar el archivo histórico `seguridad.sql` sobre las tablas existentes.
2. Revisar `p0005_integracion_totp.py`, comparar estructuras y resolver manualmente cualquier incompatibilidad u orfandad. No borrar registros para hacer pasar una validación.
3. Obtener autorización para esa migración nueva. Con conexión de migraciones del propietario separada de FastAPI, comprobar `alembic -c alembic.ini current` y aplicar únicamente la revisión revisada mediante `alembic -c alembic.ini upgrade p0005_integracion_totp`. Verificar primero el nombre real del archivo INI en la instalación. No usar `stamp`.
4. La propuesta añade cinco FK de usuarios y una FK compuesta de contexto de autorización, una UNIQUE, cuatro triggers de auditoría inmutable y dos políticas internas idempotentes. Concede USAGE de esquema, SELECT/INSERT donde corresponde, UPDATE limitado a columnas y uso de secuencias; nunca privilegios administrativos al backend. No crea ni recrea las siete tablas. No altera usuarios, contraseñas ni roles. Si hay nombres/estructuras incompatibles, aborta la transacción.
5. Aprovisionar externamente `TOTP_CLAVE_CIFRADO`: Base64 estándar de 32 bytes criptográficamente aleatorios. No imprimirla en logs, guardarla en Git ni reutilizar JWT como clave AES. Conservar respaldo seguro de esa clave: perderla inutiliza factores existentes. La rotación requiere un procedimiento de recifrado autorizado; no regenerarla en cada arranque.
6. Establecer `TOTP_HABILITADO=true` en configuración protegida solo después de comprobar permisos, políticas, integridad y clave. Reiniciar backend. Ante configuración incompleta el login habilitado falla cerrado con 503, sin omitir el segundo factor.
7. Verificar con una cuenta de prueba autorizada en ese despliegue: QR, activación, login 202 → TOTP → sesión, cierre y desbloqueo sin JWT. No bloquear cuentas reales para probar.

La migración no permite downgrade destructivo automático: un rollback requiere plan autorizado que conserve factores y auditoría. No confundir deshabilitar una bandera de funcionalidad con un mecanismo seguro de recuperación de factores.

## Archivos y validación

Backend: modelos `totp.py`, servicios `totp.py` y `autorizacion_acciones.py`, routers `totp.py` y `acciones_seguras.py`; integración en configuración, principal, autenticación y seguridad_login; propuesta p0005; dependencias PyOTP/cryptography. Frontend: servicio TOTP, servicio/modelo de sesión, componente existente `paginas/totp`, login, botón de desbloqueo y ruta protegida `/totp`. No se modificó la lógica académica.

Pruebas: `test_totp_unidad.py`, `test_totp_pg.py`, regresiones CAPTCHA, sesión y Angular; herramientas de clúster aislado y navegador. El laboratorio instala el esquema histórico solamente en un clúster nuevo vacío, aplica las migraciones y usa las rutas HTTP reales con permisos de aplicación. La captura del CAPTCHA generado y los códigos TOTP del laboratorio solo sirven para automatizar cuentas aisladas; no se incorpora esa observación al backend operativo.

Comandos desde backend: `.venv\Scripts\python.exe -m pytest -ra`, `.venv\Scripts\python.exe -m ruff check .`, `.venv\Scripts\python.exe -m herramientas.probar_seguridad_aislada`. Desde frontend/esart: `npm test -- --watch=false`, `npm run build`. El último comando de backend inicia PostgreSQL/Chrome locales y requiere permiso del sistema para crear procesos.

Angular: 61 pruebas aprobadas; build aprobado con aviso de optimización CommonJS de la dependencia local qrcode. Ruff sin errores. Los resultados finales PostgreSQL/navegador se consignan al terminar la ejecución aislada. No se afirma que TOTP esté operativo en esart_db: faltan los pasos de despliegue anteriores.


## Evidencia de ejecuci?n aislada final

Directorio retenido: `backend/respaldos/hu06_f9c638f3fcd74a66ab82452993e58f27`; cl?ster detenido al finalizar.

- `navegador_totp/resultado.json`: QR local v?lido y retirado al activar; primer factor 202; sin JWT antes de TOTP; confirmaci?n 200; consulta de sesi?n 200; logout 204. Sin interceptar HTTP ni inyectar estado privado de Angular.
- `navegador_desbloqueo/resultado.json`: CAPTCHA desde cuarto intento; s?ptimo fallo 423; desaf?o 202; desbloqueo 200; sin JWT; formulario de login habilitado.
- Capturas sin QR ni c?digos: `navegador_totp/activado.png`, `navegador_totp/segundo_factor.png`, `navegador_desbloqueo/desbloqueo.png`. El QR real se valida en DOM sin conservar una captura de su secreto.
- Pruebas de servicio: concurrencia/replay, cookie ajena, expiraci?n de vinculaci?n, revocaci?n, auditor?a inmutable, consumo ?nico, permisos cambiados, versi?n cambiada y rollback de la mutaci?n/autorizaci?n.

Estas evidencias demuestran la implementaci?n integrada en laboratorio, no la puesta en servicio en la base principal. Siguen pendientes la aprobaci?n de p0005, los permisos, la clave protegida y la verificaci?n de pol?ticas reales con un operador autorizado.
