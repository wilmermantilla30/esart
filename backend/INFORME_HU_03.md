# HU-03 — Migración inicial ESART

Fecha: 14 de noviembre de 2026.

**Estado: migración 0001 validada en PostgreSQL 18.7, exclusivamente en base aislada.**
Se ejecutó satisfactoriamente upgrade → validaciones → downgrade → nuevo upgrade
en `esart_hu03_pruebas`, como `esart_aplicacion`. Queda en `0001`, con las 22 tablas
y cero filas de prueba. `esart_db` solo se consultó en modo de lectura; conserva
sus 42 tablas existentes. No se modificaron credenciales ni configuración permanente.

## Fuentes y decisiones aprobadas

Se revisaron el informe anterior, ambos SQL de `aplicacion/base_datos/`, contratos
de esquema/API, `docs/esquema_referencia.sql`, configuración, BaseModelo,
sesiones, Alembic, modelos, pruebas y README.

El usuario aprobó expresamente en esta conversación:

- Las 19 tablas contractuales, UUID, nombres españoles, relaciones y restricciones.
- Tres tablas adicionales: `componentes`, `rol_permisos`, `usuario_permisos`,
  adaptadas a UUID. Una sola tabla de usuarios y roles; conservar `usuarios.rol_id`.
- Únicamente ADMINISTRADOR y USUARIO; sin datos semilla en esta revisión.
- Permisos CRUD por componente comprobables desde FastAPI y conservación de
  permisos por código del contrato API. No implementar login.
- Completar auditoría en tablas de negocio y catálogos; UNIQUE global del hash
  de importación, incluso para importaciones rechazadas; notas 0–5 y grado libre.
- Requisitos inicialmente vacíos y compatibilidad Vulcano diferida. La futura
  evaluación deberá devolver NO APTO cuando no haya requisitos configurados.
- Crear/modificar exclusivamente `esart_hu03_pruebas` para pruebas destructivas.

Estas aprobaciones resuelven para HU-03 los seis puntos abiertos: requisitos y
catálogo de grados quedan pendientes de datos oficiales; PK/nombres Vulcano se
difieren; se acepta escala 0–5 y la implementación conjunta de modelos/migración.
No se modificaron unilateralmente los contratos en `docs/`.

Los índices FK se implementaron individualmente para cumplir §9 sin interpretar
que un índice compuesto equivale a un índice propio. Las definiciones particulares
se complementaron con las fechas aprobadas. El UNIQUE del hash sustituye el índice
no único de referencia y prohíbe crear otra fila para el mismo archivo rechazado.

### Inventarios de referencia, excluidos de la migración

`docs/esquema_referencia.sql` contiene las 19 tablas del núcleo y tres de segunda
entrega (`instructores`, `materias_curso`, `artillero_notas_materia`). Estas últimas
no se crean en `0001`.

`esart_vulcano_postgresql.sql` contiene **37 tablas**: cuatro stubs en `esart_ref`
(`usuarios`, `unidades_militares`, `sistemas_artilleria`, `sistemas_en_operacion`)
y 33 tablas en `esart`. Incluye formación académica ampliada, disparos, doctrina,
instructores, inscripciones, notas, egresados, reentrenamientos y operadores.
Usa BIGINT y otros nombres/relaciones; no es equivalente al contrato UUID ESART.

El SQL de seguridad añade cinco tablas en `esart` (`roles`, `usuario_roles`,
`componentes`, `rol_permisos`, `usuario_permisos`), altera `esart_ref.usuarios`
y define una vista de permisos efectivos. Sus múltiples roles por usuario no se
adoptan. Tampoco se ejecutan sus INSERT ni su recomendación de cambiar a Argon2id:
esta historia conserva bcrypt. Ninguno de los SQL de referencia fue ejecutado.

## Inventario final implementado

Los 22 modelos se encuentran en `aplicacion/modelos/nucleo.py` y se importan desde
`aplicacion/modelos/__init__.py`, reutilizando `BaseModelo`.

| Tabla | Modelo | FK | CHECK | Índices |
|---|---|---:|---:|---:|
| unidades_militares | UnidadMilitar | 1 | 0 | 1 |
| personal_militar | PersonalMilitar | 1 | 3 | 2 |
| hoja_vida_artillero | HojaVidaArtillero | 1 | 0 | 1 |
| tipos_curso | TipoCurso | 0 | 2 | 0 |
| artillero_cursos | ArtilleroCurso | 3 | 3 | 4 |
| tipos_certificacion | TipoCertificacion | 0 | 0 | 0 |
| artillero_certificaciones | ArtilleroCertificacion | 3 | 2 | 4 |
| sistemas_artilleria | SistemaArtilleria | 0 | 0 | 0 |
| requisitos_habilitacion | RequisitoHabilitacion | 3 | 2 | 3 |
| tipos_cargo | TipoCargo | 0 | 0 | 0 |
| artillero_cargos | ArtilleroCargo | 3 | 1 | 3 |
| roles | Rol | 0 | 1 | 0 |
| permisos | Permiso | 0 | 0 | 0 |
| roles_permisos | RolPermisoCodigo | 2 | 0 | 2 |
| usuarios | Usuario | 1 | 0 | 2 |
| intentos_inicio_sesion | IntentoInicioSesion | 1 | 0 | 3 |
| sesiones_usuario | SesionUsuario | 1 | 0 | 1 |
| auditoria_eventos | AuditoriaEvento | 1 | 1 | 4 |
| importaciones_excel | ImportacionExcel | 1 | 1 | 1 |
| componentes | Componente | 1 | 0 | 1 |
| rol_permisos | RolPermiso | 2 | 1 | 2 |
| usuario_permisos | UsuarioPermiso | 3 | 1 | 3 |
| **Total** | **22** | **28** | **18** | **37** |

Los índices anteriores son los explícitos de metadatos; no cuentan los índices
implícitos de PK/UNIQUE de PostgreSQL. Incluyen la unicidad de la hoja por militar
y el índice funcional único `lower(nombre_usuario)`. Hay además 11 restricciones
UNIQUE, incluyendo códigos, documento, hash y curso/hoja/cohorte. La unicidad de
cohortes nulas conserva la semántica PostgreSQL contractual (NULL no es igual a NULL).

## Relaciones, restricciones y auditoría

- Jerarquías de unidades/componentes mediante FK autorreferenciadas.
- Personal pertenece opcionalmente a unidad y tiene como máximo una hoja de vida.
- Cursos, certificaciones y cargos pertenecen a hoja y a sus respectivos catálogos;
  cargos pueden referenciar unidad; cursos/certificaciones pueden referenciar importación.
- Requisitos apuntan a sistema opcional y exactamente a curso o certificación según tipo.
- Usuarios tienen un rol; roles y permisos por código se asocian con PK compuesta.
  Intentos, sesiones, importaciones y auditoría referencian usuarios según contrato.
- Mallas rol/componente y usuario/componente tienen PK compuesta, cinco booleanos
  con default false y CHECK de que CRUD requiere acceso. El autor opcional de una
  excepción referencia usuarios con ON DELETE SET NULL. Las FK nuevas conservan
  CASCADE/RESTRICT del SQL de seguridad; las contractuales conservan NO ACTION.
- CHECK de cédula, categoría, estado de servicio, notas 0–5, vigencia positiva,
  estados de curso/certificación/importación, coherencia de requisitos y fechas.
- UUID con `gen_random_uuid()` salvo el UUID de sesión, que debe suministrarse.
  Intentos y auditoría usan BIGINT GENERATED ALWAYS AS IDENTITY.
- TIMESTAMPTZ y default `now()`; se preservan las fechas específicas de sesiones,
  intentos y auditoría en lugar de añadirles las fechas de negocio.

La revisión crea dos funciones, sin reemplazar funciones existentes:
`public.actualizar_fecha_actualizacion()` y `public.impedir_modificacion_auditoria()`.
La primera tiene 19 triggers, exclusivamente sobre tablas con `fecha_actualizacion`.
La segunda bloquea UPDATE/DELETE y TRUNCATE de auditoría con dos triggers.
Se revocan privilegios de PUBLIC y UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER de
CURRENT_USER sobre auditoría, conservando INSERT/SELECT. El propietario de tablas
puede volver a concederse privilegios; para producción conviene separar cuenta
de migración y ejecución. Los triggers refuerzan la protección de DML.

## Autorización desde FastAPI

`aplicacion/seguridad/permisos.py` implementa consultas async y la dependencia
`requerir_permiso_componente`. El proveedor de identidad confiable debe entregarse
explícitamente y devolver UUID autenticado por el servidor; no existe login nuevo
ni se acepta identidad desde Angular como mecanismo de autenticación.

Las excepciones por usuario sustituyen toda la fila del rol. Un false explícito
deniega y una fila ausente permite usar la del rol. Usuarios/componentes inactivos
no reciben permisos. Un rol inactivo deja de aportar permisos; las excepciones
individuales conservan la semántica del SQL de seguridad. No hay acceso implícito
por ser ADMINISTRADOR. CREATE/READ/UPDATE/DELETE exigen acceso y acción habilitada.

La dependencia puede exigir además `codigo_permiso`, usando `permisos` y
`roles_permisos`. No se inventaron equivalencias entre códigos API y componentes:
las futuras rutas deberán declarar ambos controles según corresponda.

## Alembic y conexión

Archivo: `migraciones/versions/0001_nucleo_inicial.py`. Revisión `0001`, sin padre.
Usa operaciones Alembic explícitas y congeladas: no importa los modelos ni ejecuta
SQL de referencia o `metadata.create_all()`. Downgrade elimina triggers, funciones,
índices y tablas en orden inverso de dependencias, sin DROP SCHEMA ni CASCADE.

Alembic conserva asyncpg, SQLAlchemy async, NullPool, run_sync y metadatos compartidos.
Se separó `ConfiguracionConexion`, compartiendo la validación URL con la API.
La configuración de la API sigue exigiendo JWT y hash seguros. Alembic y las
herramientas solo necesitan datos de conexión, nunca JWT ni administrador.
La URL sigue siendo URL_BASE_DATOS; no se guardan credenciales en código.

El `.env` real está en `backend/`; no existe el raíz que usa la configuración por
defecto. Se añadió selección explícita `-x archivo_env=.env` a Alembic y
`--archivo-env .env` a las herramientas, sin mover ni modificar secretos.
La aplicación conserva la ruta raíz. Una inspección anterior detectó una clave
JWT demasiado corta; revisar la configuración de autenticación corresponde a la
historia posterior y no condiciona las pruebas de migración ya ejecutadas.

Antes de instalar, `0001` verifica esquema public, usuario no superusuario y
ausencia de tablas de aplicación en la base. Ante tablas existentes aborta la
transacción sin recrearlas. Downgrade solo está autorizado por el código para
`esart_hu03_pruebas`; el SQL offline de downgrade incluye esa misma guardia.

## Evidencias ejecutadas

Se prepararon Python **3.11.9** local en `.python311` y el entorno `.venv311`, ambos
ignorados por Git, con las dependencias fijadas del backend. No se instaló Docker.

| Comprobación con `.venv311/Scripts/python.exe` | Resultado |
|---|---|
| `-m alembic heads` | `0001 (head)` |
| `-m alembic history` | `<base> -> 0001 (head)` |
| `-m pytest` | **51 passed** |
| `-m ruff check .` | I001 previo en `herramientas/generar_hash.py`; archivo conservado |
| Ruff específico de archivos HU-03, incluido Alembic | Pasa |
| `git diff --check` | Pasa |
| Inspección PostgreSQL de solo lectura | Pasa: esart_db / esart_aplicacion / 5432 / public; 42 tablas |
| Ejecutor real `verificar_hu03 --archivo-env .env` | **Pasa**, exit code 0 |
| `alembic upgrade head` mediante conexión explícita de pruebas | **Pasa**, 22 tablas contractuales/adicionales y revisión 0001 |
| Comparación ORM/PostgreSQL | **Pasa**, sin diferencias de tipos, defaults, nulos, FK, UNIQUE e índices; CHECK reflejados coinciden |
| Comportamiento de restricciones | **Pasa**, 18 casos CHECK inválidos rechazados y pruebas UNIQUE/FK |
| Funciones, triggers, privilegios y CRUD | **Pasa**, actualización de fechas, auditoría inmutable y precedencia de permisos |
| `alembic downgrade base` mediante conexión explícita de pruebas | **Pasa**, sin tablas de revisión ni funciones propias; solo queda alembic_version vacía |
| Nuevo `alembic upgrade head` | **Pasa**, revisión 0001 y comparación ORM sin diferencias |

Las pruebas unitarias no dependen del `.env` principal ni de PostgreSQL. Incluyen
SQL offline de upgrade/downgrade; reconstrucción de las 22 tablas desde la revisión
para comparar columnas, tipos, nulos, defaults, identity, PK, FK, UNIQUE, CHECK e
índices contra el ORM; configuración; y controles FastAPI de las cuatro operaciones
y del código API adicional.

### Ejecución real y estado final

Los impedimentos anteriores quedaron resueltos: el usuario corrigió localmente
la conexión y creó `esart_hu03_pruebas` con `esart_aplicacion` como propietario.
No fue necesario conceder CREATEDB ni utilizar un superusuario para las pruebas.

La conexión de pruebas se derivó temporalmente de URL_BASE_DATOS cambiando solo
el nombre de base en memoria, y se pasó explícitamente a Alembic mediante
`Config.attributes`. Se ejecutaron las funciones `command.upgrade(..., 'head')`,
`command.downgrade(..., 'base')` y `command.upgrade(..., 'head')` contra PostgreSQL
real. La identidad del destino se comprobó antes de modificarlo: base aislada,
cuenta de aplicación, puerto 5432 y esquema public. El destino estaba vacío.

El primer upgrade y sus comprobaciones compartieron una transacción. Los datos
sintéticos y concesiones temporales de auditoría se revirtieron con SAVEPOINT
antes de confirmar el esquema. Se comprobó después el downgrade y un nuevo
upgrade confirmado. No se cambió el archivo `.env` ni la URL permanente de esart_db.

Se probaron las 18 restricciones CHECK con entradas inválidas, duplicados de
unidad/hoja/usuario sin distinguir mayúsculas/hash de archivo rechazado, FK de
sesiones, privilegios INSERT/SELECT de auditoría y bloqueo UPDATE/DELETE/TRUNCATE.
Se verificaron los 19 triggers de fecha y su función mediante un UPDATE real.
También se probaron los cuatro permisos CRUD del rol, la excepción individual
que deniega, la excepción READ que sustituye la fila completa, el usuario inactivo
y los códigos de permisos API. Las 51 pruebas unitarias volvieron a pasar.

Una consulta final READ ONLY confirmó el estado, recogido en
[`evidencias/hu03_postgresql.json`](evidencias/hu03_postgresql.json):

- PostgreSQL **18.7**, base `esart_hu03_pruebas`, usuario `esart_aplicacion`.
- Revisión **0001**; **22 tablas de negocio** más `alembic_version`.
- **22 PK, 28 FK, 18 CHECK y 11 UNIQUE**.
- **37 índices explícitos**, **70 índices físicos** contando PK y UNIQUE.
- **Dos funciones y 21 triggers** (19 de fechas y dos de auditoría).
- **Cero filas en las 22 tablas**; no quedan datos sintéticos.

El ejecutor exige destino inicialmente vacío y abortará si se vuelve a invocar
ahora, porque ya quedó instalado. No borra ni recrea automáticamente el esquema
para repetir las pruebas. Cualquier nueva prueba destructiva debe mantener el
destino aislado y comprobar primero su estado y contenido.

La inspección de origen confirmó `esart_db`, `esart_aplicacion`, puerto 5432,
esquema activo public y search_path `"$user", public`. Allí hay **42 tablas**:
38 en `esart` y cuatro en `esart_ref`, sin revisión Alembic en el inventario.
No se aplicó `0001` sobre esa base ni se duplicaron sus usuarios o roles. Su futura
instalación requiere un plan aprobado de conciliación con el esquema existente.

## Criterios de aceptación y continuación

| Criterio | Estado |
|---|---|
| Upgrade crea núcleo, cargos y CRUD | **Cumple**, 22 tablas verificadas en PostgreSQL aislado |
| Downgrade base correcto | **Cumple**, elimina objetos propios sin errores |
| CHECK, UNIQUE, FK e índices | **Cumple**, reflejados y comparados; casos inválidos rechazados |
| Modelos coinciden con revisión | **Cumple**, comparación estática y PostgreSQL sin diferencias |
| Identificador inicial 0001 | Verificado mediante heads/history |
| Función/triggers fecha_actualizacion | **Cumple**, 19 triggers presentes y actualización real verificada |
| Reproducibilidad upgrade/downgrade/upgrade | **Cumple**, ciclo completo ejecutado |

No quedan bloqueos para la validación aislada de HU-03. Ruff global mantiene
I001 preexistente en generar_hash.py; la revisión específica de HU-03 pasa. La
instalación sobre esart_db sigue pendiente de conciliación expresa y no se
certifica que la base principal tenga el esquema contractual 0001.

Para HU-04: tras aceptar esta validación aislada, preparar
roles ADMINISTRADOR/USUARIO, códigos API, componentes y asignaciones aprobadas.
Los requisitos oficiales y el catálogo de grados siguen pendientes de la Escuela.
El login posterior deberá aportar identidad confiable a la dependencia, proteger
las rutas en FastAPI y utilizar las tablas ya migradas. No se implementaron JWT,
sesiones de autenticación ni inserción automática de administrador en esta historia.

## Archivos de esta implementación

- `.gitignore`: entornos locales Python 3.11.
- `aplicacion/base_datos/configuracion.py`: configuración de conexión aislada de autenticación.
- `aplicacion/configuracion.py`: reutilización del validador URL, conservando controles API.
- `aplicacion/modelos/nucleo.py` y `__init__.py`: 22 modelos y registro.
- `aplicacion/seguridad/permisos.py`: consultas y dependencia FastAPI.
- `migraciones/env.py` y `versions/0001_nucleo_inicial.py`: entorno async y revisión.
- `herramientas/inspeccionar_base_datos.py` y `verificar_hu03.py`: inspección y pruebas aisladas.
- `pruebas/test_migraciones.py`, `test_modelos_hu03.py`, `test_permisos_hu03.py`,
  `test_configuracion_conexion.py`: validaciones sin conexión.
- `README.md` e `INFORME_HU_03.md`: uso, decisiones y evidencias.
- `evidencias/hu03_postgresql.json`: estado final consultado en modo de solo lectura.

Se conservaron los cambios previos del repositorio. No se modificaron frontend,
Stitch, SQL de referencia, herramientas de hash ni contratos. No se crearon commits.
