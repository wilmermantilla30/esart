# Datos reales de la terminal y autorización del flujo bloqueado

Fecha: 16 de noviembre de 2026, Colombia.

## Resultado de la inspección de solo lectura

Se consultó directamente esart_db con esart_aplicacion, dentro de una transacción READ ONLY, sin intentos de login ni cambios de cuenta:

| Dato de prueba.seguridad | Resultado |
| --- | --- |
| Usuario | prueba.seguridad |
| intentos_fallidos_consecutivos | **7** |
| bloqueado_hasta | **2026-11-16T10:08:16.295504+00:00** |
| Hora de Colombia | **16/11/2026, 5:08:16 a. m.** |
| Bloqueo vigente al consultar | Sí |
| Evento CUENTA_BLOQUEADA auditado | Presente |
| IP del intento que produjo ese evento | Registrada, pero de loopback |

La IP se obtuvo relacionando auditoria_acceso.intento_id con intentos_inicio_sesion.id y filtrando el evento CUENTA_BLOQUEADA del usuario. Auditoría no tiene una IP propia. Una dirección de loopback identifica al peer local observado, posiblemente un proxy; no prueba la dirección de la terminal. No se publica como IP del usuario ni se incluyen direcciones concretas en este informe.

El campo bloqueado_hasta no se sustituye por una fecha generada en el navegador. El estado vigente se calcula contra el reloj del servidor; después del vencimiento puede permanecer una fecha pasada almacenada hasta el siguiente intento, conforme al desbloqueo lógico existente.

## Por qué no se habilitó el contador en el login público

El comprobante actual protege firma, audiencia, contexto y expiración. Es HttpOnly y no es un JWT de sesión. Sin embargo, la ruta de login lo entrega ante **cualquier 423**, también cuando un navegador nuevo envía el nombre de una cuenta que ya estaba bloqueada. No acredita que ese navegador originó los fallos anteriores ni que su operador sea el titular de la cuenta.

Por tanto, permitir que ese comprobante consulte el contador o una IP histórica divulgaría datos a quien solo conoce un nombre. Agregar un identificador aleatorio al comprobante sin verificar identidad tampoco resuelve esa autorización: un tercero podría obtener un nuevo flujo para el mismo nombre.

Se aplicó la condición expresa del encargo: **conservar detalles restringidos y proponer un mecanismo seguro antes de habilitarlos**. No se cambió la ventana para mostrar siete por inferencia del umbral, ni se inyectó el resultado de esta inspección administrativa en el frontend.

La consulta administrativa autenticada existente, GET `/api/auth/administracion/bloqueos/{usuario_id}`, sigue siendo la vía disponible para leer el contador real. No acepta el comprobante de bloqueo como sesión ni concede permisos a partir del nombre enviado. La IP sigue sin exponerse, incluso allí, porque no hay atribución confiable a una terminal ni autorización específica de exposición.

## Qué muestra ahora cada dato y su origen

| Elemento | Origen y protección |
| --- | --- |
| Usuario ingresado | Entrada original del flujo conservada en el comprobante; no confirma una identidad registrada |
| Intentos fallidos | Restringidos en el login público; el valor real se consulta solo bajo autorización administrativa |
| Dirección IP terminal | No disponible: el registro inspeccionado es loopback, no una IP terminal acreditada |
| Desbloqueo estimado | Campo bloqueado_hasta leído de PostgreSQL para el contexto firmado |
| Reintento disponible | Fecha de desbloqueo y hora del servidor; el modal muestra HH:MM, redondeando el minuto hacia arriba para no anunciar 00:00 antes del vencimiento |

GET `/api/auth/bloqueo` ahora incluye `segundos_restantes`, calculados en FastAPI, y `detalles_autorizados: false`. Mantiene contador e IP en null. Ni query string ni X-ESART-Usuario cambian el contexto firmado. El frontend conserva un único reloj de presentación derivado de la fecha; no crea ni reinicia contadores de seguridad. El diseño, CSS y estructura institucional no se modificaron.

La cookie permite recuperar el estado temporal del contexto previo al recargar; no autoriza información privada. Eliminarla no elimina el bloqueo de PostgreSQL. El login continúa aplicando CAPTCHA desde el cuarto intento, bloqueo al séptimo fallo y duración de tres horas.

## Propuesta pendiente de aprobación: continuidad de flujo más prueba de identidad

No se implementó ni desplegó este mecanismo en esta tarea:

1. Iniciar un flujo con nonce aleatorio del servidor en cookie HttpOnly/Secure/SameSite; persistir únicamente su huella, contexto normalizado, expiración y referencias a intentos. La persistencia compartida por trabajadores necesita un diseño de esquema revisado y autorización de migración; no usar un diccionario de proceso.
2. Vincular cada intento y el evento que causa el bloqueo a ese flujo. Un simple rechazo BLOQUEO_VIGENTE no concede acceso a detalles ni crea evidencia de autoría del bloqueo.
3. Antes de consultar datos de la cuenta, exigir una prueba de titularidad independiente del nombre: por ejemplo un factor institucional previamente registrado y verificado mediante un canal interno autorizado. ESART no dispone aquí de un proveedor de recuperación que pueda asumirse operativo; no se simula OTP ni se inventa una validación. Como alternativa ya disponible, la consulta se realiza por un administrador autenticado.
4. Tras verificar identidad, emitir una capacidad de alcance exclusivo `leer_detalle_bloqueo`, vinculada a nonce, contexto, evento y expiración breve. Mantener revocación/consumo y auditoría en servidor. No convertirla en sesión de aplicación, no reiniciar fallos y no permitir iniciar sesión durante el bloqueo.
5. El endpoint comprueba capacidad, identidad verificada, evento y estado vigente antes de devolver contador real. No acepta selectores arbitrarios de otra cuenta. El flujo inválido no revela existencia, canales de contacto ni motivos internos; la cuota y auditoría de verificaciones se diseñan antes de habilitar el servicio.
6. Para IP, devolver como máximo la observación del evento de ese flujo, solo si su atribución es confiable y su exposición fue autorizada. Si existe proxy, definir una lista de proxies de confianza y la cadena de origen; nunca aceptar X-Forwarded-For del cliente sin esa configuración ni etiquetar loopback como terminal.

Antes de habilitar detalles públicos se requiere aprobar el factor/proveedor real, el modelo de persistencia, la política de exposición de IP, la revocación y sus pruebas. La firma del comprobante actual, por sí sola, no satisface estos requisitos.

## Verificación

Se añadió una prueba HTTP que simula el rechazo 423 a un nombre y obtiene el comprobante real. Con ese comprobante, otra cabecera/nombre no cambia la consulta, contador/IP permanecen restringidos y la ruta administrativa sigue rechazando el acceso sin sesión. La prueba no valida credenciales ni genera datos en la principal.

Se ejecutan las suites de seguridad/backend/Angular y las pruebas PostgreSQL en un clúster separado con cuentas generadas, sin bloquear usuarios reales. Las migraciones existentes solo preparan ese clúster de pruebas, no la instancia operativa. No se modificaron migraciones del proyecto, estructuras ni registros existentes en esart_db.

## Archivos de esta revisión

- `backend/aplicacion/servicios/estado_bloqueo.py`: segundos restantes reales y autorización de detalles explícitamente denegada.
- `backend/pruebas/test_comprobante_bloqueo.py`: regresión contra divulgación mediante un 423/comprobante y sustitución de nombre.
- `frontend/esart/src/app/paginas/inicio-sesion/ventana-bloqueo/ventana-bloqueo.ts`: formato HH:MM sin un reloj independiente.
- `ventana-bloqueo.spec.ts`: expectativas del formato nuevo.
- Este informe con diagnóstico y propuesta. No se habilitaron detalles adicionales ni se modificaron el componente padre, el HTML institucional o el CSS.
