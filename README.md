# ESART — Habilitación del personal de artillería

ESART organiza formación, capacitación, certificación, experiencia y habilitación del personal de artillería. HU-04 incorporó referencias institucionales y su clasificación; el cálculo integral de aptitud y COOFU todavía no es un servicio operativo.

**Base operativa única: `esart_db`.** `esart` y `esart_ref` son esquemas de esa misma base. No apuntar la aplicación a las antiguas bases de pruebas. Los estados operacionales y logísticos de material pertenecen a VULCANO, fuera del alcance actual de ESART.

## Estado comprobado

Revisión de documentación y consultas de solo lectura: **15 de noviembre de 2026**, rama local `HU-04-poblacion_data`. Esta tarea no hizo commit ni push.

| Componente | Estado real |
|---|---|
| PostgreSQL | 43 tablas de negocio auditadas, más `esart.alembic_version` observada actualmente |
| Catálogos | SQL real como esart_aplicacion: 40 unidades, 9 tipos de unidad, 5 cargos, 14 cursos; 39 clasificadas y FUTOM pendiente |
| Personal | Cero como referencia histórica; no recontado por falta de SELECT |
| Alembic | Único head principal p0001_real; el operador reportó esa revisión aplicada. La cuenta de aplicación no puede leer su tabla de versión |
| Backend | Modelos BIGINT y consultas implementados; falta autenticación funcional y configuración JWT segura para validar HTTP real |
| Angular | Pantalla de unidades, filtros y jerarquía; compila. Falta demostrar visualización con sesión real |
| Instalación nueva | **INSTALACIÓN DESDE CERO NO DISPONIBLE TODAVÍA.** La línea base adopta un esquema existente |

Los conteos son fotografías que deben verificarse nuevamente, no instrucciones para sobrescribir registros. Los contratos y los informes antiguos pueden describir funcionalidades futuras o estados anteriores.

## Requisitos y arquitectura

- Python **3.12**, entorno `backend/.venv`; comprobado localmente con 3.12.10.
- FastAPI 0.115.6, SQLAlchemy async 2.0.36, asyncpg 0.30.0, Alembic 1.14.0: [dependencias fijadas](backend/requirements.txt).
- PostgreSQL **18**, entorno documentado 18.7. Cuenta del backend: `esart_aplicacion`; operador estructural separado.
- Angular 22.2.x, TypeScript 6.0.x y RxJS 7.8.x. Node comprobado 26.13.1 y npm 11.20.0. No hay campo `engines`; usar una versión compatible con el lockfile y comprobar compilación.
- Ejecución local sin Docker. Backend 8081, frontend 4200, proxy relativo `/api`.

```text
backend/
  aplicacion/                  FastAPI, configuración, sesiones, modelos y rutas
    modelos/persistencia.py    Tablas reales, sin DDL al importar
    modelos/historico/         Contrato UUID anterior, separado del operativo
  migraciones_principal/       Línea principal y fotografía estructural p0001
  migraciones/                 Historial UUID 0001/0002
  seeds/                      Seeds y evidencias históricos
  sql/                        Propuestas de distinto alcance; no instalador único
  herramientas/               Diagnóstico, verificación y respaldo
  pruebas/                    Pytest
frontend/esart/                Proyecto Angular ejecutable
docs/                         Contratos, decisiones, evidencias y entrega
```

`principal.py` construye FastAPI y registra salud y catálogos. El motor y las sesiones viven en `base_datos/sesion.py`; las rutas reciben sesiones por dependencia. Los modelos respetan los esquemas y las claves BIGINT; los identificadores JSON se entregan como cadenas para evitar pérdida de precisión en JavaScript. Servicios y esquemas de negocio todavía están incompletos.

## Dependencias y configuración

Desde la raíz, PowerShell:

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-desarrollo.txt
Set-Location frontend/esart
npm ci
Set-Location ../..
```

Si el entorno ya existe, comprobar su versión antes de reutilizarlo. Producción instala `requirements.txt`, pero el despliegue integral sigue pendiente de validación.

El archivo efectivo es **`backend/.env`**, no un `.env` en la raíz. Conservar uno existente. Para preparar uno nuevo:

```powershell
if (-not (Test-Path backend/.env)) {
    Copy-Item backend/env.ejemplo backend/.env
}
```

Editar sus valores localmente; nunca publicar o imprimir su contenido.

| Variable | Uso |
|---|---|
| `URL_BASE_DATOS` | URL asyncpg de esart_aplicacion hacia 127.0.0.1:5432/esart_db; codificar caracteres reservados de la contraseña |
| `ENTORNO`, `NIVEL_REGISTRO` | Entorno y registro |
| `TAMANO_POOL_CONEXIONES`, `SEGUNDOS_ESPERA_CONEXION` | Pool y timeout validados |
| `JWT_CLAVE_SECRETA` | Secreto local fuerte, mínimo 32 caracteres; se rechazan valores de ejemplo |
| `MINUTOS_INACTIVIDAD_SESION`, `COOKIE_SEGURA` | Parámetros contractuales; no prueban que las sesiones estén implementadas. Cookie segura obligatoria en producción |
| `ADMIN_USUARIO`, `ADMIN_HASH_CONTRASENA` | Variables exigidas; hash bcrypt válido, sin contraseña plana. No crean automáticamente un administrador |

La plantilla no permite arrancar con sus valores de ejemplo. El último diagnóstico detectó una clave JWT de ejemplo: reemplazarla localmente mediante un gestor de secretos; nunca usar una clave fija de documentación. El proveedor de identidad aún debe implementarse. TLS solo se desactiva para loopback, sin rebajar automáticamente conexiones remotas.

Antes de crear estructuras o cargar datos, leer la [guía de PostgreSQL](docs/ESART_INSTALACION_BASE_DATOS.md). No usar upgrade o stamp como paso automático de instalación.

## Ejecutar

Desde `backend/`, con configuración local segura e instalación existente compatible:

```powershell
.venv/Scripts/python.exe -m herramientas.verificar_persistencia_principal
.venv/Scripts/python.exe -m uvicorn aplicacion.principal:aplicacion --reload --host 127.0.0.1 --port 8081
```

El verificador solo lee PostgreSQL y guarda evidencia JSON local. `GET /api/salud` ejecuta SELECT 1 y responde 200 o 503; no prueba por sí solo el acceso a catálogos.

En otra terminal, desde `frontend/esart/`:

```powershell
npm start
```

Abrir `http://localhost:4200/unidades`. `UnidadesService` consulta `/api/catalogos/unidades` por `proxy.conf.json`. Se espera 401 sin proveedor de identidad del servidor. No sustituirlo por mocks ni desactivar protección. JWT en cookie HttpOnly y CSRF son el contrato; falta completar su implementación. FastAPI no monta todavía automáticamente el Angular compilado en producción.

## Verificar sin modificar datos

Desde `backend/`:

```powershell
.venv/Scripts/python.exe -m pytest -o addopts='' -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m compileall -q aplicacion herramientas migraciones_principal
.venv/Scripts/python.exe -m alembic history --verbose
.venv/Scripts/python.exe -m alembic heads
```

Desde `frontend/esart/`:

```powershell
npm run build
npm test -- --watch=false
```

No activar las pruebas históricas que escriben en otras bases. Los tests con mocks validan contratos y rechazo de acceso, no una consulta HTTP autenticada real. Resultados en [estado de desarrollo](docs/ESART_ESTADO_DESARROLLO.md).

## Documentación

| Documento | Contenido |
|---|---|
| [HU-04](docs/HU04_POBLACION_DATOS.md) | Fases, fuentes, clasificación e idempotencia |
| [Instalación de PostgreSQL](docs/ESART_INSTALACION_BASE_DATOS.md) | Escenarios, Alembic y SQL de verificación |
| [Inventario de scripts](docs/HU04_INVENTARIO_SCRIPTS.md) | Rutas, destinos, comandos, requisitos y riesgos |
| [Estado de desarrollo](docs/ESART_ESTADO_DESARROLLO.md) | Implementado, probado y pendiente |
| [Entrega a otro desarrollador](docs/ESART_ENTREGA_OTRO_DESARROLLADOR.md) | Clonación, configuración y precauciones de publicación |
| [Contrato API](docs/contrato_api.md) | Incluye rutas todavía no implementadas |
| [Contrato de esquema](docs/contrato_esquema_bd.md) | Diseño que debe contrastarse con la estructura real |
| [Corrección de persistencia](docs/ESART_CORRECCION_INTEGRAL.md) | Auditoría y matriz de modelos en una fotografía anterior |
| [Backlog](docs/backlog_sprint1_esart.xlsx) | Historias y planificación |

## Convenciones

Español descriptivo y comentarios que expliquen propósito y decisiones, reutilización de servicios existentes, rutas bajo `/api`, bcrypt directo sin passlib, requirements en ASCII y errores sin secretos. Cambios de contrato mediante PR y revisión del equipo. Credenciales, tokens y documentos de identidad nunca en logs. Las guías de backend/frontend enlazan a estos procedimientos vigentes.

No publicar `.env`, entornos virtuales, node_modules, cachés, respaldos, claves ni datos sensibles. Revisar también los JSON antes de añadirlos a Git. La rama `HU-04-poblacion_data` debe publicarse antes de que otro desarrollador pueda descargarla; su existencia local no demuestra publicación.

Definición de terminado: revisión por otro desarrollador, pruebas aprobadas, contratos conciliados y criterios funcionales comprobados con el entorno real. Compilar o manejar correctamente un 401 no demuestra integración completa.
