# CAPTCHA: diagnóstico del 422 y verificación del contrato

> Actualización: el fallo posterior con cabecera presente era 503 por estructura p0004 ausente. Tras el COMMIT administrativo, Chrome mostró el PNG real y se verificaron regeneración y consumo. Véase [evidencia actualizada](ESART_CAPTCHA_EJECUCION_P0004.md).

## Causa comprobable

`header.X-ESART-Usuario: Field required` significa que FastAPI recibió una solicitud sin esa cabecera. La validación ocurre antes de generar el desafío; no es un fallo de Pillow, JWT o contraseña.

En el árbol de trabajo revisado, `SesionService.obtenerCaptcha` **ya enviaba la cabecera**. `ClienteApiService` la conserva al llamar a HttpClient y el modal recibe el nombre desde el formulario. No se encontró otra llamada al endpoint en el código Angular. No se puede atribuir el error observado a un archivo concreto sin inspeccionar la petición del navegador que lo produjo. Abrir la URL directamente en la barra del navegador omite esta cabecera y produce legítimamente 422. También debe descartarse un frontend servido con un build anterior.

Se mantiene la cabecera obligatoria. Se documentó explícitamente su función en OpenAPI y se añadió validación preventiva en el servicio Angular: usuario vacío, corto, demasiado largo o con controles produce un mensaje comprensible y no una petición incompleta. No se introdujo ningún valor predeterminado ni usuario ficticio.

## Seguridad y flujo

- GET `/api/auth/captcha` es público, sin dependencia de sesión autenticada ni JWT. La cabecera expresa el usuario del intento; **no prueba identidad**, no concede roles y no comprueba si existe la cuenta.
- El desafío se liga al nombre normalizado mediante HMAC. El login exige credenciales reales y compara el contexto. Cambiar de nombre no permite reutilizar una imagen para otra cuenta.
- La cuota de generación usa exclusivamente la IP canónica con un dominio HMAC propio; cambiar el usuario no reinicia esa cuota. El límite IP de login también precede al estado por usuario. No se confía silenciosamente en cabeceras de proxy.
- El modal presenta el PNG del servidor con seis caracteres, conserva ID y respuesta introducida y los envía al login. No conoce la solución ni decide si fue correcta. Se conservan los estilos institucionales.
- Regenerar remite `X-ESART-Captcha-Anterior` y el servidor invalida el anterior. La vigencia es de cinco minutos y el consumo es de un solo uso bajo bloqueo PostgreSQL. Se conservan los umbrales de intentos y bloqueo de tres horas.

## Comprobación en el navegador

1. Servir el frontend actualizado (reiniciar `npm.cmd start` en desarrollo o desplegar `dist/esart` según el procedimiento habitual) y recargar el navegador sin caché.
2. En Network, revisar la petición originada por el modal, no abrir directamente su URL. Debe ser GET `/api/auth/captcha`, con `X-ESART-Usuario` igual al nombre del formulario, sin espacios exteriores. No requiere `Authorization`.
3. Confirmar respuesta 200 con `captcha_id`, `imagen_png_base64`, `expira_en`, `longitud: 6` y `Cache-Control: no-store`. La imagen usa un origen `data:image/png;base64,...`.
4. Al regenerar debe enviarse también el ID anterior. En el POST de login deben viajar `captcha_id` y `captcha_respuesta` junto a las credenciales; no registrar esos cuerpos.
5. Si la cabecera aparece en el navegador pero FastAPI informa que falta, revisar el destino y las reglas del proxy intermedio. El proxy de desarrollo del repositorio dirige `/api` a `127.0.0.1:8081` y no declara eliminación de cabeceras.

No se ejecutaron estos pasos contra PostgreSQL operativo: emitir y validar un CAPTCHA escribe desafíos, límites y auditoría, y requiere autorización según la restricción de este encargo. Si falta p0004, corregir la cabecera puede revelar posteriormente un 503 de estructura; no se aplicó ninguna migración para ocultarlo.

## Pruebas de esta revisión

- Backend: **173 aprobadas, 36 omitidas**; sin habilitar conexiones de integración. Ruff sin errores.
- Contrato HTTP FastAPI: sin cabecera devuelve 422; con cabecera devuelve 200 sin JWT y transporta un PNG generado realmente por Pillow. La persistencia se sustituye en esta prueba, por lo que no acredita el estado del PostgreSQL operativo.
- Angular: **43 aprobadas en ocho archivos** y build de producción aprobado. Incluye cabeceras de usuario/regeneración, ausencia de Authorization, bloqueo de solicitud con usuario vacío, renderizado de PNG y envío desde modal al login.
- La prueba PostgreSQL existente del límite de generación se amplió para intentar evadirlo cambiando de nombre con la misma IP. **No se ejecutó en esta revisión**, para respetar la prohibición de escrituras sin autorización. Las pruebas de integración de expiración, consumo, concurrencia y bloqueo siguen preparadas en `test_captcha_local_pg.py`; véase la evidencia aislada de la entrega anterior en `HU_CAPTCHA_LOCAL.md`, sin confundirla con una nueva verificación operativa.

Archivos de esta revisión: `backend/aplicacion/rutas/autenticacion.py`, `backend/pruebas/test_captcha_contrato.py`, `backend/pruebas/test_captcha_local_pg.py`, `frontend/esart/src/app/nucleo/servicios/sesion.service.ts`, su prueba `sesion.service.spec.ts` y este informe. No se modificaron migraciones, registros PostgreSQL ni el diseño del modal.
