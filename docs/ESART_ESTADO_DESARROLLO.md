# Estado de desarrollo de ESART

Fotografía: **2026-11-15**, rama local HU-04-poblacion_data. «Implementado» describe código; «probado» identifica una verificación concreta. Ningún test con mocks sustituye una sesión real contra PostgreSQL y Angular.

## Matriz de seguimiento

| Módulo | Estado | Implementado | Pendiente | Prioridad |
|---|---|---|---|---|
| Autenticación | Pendiente operativa | Dependencia de identidad confiable, rechazo 401 sin identidad | Login real, identidad validada del servidor, pruebas de sesión; no hay proveedor que llene request.state.usuario_id | P0 |
| JWT | Configuración parcial | Validación de secreto y rechazo de ejemplos; contrato cookie HttpOnly/CSRF | Configuración local segura, emisión/verificación/expiración/revocación e inactividad. El último diagnóstico detectó valor de ejemplo | P0 |
| Roles y permisos | Parcial, probado con mocks/SQL compilado | Modelos de roles, usuario_roles y malla CRUD real; excepción individual y denegación por defecto | Lectura y pruebas reales con usuarios autorizados. Permisos granulares sin tabla: no inferir concesiones | P0 |
| Catálogos | Datos SQL comprobados; HTTP pendiente | SELECT real de 9 tipos de unidad, 5 cargos y 14 cursos; rutas y servicio HTTP | Sesión real para consultas protegidas, reconciliación futura de referencias | P0 |
| Unidades militares | Datos SQL comprobados; interfaz parcial | 40 unidades, 39 clasificadas y FUTOM NULL; ORM BIGINT, filtros, padres y árbol | Evidencia HTTP autenticada y visual de las 40 filas; pruebas completas de filtros/jerarquía real | P0 |
| Personal militar | Mapeo implementado | Columnas reales, FK de unidad y relaciones | CRUD seguro, autorización, UI y reconsulta del conteo histórico 0 por propietario | P1 |
| Cursos | Catálogo implementado, negocio pendiente | TipoCurso y tablas académicas mapeadas; 14 referencias SQL | Gestión de cursos, matrículas, notas, egresos, API y UI | P1 |
| Certificaciones | Parcial en persistencia | Tabla heredada artillero_certificaciones mapeada | Lógica de vigencia, documentos, rutas y UI; tipo_certificacion y requisitos todavía sin tabla operativa | P1 |
| COOFU | Referencias, sin servicio operativo | Curso COOFU y cargos con cuenta_para_coofu | Reglas aprobadas de idoneidad y cálculo de experiencia, pruebas y pantalla de resultado | P1 |
| Frontend Angular | Compilado/probado parcialmente | Ruta /unidades, servicio relativo, HttpClient/CSRF, búsqueda/tipo/activas, ruta jerárquica y manejo de errores | Login, guarda/proveedor de sesión, integración de negocio y demostración visual autenticada | P0 |
| API FastAPI | Compilada/probada parcialmente | Salud, siete rutas de lectura de catálogos, sesiones async, errores y filtrado de logs | Identidad real, autorización granular conciliada, modelos de respuesta/servicios completos, pruebas HTTP con datos reales | P0 |
| Alembic | Líneas separadas; adopción reportada | Único head principal p0001_real; historial 0001/0002 preservado; validación de estructura, incluye esquemas | Reconsultar revisión con operador: cuenta aplicación sin SELECT sobre historial; revisiones futuras e instalador inicial | P1 |
| Instalación desde cero | No disponible | Piezas SQL y snapshot de estructura existente | Cadena reproducible aprobada, migración inicial, seeds BIGINT independientes y pruebas de instalación/recuperación | P0 |
| Pruebas | Offline aprobadas; integración parcial | Pytest, Ruff, compileall, Angular build/tests y consultas SQL reales de catálogos | Autenticación, HTTP exitoso real, UI real, instalación nueva, recuperación e idempotencia operativa | P0 |
| Despliegue | No certificado | Herramientas de diagnóstico y respaldo, configuración local | Provisión segura, servidor de frontend compilado, secretos, observabilidad, recuperación y pruebas de aceptación | P1 |

P0 bloquea la entrega integral. P1 es trabajo posterior funcional o de operación. La prioridad es de esta fotografía, no sustituye el backlog aprobado.

## Evidencia actual y límites

En esta tarea documental se hizo SELECT de solo lectura contra esart_db como esart_aplicacion: unidades 40, tipos 9, cargos 5 y cursos 14; clasificadas 39, pendientes 1 y FUTOM pendiente 1. Las tablas ya tenían esos registros; no se cargaron para esta documentación. Se observa esart.alembic_version, pero no se puede consultar version_num con esa cuenta. El operador había confirmado p0001_real (head); el head de código local también es p0001_real, lo cual por sí solo no certifica el historial físico.

Personal 0 queda como referencia histórica: no se dispone de SELECT de personal. No se solicitan permisos más amplios para hacer coincidir un informe. La fotografía anterior que decía «sin USAGE/SELECT de catálogos» quedó superada por esta lectura real; se preserva como historia en sus documentos originales.

El último diagnóstico de configuración detectó JWT_CLAVE_SECRETA de ejemplo. La API valida secretos antes de arrancar; el código no implementa un login que establezca identidad. Una respuesta 401 en la ruta de catálogo no se soluciona con permisos PostgreSQL ni con arrays simulados. No se ha demostrado un 200 autenticado de estos catálogos ni la visualización real desde Angular.

## Procedimientos comprobados

- Inspección directa de metadatos y dependencias, sin DDL/DML.
- Modelos operativos separados del contrato UUID histórico y relaciones configurables sin crear tablas.
- Lectura SQL de catálogos y clasificación como usuario operativo.
- Existencia de la tabla de versión y carga local del único head principal.
- Pruebas offline del contrato de persistencia y rechazo HTTP sin identidad; no equivalen a permisos/usuarios de producción.
- Compilación y pruebas Angular; el test de transporte usa datos en memoria y no certifica visualización real.

## Procedimientos pendientes y bloqueos

1. Configurar JWT localmente sin valores predeterminados e implementar autenticación/sesión según contrato. No publicar secretos ni crear administradores de prueba.
2. Validar HTTP con identidad real, permisos y cookies; después demostrar Angular con las cuarenta unidades y FUTOM pendiente.
3. Consultar revisión Alembic mediante el operador y guardar evidencia sanitizada; no volver a hacer stamp/adopción ni modificar el historial durante documentación.
4. Crear instalador inicial y seeds operativos separados del DDL. Revisar qué objetos de los ocho modelos ausentes se necesitan; no crear tablas por simple existencia de clases históricas.
5. Comprobar recuperación del respaldo actual en un procedimiento autorizado. Índice legible o decodificación no son prueba suficiente de restaurabilidad.
6. Antes de publicar, revisar scripts heredados con módulos app.*, destinos externos y ejemplos de administrador/credenciales. No ejecutarlos ni considerar el repositorio listo para publicar porque Ruff pase.

## Registro de validaciones de esta entrega

| Comprobación ejecutada | Resultado y alcance |
|---|---|
| Pytest, Python 3.12.10 de backend/.venv | **117 aprobadas, 2 omitidas**; no se habilitaron integraciones históricas de escritura |
| Ruff global backend | Sin errores |
| compileall de aplicacion/herramientas/migraciones_principal | Correcto |
| Alembic history --verbose / heads | Única revisión principal p0001_real; inspección de código, no migración |
| Alembic current -v | No ejecutado: requiere conexión del operador en ESART_MIGRACIONES_URL; no se pidió ni imprimió un secreto |
| Angular build | Correcto; bundle en frontend/esart/dist/esart |
| Angular tests | **3 aprobadas en 2 archivos**; pruebas locales, no sesión real |
| Enlaces y rutas de documentación | Nueve documentos revisados, sin destinos locales inexistentes |
| PostgreSQL como usuario operativo | Verificador principal: lectura_validada; estructura y cuatro conteos correctos; FUTOM pendiente |
| Revisión Alembic física y personal | Tabla de historial observada; SELECT restringido. Se conserva la referencia del operador sin inventar una reconsulta |
| Datos y publicación | Sin DDL/DML, cambios de historial, commit ni push |

Las dos pruebas históricas optativas de escritura permanecieron omitidas. No se ejecutaron upgrade, downgrade, stamp, autogenerate, cargas o actualizaciones. Las pruebas pueden crear cachés y artefactos de compilación locales; no escriben registros en PostgreSQL.

## Archivos documentales modificados en esta tarea

- README.md.
- docs/HU04_POBLACION_DATOS.md.
- docs/ESART_INSTALACION_BASE_DATOS.md.
- docs/ESART_ESTADO_DESARROLLO.md.
- docs/ESART_ENTREGA_OTRO_DESARROLLADOR.md.
- docs/HU04_INVENTARIO_SCRIPTS.md.
- backend/README.md, frontend/README.md y frontend/esart/README.md: actualizados para evitar instrucciones obsoletas.

No se cambió código funcional, configuración .env, migraciones o scripts de carga durante esta tarea documental. El árbol de trabajo ya tenía cambios de desarrollo; no atribuir todo git status a esta entrega.
