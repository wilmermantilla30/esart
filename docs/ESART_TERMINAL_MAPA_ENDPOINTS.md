> Flujo publico actualizado: [registro del envio actual y prueba completa en Chrome](ESART_FLUJO_PUBLICO_REGISTRO_TERMINAL.md). Ahora el modal publico presenta la instantanea de su propio POST y la conserva al recargar; el historico sigue restringido. Esta revision anterior describe el estado previo.

> Actualizacion: la consulta administrativa ahora devuelve la IP registrada del ultimo intento, con advertencia de loopback. El login publico sigue restringido. Consulte [validacion real autorizada](ESART_TERMINAL_VALIDACION_REAL_AUTORIZADA.md). Las referencias a IP null administrativa siguientes describen el estado anterior.

# Diagnóstico definitivo del contrato del Registro de la terminal

Fecha: 16 de noviembre de 2026, Colombia.

## Causa exacta, separando servidor y frontend

No hay un fallo de PostgreSQL que borre o pierda el contador. La consulta READ ONLY directa en esart_db confirmó `prueba.seguridad`, contador **7** y `bloqueado_hasta = 2026-11-16T15:33:41.636454+00:00`, equivalente a **10:33:41 a. m. de Colombia**. Es un bloqueo posterior al documentado en la revisión anterior; no se reemplazó ni modificó aquí.

Hay cuatro decisiones que explicaban los textos:

1. **Backend:** el servicio del endpoint público devuelve contador/IP null y `detalles_autorizados: false`. Es una restricción deliberada, no información perdida en transporte.
2. **Interfaz TypeScript:** `EstadoBloqueoPublico` no declaraba contador, IP, segundos ni autorización, aunque algunos de esos campos ya estaban en el JSON.
3. **Padre Angular:** tanto al recuperar estado como al recibir un 423 fijaba `intentos: null` e `ip: ''`. Por tanto, también habría descartado un futuro detalle correctamente autorizado.
4. **Modal:** su entrada `detallesAdministrativos` quedaba en false porque el padre nunca la enlazaba. El componente ocultaba los campos incluso si se le suministraban valores.

Se corrigieron 2, 3 y 4. No se eliminó la restricción de 1 sin una prueba de autorización suficiente.

## Qué endpoint alimenta cada campo

| Campo | Al producirse el bloqueo | Al recargar | Consulta administrativa |
| --- | --- | --- | --- |
| Usuario ingresado | Valor enviado por el formulario al POST `/api/auth/login`; no confirma identidad | GET `/api/auth/bloqueo`: `usuario_intentado` del comprobante | GET `/api/auth/administracion/bloqueos/{usuario_id}`: `usuario_intentado` leído de usuarios.usuario |
| Intentos | POST login, 423: `detalle.intentos_fallidos_consecutivos = null` | GET bloqueo: `intentos_fallidos_consecutivos = null` | Campo real `usuarios.intentos_fallidos_consecutivos`, solo tras sesión administrativa válida |
| IP | POST login, 423: `detalle.direccion_ip = null` | GET bloqueo: `direccion_ip = null` | También null: no existe autorización/atribución segura a terminal |
| Desbloqueo | POST login, 423: `detalle.bloqueado_hasta` | GET bloqueo: `bloqueado_hasta` | Campo usuarios.bloqueado_hasta |
| Tiempo restante | Fecha anterior y `ahora_servidor` del detalle 423 | Fecha y hora del GET, más `segundos_restantes` calculados en FastAPI | Fecha, hora de servidor y segundos calculados |
| Autorización de detalles | `detalle.detalles_autorizados = false` | `detalles_autorizados = false` | `detalles_autorizados = true` tras comprobar sesión y rol ADMINISTRADOR |

El servicio HTTP añade `/api`; el proxy de Angular dirige `/api` a `http://127.0.0.1:8081`. No hay otro endpoint oculto que suministre el contador al login. La ventana pública no consulta automáticamente la ruta administrativa ni obtiene ese permiso por cambiar su nombre de usuario.

## Evidencia más allá de pruebas unitarias

Resultado del servicio real que construye GET bloqueo, ejecutado en transacción de solo lectura contra esart_db, a las 07:41:30 de Colombia:

```json
{
  "bloqueado": true,
  "usuario_intentado": "prueba.seguridad",
  "bloqueado_hasta": "2026-11-16T15:33:41.636454+00:00",
  "ahora_servidor": "2026-11-16T12:41:30.614611+00:00",
  "segundos_restantes": 10332,
  "detalles_autorizados": false,
  "intentos_fallidos_consecutivos": null,
  "direccion_ip": null
}
```

Esta captura procede de invocar el servicio real con la conexión de solo lectura autorizada, no de obtener una sesión o comprobante para el usuario real. No se afirma haber accedido al navegador privado del usuario. El tiempo es una observación puntual, no un valor que se fija en Angular.

Petición HTTP real a través del proxy, sin cookie de contexto: `GET http://127.0.0.1:4200/api/auth/bloqueo?nombre_usuario=prueba.seguridad` devolvió **200, `{"bloqueado":false}`**. Eso prueba que poner el nombre en la URL no obtiene los datos; no significa que la cuenta consultada esté desbloqueada.

Las pruebas PostgreSQL aisladas complementan estas lecturas: HTTP real con cookie generada por un bloqueo, cliente nuevo que recupera el estado, contador siete almacenado, datos privados null públicamente, rechazo 401 sin sesión y 403 con rol USUARIO, consulta administrativa con contador siete y autorización explícita. Usan otra instancia y cuentas generadas, no prueba.seguridad en la operativa.

## IP: origen y limitaciones comprobadas

La IP se registra en `esart.intentos_inicio_sesion.direccion_ip`. `esart.auditoria_acceso` no tiene una IP independiente: referencia al intento mediante intento_id. Se inspeccionó el intento vinculado al evento CUENTA_BLOQUEADA más reciente del usuario, no un reintento arbitrario posterior.

Ese registro contiene una dirección **loopback**. El proxy se comunica localmente con FastAPI; la dirección observada no permite asegurar cuál era la terminal del operador. No se imprime ni presenta como IP terminal. La función obtener_ip_cliente tampoco confía en Forwarded/X-Forwarded-For/X-Real-IP: si están presentes considera el origen no verificable. No se habilitó confianza indiscriminada en esas cabeceras ni se modificó la configuración del proxy.

## Cambios de integración

- `DetalleBloqueo` y `EstadoBloqueoPublico` se declaran en los modelos TypeScript con los campos reales del JSON.
- `SesionService` usa ese modelo compartido; no descarta ni traduce campos de seguridad.
- `inicio-sesion.ts` utiliza una única función de mapeo para recuperación y error 423. Solo copia contador/IP si `detalles_autorizados === true`, valida que el contador sea entero no negativo y nunca sustituye un dato ausente por cero.
- El HTML enlaza la autorización del servidor con el modal. El indicador controla presentación; no concede permisos de API y no se recibe como autoridad desde el cliente.
- El 423 ahora declara explícitamente null para los campos privados y false para su autorización, igual que GET bloqueo.
- La ruta administrativa devuelve nombre, contador real, fecha, hora, segundos restantes y autorización tras comprobar la identidad administrativa. No lee contraseñas y no expone IP.
- Se conserva HH:MM en la ventana, derivado de bloqueado_hasta y la hora del servidor. El minuto se redondea hacia arriba; no hay contador de seguridad local ni segundo reloj en el hijo.
- No se alteraron estilos o estructura visual: solo el enlace de datos y sus tipos.

La prueba Angular de respuesta autorizada usa un payload controlado para verificar el mapeo y el DOM. **No supone que el endpoint público actual haya adquirido autorización**. La prueba complementaria confirma que valores recibidos con autorización false siguen ocultos.

## Por qué la ventana pública seguirá restringida y qué falta

El comprobante firmado puede obtenerlo un navegador nuevo que solo intente acceder a una cuenta ya bloqueada: la ruta lo emite ante cualquier 423. Firma y HttpOnly protegen integridad/contexto; no prueban titularidad ni autoría de los fallos. Por eso no basta con copiar el contador de usuarios al GET público.

La condición del encargo permite conservar la restricción cuando el comprobante sea insuficiente. Para habilitar detalles del propietario hace falta una verificación adicional mediante un factor institucional previamente registrado y operativo, o una sesión administrativa válida. Un nonce de flujo por sí solo no prueba titularidad de la cuenta. La propuesta detallada de continuidad, factor de identidad, capacidad de alcance limitado, auditoría y atribución de IP está en [Datos reales y autorización](ESART_TERMINAL_DATOS_REALES_Y_AUTORIZACION.md).

Ese factor de recuperación no está implementado ni autorizado aquí; no se simuló OTP, autenticación o consentimiento. No se ejecutaron migraciones, GRANT ni escrituras sobre esart_db. El resultado actual es: integración capaz de presentar datos autorizados, contador real disponible administrativamente y detalles del login público aún restringidos por una razón comprobada.

## Archivos de esta revisión

Verificación final: **183 pruebas backend aprobadas, 40 omitidas** por requerir integración; **27 PostgreSQL aisladas aprobadas**, además de compatibilidad HTTP sobre p0003 en esa instancia; **51 Angular aprobadas**, build de producción correcto y Ruff sin errores. Evidencia PostgreSQL: `backend/respaldos/hu06_cee95cd269e942a5945a370d4376400c/resultado.json`; clúster detenido. No se realizaron intentos fallidos ni cambios sobre cuentas reales.

- `backend/aplicacion/servicios/seguridad_login.py`: contrato explícito del 423.
- `backend/aplicacion/rutas/autenticacion.py`: contrato completo de la consulta administrativa.
- `backend/pruebas/test_captcha_local_pg.py`: verificación de esos campos autorizados.
- `frontend/esart/src/app/nucleo/modelos/sesion.ts` y `nucleo/servicios/sesion.service.ts`: modelo JSON compartido.
- `paginas/inicio-sesion/inicio-sesion.ts`, `inicio-sesion.html`, `inicio-sesion.spec.ts`: mapeo único, enlace y pruebas autorizadas/restringidas.
- Este informe con el mapa de endpoints y evidencia. Ninguna migración fue modificada.
