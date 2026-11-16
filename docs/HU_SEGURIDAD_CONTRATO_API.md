> Contrato actualizado: [correccion de bloqueo y CAPTCHA](HU_SEGURIDAD_BLOQUEO_CAPTCHA_CORRECCION.md). Sustituye la politica anterior de no contar ningun fallo CAPTCHA y el rechazo 401 durante bloqueo. Los resultados historicos siguientes conservan su contexto original.

# Contrato backend de seguridad para integración del login

Alcance acordado: **backend exclusivamente**. Angular y el generador CAPTCHA se desarrollan en otro proceso. Este contrato describe endpoints existentes y el puerto del proveedor que ese trabajo debe integrar. No implica despliegue en la principal ni aceptación de una validación realizada en JavaScript.

## POST /api/auth/login

Solicitud JSON existente, sin campos nuevos de autoridad del cliente:

```json
{
  "nombre_usuario": "nombre.del.usuario",
  "contrasena": "entrada-del-operador",
  "captcha_id": null,
  "captcha_respuesta": null
}
```

El ejemplo no es una credencial real ni predeterminada. No guardar el cuerpo ni incluirlo en logs. Los campos CAPTCHA pasan de null a las cadenas emitida/contestada cuando exista un desafío real. Límite de nombre 3–80 caracteres; contraseña no vacía y límite bcrypt 72 bytes UTF-8. captcha_id hasta 64 caracteres, captcha_respuesta hasta 20. Campos adicionales se rechazan: no se aceptan captcha_valido, intentos, bloqueado_hasta o claves de rol.

El nombre se normaliza en el servidor mediante strip y lower de PostgreSQL. Estado de la cuenta, IP, CAPTCHA y tiempos son decisiones exclusivas del servidor.

### 200: autenticación correcta

Se conserva el contrato actual: objeto usuario con nombre_usuario, nombre_completo y rol; expira_por_inactividad_segundos. El JWT se envía exclusivamente en cookie esart_sesion HttpOnly, SameSite Strict, Secure según configuración. Se conserva la cookie CSRF del flujo existente. No se devuelve JWT, hash ni contraseña en JSON.

El éxito reinicia el contador y confirma intento, auditoría, último acceso y sesión dentro de la transacción. GET /api/auth/yo y POST /api/auth/cerrar-sesion mantienen sus contratos; validar_sesion rechaza también un usuario que esté bloqueado en ese momento. No se cambió el algoritmo JWT ni se agregó un bypass.

### 401: rechazo genérico

```json
{
  "error": {
    "codigo": "CREDENCIALES_INVALIDAS",
    "mensaje": "No fue posible iniciar sesión. Compruebe los datos o inténtelo más tarde.",
    "detalle": {
      "captcha_requerido": true,
      "acceso_temporalmente_restringido": false
    }
  }
}
```

- captcha_requerido indica el requisito para el siguiente intento. Se activa en la respuesta del tercer fallo; el cuarto exige validación antes de bcrypt.
- acceso_temporalmente_restringido indica el estado público genérico. No contiene fecha exacta, contador, motivo interno o confirmación de existencia.
- Los nombres inexistentes mantienen la misma política persistente y respuesta pública; no se crean cuentas para ellos.
- Un CAPTCHA inválido/ausente consume cuota IP y auditoría, pero no incrementa el contador de credenciales ni comprueba contraseña. No se puede verificar ninguna contraseña por esa ruta.
- Siete fallos de credenciales, con CAPTCHA válido desde el cuarto, bloquean tres horas. Reintentar durante el bloqueo no prorroga el plazo. En el instante exacto de vencimiento comienza un ciclo nuevo.

La interfaz debe interpretar el detalle del servidor, sin contar 401 locales ni calcular el desbloqueo. No debe quedar bloqueada para siempre por una bandera local: un reintento posterior debe poder consultar de nuevo al servidor. No usar USUARIO_BLOQUEADO como único código esperado para esta HU.

### 429: cuota IP

error.codigo = INTENTOS_LIMITADOS y mensaje genérico. Se aplica antes de comprobar la contraseña o consultar el estado de una cuenta. No se debe convertir este resultado en un incremento local del contador. La ausencia de detalle CAPTCHA en un 429 no significa que se haya validado o reiniciado el estado de una cuenta.

### 503: despliegue de seguridad incompleto

error.codigo = SEGURIDAD_NO_DISPONIBLE. Los objetos p0003 no están disponibles; no se autentica sin estos controles. No crear fallback a un login anterior ni a una base de pruebas.

### 422: solicitud inválida

Se mantiene el manejador de validación existente, sin devolver la contraseña enviada. No se autentica ni se emite una sesión. Las entradas que no pasan validación de esquema no se consideran comprobaciones de credenciales.

## Puerto de CAPTCHA real

Ruta de integración de código: aplicacion/seguridad/captcha.py, dependencia obtener_verificador_captcha del endpoint de login. El otro proceso debe proporcionar una implementación real de:

```python
async def verificar(identificador: str | None, respuesta: str | None, contexto: str) -> bool:
    ...
```

contexto es una clave HMAC del nombre normalizado, calculada por el backend. No la elige el cliente. El verificador debe comprobar vínculo al contexto, expiración, autenticidad y consumo de un solo uso **atómico**. El generador debe usar la misma normalización y clave del servidor al asociar un desafío. Una validación booleana del componente Angular no sirve como prueba.

El proveedor por defecto siempre rechaza. No hay respuestas prefijadas, CAPTCHA falso, modo permisivo ni generador de imágenes en esta HU. El servicio captura un fallo del proveedor como CAPTCHA no válido y no procede a bcrypt. Los dobles que validan desafíos conocidos existen exclusivamente en las pruebas aisladas; no se registran en producción.

## Endpoint de emisión: propuesta para acordar con la siguiente HU

No se implementó un endpoint que fabrique o simule desafíos. Para evitar exponer el nombre en URLs, se propone **POST /api/auth/captcha**, con nombre_usuario en JSON, y respuesta que contenga captcha_id, expiración y recurso de imagen local. Es una propuesta, no una ruta disponible ni un formato final de imagen aprobado.

La siguiente HU deberá acordar su cuerpo exacto, almacenamiento/consumo, vinculación al contexto y cuota IP, antes de implementar el generador. Debe crear desafíos independientemente de la existencia del nombre, sin revelar ese dato. No enviar respuesta esperada al navegador ni guardar el desafío o respuesta en logs. No aceptar un id inventado por el cliente.

Mientras no exista ese proveedor real, el login inicial puede funcionar antes de alcanzar el umbral, pero una cuenta que necesita CAPTCHA no podrá completar el siguiente login. Debe coordinarse el despliegue de ambas partes; no declarar terminada la integración extremo a extremo por aprobar tests con un doble de CAPTCHA.

## IP y auditoría

La IP proviene del peer ASGI; no se confía en cabeceras del cliente. Forwarded/X-Forwarded-For/X-Real-IP presentes hacen usar una cuota compartida de origen no verificable, sin aceptar la IP reenviada. Se recomienda Uvicorn --no-proxy-headers para el acceso directo. Una topología de proxy confiable requiere diseño explícito, fuera de esta integración provisional.

Ventana IP persistente: 30 solicitudes/900 segundos por defecto, configurable con LIMITE_INTENTOS_IP y VENTANA_INTENTOS_IP_SEGUNDOS. Auditoría e intentos guardan motivo técnico y datos mínimos, sin exponerlos en el error público. No se necesita ni se habilita un endpoint público de consulta de auditoría.

## Migración y comprobaciones

La revisión propuesta es p0003_control_intentos, sobre p0002_seguridad_sesiones. Ver [documentación técnica](HU_SEGURIDAD_INTENTOS_BLOQUEO.md) y [SQL de revisión](../backend/sql/HU_SEGURIDAD_P0003_PROPUESTA.sql). Aplicación en principal pendiente de autorización expresa; ninguna revisión histórica se modificó.

Pruebas backend: 171 offline aprobadas; 14 pruebas PostgreSQL reales en otra instancia/puerto, incluidos login HTTP con cookie/yo, concurrencia y expiración exacta. Los rechazos previstos persisten antes de devolver HTTP. No se generó ningún intento ni usuario en la principal. El clúster de pruebas quedó detenido.
