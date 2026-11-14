# ESART — Verificación de habilitación de artilleros

Herramienta para que el Comandante de la Escuela de Artillería verifique en tiempo real si un
artillero está **APTO** o **NO APTO**, y por qué.

Se construye aparte de Vulcano 3.0 y se integrará cuando Vulcano salga a producción. El esquema
y la estructura de carpetas siguen la organización de Vulcano para que la integración consista en
mover archivos, no en reescribirlos.

| Parte | Tecnología | Guía |
|---|---|---|
| **Backend** | Python 3.11 · FastAPI · SQLAlchemy 2 async + asyncpg · Alembic | [backend/README.md](backend/README.md) |
| **Frontend** | Angular (TypeScript) | [frontend/README.md](frontend/README.md) |
| **Base de datos** | PostgreSQL (`esart_db`, independiente de Vulcano) | [docs/contrato_esquema_bd.md](docs/contrato_esquema_bd.md) |

Sin Docker: backend, frontend y PostgreSQL se ejecutan directamente en la máquina.

---

## Estructura del repositorio

```
esart/
├── backend/            # API FastAPI: aplicacion/, migraciones/, datos_iniciales/, pruebas/
├── frontend/           # Proyecto Angular del dashboard
├── docs/               # Contratos (base de datos y API) y backlog del sprint
├── .env                # Variables de entorno (NO va a git; .env.ejemplo tampoco, se comparte entre los devs)
├── .gitignore
└── README.md
```

## Documentos del proyecto

| Documento | Para qué |
|---|---|
| [docs/contrato_esquema_bd.md](docs/contrato_esquema_bd.md) | Tablas, columnas y reglas de la base de datos |
| [docs/esquema_referencia.sql](docs/esquema_referencia.sql) | El mismo esquema en SQL (referencia) |
| [docs/contrato_api.md](docs/contrato_api.md) | Rutas, respuestas y errores entre frontend y backend |
| [docs/backlog_sprint1_esart.xlsx](docs/backlog_sprint1_esart.xlsx) | Historias del sprint y reparto del trabajo |

## Flujo de trabajo local

1. **PostgreSQL** corriendo con la base `esart_db` (ver backend/README.md).
2. **Backend** desde `backend/`: `uvicorn aplicacion.principal:aplicacion --reload` → puerto 8000.
3. **Frontend** desde `frontend/`: `npm start` → puerto 4200, con proxy de `/api` hacia el backend.
4. El navegador abre <http://localhost:4200>.

En producción el frontend se compila (`npm run build`) y FastAPI sirve el resultado: un solo
servidor, una sola URL, sin Node.js en el servidor.

---

## Convenciones obligatorias

1. **Español descriptivo** en variables, funciones, parámetros y comentarios (backend y frontend). Nombres completos, sin abreviaturas oscuras.
2. **Todo el código comentado** en español: qué hace cada bloque y por qué cuando no es obvio.
3. **Reutilizar, no duplicar.** Antes de escribir una función, buscar si ya existe (buscar artillero, validar JWT, consultar la BD, llamar a la API).
4. **`requirements*.txt` en ASCII puro** (pip en Windows usa cp1252). Una prueba lo verifica.
5. **`.env` nunca va a git.**
6. **bcrypt directo**, sin passlib (incompatible con bcrypt 5.x).
7. **Credenciales, contraseñas, tokens y cédulas nunca en logs ni en respuestas de error.**
8. **Errores siempre con el formato único** del contrato de API.
9. **Rutas de la API bajo `/api`.**
10. **Cambios a los contratos** (`docs/contrato_*.md`) por Pull Request, aprobados por ambos desarrolladores.

### Definición de terminado

Código en el repositorio con revisión del otro desarrollador · comentado en español · pruebas
pasando · sin credenciales en logs ni respuestas · criterios de aceptación de la historia verificados.
