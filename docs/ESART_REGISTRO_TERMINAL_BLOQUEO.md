> Actualizacion: la consulta administrativa ahora devuelve la IP registrada del ultimo intento, con advertencia de loopback. El login publico sigue restringido. Consulte [validacion real autorizada](ESART_TERMINAL_VALIDACION_REAL_AUTORIZADA.md). Las referencias a IP null administrativa siguientes describen el estado anterior.

# Registro de la terminal: datos de bloqueo y privacidad

## Causa de la inconsistencia

La ventana tenía `intentosFallidos = input<number>(0)` y el padre convertía en cero la ausencia de `detalle.intentos_fallidos`. Sin embargo, el login público no devuelve ese dato, deliberadamente, para no divulgar información de cuentas. Ese cero no procedía de PostgreSQL. Además, padre e hijo mantenían intervalos independientes: uno partía de segundos restantes y el otro de la fecha y reloj local.

La corrección mantiene el diseño institucional, elimina el cero inventado y utiliza un solo reloj de presentación derivado de `bloqueado_hasta` y `ahora_servidor`. No se altera el contador de seguridad en Angular.

## Contratos y autorización

### Login público y ventana

El 423 conserva `CUENTA_BLOQUEADA`, fecha y segundos restantes y añade `ahora_servidor`, calculada con el reloj PostgreSQL del intento. La fecha procede del campo `bloqueado_hasta`. Los nombres existentes e inexistentes conservan las mismas respuestas externas y política de bloqueo; no se comunica si existe una cuenta.

En la ventana pública:

- Usuario se etiqueta como **Usuario ingresado**: es la entrada del intento, no una cédula o identidad comprobada.
- Intentos: **No disponible (vista administrativa)**, nunca cero como sustituto de un dato ausente.
- IP: **No disponible**. No se habilitó exposición de direcciones IP.
- Fecha y cuenta regresiva comparten el mismo plazo del servidor. El hijo solo recibe los segundos calculados por el padre y no ejecuta un intervalo propio.

### Consulta administrativa del contador real

`GET /api/auth/administracion/bloqueos/{usuario_id}` exige sesión validada por el mecanismo existente y rol activo `ADMINISTRADOR`. Esta es la política explícita de la nueva consulta de seguridad; no se cambiaron asignaciones ni permisos PostgreSQL. Sin sesión responde 401; con rol USUARIO, 403, antes de consultar el usuario objetivo.

Lee únicamente ID, `intentos_fallidos_consecutivos` y `bloqueado_hasta`, sin seleccionar contraseñas. Devuelve esos datos, estado temporal y hora del servidor. IP permanece null porque no hay autorización específica para exponerla. No hay operaciones de desbloqueo ni escritura en esa ruta.

No se añadió una pantalla completa de administración. El componente admite datos administrativos explícitos para su reutilización bajo esa autorización; la ventana del login nunca habilita ese modo ni consulta el endpoint administrativo. Una bandera de presentación Angular no concede acceso al backend.

### Recuperación al recargar

Al devolver un 423, FastAPI entrega `esart_contexto_bloqueo`: cookie HttpOnly, SameSite Strict, Secure según la configuración existente, ruta /api/auth y expiración limitada al bloqueo. Lleva el nombre normalizado que el propio cliente intentó, con firma HS256 mediante clave derivada y audiencia específica. No contiene ID de cuenta, contador, contraseña ni IP y no constituye una sesión de autenticación. La clave derivada y los reclamos son distintos del JWT de sesión.

`GET /api/auth/bloqueo` usa solo ese comprobante para recuperar el contexto previo y volver a leer el estado en PostgreSQL. No acepta un selector público de cuenta por nombre, cabecera o parámetro. Sin comprobante válido devuelve `{ "bloqueado": false }`, sin consultar una cuenta; esa respuesta no significa que las cuentas estén desbloqueadas. Con comprobante, devuelve bloqueo, fecha y hora actuales, reitera el nombre ingresado y mantiene contador/IP como null. No incrementa intentos ni realiza escrituras para desbloquear.

Angular realiza esa lectura al crear la página y reconstruye la ventana y el reloj. No usa localStorage/sessionStorage para conservar contadores o plazos. Al terminar el plazo, el padre cierra la ventana, elimina la restricción visual y permite otro envío. El login vuelve a consultar PostgreSQL y sigue siendo la autoridad final.

Si se eliminan cookies o se usa otro navegador no se recupera el contexto anterior: por privacidad no se ofrece una búsqueda pública. El bloqueo de PostgreSQL sigue vigente y el siguiente intento de autenticación se somete a él. Si la lectura falla por red, no se inventa una fecha o contador; el login sigue verificando el estado en servidor.

## Datos y pruebas

No se modificaron migraciones ni estructuras, ni usuarios, contraseñas o bloqueos de la base operativa. La preparación y escrituras de prueba se hicieron exclusivamente en otra instancia PostgreSQL con directorio marcado, puerto independiente y cuentas generadas de prueba. Las migraciones existentes solo preparan esa instancia aislada; no se ejecutan sobre la principal.

La prueba PostgreSQL verificó siete fallos, cookie de contexto, consulta desde otro cliente que simula recarga, mismo `bloqueado_hasta` y contador siete sin incrementos por leer. Verificó también contador null e IP null públicamente, 401 sin sesión, 403 con rol de usuario y contador real siete en la consulta administrativa. Las comprobaciones de autorización administrativa usan sustituciones de identidad limitadas al test; las pruebas existentes de login/sesión verifican el mecanismo de identidad real por separado.

Se mantienen las pruebas de CAPTCHA incorrecto y vencido, séptimo fallo, consumo único, concurrencia, desbloqueo con reloj simulado y éxito que reinicia el contador. Las pruebas Angular cubren recuperación al crear la página, ausencia del cero ficticio, ocultación de detalles y reloj único. También se comprueban firma alterada, vencimiento y rechazo del comprobante como token de sesión.

Resultados finales: backend offline **182 aprobadas y 40 omitidas** (integraciones deshabilitadas en ese comando); PostgreSQL aislado **27 aprobadas**, además de compatibilidad HTTP con p0003; Angular **49 aprobadas** en nueve archivos. Ruff sin errores. Evidencia: `backend/respaldos/hu06_666ceaa0b38f4dc193f1f49795bfa2eb/resultado.json`; clúster detenido. Build Angular de producción verificado al cierre.

## Archivos corregidos

- Backend: `aplicacion/rutas/autenticacion.py`, `servicios/seguridad_login.py`, nuevos `servicios/estado_bloqueo.py` y `seguridad/comprobante_bloqueo.py`.
- Frontend: `nucleo/servicios/sesion.service.ts`, `paginas/inicio-sesion/inicio-sesion.ts`, `inicio-sesion.html`, `ventana-bloqueo/ventana-bloqueo.ts` y `ventana-bloqueo.html`. CSS institucional conservado.
- Pruebas: `backend/pruebas/test_comprobante_bloqueo.py`, `test_captcha_local_pg.py`, `inicio-sesion.spec.ts` y `ventana-bloqueo.spec.ts`.
- Este informe. No se aplicaron GRANT adicionales ni migraciones nuevas.
