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
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-desarrollo.txt
```

En producción se instala solo `requirements.txt`.

### 3. Variables de entorno

El `.env` vive en la **raíz del repositorio** (no dentro de `backend/`):

```powershell
Copy-Item ..\.env.ejemplo ..\.env
```

Edite `.env` y reemplace **todos** los valores de ejemplo. La aplicación se niega a arrancar si
encuentra un valor de ejemplo, una clave JWT corta o una contraseña en texto plano.

Clave del JWT:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Hash de la contraseña del administrador (la contraseña se escribe sin mostrarse):

```powershell
python -c "import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass('Contrasena: ').encode(), bcrypt.gensalt(12)).decode())"
```

Pegue el hash entre comillas simples: `ADMIN_HASH_CONTRASENA='$2b$12$...'`.

### 4. Arrancar (desde `backend/`)

```powershell
uvicorn aplicacion.principal:aplicacion --reload --port 8081
```

- Salud: <http://127.0.0.1:8081/api/salud> → `{"estado": "ok", "base_datos": "ok"}`
- Documentación de la API (solo fuera de producción): <http://127.0.0.1:8081/api/documentacion>

### 5. Pruebas y revisión de estilo (desde `backend/`)

```powershell
pytest
ruff check .
```

Las pruebas no usan el `.env` ni una base de datos real.

## Reglas propias del backend

- Las sesiones de BD se obtienen siempre con `obtener_sesion_base_datos()`; la configuración con
  `obtener_configuracion()`; los errores de negocio se lanzan con `ErrorAplicacion`.
- Las rutas no contienen lógica de negocio: llaman a `servicios/`.
- Todas las rutas de la API van bajo `/api`.
