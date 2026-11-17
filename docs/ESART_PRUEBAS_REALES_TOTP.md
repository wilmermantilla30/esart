# Pruebas reales Angular → FastAPI → PostgreSQL

Fecha: 16 de noviembre de 2026. Destino: esart_db local; rol de aplicación: esart_aplicacion.

## Comprobación posterior a los GRANT

Se ejecutó el diagnóstico READ ONLY sobre PostgreSQL real después de la confirmación del propietario. Resultado:

- `permisos_faltantes_login: []`.
- `preparacion_login.disponible: true`.
- Cifrado habilitado, clave presente y Base64 válida de 32 bytes; sin revelar su contenido.
- Las columnas del modelo están presentes.
- `politicas_login.lectura_autorizada: true`, pero `filas: []`.

Los permisos mínimos solucionan TOTP_PERMISOS_FALTANTES. No se concedieron permisos sobre autorizaciones desde el agente ni se modificó estructura.

## Error adicional encontrado

Se intentó `python -m herramientas.probar_totp_desarrollo --ejecutar`. La comprobación real previa al recorrido devolvió `POLITICA_NO_DISPONIBLE`. No se creó la cuenta de prueba ni se llegó a arrancar Angular/Chrome en ese intento.

Faltan las filas LOGIN_TOTP y DESBLOQUEO_TOTP en seguridad.politicas_accion. El servicio necesita sus identificadores para crear los desafíos persistentes. No se sustituye la política por una fila académica ni se omite el segundo factor para evitar el error.

La propuesta revisable está en [ESART_TOTP_POLITICAS_MINIMAS.sql](ESART_TOTP_POLITICAS_MINIMAS.sql). Solo inserta esas dos filas si faltan, con vigencia de 120 segundos; no modifica estructura ni concede INSERT al backend. Se solicitó al propietario su ejecución en DBCode. Hasta recibir confirmación, no se considera resuelto el incidente ni se afirma que /auth/login haya completado el recorrido sin 503.

## Recorrido preparado

`python -m herramientas.probar_totp_desarrollo --ejecutar` comprueba el registro inicial, QR, código real, ausencia de cookie JWT y acceso HTTP denegado antes de los factores, sesión posterior y siguiente login con contraseña/TOTP. Utiliza Angular, FastAPI y PostgreSQL reales, sin respuestas HTTP simuladas.

Para comprobar también CAPTCHA y bloqueo desde la interfaz: `python -m herramientas.probar_totp_desarrollo --ejecutar --captcha-manual`. Se abre Chrome para que el usuario resuelva personalmente cada CAPTCHA. La herramienta rellena únicamente contraseñas incorrectas de la cuenta exclusiva de validación y observa respuestas reales: tres fallos, aparición del CAPTCHA, séptimo fallo 423, plazo de tres horas, VentanaBloqueo y persistencia tras recargar. No interpreta ni sortea los CAPTCHA, altera el reloj, consulta sus respuestas secretas ni cambia los umbrales.

El recorrido crea una cuenta exclusiva mfa.validacion.<aleatorio> con el rol USUARIO ya existente. Al finalizar la desactiva y revoca sus sesiones, factor, recuperación y desafíos pendientes. No toca cuentas existentes ni elimina auditoría. Guarda evidencia sin QR, secretos ni códigos TOTP. Las pruebas de interfaz automatizadas validan la URI real y calculan su TOTP con una implementación independiente; no equivalen a un escaneo con un teléfono físico.

## Estado de aceptación

### Comprobación tras la confirmación de inserción de políticas

El propietario informó que ejecutó ESART_TOTP_POLITICAS_MINIMAS.sql. Se abrió una conexión nueva desde la configuración efectiva de la API: 127.0.0.1:5432/esart_db, rol esart_aplicacion. La consulta directa de todas las políticas sigue devolviendo únicamente las siete de CURSOS/PERSONAL. relrowsecurity y relforcerowsecurity son false, por lo que no existe un filtro RLS que oculte las filas al backend.

Se repitió el inicio de la herramienta real: sigue deteniéndose con POLITICA_NO_DISPONIBLE antes de crear la cuenta de prueba. No se interpreta la confirmación verbal como evidencia de que las dos filas estén visibles para la API, ni se atribuye el fallo a permisos que ya pasan.

Se preparó [ESART_TOTP_COMPROBAR_DESTINO.sql](ESART_TOTP_COMPROBAR_DESTINO.sql), exclusivamente de lectura, para comparar base, puerto, servidor, inicio de instancia y las dos filas en DBCode. Está pendiente su resultado para distinguir conexión diferente de una transacción aún sin confirmar. No se ejecutaron INSERT adicionales, cambios de otras políticas, GRANT ni modificaciones de estructura.

| Requisito | Estado observado |
|---|---|
| Permisos TOTP | Verificados en la base real; sin faltantes. |
| Login sin 503 | Pendiente de las dos políticas y del recorrido HTTP completo. |
| Vinculación QR y TOTP de seis dígitos | Pendiente de ejecución real tras completar políticas. |
| Segundo factor obligatorio y ausencia de JWT prematuro | Comprobaciones preparadas; pendientes del recorrido real actual. |
| CAPTCHA y bloqueo al séptimo fallo | Pendiente de recorrido con CAPTCHA resuelto por el usuario. |

Evidencia de solo lectura: [ESART_TOTP_REVISION_PERMISOS_REAL.json](ESART_TOTP_REVISION_PERMISOS_REAL.json). Los resultados anteriores de laboratorio no se presentan como evidencia de la base principal. No se ejecutaron migraciones, DDL ni commits.
