> Contrato actualizado: [correccion de bloqueo y CAPTCHA](HU_SEGURIDAD_BLOQUEO_CAPTCHA_CORRECCION.md). Sustituye la politica anterior de no contar ningun fallo CAPTCHA y el rechazo 401 durante bloqueo. Los resultados historicos siguientes conservan su contexto original.

# HU Seguridad — Intentos fallidos, CAPTCHA y bloqueo temporal

**Estado: código preparado y validado en una instancia PostgreSQL independiente. Migración principal NO aplicada. El verificador CAPTCHA real corresponde a la siguiente HU.** No se probaron contraseñas ni se generaron intentos de login en la base operativa.

**Alcance actualizado por el usuario: solo backend.** Se pausaron las modificaciones de Angular y CAPTCHA, que continúan en otro proceso. Las menciones de pruebas/cambios Angular más abajo describen trabajo anterior a esa separación, no una certificación de los archivos que se están editando en paralelo. El punto de entrega vigente es [HU_SEGURIDAD_CONTRATO_API.md](HU_SEGURIDAD_CONTRATO_API.md).

## Diagnóstico previo

Se revisaron los modelos operativos, servicio/ruta de autenticación, cookies/JWT, permisos, migraciones principales y formulario Angular. La inspección PostgreSQL de solo lectura confirmó esart_db/esart_aplicacion, existencia de esart.intentos_inicio_sesion y permisos UPDATE de columna sobre intentos_fallidos_consecutivos/bloqueado_hasta. No se encontró auditoria_acceso ni un sistema operativo de auditoria_eventos; este último existía como propuesta histórica, no como entidad operativa.

La estructura de seguridad ya incluye usuarios con contador y bloqueo (p0002_seguridad_sesiones), sesiones UUID relacionadas con usuarios BIGINT e intentos con usuario opcional/IP/fecha/resultado/motivo. Se reutiliza todo ello. El servicio anterior no incrementaba contadores ni registraba intentos. No había verificador CAPTCHA funcional. El componente Angular local de CAPTCHA es un esqueleto; no valida una autenticación.

La cuenta de aplicación ya tiene en p0002 lectura de usuarios/roles/asignaciones, UPDATE limitado a contadores/bloqueo/último acceso y SELECT/INSERT para intentos. Se conserva el algoritmo bcrypt, el rol, las cookies, JWT y el modelo de sesión vigente. No se crean usuarios o roles en producción.

## Política definida

| Estado / solicitud | Tratamiento |
|---|---|
| Credenciales fallidas 1, 2 y 3 | Contador persistente 1, 2, 3. La respuesta del tercer fallo indica que el próximo intento requiere CAPTCHA |
| Desde el cuarto intento | CAPTCHA obligatorio antes de cualquier comprobación bcrypt |
| CAPTCHA ausente, inválido o proveedor no disponible | Rechazo sin comprobar contraseña; consume cuota IP y genera intento/auditoría. **No incrementa el contador de credenciales**, no reinicia el ciclo ni modifica el plazo |
| CAPTCHA válido, credenciales fallidas 4–6 | Contador se incrementa; mantiene requisito CAPTCHA |
| Séptimo fallo de credenciales | Contador 7; bloqueado_hasta = reloj PostgreSQL + 3 horas, inmediatamente |
| Intentos durante bloqueo | No verifica contraseña ni emite JWT. No incrementa contador ni prorroga el vencimiento; sí audita y consume cuota IP |
| ahora >= bloqueado_hasta | Reinicia contador a 0 y elimina el bloqueo de forma perezosa en el siguiente intento; registra BLOQUEO_VENCIDO. En la frontera exacta ya permite iniciar un ciclo nuevo |
| Login exitoso | Contador 0 y bloqueo NULL, último acceso y sesión normal; intento y auditoría en la misma transacción |
| Cuota IP agotada | 429 genérico; no verifica credenciales ni modifica contador/bloqueo de cuenta. La ventana no se desplaza por rechazos |

Contar CAPTCHA inválidos como credenciales permitiría bloquear una cuenta enviando peticiones vacías, sin resolver desafíos. Por ello se distinguen ambos tipos de rechazo. El cliente no puede eludir bcrypt mediante esta separación: sin CAPTCHA válido la contraseña nunca se comprueba, y el presupuesto IP se consume igualmente.

La política es idéntica para nombres inexistentes mediante un estado seudonimizado separado. No se crean usuarios ficticios ni se devuelve si un nombre existe. Para rechazos equivalentes, usuario real/inexistente comparten estado HTTP, mensaje y señales públicas. El bloqueo no se prolonga mientras está vigente. Un atacante que logra siete nuevos fallos válidos tras expirar puede provocar otro ciclo: la política de bloqueo por cuenta tiene ese riesgo de denegación de servicio; CAPTCHA real y límites distribuidos lo reducen, pero no se afirma inmunidad absoluta. Recuperación/desbloqueo administrativo requeriría otra autorización e implementación.

La validación de sesiones existentes también rechaza acceso mientras el usuario está bloqueado. No se cambian claves, firma, claims ni filas previas de sesión por el bloqueo; tras expirar siguen aplicándose las comprobaciones normales de revocación e inactividad.

## Persistencia y concurrencia

La fuente del contador real sigue siendo esart_ref.usuarios. Se bloquea su fila FOR UPDATE y se relee aunque hubiera objetos en el identity map. Para nombres inexistentes se bloquea una fila de estado anónimo. La cuota IP se bloquea antes que la cuenta, manteniendo el mismo orden en todos los workers. INSERT ON CONFLICT DO NOTHING inicializa filas auxiliares sin perder incrementos concurrentes.

Los tiempos provienen de clock_timestamp() de PostgreSQL después de esperar los bloqueos, con timestamptz/UTC. El contador no depende del proceso, navegador, IP utilizada para una cuenta real o reinicio de FastAPI. Los rechazos previstos confirman el estado y la auditoría **antes** de lanzar el error HTTP; un rollback del manejador no pierde los fallos ya contabilizados. Un fallo técnico antes del COMMIT revierte todo y no emite token. El token de éxito se prepara antes del COMMIT y solo se devuelve después de confirmarlo.

Un fallo de auditoría impide autenticar: no existe fallback que omita su registro. La contraseña se comprueba en un thread para no bloquear el event loop, manteniendo la transacción y sus bloqueos. La serialización por IP/cuenta reduce concurrencia deliberadamente; deben medirse latencia y capacidad con la carga real antes de producción.

## Migración propuesta: p0003_control_intentos

Archivo: [p0003_control_intentos.py](../backend/migraciones_principal/versions/p0003_control_intentos.py). Padre: p0002_seguridad_sesiones. No se modifica p0000_instalacion_inicial, p0001_real ni p0002. No se añade un segundo head.

| Objeto | Cambios |
|---|---|
| esart.intentos_inicio_sesion | Añade captcha_requerido boolean NOT NULL DEFAULT false y captcha_validado boolean opcional. No duplica la tabla ni elimina intentos |
| esart.limites_inicio_ip | clave HMAC varchar(64) PK, inicio timestamptz e intentos >=0; ventana fija compartida entre workers |
| esart.estados_acceso_anonimos | clave HMAC PK, contador >=0 y bloqueado_hasta opcional; refleja la misma política para nombres inexistentes |
| esart.auditoria_acceso | Identidad BIGINT, FK intento_id, evento tipado por el servicio y fecha UTC. Correlación con intento; sin cuerpo de petición, contraseña, hash o JWT |

La auditoría registra LOGIN_RECHAZADO, CUENTA_BLOQUEADA, BLOQUEO_VENCIDO, LOGIN_EXITOSO e IP_LIMITADA. El intento distingue credenciales inválidas, CAPTCHA inválido, bloqueo vigente y cuota IP. Se registra captcha_validado=NULL cuando no se validó, false si se rechazó y true si el proveedor lo aceptó. Las tablas auxiliares representan estado de control, no duplicados de usuarios o unidades.

Permisos propuestos exclusivamente sobre objetos necesarios: USAGE en esart/esart_ref; SELECT/INSERT/UPDATE de las dos tablas de estado; SELECT/INSERT y USAGE de secuencia en auditoría. UPDATE/DELETE/TRUNCATE de auditoría se revocan de esart_aplicacion y PUBLIC. No se concede UPDATE de contraseñas, CREATE, permisos administrativos ni cambios de malla de roles. El rol heredado p0002 proporciona los permisos de usuarios/intentos; comprobarlo antes de desplegar.

Se generó [SQL de revisión](../backend/sql/HU_SEGURIDAD_P0003_PROPUESTA.sql) offline. **No ejecutarlo manualmente**: no registra por sí solo la revisión Alembic. La reversión destructiva no está habilitada; conservar intentos/auditoría y preparar un procedimiento aprobado si fuera necesario.

## Configuración, privacidad e IP

Variables nuevas de Configuracion, sin modificar backend/.env:

- LIMITE_INTENTOS_IP: default **30**, entre 1 y 1000 solicitudes por ventana.
- VENTANA_INTENTOS_IP_SEGUNDOS: default **900**, entre 60 y 86400 segundos.

El límite cuenta éxitos y rechazos. No se reinicia por login exitoso para evitar evadirlo con una cuenta válida. Una ventana nueva comienza al expirar, no se extiende por peticiones bloqueadas. Si la IP no se puede verificar, las solicitudes comparten una cuota restrictiva común.

La ruta solo considera el peer ASGI y no acepta Forwarded, X-Forwarded-For ni X-Real-IP como fuente de identidad IP. Si llegan esas cabeceras, usa el bucket de origen no verificable en lugar de una dirección controlada por el cliente, incluso si middleware previo reescribió client. Para acceso directo local se recomienda iniciar Uvicorn con **--no-proxy-headers**. Una futura topología con proxy de confianza necesita configurar explícitamente sus redes y extracción de peer; no se habilita confianza genérica en esta HU. El proxy Angular /api se conserva.

Nombres introducidos y claves de estado/IP se seudonimizan con HMAC-SHA256, con derivación de dominio a partir del secreto JWT existente. No se almacenan nombres desconocidos en texto plano; nombre_usuario_intentado contiene 64 caracteres hexadecimales para los **nuevos** intentos. La IP se conserva como INET en el intento según la necesidad de trazabilidad; no se copia a texto libre de auditoría. IPv4 mapeada en IPv6 se normaliza a IPv4. Seudonimizar no equivale a anonimizar.

La clave debe persistir entre reinicios. Rotar el secreto JWT cambia los seudónimos y reinicia la identificación de ventanas/estados anónimos; los contadores de usuarios reales permanecen. Planificar esa rotación y, si se requiere, introducir una clave de seudonimización independiente mediante una revisión posterior. No hay claves fijas nuevas. Los intentos antiguos se conservan sin transformar sus nombres: su tratamiento histórico requiere una decisión de datos separada.

Cada petición rechazada registra un intento/evento, incluso si está limitada. Deben establecerse capacidad, monitorización y retención de estas tablas: esta entrega no borra registros ni crea un purgador automático. La cuenta de aplicación no puede borrar auditoría, pero un propietario de base puede administrarla; no se presenta como almacenamiento inviolable ante un administrador.

## CAPTCHA: límite explícito de esta historia

[VerificadorCaptcha](../backend/aplicacion/seguridad/captcha.py) define el puerto async. El verificador futuro debe validar expiración, contexto de cuenta y consumo atómico de un solo uso. Se conecta por la dependencia obtener_verificador_captcha. No hay flag de cliente captcha_valido ni aceptación de valores fijos.

El proveedor por defecto **rechaza todos los desafíos**. Es una denegación segura, no una autenticación simulada. No se implementan imágenes, generador, endpoint de desafío ni respuestas prefijadas. Desde el cuarto intento no podrá completarse un login en producción hasta conectar el CAPTCHA real de la siguiente HU. La prueba de esos caminos usa un doble exclusivo de validación CAPTCHA en la base aislada; bcrypt, filas, sesiones y JWT sí son reales.

Angular conserva sus componentes y estilos. SesionService acepta un desafío/respuesta del servidor para la futura conexión; la página interpreta captcha_requerido y acceso_temporalmente_restringido del detalle del error. No cuenta fallos ni calcula fechas ni impide indefinidamente reintentar por una bandera local. Se muestran mensajes genéricos; no se envía el instante exacto de desbloqueo. El esqueleto CAPTCHA local existente no recibe autoridad para validar credenciales.

## Despliegue pendiente y comportamiento sin migración

**No se aplicó p0003 a la principal.** El login comprueba disponibilidad de sus objetos; si faltan responde 503 SEGURIDAD_NO_DISPONIBLE y no intenta autenticar por un camino antiguo sin controles. Por tanto, no desplegar este código aisladamente sobre p0002 como si fuera una actualización completa. Coordinar migración, permisos y verificador CAPTCHA real antes de habilitar el flujo para usuarios.

Solo después de aprobación expresa, respaldo recuperable y comprobación de destino/revisión con conexión administrativa protegida, el comando propuesto desde backend sería:

```powershell
.venv/Scripts/python.exe -m alembic upgrade p0003_control_intentos
```

Requiere ESART_MIGRACIONES_URL administrativa temporal. No se ejecutó contra 127.0.0.1:5432 ni se hizo stamp. No enviar credenciales por chat ni incorporar conexiones al repositorio. La URL de la aplicación permanece independiente. Ningún restablecimiento de admin.esart se realizó como parte de esta HU.

## Pruebas reales aisladas y reproducibilidad

[probar_seguridad_aislada.py](../backend/herramientas/probar_seguridad_aislada.py) crea un clúster PG18 nuevo bajo backend/respaldos/hu06_*, marcado ESART_SOLO_PRUEBAS, puerto dinámico **distinto de 5432** y secretos efímeros aleatorios. Crea una base de nombre esart_db **en esa otra instancia**, no usa la principal. Verifica data_directory antes de preparar/migrar; el fixture vuelve a comprobar marcador, ruta, puerto y servidor. Migra desde p0000 hasta p0003 e invoca pruebas como esart_aplicacion, no como superusuario. Al terminar detiene el clúster, elimina el archivo temporal del secreto y conserva evidencias ignoradas por Git.

Desde backend, en un entorno autorizado para abrir esa instancia de pruebas:

```powershell
.venv/Scripts/python.exe -m herramientas.probar_seguridad_aislada
```

Requiere binarios locales PostgreSQL 18; su ruta Windows está explícita en la herramienta. No configurar manualmente ESART_SEGURIDAD_TEST_URL hacia una base ajena. Las pruebas rechazan puerto 5432 y servidores sin el marcador/directorio de pruebas. El comando crea datos ficticios exclusivamente en la instancia aislada. No restaura ni modifica esart_db operativa y no elimina bases existentes.

Las pruebas cubren: umbrales 1–3/CAPTCHA/siete fallos, CAPTCHA ausente/incorrecto sin bcrypt, no prórroga, tres horas/frontera exacta, reset exitoso, concurrencia desde varias IP, estado anónimo, cuota persistente/ventana exacta, nueva aplicación/pool tras reinicio, cabeceras no confiables, auditoría append-only, rollback ante fallo de auditoría, roles/hash inalterados y bloqueo de una sesión existente. También se prueba HTTP login/yo con credenciales, cookies y JWT reales del clúster de pruebas.

Las pruebas offline se ejecutan sin activar flags históricos de escritura. Las pruebas Angular comprueban señal de CAPTCHA/bloqueo y transporte del desafío sin contadores del cliente. Una compilación o un doble CAPTCHA no se presentan como verificación del proveedor real, aún pendiente.

## Archivos de esta HU

- Modelos/configuración: aplicacion/modelos/seguridad.py y aplicacion/configuracion.py.
- Migración nueva: migraciones_principal/versions/p0003_control_intentos.py; propuesta SQL de revisión.
- Servicios: servicios/seguridad_login.py, servicios/autenticacion.py y seguridad/captcha.py.
- Ruta: rutas/autenticacion.py; JWT/cookies existentes conservados.
- Angular: servicio/modelo de sesión, página de login y sus pruebas; sin generador de imágenes.
- Pruebas: test_seguridad_login.py, test_seguridad_login_pg.py y ajuste del contrato de metadatos/head en test_persistencia_principal.py.
- Herramienta de instancia aislada, este documento y diagnóstico de solo lectura.

Los cambios anteriores del administrador, diseño de la página, fotografías y componente CAPTCHA local pertenecen a trabajo preexistente/concurrente: no se eliminaron ni se consideran generación de CAPTCHA de esta HU. No se hace commit ni push.

## Resultado final de las comprobaciones

- **171 pruebas Python offline aprobadas, 29 omitidas**: los casos PostgreSQL y otros casos optativos no se ejecutan al configurar la suite sin destinos explícitos.
- **14 pruebas PostgreSQL reales aprobadas** por separado en la instancia independiente, tras ejecutar la cadena Alembic completa y usar esart_aplicacion para autenticar. Incluye el login HTTP/yo real con cookie/JWT, sin simular identidad ni comprobar contraseñas de producción.
- **38 pruebas Angular aprobadas en 8 archivos**, compilación Angular correcta.
- Ruff global sin errores y compilación Python correcta.
- Los archivos históricos p0000, p0001 y p0002 no tienen cambios de esta HU.
- Clúster de pruebas detenido; evidencias conservadas sin secretos en el árbol ignorado de respaldos. Ninguna migración, intento de autenticación, usuario, contraseña o clasificación se escribió en la principal.

Resumen sanitizado: [HU_SEGURIDAD_PRUEBAS.json](HU_SEGURIDAD_PRUEBAS.json). Diagnóstico de solo lectura: [HU_SEGURIDAD_DIAGNOSTICO.json](HU_SEGURIDAD_DIAGNOSTICO.json). Estos resultados no certifican un proveedor CAPTCHA real ni un despliegue de p0003 en esart_db operativa.
