# Corrección del bloqueo de cuentas y CAPTCHA

Fecha: 16 de noviembre de 2026, Colombia.

## Causa y resultado

`seguridad_login.preparar` enviaba todos los rechazos de CAPTCHA a `rechazar(..., contar=False)`. Era una decisión de la política anterior para evitar incrementar cuentas con peticiones sin desafío; también excluía incorrectamente, para el nuevo requisito, respuestas erróneas de desafíos propios y pendientes. Por eso la repetición de CAPTCHA incorrectos nunca alcanzaba el séptimo fallo.

La corrección distingue un primer envío legítimamente asociado a un desafío de los envíos vacíos, ajenos o repetidos. Credenciales y CAPTCHA utilizan la misma función central de rechazo, que incrementa una vez, decide el bloqueo, registra intento/auditoría y confirma la transacción antes de devolver el error.

No hay cambios de esquema ni migraciones nuevas. La inspección de solo lectura de esart_db confirmó `esart_ref.usuarios.intentos_fallidos_consecutivos`, `bloqueado_hasta` y las tablas de intentos, auditoría, límites IP, estados anónimos y desafíos de p0004. La revisión p0004 fue confirmada administrativamente en la entrega anterior. No se escribió en la base operativa durante esta corrección ni se probaron bloqueos o contraseñas de cuentas reales.

## Qué cuenta como intento fallido

Las credenciales deben superar primero la validación del esquema de login. Desde el cuarto intento, el servidor exige CAPTCHA y no comprueba la contraseña si falla el desafío.

| Situación | Contador de cuenta | Otros efectos |
| --- | --- | --- |
| Credenciales incorrectas, con CAPTCHA válido cuando es obligatorio | +1 | Intento y auditoría |
| Primer envío incorrecto de desafío pendiente del mismo contexto | +1 | Consumo atómico, intento y auditoría |
| Primer envío de desafío vencido del mismo contexto | +1 | Consumo atómico, intento y auditoría |
| Respuesta con caracteres inválidos a un desafío propio pendiente | +1 | Rechazo sin bcrypt, consumo y auditoría |
| Desafío ausente, ID desconocido, contexto ajeno o desafío ya consumido | Sin incremento | Cuota IP, intento rechazado y auditoría; nunca bcrypt |
| Solicitud que no supera validación de esquema | Sin incremento | 422, sin autenticación |
| Generar o regenerar imagen | Sin incremento | Cuota IP propia y auditoría CAPTCHA |
| Avería del proveedor o estructura ausente | Sin incremento | 503 y rollback; no se confirma un fallo de cuenta |
| Intento durante bloqueo vigente | Sin incremento ni prórroga | 423, intento y auditoría |

El proveedor PostgreSQL comunica internamente `fallo_contabilizable`, reiniciado en cada validación y habilitado solo al consumir por primera vez un desafío del contexto correcto. No es un campo recibido de Angular ni una prueba de identidad. El cliente no puede enviar un booleano para aumentar, reiniciar o validar el contador.

Los IDs y respuestas ausentes, ajenos o repetidos no permiten probar contraseñas y no se tratan como nuevos fallos independientes de cuenta. Exigir un desafío nuevo para contar otro rechazo evita multiplicar un único envío mediante carreras o replay. Las cuotas IP de login y generación siguen siendo independientes del nombre enviado, por lo que cambiar de nombre no reinicia esas ventanas.

Esta política permite que fallos reales de CAPTCHA provoquen bloqueo antes de verificar contraseñas, como exige el encargo. Un desafío está ligado al contexto del nombre, no acredita quién lo solicitó; los límites IP siguen siendo necesarios frente a intentos de provocar bloqueos de otras cuentas. No se añadió una vía de omisión del CAPTCHA o del bloqueo.

## Atomicidad, bloqueo y desbloqueo

Se conserva el orden de bloqueos de filas: cuota IP, usuario o estado anónimo y después desafío. El contador se lee con `FOR UPDATE`; el desafío también se bloquea y su consumo participa en la misma transacción que el incremento y auditoría. Envíos concurrentes del mismo desafío solo pueden sumar una vez. Los otros rechazos siguen consumiendo presupuesto IP y registrándose.

Fallos 1–3 se registran; la respuesta del tercero exige CAPTCHA para el siguiente. Al alcanzar siete se fija `bloqueado_hasta = ahora_del_servidor + 3 horas`. El contador se limita a siete. Durante un bloqueo no se verifican contraseña ni CAPTCHA y el plazo no se extiende. En el instante exacto de expiración, el siguiente intento reinicia el ciclo y registra `BLOQUEO_VENCIDO`; no se necesita una tarea que escriba periódicamente. Un login exitoso reinicia el contador, como antes.

Una excepción inesperada del proveedor ya no se convierte en CAPTCHA incorrecto: provoca rollback y 503. Las respuestas con caracteres no válidos se rechazan antes de calcular su HMAC, evitando tratar texto Unicode no codificable como una avería de infraestructura.

## Contrato vigente del login

Solicitud y cookies/JWT se mantienen. 200 sigue indicando éxito; 401 `CREDENCIALES_INVALIDAS` corresponde a un rechazo sin bloqueo; 422 a entrada inválida; 429 `INTENTOS_LIMITADOS` a cuota IP; 503 a indisponibilidad. El límite IP se aplica primero: una petición que ya agotó esa cuota puede obtener 429 sin consultar el estado de una cuenta.

Al séptimo fallo y durante un bloqueo:

```json
{
  "error": {
    "codigo": "CUENTA_BLOQUEADA",
    "mensaje": "Su cuenta se encuentra bloqueada temporalmente por múltiples intentos fallidos de inicio de sesión.",
    "detalle": {
      "bloqueado_hasta": "2026-11-16T15:00:00+00:00",
      "segundos_restantes": 10800,
      "captcha_requerido": false,
      "acceso_temporalmente_restringido": true
    }
  }
}
```

HTTP **423 Locked**. La fecha del ejemplo es ilustrativa, no una modificación programada. `segundos_restantes` lo calcula FastAPI con el reloj del servidor, redondeando hacia arriba. No se devuelve el contador, el motivo interno, el ID de cuenta ni una indicación de existencia.

Los nombres inexistentes conservan estado anónimo persistente y la misma política: a la misma secuencia de fallos responden con los mismos códigos, campos y duración. Así el nuevo 423 no se reserva a cuentas registradas. Las fechas concretas corresponden al ciclo de intentos de cada contexto, sin confirmar su existencia. Las rutas de sesión autenticada mantienen su rechazo previo cuando un usuario está bloqueado.

## Angular

`inicio-sesion.ts` reconoce el par 423/CUENTA_BLOQUEADA. Cierra el modal, suprime la solicitud de CAPTCHA, vacía la contraseña y muestra la alerta existente, fecha de desbloqueo y tiempo restante HH:MM:SS. Se conserva el diseño institucional.

El botón de acceso queda deshabilitado y sus manejadores también rechazan el envío mientras el bloqueo sea conocido. Un intervalo actualiza solo la presentación, a partir de los segundos enviados por el backend y del reloj monotónico del navegador; no cuenta fallos ni hace peticiones de login. Al llegar a cero elimina la restricción local y permite un nuevo envío: PostgreSQL y FastAPI siguen decidiendo si procede CAPTCHA o autenticación. Cambiar de usuario limpia el aviso asociado al nombre anterior, sin alterar ningún estado de servidor.

El intervalo se limpia al destruir el componente. Un plazo ausente o malformado no se inventa: se conserva la restricción conocida sin mostrar una cuenta regresiva falsa. La fecha local se presenta con es-CO; el formato anterior de fecha se conserva como compatibilidad de presentación.

## Pruebas y alcance de ejecución

Se usan cuentas generadas exclusivamente dentro de un clúster nuevo, directorio marcado bajo backend/respaldos, puerto diferente del operativo y credenciales efímeras. El ejecutor comprueba data_directory. Su base se llama esart_db para usar el mismo esquema de migraciones, pero es otra instancia: no es la base operativa ni las bases históricas de pruebas.

Las migraciones históricas solo preparan ese entorno vacío de pruebas; no hay una migración nueva y ninguna se ejecuta en PostgreSQL operativo. El clúster se detiene al terminar y conserva evidencia local ignorada por Git.

Casos cubiertos: fallos 1–3, CAPTCHA obligatorio desde el cuarto, fallos CAPTCHA 4–7, 423 inmediato y tres horas, credenciales correctas durante bloqueo, desbloqueo exacto con reloj simulado, reinicio por éxito, intentos/auditoría, carreras, replay, errores de infraestructura, cuota IP al cambiar nombres, estados anónimos y regeneración sin incremento. Angular comprueba cierre del modal al recibir 423, alerta, botón deshabilitado, cuenta regresiva y reactivación sin peticiones automáticas.

Resultados finales:

- Backend offline: **179 aprobadas, 40 omitidas** (integraciones no habilitadas en ese comando).
- PostgreSQL real aislado: **27 aprobadas**, además de una prueba de compatibilidad HTTP sobre p0003 antes de preparar p0004 en esa instancia.
- Evidencia final: `backend/respaldos/hu06_7b1a418ac11b4c8aada7877ecc13827e/resultado.json`. Clúster detenido.
- Angular: **45 aprobadas**, ocho archivos; build de producción correcto.
- Ruff sobre backend completo: sin errores.

La autenticación con admin.esart no se intentó y su contraseña no se modificó. No se certifica un bloqueo real en la instancia operativa: la verificación de fallos usa exclusivamente cuentas aisladas. Los cambios están preparados en el código; el servicio desplegado debe recargar la versión actual y el frontend usar el nuevo build para adoptar el contrato 423.

## Archivos de esta corrección

- Backend: `aplicacion/servicios/seguridad_login.py`, `aplicacion/servicios/captcha_local.py`, `aplicacion/seguridad/captcha.py`.
- Pruebas backend: `pruebas/test_seguridad_login.py`, `pruebas/test_seguridad_login_pg.py`, `pruebas/test_captcha_local_pg.py`, `pruebas/test_captcha_vigencia.py`.
- Frontend: `src/app/paginas/inicio-sesion/inicio-sesion.ts`, `inicio-sesion.html`, `inicio-sesion.spec.ts`.
- Documentación: este informe y avisos de actualización en los contratos anteriores.

No se modifican modelos, migraciones, credenciales, configuración operativa ni módulos ajenos a autenticación.
