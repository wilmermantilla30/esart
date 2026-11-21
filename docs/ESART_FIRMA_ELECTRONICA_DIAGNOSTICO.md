# Diagnóstico de firma electrónica ESART

Fecha de inspección: 19 de noviembre de 2026

## Estado

La firma electrónica solicitada no está implementada en esta rama. No se añadió una interfaz o endpoint que simule una autorización, firma, QR temporal o emisión segura. La conexión de un flujo parcial antes de resolver la identidad del firmante, el almacenamiento protegido y el vínculo entre documento y versión permitiría presentar como firmado un documento que no fue autorizado correctamente.

## Arquitectura encontrada

- **Frontend:** Angular 22 standalone, con sesión en cookie `HttpOnly`, protección CSRF y guardas de permisos. La página `verificar-artillero` genera y descarga PDFs, pero no ofrece un visor ni un editor de firma. No hay pantallas de generación de oficio o certificado independientes: ambos documentos se eligen desde la verificación del artillero.
- **Backend:** FastAPI, SQLAlchemy asíncrono y PostgreSQL. `GET /api/verificar/artillero/{numero_documento}/documento` genera el PDF en la respuesta y lo entrega para descarga. Los reportes `oficio_remisorio.py` y `certificacion.py` producen bytes PDF con ReportLab.
- **Autenticación:** sesión JWT en cookie, autenticación con TOTP integrada al inicio de sesión y permisos resueltos en el backend por componente. No se encontró una sesión TOTP de firma ni una autorización de firmante conectada con el usuario de ESART.
- **Dependencias de interfaz:** el package incluye `qrcode`, pero no contiene visor PDF ni `signature_pad`. La dependencia QR por sí sola no genera tokens ni valida solicitudes.
- **Base de datos:** `backend/aplicacion/base_datos/esart_firma_certificados_seguridad.sql` define las tablas del esquema `esart_firma`, pero el archivo aparece sin seguimiento en Git. La inspección del repositorio no permite confirmar que el esquema haya sido aplicado al PostgreSQL conectado.

## Tablas declaradas en el SQL existente

El archivo define identidades y asignaciones de firma, factores TOTP, sesiones y desafíos, certificados y versiones, autorizaciones de firmantes, solicitudes, consentimientos, firmas, validaciones criptográficas, verificaciones públicas, auditoría, cambios y evidencias. Se deben reutilizar estas estructuras tras verificar su existencia y permisos en la base desplegada.

Hay dos brechas que impiden conectar directamente el requerimiento a ese modelo:

1. `solicitudes_firma.certificado_id` es obligatorio y su FK compuesta apunta a `versiones_certificado`. No existe una entidad documental genérica para representar un oficio remisorio, por lo que el flujo no puede asociar ambos tipos de PDF sin cambiar el modelo.
2. `versiones_certificado` solo vincula versiones a `certificados`. Además, el hash del archivo fuente no se copia a la solicitud; se puede consultar mediante la versión, pero falta una relación clara con el PDF temporal producido por el endpoint actual.

El SQL incluye disparadores inmutables y roles de firma, pero no configura el vínculo de identidad con los usuarios reales de ESART, la cadena de auditoría con hash, permisos mínimos del rol de aplicación, almacenamiento privado ni anclaje externo. El propio SQL marca esos pasos como operación posterior.

## Archivos revisados

- `frontend/esart/src/app/paginas/personal-militar/verificar-artillero/`: generación y descarga actual.
- `frontend/esart/src/app/nucleo/servicios/verificacion.service.ts`: consumo del endpoint de PDF.
- `frontend/esart/src/app/app.routes.ts`: rutas y módulos existentes.
- `backend/aplicacion/rutas/verificacion.py`: generación del PDF.
- `backend/aplicacion/reportes/{maestro,oficio_remisorio,certificacion,comun}.py`: generación de documentos.
- `backend/aplicacion/seguridad/{sesion_http,permisos}.py` y `backend/aplicacion/servicios/{autenticacion,totp}.py`: sesión, autorización y TOTP.
- `backend/aplicacion/base_datos/esart_firma_certificados_seguridad.sql`: esquema propuesto de firma.

## Trabajo necesario antes del flujo de firma

1. Verificar en un entorno de lectura que las tablas y columnas del SQL existen, y que la aplicación puede consultarlas con su rol actual. No ejecutar el archivo SQL ni migraciones de producción como parte de esta inspección.
2. Definir cómo se identifica y autoriza al firmante real. La identidad `esart_firma.identidades` debe vincularse a una cuenta activa de ESART; el QR no puede sustituir login, TOTP ni autorización documental.
3. Resolver la asociación de oficios y certificados a versiones inmutables. Si el esquema desplegado coincide con el SQL revisado, será indispensable una migración aditiva para documentos genéricos o una estructura equivalente aprobada. No se deben crear tablas duplicadas.
4. Definir almacenamiento privado temporal y permanente para el PDF original, la rúbrica, el PDF final y evidencias; fijar controles de acceso, retención y limpieza. El proyecto no contiene hoy un servicio de almacenamiento de documentos para este flujo.
5. Implementar endpoints autenticados para crear, consultar, cancelar y renovar solicitudes; intercambiar la rúbrica; guardar ubicación en coordenadas PDF; presentar vista previa; registrar consentimiento y emitir el archivo final. Asegurar expiración y uso único del token, hash SHA-256, control de versiones, permisos independientes y auditoría append-only.
6. Añadir al Angular el visor y la capa de ubicación por página, con coordenadas independientes del zoom y rotación, y una página móvil bajo sesión autenticada. Seleccionar e instalar dependencias solo después de verificar compatibilidad y licencia.
7. Mantener la imagen de rúbrica diferenciada de una firma digital PAdES. Si se exige validez criptográfica, firmar el PDF después de todos los cambios y validar la firma resultante.

## Matriz de pruebas requerida

No se ejecutaron pruebas de firma porque no hay implementación ni esquema desplegado verificado. Antes de habilitar el flujo se deben automatizar las pruebas de token vencido y reutilizado, falta de permisos, autenticación/TOTP fallida, cancelación, desconexión, cambio de hash, consentimiento sobre la versión exacta, límites de página, rotación y zoom; además de la emisión y descarga para los dos tipos de documento y revisión de los eventos de auditoría.

## Cambios y limitaciones

Este diagnóstico es el único archivo nuevo. No se modificaron procesos académicos, generadores PDF, autenticación, TOTP ni base de datos; tampoco se ejecutaron migraciones. El archivo SQL preexistente y sin seguimiento quedó intacto. La rúbrica visual por sí sola no constituye una firma digital criptográfica ni determina por sí sola la validez jurídica del documento.

## Verificacion de la base de datos local (19 de noviembre de 2026)

Se consulto PostgreSQL en una transaccion de solo lectura. La configuracion reporta `desarrollo`; el servidor es `127.0.0.1:5432`, base `esart_db`, rol `esart_aplicacion`. La consulta a `information_schema.tables` no encontro tablas en el esquema `esart_firma` (el esquema no esta instalado en esta base). Por tanto, el SQL presente es una propuesta local no aplicada, no tablas existentes reutilizables en el entorno conectado.

No se hizo ninguna escritura en PostgreSQL. Tampoco se incorporo un boton QR simulado: hasta instalar y vincular el modelo documental con las cuentas y permisos reales, no hay forma de verificar que el telefono autoriza la version exacta del PDF ni de emitir una firma auditable. El endpoint actual genera el PDF al vuelo y lo devuelve como descarga, sin conservar una version inmutable.
