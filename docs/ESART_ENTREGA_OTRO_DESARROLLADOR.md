# Recepción del proyecto desde GitHub

## Qué se entrega

Código Python/FastAPI y Angular, modelos del esquema real, referencias institucionales, dos historiales Alembic separados y documentación de HU-04. El clon no incluye PostgreSQL, datos operativos, secretos ni respaldos privados. La entrega no equivale a un instalador desde cero ni a despliegue certificado.

Leer primero [README](../README.md), [estado](ESART_ESTADO_DESARROLLO.md), [instalación de base](ESART_INSTALACION_BASE_DATOS.md) e [inventario de scripts](HU04_INVENTARIO_SCRIPTS.md). No ejecutar los scripts heredados para intentar llenar una interfaz vacía.

## Descargar la rama correcta

La rama local revisada es HU-04-poblacion_data. Las instrucciones siguientes **solo funcionan después de que el equipo publique la rama**. Esta tarea no hace commit, push ni verifica publicación remota.

Con un repositorio ya clonado:

```powershell
git fetch origin
git switch --track origin/HU-04-poblacion_data
git branch --show-current
git status --short
```

Si ya existe una rama local, usar `git switch HU-04-poblacion_data`, sin reemplazar cambios locales. Para el primer clon, obtener la URL autorizada del equipo:

```powershell
git clone <URL-autorizada-del-repositorio> esart
Set-Location esart
git fetch origin
git switch --track origin/HU-04-poblacion_data
```

No se inventa una URL de GitHub ni se presupone que el remoto exista. Si la rama remota no aparece, pedir que el responsable termine la publicación; no cambiar a otra rama como alternativa silenciosa.

## Preparar herramientas

Instalar Python 3.12, PostgreSQL 18 y herramientas cliente. En el entorno original se comprobó Python 3.12.10, Node 26.13.1 y npm 11.20.0. Angular 22/TypeScript 6 están definidos en package.json/lockfile; verificar compatibilidad local, no usar una versión global de Angular diferente como sustituto del proyecto.

Desde la raíz:

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-desarrollo.txt
Set-Location frontend/esart
npm ci
Set-Location ../..
```

Los entornos y node_modules se recrean; no copiarlos de otra máquina ni publicarlos. No ejecutar Python scripts heredados como parte de pip ni npm.

## Configuración y datos equivalentes

Conservar `backend/.env` si existe; si falta, copiar `backend/env.ejemplo` y completar sus valores localmente. El README enumera variables y validaciones. URL_BASE_DATOS debe apuntar a esart_db con esart_aplicacion; nunca usar la cuenta administrativa como usuario permanente del backend. No enviar contraseñas/JWT por chat ni guardarlas en Git. No cambiar la base para superar errores de conexión.

Obtener del propietario acceso a una instalación existente equivalente o un respaldo autorizado por un canal privado. **INSTALACIÓN DESDE CERO NO DISPONIBLE TODAVÍA.** p0001_real adopta estructura; no genera las tablas que faltan. Antes de una restauración nueva se necesita un procedimiento aprobado y comprobación del destino; nunca restaurar sobre esart_db con información existente.

Los 40 códigos/unidades, nueve tipos, cinco cargos y catorce cursos tienen referencias reconstruibles en el repositorio. Eso no implica un seed BIGINT integral probado. UUID, identidades, usuarios, hashes, personal, documentos, experiencia y registros académicos no deben copiarse de los JSON de pruebas: proceden de fuentes operativas autorizadas o respaldo. Los 36 permisos y dos roles constan en evidencia histórica, sin certificar el catálogo granular como operativo actual.

## Primera verificación

Desde backend, sin activar flags de integración histórica:

```powershell
.venv/Scripts/python.exe -m herramientas.verificar_persistencia_principal
.venv/Scripts/python.exe -m alembic history --verbose
.venv/Scripts/python.exe -m alembic heads
.venv/Scripts/python.exe -m pytest -o addopts='' -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m compileall -q aplicacion herramientas migraciones_principal
```

El verificador es de lectura, pero sustituye su JSON de evidencia local: guardar el resultado requerido antes de repetir. No forzar una migración si detecta diferencias. Confirmar current_database(), cuatro conteos y FUTOM. El propietario debe comprobar personal y revisión física Alembic si faltan permisos. Para `current -v`, seguir la configuración administrativa efímera descrita en la guía PostgreSQL, sin publicar ESART_MIGRACIONES_URL.

Desde frontend/esart:

```powershell
npm run build
npm test -- --watch=false
```

Luego, con configuración segura y proveedor de identidad funcional, arrancar backend en 8081 y `npm start` en frontend/esart. Abrir /unidades; comprobar las cuarenta filas, filtros, padres, jerarquía, 39 clasificaciones y FUTOM pendiente. No marcar esta validación como aprobada por ver un 401 correctamente manejado.

## No ejecutar durante la recepción

No ejecutar upgrade, downgrade, stamp, autogenerate, ESART_CARGAR_ESART_DB.sql, initial_data.py, cargadores Vulcano, SQL de propuestas ni ejecutores de antiguas bases. No habilitar ESART_SEEDS_INTEGRACION o ESART_FASE3_DDL_APROBADO. No crear otra base ni reemplazar una entidad equivalente en public. No conceder privilegios globales ni desactivar autenticación.

## Revisar antes de publicar o recibir cambios

```powershell
git status --short
git diff --stat
git diff --check
git ls-files backend/.env
git ls-files '*.dump' '*.backup'
git check-ignore backend/.env backend/.venv frontend/esart/node_modules
```

No publicar `.env`, `.env.*`, .venv, node_modules, __pycache__, .pytest_cache, archivos dump/backup, claves/tokens, logs, datos personales ni respaldos reales. `.gitignore` no protege archivos ya versionados ni sustituye la revisión de contenido. El build genera frontend/esart/dist: revisar su exclusión antes de añadir archivos; las reglas antiguas para frontend/dist no implican que esa ruta anidada esté cubierta.

Los JSON de inspección y simulación pueden contener identificadores o fotografías de tablas; revisarlos individualmente. Los scripts heredados contienen destinos y credenciales de ejemplo y comportamiento de administrador de prueba: deben sanearse o excluirse del alcance antes de publicar, sin copiar esos valores a documentación. No asumir que son credenciales actuales, pero tampoco publicarlos sin revisión.

No usar git add . a ciegas: hay artefactos históricos y archivos nuevos que deben seleccionarse. No se hace commit ni push en esta tarea. Una revisión del otro desarrollador, pruebas y criterios funcionales comprobados siguen siendo la definición de terminado.

## Acta mínima de recepción

Registrar commit recibido, rama, versiones, destino/usuario sin contraseña, revisión Alembic consultada realmente, conteos y fecha, resultados de pruebas y bloqueos de autenticación/UI. Confirmar que no hubo escrituras inesperadas y señalar expresamente si faltó acceso para comprobar alguna condición. Mantener la matriz de seguimiento al día; no declarar completo lo que solo está implementado o simulado.
