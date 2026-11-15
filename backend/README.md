# Backend ESART

Python **3.12**, FastAPI, SQLAlchemy 2 async, asyncpg, Alembic y PostgreSQL 18, sin Docker. La configuración efectiva es **backend/.env**; la base operativa es exclusivamente esart_db, usuario esart_aplicacion.

El [README principal](../README.md) contiene instalación, variables y pruebas. La [guía PostgreSQL](../docs/ESART_INSTALACION_BASE_DATOS.md) distingue instalación existente, base vacía y población; **la instalación desde cero aún no está disponible**. No ejecutar automáticamente upgrade/stamp ni los cargadores heredados.

Desde backend, con .venv 3.12 y configuración válida:

```powershell
.venv/Scripts/python.exe -m herramientas.verificar_persistencia_principal
.venv/Scripts/python.exe -m uvicorn aplicacion.principal:aplicacion --reload --host 127.0.0.1 --port 8081
.venv/Scripts/python.exe -m pytest -o addopts='' -q
.venv/Scripts/python.exe -m ruff check .
```

## Organización

- aplicacion/principal.py registra salud y catálogos; prefijo /api.
- aplicacion/configuracion.py valida secretos; base_datos/configuracion.py permite diagnóstico sin JWT.
- base_datos/sesion.py centraliza motor y sesiones asíncronas; no crear motores en rutas.
- modelos/persistencia.py representa tablas reales; modelos/historico conserva el contrato UUID anterior.
- seguridad/permisos.py consulta la malla CRUD y excepciones; falta proveedor de identidad/login operativo.
- rutas/unidades.py implementa consultas de catálogos; servicios y esquemas de negocio están pendientes.
- migraciones_principal se selecciona mediante alembic.ini; migraciones históricas mediante alembic_historico.ini.
- seeds contiene referencias/evidencias históricas, no un instalador de la principal. Ver [inventario](../docs/HU04_INVENTARIO_SCRIPTS.md).

El estado y los bloqueos actuales están en [ESART_ESTADO_DESARROLLO.md](../docs/ESART_ESTADO_DESARROLLO.md). Los contratos describen también funciones futuras: no confundir una ruta diseñada con implementada. Mantener español descriptivo, requirements ASCII, bcrypt directo y secretos fuera de logs/Git. No crear administradores con contraseñas predeterminadas.
