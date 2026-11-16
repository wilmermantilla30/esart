# Corrección integral de persistencia ESART

Estado: correcciones de código realizadas; **integración operativa bloqueada y no certificada**. No se ejecutaron DDL, DML, seeds, stamp ni cambios de historial. No se crearon bases de datos. No se modificó `.env`.

## Auditoría real

La conexión local de `backend/.env` se comprobó contra **esart_db**, usuario **esart_aplicacion**, en transacciones de solo lectura. El servidor local acepta la conexión sin TLS; la negociación SSL del controlador interrumpía la conexión anterior. El código desactiva TLS únicamente para los hosts de loopback; los servidores remotos conservan el comportamiento TLS del controlador.

Se inspeccionaron mediante `pg_catalog` los tres esquemas `esart`, `esart_ref` y `public`: 43 tablas, 335 columnas, 436 restricciones —incluidas las restricciones NOT NULL que registra PostgreSQL 18—, 134 índices y 40 secuencias. No hay triggers de usuario ni funciones institucionales. No existe tabla `alembic_version`. El detalle verificable está en `ESART_AUDITORIA_PERSISTENCIA.json`.

La tabla de unidades tiene realmente `id BIGINT`, `codigo`, `nombre`, `tipo_unidad_id BIGINT`, `unidad_padre_id BIGINT`, `latitud`, `longitud`, `activo` y las dos fechas. El catálogo de tipos usa BIGINT. Esto difiere del paquete SQL anterior que proponía UUID públicos y `unidad_superior_id`; **no ejecutar ese paquete anterior contra esta estructura**. Tampoco ejecutar `revision_pendiente.sql`, que pertenece al contrato UUID histórico.

Las cinco FK entrantes originales de unidades siguen declaradas en personal, cargos, disparos, egresados y reentrenamientos; además existe la FK autorreferencial de `unidad_padre_id`. No se alteraron sus identificadores, acciones ni destinos. Las relaciones exactas están en el inventario.

`esart_aplicacion` no tiene USAGE/SELECT sobre ninguna de las 43 tablas institucionales. Los metadatos pudieron inspeccionarse mediante los catálogos del sistema, pero **no fue posible consultar las filas**. Los conteos 40/39/1, 9 tipos, 5 cargos, 14 cursos y cero personas son el estado comunicado por el usuario; no se presentan como conteos verificados por este proceso. Véase `ESART_VERIFICACION_PRINCIPAL.json`, que registra los conteos bloqueados como null, nunca como cero.

## Correcciones implementadas

- `aplicacion/modelos/persistencia.py` mapea explícitamente las 43 tablas existentes, con sus columnas, esquemas, BIGINT, identidades, defaults, PK, FK, UNIQUE, CHECK e índices. No refleja ni crea tablas durante el arranque. Las entidades canónicas se reexportan desde `nucleo.py`, `catalogos_organizacion.py` e `__init__.py`.
- Se incorporaron relaciones ORM comprobadas para la jerarquía, clasificación, personal, hoja de vida, cargos, cursos y asignaciones de roles. Las relaciones usan carga explícita para evitar consultas asíncronas implícitas.
- Ocho modelos no tienen tabla real: permisos granulares, roles/permisos granulares, intentos de inicio, sesiones, importaciones, auditoría, tipos de certificación y requisitos de habilitación. Sus definiciones y pruebas UUID se conservan en `modelos/historico/`, con metadatos separados. No se consultan como si existieran en la principal. No se eliminó ninguna funcionalidad de la base. Su incorporación requiere diseño y migración posterior aprobada, con FK BIGINT reales.
- La autorización CRUD consulta `esart.usuario_roles` —la tabla real de asignación— y aplica las excepciones de `usuario_permisos`. Ya no presupone un `usuarios.rol_id` inexistente. Un código granular se deniega si su catálogo no está implementado: no se deducen concesiones equivalentes ni se da acceso implícito al administrador.
- FastAPI y las herramientas de conexión leen `backend/.env`, sin cambiar su contenido ni la base operativa. Los errores no incluyen credenciales.
- Las rutas `/api/catalogos/unidades`, `/unidades/{id}`, `/unidades/{id}/subordinadas`, `/unidades/jerarquia`, `/tipos-unidad`, `/cargos` y `/cursos` consultan los modelos reales. Las unidades admiten búsqueda, filtros por tipo, actividad, padre y clasificación pendiente. Se validan ciclos y referencias en el árbol. Los BIGINT del contrato JSON se serializan como cadenas, sin pérdida de precisión en Angular.
- Angular usa HttpClient, rutas relativas, proxy de desarrollo hacia `127.0.0.1:8081`, configuración CSRF y carga real del catálogo. La vista muestra código, nombre, tipo, superior, ruta jerárquica, conteos, filtros, carga y errores. No incluye listas de unidades simuladas ni datos de otras bases.

## Autenticación y arranque: pendientes reales

El proyecto no tenía un login/proveedor de identidad implementado. Las rutas nuevas exigen una identidad puesta por un proveedor confiable en `request.state.usuario_id`. No aceptan identificadores suministrados en cabeceras ni añaden un bypass. Mientras ese proveedor no esté integrado, responden 401 y Angular muestra la necesidad de iniciar sesión. No se afirma que exista una sesión funcional.

Además, la validación real de `Configuracion()` detecta que `JWT_CLAVE_SECRETA` sigue siendo un valor de ejemplo. Por ello el arranque normal de FastAPI se detiene, como exige su control de seguridad. No se cambió ni imprimió ese secreto. El operador debe reemplazarlo localmente por un valor seguro; no debe enviarlo por chat. Esta corrección no sustituye la implementación y validación de login, expiración y revocación de sesiones.

No se exponen listados públicos de usuarios ni de personal. Sus modelos se corrigieron, pero sus endpoints requieren el proveedor de identidad y una autorización funcional antes de incorporar acceso a información personal. Las rutas de catálogos están preparadas; la consulta autenticada real y la visualización de las 40 filas permanecen pendientes.

## Alembic

`alembic.ini` selecciona exclusivamente `migraciones_principal/`, con un solo head: `p0001_real`. Las revisiones `0001` y `0002` no se modificaron. `alembic_historico.ini` conserva su historial separado y su entorno rechaza conexiones a esart_db antes de ejecutar revisiones.

La revisión propuesta `p0001_estructura_real.py` adopta la estructura existente mediante **verificación efectiva**, no stamp. Comprueba tablas, columnas, tipos, nulabilidad, defaults, identidades, columnas generadas, restricciones e índices originales, sus estados válidos y las funciones registradas en el inventario congelado. La herramienta de solo lectura ejecutó su validador y confirmó equivalencia con la estructura actual, sin llamar a Alembic upgrade ni escribir historial.

**No se ha aplicado p0001_real.** Cuando se autorice, Alembic creará `esart.alembic_version` e insertará `p0001_real` solo tras comprobar la equivalencia dentro de la transacción. Esto requiere CREATE en el esquema esart para la cuenta de migraciones y privilegios sobre su propia tabla de versión; no se pide concederlos a esart_aplicacion. La conexión administrativa no se guarda en `.env` ni se usa como conexión del backend.

No ejecutar `stamp`, el historial UUID ni autogenerate. La autogeneración está bloqueada hasta conciliar también funciones y triggers con un procedimiento revisado. Las revisiones posteriores se prepararán manualmente en este único historial y deberán preservar el esquema existente.

Esta línea base **adopta una instalación existente**, no crea una instalación vacía. La reproducción desde cero sigue pendiente de una migración inicial completa revisada; no se declara resuelta por el hecho de poder adoptar la principal. No se ha creado otra rama head ni otro esquema paralelo.

## Respaldo

`backend/respaldos/esart_db_pre_alembic.dump` existe, mide 153402 bytes y su SHA-256 es `7488edaf5152b8603809f5fa8b5996d13c97b576a77e4d705b07bca0511511fc`.

Se comprobó el índice con pg_restore 18.7 y la decodificación completa del archivo hacia NUL, sin conexión a una base. Ambas operaciones terminaron correctamente. **No se considera esto una restauración validada.** La evidencia anterior de restauración correspondía a otro respaldo, `esart_db_pre_hu04.backup`, con otra huella y otro estado. No se trasladó esa certificación al archivo nuevo. No se crearon bases ni se restauró sobre esart_db.

## Operación mínima pendiente de aprobación

`backend/sql/ESART_PERMISOS_LECTURA_PENDIENTES.sql` contiene exactamente la propuesta de acceso a los cuatro catálogos:

```sql
GRANT USAGE ON SCHEMA esart, esart_ref TO esart_aplicacion;
GRANT SELECT ON esart_ref.unidades_militares,
                esart.tipos_unidad, esart.tipos_cargo, esart.tipos_curso TO esart_aplicacion;
```

Debe ejecutarla el propietario o un administrador tras aprobación expresa. No concede escritura, CREATE, permisos globales, acceso a hashes de usuarios ni lectura de personal. La verificación de personal puede realizarla el propietario sin ampliar los permisos del backend. No se ejecutaron estas sentencias.

Después de resolver permisos y autenticación, repetir desde backend:

```powershell
.venv/Scripts/python.exe -m herramientas.verificar_persistencia_principal
.venv/Scripts/python.exe -m uvicorn aplicacion.principal:aplicacion --port 8081
```

Desde frontend/esart, `npm start`; abrir `/unidades` con sesión real. Guardar conteos, respuestas HTTP y evidencia visual. No considerar el trabajo completado antes de comprobar 40 unidades, 39 clasificadas, FUTOM pendiente y los catálogos desde el usuario operativo.

## Pruebas y conservación

Resultados finales: **117 pruebas Python aprobadas, 2 omitidas**, Ruff global sin errores, compilación Python correcta, `alembic heads` con un único `p0001_real`, compilación Angular correcta y **3 pruebas Angular aprobadas**. La comprobación de estructura contra PostgreSQL fue real y de solo lectura; la comprobación de filas terminó explícitamente en estado `bloqueado_por_permisos`. Las pruebas omitidas son históricas de integración y no se ejecutaron contra otra base.

Las pruebas locales no insertan filas y no crean bases. Las pruebas históricas conservan su contrato aislado de los modelos operativos. Las pruebas HTTP verifican el rechazo sin autenticación; no se presentan como evidencia de una consulta real exitosa. La prueba Angular del transporte usa un identificador límite en memoria, sin crear un registro institucional.

Los registros permanecen sin escrituras por parte de este trabajo: todas las conexiones de auditoría usaron READ ONLY y terminaron con rollback. La comparación de huellas de filas antes/después está bloqueada por permisos, por lo que no se inventa una comprobación de contenido. Ninguna sentencia de carga o actualización se ejecutó.

La matriz exhaustiva de modelos y tablas se adjunta a continuación.

| Modelo | Tabla PostgreSQL | Diferencias revisadas | Correccion |
|---|---|---|---|
| AlertasAcademicas | esart.alertas_academicas | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| AlertasCertificacion | esart.alertas_certificacion | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| AlumnosActivos | esart.alumnos_activos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ArtilleroCargo | esart.artillero_cargos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ArtilleroCertificacion | esart.artillero_certificaciones | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ArtilleroCurso | esart.artillero_cursos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ArtilleroDisparos | esart.artillero_disparos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| CertificadosReentrenamiento | esart.certificados_reentrenamiento | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ComiteMovilInstructores | esart.comite_movil_instructores | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ComitesMoviles | esart.comites_moviles | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Componente | esart.componentes | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ConsejosAcademicos | esart.consejos_academicos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Cursos | esart.cursos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| CursosInstructores | esart.cursos_instructores | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Diplomas | esart.diplomas | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| DoctrinaDocumentos | esart.doctrina_documentos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| EgresadosCurso | esart.egresados_curso | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| EspecialidadesInstructor | esart.especialidades_instructor | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Habilitaciones | esart.habilitaciones | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| HojaVidaArtillero | esart.hoja_vida_artillero | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| InscripcionesCurso | esart.inscripciones_curso | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Instructores | esart.instructores | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| InstructoresEspecialidades | esart.instructores_especialidades | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| MallaCurricular | esart.malla_curricular | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Materias | esart.materias | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| NotasFinalesEgresado | esart.notas_finales_egresado | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| NotasMateria | esart.notas_materia | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| OperadoresSistema | esart.operadores_sistema | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| ParticipantesReentrenamiento | esart.participantes_reentrenamiento | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| PersonalMilitar | esart.personal_militar | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Reentrenamientos | esart.reentrenamientos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| RolPermiso | esart.rol_permisos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Rol | esart.roles | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| SemestresAcademicos | esart.semestres_academicos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| TipoCargo | esart.tipos_cargo | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| TipoCurso | esart.tipos_curso | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| TipoUnidad | esart.tipos_unidad | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| UsuarioPermiso | esart.usuario_permisos | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| UsuarioRoles | esart.usuario_roles | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| SistemaArtilleria | esart_ref.sistemas_artilleria | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| SistemasEnOperacion | esart_ref.sistemas_en_operacion | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| UnidadMilitar | esart_ref.unidades_militares | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Usuario | esart_ref.usuarios | BIGINT y columnas reales; esquemas/PK/FK/defaults revisados | Mapeo operativo corregido |
| Permiso | No existe: esart.permisos | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
| RolPermisoCodigo | No existe: esart.roles_permisos | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
| IntentoInicioSesion | No existe: esart.intentos_inicio_sesion | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
| SesionUsuario | No existe: esart.sesiones_usuario | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
| ImportacionExcel | No existe: esart.importaciones_excel | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
| AuditoriaEvento | No existe: esart.auditoria_eventos | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
| TipoCertificacion | No existe: esart.tipos_certificacion | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
| RequisitoHabilitacion | No existe: esart.requisitos_habilitacion | Contrato UUID sin tabla real | Conservado en historico; migracion pendiente |
