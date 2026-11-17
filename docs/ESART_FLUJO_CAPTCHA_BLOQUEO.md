# Corrección del flujo visible CAPTCHA → bloqueo

Fecha: 16 de noviembre de 2026.

## Causa raíz

El backend diferencia correctamente una contraseña comprobada incorrecta de un CAPTCHA rechazado. El contador detenido en tres no autoriza a omitir CAPTCHA: hay que permitir resolverlo desde la interfaz. La regresión de experiencia estaba en `InicioSesion`: ocultaba el modal ante todo error HTTP y al recibir `captcha_requerido=true` solo activaba un aviso. El usuario debía volver a pulsar el login para abrirlo. Además, el padre limpiaba la contraseña y el modal no ofrecía un campo para reintroducirla, por lo que mantener abierto el desafío sin corregir ese dato también impedía avanzar.

La validación real en Chrome detectó otro contrato que una respuesta HTTP simulada no reproducía: el backend rechaza con 409 `X-ESART-Captcha-Anterior` cuando identifica un desafío ya consumido. Todos los envíos de login consumen el CAPTCHA correspondiente, incluso cuando la respuesta es incorrecta. Por eso **después de un envío se solicita un desafío nuevo sin esa cabecera**. El botón manual de regeneración sí envía el ID anterior aún no consumido, para invalidarlo. No se cambió esa regla del backend.

## Contratos revisados

- POST `/api/auth/login`: recibe `nombre_usuario`, `contrasena`, `captcha_id` y `captcha_respuesta`. El servicio mapea `{id,respuesta}` del componente a los dos campos CAPTCHA reales.
- GET `/api/auth/captcha`: recibe `X-ESART-Usuario` en todas las solicitudes; solo añade `X-ESART-Captcha-Anterior` para reemplazar un desafío no enviado. Devuelve `captcha_id`, `imagen_png_base64`, `longitud=6` y `expira_en`.
- La imagen se muestra mediante `data:image/png;base64,` más el contenido recibido; no se genera ni resuelve en Angular.
- 401 `CAPTCHA_INVALIDO`: no se comprobó la contraseña; mantener modal y solicitar otro código. También se renueva tras un CAPTCHA válido con credenciales incorrectas, porque su ID ya fue consumido.
- 423 `CUENTA_BLOQUEADA`: cerrar CAPTCHA, abrir automáticamente `VentanaBloqueo`, deshabilitar login y usar `bloqueado_hasta`, `ahora_servidor` y `segundos_restantes` del backend.
- GET `/api/auth/bloqueo`: recupera el bloqueo mediante el comprobante HttpOnly del flujo tras recargar. No consulta datos de otras cuentas a partir de un nombre arbitrario.

## Corrección aplicada

`InicioSesion` abre automáticamente el CAPTCHA al recibir la exigencia del servidor y lo mantiene durante los reintentos. Se añade una revisión del desafío para solicitar uno nuevo después de cada envío rechazado. El modal dispone de contraseña de reintento vinculada al mismo control del formulario padre: no hay otra copia persistente ni almacenamiento web. Se limpia después de cada rechazo, cancelación o éxito como antes. No se envían credenciales sin CAPTCHA cuando ya es obligatorio.

El componente `Captcha` mantiene las señales de carga y error, regenera desafíos consumidos sin cabecera anterior, valida la fecha recibida y solicita otro al vencer. No envía un código que ya considera expirado; PostgreSQL sigue siendo la autoridad definitiva sobre expiración y consumo único. Los mensajes del servidor permanecen visibles dentro del modal. Se conserva el diseño institucional, la certificación y el botón de regeneración. Cancelar es una acción explícita del usuario y no elimina la exigencia del backend: el siguiente intento vuelve a abrir el desafío.

No se modifican registro de usuarios, roles, permisos, esquema, QR, TOTP ni duración del bloqueo. El desbloqueo temprano continúa sujeto a un factor previamente ACTIVO y a su validación en el backend. El navegador no puede autorizar ese desbloqueo por su cuenta.

## Comprobación del entorno local

Sin enviar contraseñas ni generar intentos de cuentas reales:

- `http://127.0.0.1:8081/api/salud`: HTTP 200.
- `http://localhost:4200/api/salud` a través del proxy: HTTP 200 JSON.
- `http://localhost:4200/inicio-sesion`: HTTP 200 HTML.
- Se inspeccionó el módulo JavaScript servido por el Angular local y se confirmó que contiene `revisionCaptcha` y el nuevo campo `captcha-contrasena`. No se infirió el estado del navegador únicamente desde los archivos del disco.

El recorrido que provoca fallos y bloquea se ejecuta exclusivamente con cuentas `hu06.*` en otro clúster PostgreSQL marcado, puerto aleatorio distinto del operativo. No se utilizaron las credenciales de `prueba.seguridad`, no se cambió su contador ni se bloquearon cuentas reales. Si una pestaña conserva código anterior, debe recargarse antes de comprobar la interfaz corregida.

## Archivos de esta corrección

- `frontend/esart/src/app/paginas/inicio-sesion/inicio-sesion.ts` y `.html`.
- `frontend/esart/src/app/paginas/inicio-sesion/captcha/captcha.ts` y `.html`.
- Pruebas `inicio-sesion.spec.ts` y `captcha.spec.ts`.
- Automatización real `backend/herramientas/navegador_publico.mjs` y `navegador_totp.mjs`.
- Comprobación PostgreSQL `backend/pruebas/test_captcha_local_pg.py`.
- `paginas/totp/totp.spec.ts`: únicamente selectores/textos de prueba adaptados a las etiquetas visuales actuales. No se modifica el componente QR ni su autenticación; se conservan las ediciones visuales concurrentes.

Los servicios HTTP, modelos y `VentanaBloqueo` se revisaron y se reutilizan: no se inventaron campos ni se reimplementó el bloqueo en memoria.

## Evidencia y pruebas

La prueba pública nueva opera sobre DOM visible: contraseñas incorrectas 1–3, aparición automática del desafío, un CAPTCHA incorrecto, regeneración sin cerrar, contraseña dentro del modal y CAPTCHA válido hasta el séptimo fallo, HTTP 423, modal de bloqueo y recarga. No hace clic detrás del modal ni intercepta respuestas HTTP. Las lecturas SQL independientes del laboratorio comprueban el contador después de cada paso, incluido que permanezca en tres después del CAPTCHA incorrecto. La instrumentación de prueba observa códigos CAPTCHA reales generados para la cuenta aislada; no se añade un solucionador ni un endpoint de prueba al producto.

Las pruebas existentes cubren expiración del bloqueo con reloj controlado, imposibilidad de saltar CAPTCHA por API, concurrencia, persistencia entre procesos y desbloqueo TOTP activo. La expiración de tres horas se verifica con tiempo controlado en aislamiento; no se afirma haber esperado tres horas reales en Chrome.

Resultados finales:

- **45 pruebas PostgreSQL aisladas aprobadas**; clúster detenido al terminar.
- **62 pruebas Angular aprobadas en 10 archivos**.
- **196 pruebas generales backend aprobadas**, 60 omitidas por requerir entornos explícitos. Las de seguridad PostgreSQL se ejecutaron mediante el laboratorio, no contra la base operativa.
- Ruff sin errores; compilación Angular aprobada, con el aviso CommonJS de qrcode ya existente.

Evidencia final en `backend/respaldos/hu06_bfd5c896b6a849bc9fcf6e8199abcfef/`:

- `navegador_publico/resultado.json`: contadores leídos realmente en PostgreSQL **[1,2,3,3,4,5,6,7]**; el cuarto valor corresponde al CAPTCHA incorrecto. Respuestas login **[401,401,401,401,401,401,401,423]**: hay ocho envíos porque uno no verifica contraseña. Cinco desafíos generados, apertura automática y regeneración confirmadas. Plazo de bloqueo 10.800 segundos.
- `navegador_publico/captcha_reintento.png`: PNG real de seis caracteres, mensaje de rechazo, contraseña de reintento dentro del modal y controles disponibles para continuar.
- `navegador_publico/bloqueo.png` y `recarga.png`: modal de bloqueo antes y después de recargar. El comprobante conserva la misma fecha de desbloqueo; la recarga no añade intentos.
- `navegador_totp/resultado.json`: vinculación QR local, confirmación real y login en dos factores aprobados.
- `navegador_desbloqueo/resultado.json`: desbloqueo mediante factor previamente activo, sin emitir JWT y con login nuevamente habilitado.

La lectura SQL intermedia utiliza exclusivamente la cuenta de aplicación del clúster aislado, transacción READ ONLY y destino validado por el laboratorio. Las credenciales administrativas se excluyen del entorno de los procesos de navegador.

No se alteraron datos de `prueba.seguridad` ni de otras cuentas operativas. El flujo destructivo se demostró en aislamiento; en el entorno operativo se verificaron disponibilidad del backend/proxy y el código Angular efectivamente servido, sin provocar bloqueos reales.
