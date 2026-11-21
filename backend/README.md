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

## Producción: un solo servidor para el dashboard y la API (HU-21)

FastAPI sirve el Angular compilado en la misma dirección que la API: el Comandante solo abre
`https://<servidor>/`. Rutas de Angular (`/instructores`, `/dashboard`…) devuelven `index.html`;
`/api/...` sigue siendo la API (sus 404 son JSON).

```powershell
# 1. Compilar el front (una vez por despliegue)
Set-Location frontend/esart; npm.cmd ci; npm.cmd run build; Set-Location ../..
# 2. Arrancar (desde backend/), sin --reload en producción
.venv/Scripts/python.exe -m uvicorn aplicacion.principal:aplicacion --host 0.0.0.0 --port 8081
```

- `RUTA_FRONT` (opcional) apunta a otra carpeta del build; por defecto `frontend/esart/dist/esart/browser`.
- Producción exige `ENTORNO=produccion` y `COOKIE_SEGURA=true`, es decir, HTTPS (certificado en el servidor
  o en un proxy delante). Con cookies seguras se envía `Strict-Transport-Security`.
- Cabeceras: CSP estricta en el dashboard (solo scripts propios, sin CDN), `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: same-origin`; `Cache-Control: no-store` en todas las respuestas de datos de la API.
- `--host 0.0.0.0` lo expone a la red: el firewall del servidor solo debe abrir el puerto de ESART.
- Caché del front: archivos con huella (`main-XXXX.js`) un año; `index.html` se revalida siempre.

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

## Administración de usuarios por consola (HU-10)

Lo mismo se hace en la web (Administración > Gestión de usuarios); la consola sirve cuando nadie
puede entrar. Usa la conexión del `.env` y cada acción queda en la auditoría como `consola`, con el
usuario del sistema operativo que la ejecutó.

```powershell
.venv/Scripts/python.exe -m herramientas.administrar_usuarios listar
.venv/Scripts/python.exe -m herramientas.administrar_usuarios crear --usuario jperez.esart --rol USUARIO --cedula 1234567890
.venv/Scripts/python.exe -m herramientas.administrar_usuarios desbloquear --usuario jperez.esart
.venv/Scripts/python.exe -m herramientas.administrar_usuarios desbloquear-ip --ip 10.1.2.3
```

- `crear` pide la contraseña **oculta** dos veces (mínimo 10 caracteres, letras y números) y
  nunca la acepta como argumento. Con rol `ADMINISTRADOR` pide confirmación.
- `--cedula` es **obligatoria**: el militar debe existir y estar activo en `personal_militar`.
- La contraseña es **temporal**: el usuario debe cambiarla la primera vez que entre (migración
  `p0009_gestion_usuarios`: permisos de la API sobre esas columnas y acciones de auditoría nuevas).
- `desbloquear` pone en cero los intentos y quita el bloqueo de 3 horas; `desbloquear-ip` pone en
  cero el contador de una IP.

## Malla curricular (S2-01)

Carga inicial de las mallas desde el Excel revisado por la Escuela (formato de
`docs/backlog_sprint2_esart.xlsx`: hojas *Materias* y *Malla por curso*). Usa la conexión del `.env`
y cada malla queda en la auditoría (`MALLA_CURRICULAR_CARGADA`) como `consola`.

```powershell
.venv/Scripts/python.exe -m herramientas.cargar_malla_curricular listar
.venv/Scripts/python.exe -m herramientas.cargar_malla_curricular cargar ..\docs\backlog_sprint2_esart.xlsx --anio 2026
.venv/Scripts/python.exe -m herramientas.cargar_malla_curricular cargar ..\docs\backlog_sprint2_esart.xlsx --anio 2026 --ejecutar
```

- Sin `--ejecutar` solo revisa el archivo y muestra qué cargaría.
- Rechaza el archivo si alguna materia no está "Confirmada" en la hoja *Materias*
  (`--aceptar-pendientes` solo funciona con `ENTORNO=desarrollo`).
- Un tipo de curso que ya tiene malla vigente se omite: los cambios se harán desde Parámetros (S2-09).
- Todo va en una transacción: se cargan todas las mallas o ninguna.
