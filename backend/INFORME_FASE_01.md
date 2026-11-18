# ESART — Validación del backend, fase 01

Fecha: 14 de noviembre de 2026.

**Resultado: preparación realizada; criterio de finalización pendiente por entorno
y configuración. No se verificó una conexión real ni un HTTP 200 contra PostgreSQL.**

## 1. Python

- El entorno existente `backend/.venv` ejecuta Python **3.12.10**, no 3.11.
- `py -0p` informa que no encuentra instalaciones. El `python` del PATH apunta
  a una carpeta Python315; no debe usarse implícitamente para este proyecto.
- No se eliminó ni reemplazó el entorno existente. Debe instalarse Python 3.11
  y crear un entorno independiente `.venv311` para completar la validación.

## 2. Dependencias

Todas las dependencias directas instaladas coinciden con los archivos de requisitos:
FastAPI 0.115.6, Uvicorn 0.34.0, SQLAlchemy 2.0.36, asyncpg 0.30.0,
Alembic 1.14.0, Pydantic 2.10.4, pydantic-settings 2.7.1, bcrypt 5.0.0,
PyJWT 2.10.1, python-multipart 0.0.20 y openpyxl 3.1.5.

Sus metadatos de Python admiten 3.11; esto no sustituye la ejecución pendiente
en esa versión. `pip check`: sin dependencias rotas en el entorno disponible.
Se conservan los pins. No se utiliza passlib; bcrypt se consume directamente.

Inicialmente faltaban pytest, httpx y Ruff. Se instalaron las versiones fijadas
en `requirements-desarrollo.txt` dentro de `.venv`, sin instalación global.
El primer intento fue bloqueado por la red del sandbox; la instalación con
permiso de red terminó correctamente.

## 3. Configuración y secretos

- No existe `.env` en la raíz. Tampoco está disponible `.env.ejemplo`.
- La carga real identifica cuatro campos obligatorios ausentes:
  `URL_BASE_DATOS`, `JWT_CLAVE_SECRETA`, `ADMIN_USUARIO`, `ADMIN_HASH_CONTRASENA`.
- `obtener_configuracion()` centraliza y cachea la configuración; el archivo se
  resuelve respecto del código, sin depender del directorio actual.
- JWT exige al menos 32 caracteres y rechaza marcadores de ejemplo. No se
  verificó la aleatoriedad de una clave real porque no fue proporcionada.
- Se usan `SecretStr`, filtro de logs y SQLAlchemy con `echo=False` y
  `hide_parameters=True`. Los errores de salud registran solo el tipo de excepción.
- Se agregó `hide_input_in_errors=True` para no mostrar entradas en el texto
  de errores de Pydantic. No deben registrarse manualmente `ValidationError.errors()`
  con sus entradas, ni secretos sin un nombre identificable.
- `.gitignore` excluye `.env` y `.env.*`; `git check-ignore .env` lo confirma y
  `git ls-files .env` no devuelve un archivo versionado.
- No se encontraron credenciales reales escritas directamente en el código
  inspeccionado. Los valores de pruebas son ficticios.

## 4. PostgreSQL

El servicio Windows `postgresql-x64-18` aparece en ejecución. Eso no prueba que
existan `esart_db`, `esart_aplicacion`, permisos correctos o tablas de ESART.
Sin la URL real no se intentó autenticar con cuentas alternativas.

El motor existente utiliza SQLAlchemy 2 async y asyncpg, con pool, tiempos de
espera, pre-ping y cierre en el ciclo de vida. La ruta usa
`obtener_sesion_base_datos()`. Se agregó validación de la estructura de URL,
rechazo del usuario `postgres` y exigencia de `esart_aplicacion`/`esart_db` fuera
del entorno de pruebas. No se modificaron datos, roles ni permisos.

## 5. Alembic, modelos y esquema

Antes de la revisión, `migraciones/` solo tenía `.gitkeep`; faltaban `alembic.ini`,
`env.py`, plantilla y directorio de revisiones. Se prepararon con conexión
asíncrona, URL desde `obtener_configuracion()`, `NullPool`, metadatos compartidos
y comparación de esquemas y tipos. No se guardan credenciales en el INI.

`modelos/` solo contiene su documentación; `BaseModelo.metadata` no tiene tablas.
Por tanto, no hay relaciones ORM ni esquemas de tablas implementados que validar.
Los documentos `docs/contrato_esquema_bd.md` y `docs/esquema_referencia.sql`
son referencias de diseño, no evidencia de tablas desplegadas.

`alembic heads` y `alembic history` terminan correctamente sin revisiones locales.
La prueba offline carga `env.py` y genera SQL únicamente en memoria, sin crear
tablas. Se bloquea `--autogenerate` con metadatos vacíos para evitar propuestas
de eliminación de tablas existentes.

**Estado de la base desconocido:** no se sabe si está vacía, si contiene tablas
o si tiene una revisión aplicada. No se ejecutó `alembic current` sin credenciales.
No se aplicaron revisiones, seeds, `stamp`, downgrade ni SQL destructivo.

## 6. FastAPI y estructura

El punto de entrada es `aplicacion.principal:aplicacion` desde `backend/`.
La configuración se valida al importar; sin las variables obligatorias el
arranque real queda bloqueado de forma prevista.

`GET /api/salud` ejecuta `SELECT 1`: devuelve 200 con
`{"estado":"ok","base_datos":"ok"}` o 503 con
`{"estado":"degradado","base_datos":"error"}`, sin detalles técnicos.
Las rutas y la documentación están bajo `/api`; la documentación se desactiva
en producción. La separación de capas se conserva. `esquemas/`, `servicios/`,
`seguridad/` y `datos_iniciales/` son todavía estructuras de preparación.

## 7. Errores y comprobaciones

Ejecutados desde `backend/` usando explícitamente el intérprete de `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff check migraciones/env.py --no-force-exclude
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history
```

Resultado final: **31 pruebas aprobadas**, ambos controles Ruff aprobados,
sin conflictos de dependencias. Las pruebas de salud usan sesiones simuladas;
no certifican PostgreSQL ni un servidor Uvicorn real. La suite se ejecutó en
Python 3.12.10. Durante el cambio, una prueba existente detectó que la nueva
validación de URL precedía a la validación de cookie: se corrigió el orden de
validación y se conservó la prueba original.

## 8. Correcciones realizadas

- Validación de URL, cuenta y base de ejecución; ocultación de entradas inválidas.
- Preparación de Alembic y protección frente a autogeneración sin modelos.
- Pruebas nuevas para configuración y carga offline de Alembic.
- README con intérprete explícito, entorno 3.11 independiente y configuración
  manual porque la plantilla mencionada no está disponible.
- Corrección del directorio de arranque en la documentación de `principal.py`.

No se cambió la arquitectura, el frontend, los pins ni datos existentes; no se
crearon tablas ni usuarios. Las variables del administrador siguen siendo un
requisito existente de configuración, pero no crean ninguna cuenta en esta fase.

## 9. Comandos para completar la validación e iniciar

Tras instalar Python 3.11, desde la raíz del repositorio:

```powershell
Set-Location D:\2026\esart\esart\esart\backend
py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe --version
.\.venv311\Scripts\python.exe -m pip install -r requirements-desarrollo.txt
```

Crear el `.env` raíz con valores propios según el README. No copiar marcadores
de ejemplo como credenciales y no sobrescribir un `.env` existente.
No es necesario activar el entorno ni cambiar la política de ejecución de PowerShell.

```powershell
.\.venv311\Scripts\python.exe -m pip check
.\.venv311\Scripts\python.exe -m pytest
.\.venv311\Scripts\python.exe -m ruff check .
.\.venv311\Scripts\python.exe -m alembic current
.\.venv311\Scripts\python.exe -m uvicorn aplicacion.principal:aplicacion --reload --host 127.0.0.1 --port 8081
```

En otra consola:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8081/api/salud -Method Get
```

Se requiere HTTP 200 y ambos estados `ok` para certificar la conexión real.
No ejecutar `upgrade head` antes de revisar el inventario y una migración concreta.

## 10. Siguiente fase

Primero completar los dos bloqueos y repetir las comprobaciones con Python 3.11.
Conectar como `esart_aplicacion` y consultar en una transacción de solo lectura:

```sql
BEGIN READ ONLY;
SELECT current_database(), current_user;
SELECT rolsuper FROM pg_roles WHERE rolname = current_user;
SELECT nspname FROM pg_namespace
WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema';
SELECT schemaname, tablename FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
COMMIT;
```

Contrastar el inventario con `alembic current` antes de diseñar la migración
inicial. Acordar los puntos abiertos del contrato de esquema, implementar e
importar los modelos en su paquete, revisar las FK y esquemas, y revisar el SQL
de cada migración antes de aplicarla. Si hay tablas preexistentes, diseñar su
conciliación explícita para evitar duplicados y pérdida de datos.
