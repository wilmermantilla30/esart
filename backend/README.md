# Backend de ESART (FastAPI)

API de verificación de habilitación de artilleros. Python 3.11 · FastAPI · SQLAlchemy 2 (async) +
asyncpg · Alembic · PostgreSQL. Sin Docker.

## Estructura

```
backend/
├── aplicacion/
│   ├── principal.py        # Punto de entrada: crea la aplicación FastAPI
│   ├── configuracion.py    # Lee y valida el .env de la raíz (no arranca si es inseguro)
│   ├── nucleo/             # Transversal: logs con filtro de datos sensibles, errores únicos
│   ├── base_datos/         # Motor async, sesiones y clase base de los modelos
│   ├── modelos/            # Modelos SQLAlchemy (tablas)
│   ├── esquemas/           # Esquemas Pydantic (entrada/salida de la API)
│   ├── servicios/          # Lógica de negocio reutilizable (habilitación, importación, auditoría)
│   ├── seguridad/          # bcrypt, JWT, sesiones, captcha, permisos
│   └── rutas/              # Endpoints; solo reciben, llaman a servicios y responden
├── migraciones/            # Migraciones de Alembic (historia HU-03)
├── datos_iniciales/        # Catálogos y datos semilla (historia HU-04)
├── pruebas/                # Pruebas automáticas (pytest)
├── pyproject.toml          # Configuración de pytest y ruff
├── requirements.txt        # Dependencias de producción (ASCII puro)
└── requirements-desarrollo.txt
```

## Instalación local (Windows)

**Requisitos:** Python 3.11 y PostgreSQL 13 o superior.

### 1. Base de datos

En `psql` (o pgAdmin), como superusuario:

```sql
CREATE USER esart_aplicacion WITH PASSWORD 'una-contrasena-segura';
CREATE DATABASE esart_db OWNER esart_aplicacion;
```

La aplicación **nunca** se conecta con el superusuario `postgres`.

### 2. Entorno de Python (desde la carpeta `backend/`)

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install -r requirements-desarrollo.txt
```

En producción se instala solo `requirements.txt`.

### 3. Variables de entorno

El `.env` vive en la **raíz del repositorio** (no dentro de `backend/`):

Si ya existe, consérvelo. La plantilla `.env.ejemplo` no viene versionada; cree
el archivo raíz `.env` con estas variables y valores propios:

```dotenv
ENTORNO=desarrollo
URL_BASE_DATOS='postgresql+asyncpg://esart_aplicacion:REEMPLAZAR@127.0.0.1:5432/esart_db'
JWT_CLAVE_SECRETA='REEMPLAZAR'
ADMIN_USUARIO='REEMPLAZAR'
ADMIN_HASH_CONTRASENA='REEMPLAZAR'
COOKIE_SEGURA=false
```

Codifique los caracteres reservados de la contraseña en la URL (por ejemplo,
`@` como `%40`). `COOKIE_SEGURA=false` es solo para desarrollo local por HTTP.

Edite `.env` y reemplace **todos** los valores de ejemplo. La aplicación se niega a arrancar si
encuentra un valor de ejemplo, una clave JWT corta o una contraseña en texto plano.

Clave del JWT:

```powershell
.\.venv311\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Hash de la contraseña del administrador (la contraseña se escribe sin mostrarse):

```powershell
.\.venv311\Scripts\python.exe -c "import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass('Contrasena: ').encode(), bcrypt.gensalt(12)).decode())"
```

Pegue el hash entre comillas simples: `ADMIN_HASH_CONTRASENA='$2b$12$...'`.
La contraseña debe tener como máximo 72 bytes UTF-8 (bcrypt 5 rechaza entradas
más largas). Estas variables no crean un administrador en esta fase.

### 4. Arrancar (desde `backend/`)

```powershell
.\.venv311\Scripts\python.exe -m uvicorn aplicacion.principal:aplicacion --reload --host 127.0.0.1 --port 8081
```

- Salud: <http://127.0.0.1:8081/api/salud> → `{"estado": "ok", "base_datos": "ok"}`
- Documentación de la API (solo fuera de producción): <http://127.0.0.1:8081/api/documentacion>

### 5. Pruebas y revisión de estilo (desde `backend/`)

```powershell
.\.venv311\Scripts\python.exe -m pytest
.\.venv311\Scripts\python.exe -m ruff check .
```

Las pruebas no usan el `.env` ni una base de datos real.

## Alembic y validación inicial

Desde `backend/`, con el entorno configurado:

```powershell
.\.venv311\Scripts\python.exe -m alembic heads
.\.venv311\Scripts\python.exe -m alembic history
.\.venv311\Scripts\python.exe -m alembic current
```

`current` necesita conexión real; los otros dos inspeccionan los archivos locales.
La revisión inicial es `0001`: 22 tablas (19 del núcleo y tres de permisos CRUD),
28 FK, 18 CHECK y 37 índices explícitos. Los modelos se registran mediante
`modelos/__init__.py`. La revisión no inserta usuarios ni catálogos.

Alembic y las herramientas usan `ConfiguracionConexion`, con la misma validación
de URL que la API, sin necesitar JWT ni administrador. La API conserva todas las
validaciones de seguridad. Si el `.env` está en `backend/`, desde esa carpeta:

```powershell
.\.venv311\Scripts\python.exe -m alembic -x archivo_env=.env current
.\.venv311\Scripts\python.exe -m alembic -x archivo_env=.env upgrade head --sql
```

El segundo comando genera SQL sin ejecutarlo. Antes de aplicar una migración real,
inspeccione tablas y esquemas. `0001` aborta si encuentra tablas existentes; no
ejecute `stamp` ni elimine objetos para forzarla. No se aplicó a `esart_db` durante
esta implementación. Alembic bloquea autogeneración con metadatos vacíos.

### Inspección HU-03 sin modificar PostgreSQL

La herramienta siguiente valida la configuración existente y consulta identidad,
puerto, esquema, tablas y revisiones Alembic en una transacción `READ ONLY`.
No muestra credenciales ni consulta filas de negocio:

```powershell
.\.venv311\Scripts\python.exe -m herramientas.inspeccionar_base_datos
```

Si el archivo está en `backend/.env`, selecciónelo explícitamente desde `backend/`:

```powershell
.\.venv311\Scripts\python.exe -m herramientas.inspeccionar_base_datos --archivo-env .env
```

La API sigue leyendo el `.env` raíz; las selecciones explícitas anteriores no
mueven ni modifican archivos. Un fallo de validación o conexión no demuestra que
PostgreSQL esté vacío. No ejecute `upgrade` sobre tablas existentes ni `downgrade`
sobre la base principal.

### Prueba real en base aislada

La estructura y la base `esart_hu03_pruebas` fueron autorizadas para HU-03.
El siguiente comando usa la conexión del archivo indicado, consulta la base origen
en modo de solo lectura y dirige todas las migraciones y datos sintéticos a la
base aislada. `--crear-base` permite crearla si no existe y la cuenta tiene CREATEDB:

```powershell
.\.venv311\Scripts\python.exe -m herramientas.verificar_hu03 --archivo-env .env --crear-base
```

Requiere una base de pruebas inicialmente vacía; aborta si encuentra tablas y no
las elimina automáticamente. Ejecuta upgrade, comparación del esquema con el ORM,
restricciones, triggers, permisos, downgrade y nuevo upgrade. Los datos sintéticos
se revierten; al completar deja solo el esquema en `0001`. Downgrade está limitado
a `esart_hu03_pruebas`, también en el SQL offline generado.

El ejecutor pasa una conexión async de pruebas explícita a Alembic, sin modificar
URL_BASE_DATOS ni depender de cambiar el `.env` principal. El ciclo real
upgrade → validaciones → downgrade → upgrade pasó en PostgreSQL 18.7; la base
aislada quedó en `0001`, con 22 tablas y sin datos de prueba. El ejecutor abortará
si se repite ahora porque el destino ya no está vacío; no elimina el esquema
automáticamente. `esart_db` conserva sus 42 tablas existentes y requiere una
conciliación aprobada antes de instalar `0001`. Evidencias completas:
[INFORME_HU_03.md](INFORME_HU_03.md) y
[estado final PostgreSQL](evidencias/hu03_postgresql.json).

### Permisos en FastAPI

`aplicacion.seguridad.permisos` ofrece `OperacionCRUD`, consultas async de permisos
y `requerir_permiso_componente(componente, operacion, obtener_identidad,
codigo_permiso=...)`. El proveedor de identidad debe devolver un UUID autenticado
por el servidor. Una futura ruta puede usar el resultado como dependencia con
`Depends`; la dependencia deniega con 403/SIN_PERMISO si falta acceso/operación y,
si se especifica, el código API. No recibe la identidad desde Angular ni implementa
login. Las excepciones por usuario sustituyen la fila del rol completa; usuarios
y componentes inactivos no reciben acceso. No hay bypass por ser administrador.

Informe de la fase 01: [INFORME_FASE_01.md](INFORME_FASE_01.md).

## Reglas propias del backend

- Las sesiones de BD se obtienen siempre con `obtener_sesion_base_datos()`; la configuración con
  `obtener_configuracion()`; los errores de negocio se lanzan con `ErrorAplicacion`.
- Las rutas no contienen lógica de negocio: llaman a `servicios/`.
- Todas las rutas de la API van bajo `/api`.
