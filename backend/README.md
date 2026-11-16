# Backend ESART

Python **3.12**, FastAPI, SQLAlchemy 2 async, asyncpg, Alembic y PostgreSQL 18, sin Docker. La configuración efectiva es **backend/.env**; la base operativa es exclusivamente esart_db, usuario esart_aplicacion.

El [README principal](../README.md) contiene instalación, variables y pruebas. La [guía PostgreSQL](../docs/ESART_INSTALACION_BASE_DATOS.md) distingue instalación existente, base vacía y población; La instalación desde cero ya está disponible con Alembic (ver abajo). No ejecutar stamp ni los cargadores heredados.

Desde backend, con .venv 3.12 y configuración válida:

```powershell
.venv/Scripts/python.exe -m herramientas.verificar_persistencia_principal
.venv/Scripts/python.exe -m uvicorn aplicacion.principal:aplicacion --reload --host 127.0.0.1 --port 8081
.venv/Scripts/python.exe -m pytest -o addopts='' -q
.venv/Scripts/python.exe -m ruff check .
```

## Organización

- aplicacion/principal.py registra salud, autenticación y catálogos; prefijo /api. Al arrancar crea el administrador del .env si no existe.
- aplicacion/configuracion.py valida secretos; base_datos/configuracion.py permite diagnóstico sin JWT.
- base_datos/sesion.py centraliza motor y sesiones asíncronas; no crear motores en rutas.
- modelos/persistencia.py representa tablas reales; modelos/historico conserva el contrato UUID anterior.
- seguridad/: contrasenas.py (bcrypt), tokens.py (JWT), sesion_http.py (cookies, CSRF y `obtener_usuario_actual`), permisos.py (malla CRUD).
- servicios/autenticacion.py: login, sesión vigente (30 min de inactividad), cierre y administrador inicial.
- modelos/seguridad.py: sesiones_usuario e intentos_inicio_sesion (revisión p0002).
- rutas/autenticacion.py: POST /api/auth/login, GET /api/auth/yo, POST /api/auth/cerrar-sesion.
- rutas/unidades.py implementa consultas de catálogos; exigen sesión válida.
- migraciones_principal se selecciona mediante alembic.ini; migraciones históricas mediante alembic_historico.ini.
- seeds contiene referencias/evidencias históricas, no un instalador de la principal. Ver [inventario](../docs/HU04_INVENTARIO_SCRIPTS.md).

El estado y los bloqueos actuales están en [ESART_ESTADO_DESARROLLO.md](../docs/ESART_ESTADO_DESARROLLO.md). Los contratos describen también funciones futuras: no confundir una ruta diseñada con implementada. Mantener español descriptivo, requirements ASCII, bcrypt directo y secretos fuera de logs/Git. No crear administradores con contraseñas predeterminadas.

## Alembic (migraciones_principal)

Cadena: `p0000_instalacion_inicial` → `p0001_real` → `p0002_seguridad_sesiones`.

| Revisión | Qué hace |
|---|---|
| p0000 | Base vacía: crea las 43 tablas de HU-04 desde `estructura_p0000.sql` (congelado, 0 diferencias con `estructura_p0001.json`). Base existente: no hace nada |
| p0001_real | Valida que la estructura coincida con la fotografía real |
| p0002 | Sesiones, intentos de inicio de sesión, campos de bloqueo y permisos de `esart_aplicacion` |

Las bases que ya estaban en `p0001_real` solo aplican `p0002`. La URL de migraciones se pasa por
`ESART_MIGRACIONES_URL` (no se lee del .env), sin dejarla en el historial:

```powershell
$conexionProtegida = Read-Host 'URL asyncpg de esart_db para migrar' -AsSecureString
try {
    $env:ESART_MIGRACIONES_URL = [System.Net.NetworkCredential]::new('', $conexionProtegida).Password
    .venv/Scripts/python.exe -m alembic upgrade head
    .venv/Scripts/python.exe -m alembic current
} finally {
    Remove-Item Env:ESART_MIGRACIONES_URL -ErrorAction SilentlyContinue
}
```

## Pruebas con PostgreSQL

Las pruebas del login (`pruebas/test_login_hu05.py`) usan la base real si se define
`ESART_URL_BD_INTEGRACION` (base con la migración p0002). Todo se revierte al final.
Sin la variable, esas pruebas se omiten.

## Datos simulados (solo desarrollo)

Mientras llega la importación por Excel, hay 10 militares de prueba que cubren cada caso de la
regla APTO / NO APTO (cédulas `99000000xx`, unidades `SIM-…`). No corre en producción.

```powershell
.venv/Scripts/python.exe -m herramientas.cargar_datos_simulados cargar
.venv/Scripts/python.exe -m herramientas.cargar_datos_simulados borrar
```

Los tipos de curso se cargan del seed oficial (`seed_catalogos_academicos.sql`) y no se borran.
