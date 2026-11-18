# Bloqueo en la séptima contraseña incorrecta

16 de noviembre de 2026. Revisión solicitada en el adjunto d3ca326e.

## Diagnóstico y causa

La revisión del estado actual confirma que el bloqueo ya se evalúa en el mismo rechazo que incrementa el contador a siete: `seguridad_login.rechazar` actualiza `esart_ref.usuarios.intentos_fallidos_consecutivos`, asigna `bloqueado_hasta` con el reloj PostgreSQL más tres horas, escribe intento/auditoría y hace commit **antes** de lanzar HTTP 423. No espera un octavo intento. No se encontró en esta revisión un reinicio del contador por CAPTCHA incorrecto.

El impedimento identificado era la continuidad de los desafíos en Angular. Las correcciones previas abren el CAPTCHA al tercer fallo, conservan su campo de contraseña y solicitan un ID nuevo después de cada login rechazado. El backend consume cada desafío enviado, incluso si su solución es incorrecta. Reutilizar su ID en `X-ESART-Captcha-Anterior` devuelve 409. Esa cabecera está destinada a invalidar un desafío aún no consumido cuando se pulsa regenerar.

Quedaba un caso de recuperación: una regeneración manual cuyo desafío hubiera sido consumido por otro envío recibía 409 y exigía un segundo clic. Ahora `Captcha` realiza **un solo reintento** sin ID anterior. Si también falla, muestra el error y termina; no genera un bucle ni cambia contadores. Conserva `X-ESART-Usuario`, que vincula el desafío y no acredita identidad autenticada.

No es correcto sumar siete envíos indistintamente. Solo una contraseña comprobada como incorrecta incrementa el contador. CAPTCHA ausente, incorrecto, vencido o reutilizado impide ejecutar bcrypt y conserva los fallos acumulados.

## Flujo real y persistencia

1. `POST /api/auth/login` (también alias `/api/v1/auth/login`) delega al servicio de autenticación.
2. `seguridad_login.preparar` bloquea las filas de cuota IP y usuario con `FOR UPDATE`, consulta bloqueo y exige CAPTCHA si el contador es al menos tres. El estado no depende de variables Angular.
3. `CaptchaPostgres.verificar` comprueba contexto, ID, consumo, vencimiento y HMAC de la solución. Su consumo se confirma en la transacción del resultado del login.
4. Solo después se comprueba la contraseña. Si es incorrecta, se incrementa bajo el bloqueo de fila. En siete, se establece y confirma el plazo de tres horas y se devuelve 423.
5. `InicioSesion` cierra CAPTCHA y abre `VentanaBloqueo` ante 423. El reloj usa `bloqueado_hasta` y `ahora_servidor`. No inventa un bloqueo ni un contador.
6. La cuenta sigue bloqueada ante solicitudes directas y contraseña correcta. No se prorroga el plazo al repetir.
7. La recarga recupera el estado por `GET /api/auth/bloqueo` mediante comprobante HttpOnly con Max-Age hasta el vencimiento. Cerrar una pestaña no borra PostgreSQL. Si el navegador elimina sus cookies al cerrarse, no puede reconstruirse públicamente el contexto por nombre; el siguiente login sigue devolviendo 423 desde PostgreSQL. No se sacrifica esa protección para enumerar cuentas.
8. Al vencer se aplican las reglas existentes de recuperación bajo bloqueo de fila. El desbloqueo anticipado TOTP conserva sus condiciones de factor previamente activo y validación en backend.

401 de credenciales comprobadas persiste el fallo. 401 `CAPTCHA_INVALIDO` conserva contador. 409 de regeneración inicia un único desafío nuevo sin ID consumido. 422 de solicitud inválida no cuenta una contraseña no comprobada. Se mantienen mensajes y tratamiento de errores existentes; no se cambia el contrato para exponer históricos de otras cuentas.

## Archivos modificados en esta revisión

- Angular: `frontend/esart/src/app/paginas/inicio-sesion/captcha/captcha.ts` (recuperación acotada de 409) y `captcha.spec.ts` (cabecera correcta, modal conservado y ausencia de bucle).
- FastAPI: **ningún archivo de producción modificado en esta revisión**. Se comprobó el servicio persistente existente y se ejecutaron sus regresiones reales.
- Documentación: este informe.

No se modifica `captcha.html`, `captcha.css`, el formulario, botones, mensajes actuales ni la imagen. No se modifica TOTP/QR, usuarios, roles, permisos, esquema ni migraciones. No se ejecutan commits ni push. El árbol de trabajo contiene cambios anteriores; este inventario distingue los de esta revisión.

## Validación

Prueba Angular nueva: provocar 409 en regeneración con ID anterior, comprobar el reintento sin `X-ESART-Captcha-Anterior`, mantener `X-ESART-Usuario` y comprobar que otro 409 termina sin más solicitudes.

El ejecutor PostgreSQL crea otro clúster marcado y cuentas `hu06.*`, valida el destino y utiliza un puerto distinto del operativo. La prueba Chrome opera sobre el DOM, proxy y endpoints reales. Las lecturas SQL READ ONLY entre pasos verifican la secuencia del contador; no utiliza valores simulados para afirmar que el bloqueo funciona.

La suite comprueba CAPTCHA incorrecto/vencido sin incremento ni ejecución de bcrypt, los siete fallos comprobados, plazo de tres horas, 423 inmediato, contraseña correcta durante bloqueo, concurrencia, otro proceso FastAPI, expiración con reloj controlado, recarga del navegador, auditoría, QR y desbloqueo TOTP. No se afirma haber esperado tres horas reales en Chrome: el vencimiento se verifica controlando el reloj en aislamiento.

Resultados Angular: 63 pruebas aprobadas en 10 archivos. Compilación de producción aprobada; existen avisos de tamaño CSS TOTP y CommonJS qrcode, fuera del alcance de esta corrección y sin modificar esos archivos.

PostgreSQL aislado: **45 pruebas aprobadas** en 125,60 segundos. Ruff sin errores. Clúster detenido al finalizar. No se ha modificado ninguna cuenta real.

Evidencia final: `backend/respaldos/hu06_915b6a8ab8b14e9a86a4aead67c34c38/`.

| Paso del navegador real | Contador SQL | HTTP |
|---|---:|---:|
| Contraseña incorrecta 1 | 1 | 401 |
| Contraseña incorrecta 2 | 2 | 401 |
| Contraseña incorrecta 3; CAPTCHA automático | 3 | 401 |
| CAPTCHA incorrecto; contraseña no comprobada | 3 | 401 |
| CAPTCHA válido + contraseña incorrecta 4 | 4 | 401 |
| CAPTCHA válido + contraseña incorrecta 5 | 5 | 401 |
| CAPTCHA válido + contraseña incorrecta 6 | 6 | 401 |
| CAPTCHA válido + contraseña incorrecta 7 | 7 | **423** |

Son siete contraseñas comprobadas incorrectas más un envío CAPTCHA rechazado; no se exige una octava contraseña incorrecta. `navegador_publico/resultado.json` contiene las lecturas reales `[1,2,3,3,4,5,6,7]`, el plazo de 10.800 segundos y la misma fecha de bloqueo recuperada al recargar. `bloqueo.png` y `recarga.png` muestran la ventana institucional; `captcha_reintento.png` conserva el CAPTCHA visible y disponible tras el rechazo.

`navegador_totp/resultado.json` confirma QR local y login de dos factores; `navegador_desbloqueo/resultado.json` confirma desbloqueo TOTP sin JWT. No hubo interceptación de respuestas HTTP ni inyección de estado privado Angular. El esquema operativo y los datos de cuentas reales permanecen sin modificaciones.
