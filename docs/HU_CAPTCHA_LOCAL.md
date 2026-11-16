> Contrato actualizado: [correccion de bloqueo y CAPTCHA](HU_SEGURIDAD_BLOQUEO_CAPTCHA_CORRECCION.md). Sustituye la politica anterior de no contar ningun fallo CAPTCHA y el rechazo 401 durante bloqueo. Los resultados historicos siguientes conservan su contexto original.

# ESART ? CAPTCHA local para intranet

> Actualización posterior: p0004 fue confirmada por el operador y se verificaron estructura, permisos, generación, regeneración y consumo en esart_db, además del PNG real en Chrome. Véase [resultado de ejecución](ESART_CAPTCHA_EJECUCION_P0004.md). Las referencias a migración pendiente describen el estado de preparación original.

## Estado y alcance

Implementaci?n preparada para FastAPI y el modal Angular existente. No se ejecutaron migraciones ni escrituras sobre la base operativa durante este trabajo. La inspecci?n de solo lectura confirm? en `esart_db` las tablas de p0003 (intentos, l?mites IP, estados an?nimos y auditor?a), y la ausencia de `esart.desafios_captcha`. p0004 queda pendiente de autorizaci?n. No se modificaron las revisiones anteriores ni la configuraci?n de credenciales/JWT.

Las pruebas PostgreSQL usan un cl?ster nuevo con directorio marcado, puerto aleatorio distinto de 5432 y contrase?a ef?mera. Aunque su base se llama esart_db para probar las mismas restricciones, no es la instancia operativa. El ejecutor comprueba `data_directory`, conserva evidencia local y detiene el cl?ster al finalizar. No usa las bases hist?ricas de pruebas como fuente operativa.

## Dise?o y persistencia

`secrets` genera seis caracteres del alfabeto `ACDEFGHJKMNPQRTUVWXY34679` y un identificador opaco de 256 bits (`token_urlsafe(32)`, 43 caracteres). PNG RGB de 312?96, con ruido leve, l?neas y rotaci?n individual. Tiempo m?ximo de espera de renderizado: dos segundos; tama?o m?ximo: 64 KiB. La generaci?n se ejecuta fuera del bucle as?ncrono; un timeout revierte la solicitud y no publica un desaf?o incompleto.

Pillow 13.0.0 utiliza Aileron Regular incorporada en `ImageFont.load_default(size=43)`: no descarga fuentes ni copia fuentes del sistema. La fuente forma parte del paquete instalado, no se distribuye aqu? un archivo de fuente separado. Documentaci?n y licencia oficial de la dependencia: [ImageFont](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html), [licencia de Pillow 13.0.0](https://github.com/python-pillow/Pillow/blob/13.0.0/LICENSE). Conservar avisos y licencias del wheel en la distribuci?n institucional.

Nueva tabla `esart.desafios_captcha`:

| Campo | Uso |
| --- | --- |
| id VARCHAR(43), PK | Identificador aleatorio |
| contexto VARCHAR(64) | HMAC del usuario normalizado; no depende de que exista |
| respuesta_hmac VARCHAR(64) | HMAC-SHA256 ligado a ID, contexto y respuesta normalizada |
| creado_en, expira_en TIMESTAMPTZ | Reloj PostgreSQL; vigencia exacta de cinco minutos |
| consumido_en TIMESTAMPTZ nullable | Consumo irreversible desde la aplicaci?n |

CHECK de plazo y orden de consumo; ?ndice de expiraci?n. El HMAC deriva una clave con dominio propio de la clave secreta JWT existente. No se cambia esa clave. Todos los trabajadores deben compartir la misma configuraci?n; rotarla invalida desaf?os pendientes. No se guardan texto de respuesta ni PNG en PostgreSQL.

Se ampl?a `esart.auditoria_acceso`: `intento_id` admite NULL, se a?aden `captcha_id` (FK) y `origen_hmac`. CHECK exige al menos una referencia. Se conservan los registros existentes. Eventos: emisi?n, regeneraci?n, rechazo de regeneraci?n, validaci?n, rechazo, vencimiento, reutilizaci?n y l?mite IP. La auditor?a previa del login permanece activa.

Permisos nuevos de aplicaci?n: SELECT e INSERT sobre desaf?os y ?nicamente UPDATE de `consumido_en`. No se conceden DELETE, administraci?n ni actualizaci?n de respuesta/expiraci?n. La auditor?a mantiene sus permisos previos de lectura/inserci?n.

La consulta `FOR UPDATE`, la comparaci?n `hmac.compare_digest` y el consumo participan en la misma transacci?n del login. Respuesta incorrecta o vencida consume el desaf?o. El contexto incorrecto no permite consumir el desaf?o de otra cuenta. Solicitudes simult?neas, incluso de procesos distintos, tienen un ?nico ganador. La regeneraci?n bloquea e invalida el ID anterior antes de publicar el siguiente.

Los desaf?os expirados se rechazan l?gicamente; no se eliminan autom?ticamente, para conservar referencias de auditor?a. La retenci?n/archivo requiere una pol?tica posterior, no implementada como borrado silencioso.

## Contrato API

### GET /api/auth/captcha

P?blico y limitado por IP. Cabecera obligatoria `X-ESART-Usuario` (3?80 caracteres); para regenerar: `X-ESART-Captcha-Anterior`. Se usan cabeceras para no colocar el usuario en la URL. No registrar estos valores ni cuerpos sensibles en proxies o trazas.

Respuesta 200:

```json
{"captcha_id":"<43 caracteres>","imagen_png_base64":"<PNG base64>","expira_en":"<UTC>","longitud":6}
```

Nunca incluye soluci?n. Cabeceras `Cache-Control: no-store` y `Pragma: no-cache` en rutas de autenticaci?n, tambi?n en errores controlados. 422: entrada incorrecta; 409: anterior inexistente, usado o de otro contexto (solicitar uno nuevo sin ID anterior); 429: l?mite IP; 503 `CAPTCHA_NO_DISPONIBLE`: falta estructura requerida. La regeneraci?n conserva el contrato de un solo uso.

L?mite predeterminado: 20 generaciones/300 segundos por IP. Configuraci?n `limite_generacion_captcha_ip` y `ventana_generacion_captcha_segundos`. Se reutiliza `limites_inicio_ip` con un dominio HMAC separado del login. No se conf?a en X-Forwarded-For, Forwarded o X-Real-IP: esas solicitudes usan un bucket compartido de origen no verificable. En un proxy con una IP de salida com?n, ajustar los l?mites al tr?fico esperado; no confiar en cabeceras sin definir antes proxies de confianza.

### POST /api/auth/login

Se conservan usuario, contrase?a, JWT y cookie existentes. Desde el cuarto intento de credenciales fallidas, enviar adem?s:

```json
{"nombre_usuario":"<usuario>","contrasena":"<entrada privada>","captcha_id":"<id>","captcha_respuesta":"<entrada del usuario>"}
```

No existe endpoint p?blico que declare el CAPTCHA resuelto ni token booleano emitido por Angular. Los fallos 1?3 no requieren CAPTCHA; desde el cuarto lo exige el backend. CAPTCHA inv?lido, ausente, reutilizado o vencido: rechazo sin ejecutar bcrypt, consumo del presupuesto IP y auditor?a, sin incrementar el contador de credenciales. As? no permite probar contrase?as ni bloquear f?cilmente una cuenta solo enviando im?genes incorrectas. El s?ptimo fallo de credenciales bloquea tres horas; los intentos durante el bloqueo no prolongan el plazo; al vencer se reinicia el estado y el ?xito tambi?n reinicia el contador. Las pruebas previas de desbloqueo, usuarios inexistentes y bloqueo siguen vigentes.

Mientras p0004 no se autorice, el login que todav?a no requiere CAPTCHA conserva compatibilidad con p0003: inserta expl?citamente solo las columnas de auditor?a anteriores. Si se necesita el desaf?o, falla cerrado con 503; nunca omite el control para evitar el error.

## Angular y accesibilidad

Se conservan encabezado, imagen institucional, estilos, casilla, regeneraci?n, cancelar y validar. El modal solicita PNG e ID, recoge la entrada y entrega ID/respuesta al padre; este realiza el login real. No hay c?digo fijo, generador aleatorio local, comparaci?n con soluci?n, contador de fallos ni almacenamiento local de respuestas. Cancelar no borra la obligaci?n del backend. Tras un rechazo se vac?a la contrase?a y se pide otro desaf?o en el siguiente env?o.

Se a?adieron foco inicial/restauraci?n, Escape, navegaci?n de teclado y contenci?n del foco del di?logo, etiquetas y estado de carga. El texto alternativo no revela el c?digo. **El CAPTCHA visual todav?a no ofrece una alternativa accesible equivalente**. Se consider? audio generado localmente con grabaciones autorizadas de los mismos caracteres, servido y validado con el mismo ID, TTL y consumo at?mico. Su publicaci?n requiere recursos de audio licenciados y revisi?n de accesibilidad; no se sustituy? por texto visible, pregunta trivial o bypass. Regenerar no resuelve esa limitaci?n. El modal informa c?mo solicitar asistencia institucional.

## Despliegue pendiente de autorizaci?n

1. Revisar `p0004_captcha_local.py` y `backend/sql/HU_CAPTCHA_P0004_PROPUESTA.sql` (este SQL es solo de revisi?n, no ejecuci?n manual).
2. Confirmar respaldo restaurable, conexi?n administrativa separada y destino `current_database() = esart_db`, revisi?n p0003 y objetos reales compatibles. Detenerse si difieren.
3. Con autorizaci?n, ejecutar desde backend y `.venv` la migraci?n `python -m alembic upgrade p0004_captcha_local`, usando la configuraci?n de migraciones protegida existente. No usar stamp ni modificar revisiones anteriores. El downgrade se detiene para impedir borrado de desaf?os/auditor?a.
4. FastAPI sigue con esart_aplicacion, nunca con el operador. Confirmar permisos espec?ficos, revisi?n, tablas y checks. No hace falta seed CAPTCHA.
5. Reiniciar backend con la dependencia instalada y desplegar el build Angular; verificar mediante una cuenta de prueba autorizada los flujos y logs sin soluciones, contrase?as, hashes o tokens. No provocar fallos de login sobre el administrador real sin coordinaci?n.

Instalaci?n sin Internet en destino: en equipo de preparaci?n compatible obtener los wheels mediante `python -m pip download --only-binary=:all: -r requirements.txt --dest <directorio-wheels>`. Transferir con sus licencias y validar hashes seg?n el procedimiento institucional. En destino: `python -m pip install --no-index --find-links=<directorio-wheels> -r requirements.txt`. No incorporar credenciales, wheels o respaldos al repositorio. El servicio no usa APIs, CDN ni fuentes externas para generar/verificar el CAPTCHA.

## Verificaci?n y archivos

Pruebas offline: imagen con sockets deshabilitados, aleatoriedad, alfabeto, HMAC ligado a contexto/ID y l?mites de entrada. Pruebas PostgreSQL reales: TTL exacto, respuesta err?nea, replay, regeneraci?n y carrera, generaci?n limitada/auditada, dos procesos y login HTTP con bcrypt/JWT reales. El ejecutor prueba primero el login en p0003 y luego aplica p0004 ?nicamente al cl?ster aislado. Los dobles de proveedor de las pruebas hist?ricas no se usan en producci?n; los casos nuevos del login usan el proveedor PostgreSQL real.

Archivos principales de esta entrega:

- `backend/aplicacion/seguridad/{captcha,imagen_captcha}.py`
- `backend/aplicacion/servicios/{captcha_local,seguridad_login}.py`
- `backend/aplicacion/{configuracion,principal}.py`, `modelos/seguridad.py`, `rutas/autenticacion.py`
- `backend/migraciones_principal/versions/p0004_captcha_local.py`, `backend/sql/HU_CAPTCHA_P0004_PROPUESTA.sql`
- `backend/requirements.txt`, `backend/herramientas/probar_seguridad_aislada.py`
- `backend/pruebas/{test_imagen_captcha,test_captcha_local_pg,test_seguridad_login,test_persistencia_principal}.py`
- `frontend/esart/src/app/nucleo/modelos/sesion.ts`, servicios `cliente-api.service.ts`, `sesion.service.ts`
- `frontend/esart/src/app/paginas/inicio-sesion/inicio-sesion.{ts,html,spec.ts}` y `captcha/{captcha.ts,captcha.html,captcha.spec.ts}`

Los documentos hist?ricos del 503 y del proveedor no disponible describen el estado anterior; esta entrega a?ade el proveedor real y reemplaza ese diagn?stico tras aplicar p0004. No se declara desplegado ni probado en la instancia operativa. Quedan pendientes su autorizaci?n, la comprobaci?n manual sobre intranet y la alternativa accesible equivalente.


## Resultado de ejecuci?n (2026-11-16)

- Backend sin habilitar conexiones de integraci?n: **171 aprobadas, 36 omitidas**. Las omitidas requieren entornos o autorizaciones de integraci?n espec?ficas; no se activaron sobre la base operativa.
- Compatibilidad HTTP con esquema p0003 en cl?ster aislado: **1 aprobada**, antes de aplicar p0004.
- Seguridad y CAPTCHA PostgreSQL tras p0004 en ese mismo cl?ster: **23 aprobadas**. Evidencia local ignorada por Git: `backend/respaldos/hu06_d3019d2707444a2e8107c4115554acd2/resultado.json`. Cl?ster detenido.
- Angular: **41 aprobadas en ocho archivos**; build de producci?n aprobado.
- Ruff sobre backend completo: **sin errores**.
- Diff de las revisiones previamente versionadas y `backend/.env`: sin cambios en esta entrega. p0004 solo fue aplicada en cl?steres aislados. No se realizaron escrituras en esart_db operativa.
