# Contrato de API (backend ↔ front) — ESART

**Versión:** 0.10 (borrador para acordar entre SS.Mantilla y SV.Valbuena)
**Fecha:** 2026-11-14

> **Propósito.** Que el front se construya **en paralelo** al backend. El front programa contra
> este contrato (usando los ejemplos como datos simulados) y el backend se compromete a responder
> exactamente con esta forma. Cualquier cambio se hace por Pull Request a este archivo y lo
> aprueban ambos desarrolladores.

---

## 1. Convenciones generales

| Tema | Convención |
|---|---|
| Origen | Producción: FastAPI sirve el Angular compilado (`frontend/dist/`) → **mismo origen**, sin CORS. Desarrollo: proxy de `ng serve` hacia el backend |
| Rutas de la API | Prefijo `/api` (ej. `/api/auth/login`). Las páginas del dashboard viven fuera de `/api` |
| Formato | JSON UTF-8. Campos en español, `snake_case` |
| Fechas | `"AAAA-MM-DD"` (fechas de negocio); `"AAAA-MM-DDTHH:MM:SSZ"` (instantes, en UTC) |
| Cédula | En las respuestas puede venir **enmascarada** (`"******5678"`) según permisos. El front nunca asume que viene completa |
| Valores de lista | Siempre en MAYÚSCULAS tal como están en la base (`"APTO"`, `"NO_APTO"`, `"ACTIVA"`). El front los traduce a texto visible |

### 1.1 Sesión — ✅ decidido (2026-11-14): JWT dentro de una cookie `httpOnly`

- El login responde con la cookie `esart_sesion` (`HttpOnly`, `SameSite=Strict`, `Path=/`, `Secure` cuando haya HTTPS).
  El JWT (HS256) va **dentro** de la cookie; **no** se devuelve en el cuerpo de la respuesta.
- El JavaScript del front **no puede leer el token** → un ataque XSS no puede robarlo.
- **Protección CSRF (doble cookie, compatible con Angular):** el login entrega además la cookie
  `esart_csrf` (legible por JavaScript, `SameSite=Strict`, sin datos de sesión). En cada petición
  que modifica datos (`POST`, `PUT`, `DELETE`) el front devuelve ese valor en la cabecera
  `X-CSRF-Token`; el backend rechaza la petición si no coinciden. Angular lo hace solo con:
  `provideHttpClient(withXsrfConfiguration({ cookieName: "esart_csrf", headerName: "X-CSRF-Token" }))`.
- El front usa siempre rutas relativas (`/api/...`) y **nunca** maneja el token de sesión.
- En desarrollo, `ng serve` usa un proxy (`proxy.conf.json`) que envía `/api` al backend, para que
  el navegador vea un solo origen y las cookies funcionen igual que en producción.
- La cookie no lleva `Max-Age`: es de sesión del navegador. El cierre por 30 minutos de inactividad lo controla el backend (`sesiones_usuario`) y renueva la cookie en cada petición válida.
- Mientras se trabaja en local sin HTTPS, `Secure` se desactiva por variable de entorno (`COOKIE_SEGURA=false`). **En producción debe ser `true`.**

Descartado: devolver el JWT en el cuerpo y enviarlo en `Authorization: Bearer` (quedaba expuesto ante un XSS).

### 1.2 Formato único de error
Todas las respuestas de error tienen esta forma, para que el front tenga **un solo manejador**:

```json
{
  "error": {
    "codigo": "USUARIO_BLOQUEADO",
    "mensaje": "La cuenta está bloqueada temporalmente.",
    "detalle": { "desbloqueo_estimado": "2026-11-18T17:30:00Z" }
  }
}
```

| HTTP | `codigo` | Qué debe hacer el front |
|---|---|---|
| 400 | `CAPTCHA_INVALIDO` | Pedir un captcha nuevo y mostrar el mensaje |
| 401 | `CREDENCIALES_INVALIDAS` | Mensaje genérico. Si `detalle.requiere_captcha = true`, mostrar el captcha |
| 401 | `CAPTCHA_REQUERIDO` | Mostrar el captcha |
| 401 | `SESION_EXPIRADA` / `NO_AUTENTICADO` | Limpiar la pantalla y redirigir al login con el aviso "Su sesión expiró por inactividad" |
| 403 | `SIN_PERMISO` | Mostrar "No tiene permiso para esta acción" (no redirigir) |
| 404 | `ARTILLERO_NO_ENCONTRADO` | Mostrar "No se encontró un militar con esa cédula" |
| 404 | `RECURSO_NO_ENCONTRADO` | Ruta inexistente: error de programación del front |
| 405 | `METODO_NO_PERMITIDO` | Método HTTP equivocado: error de programación del front |
| 409 | `ARCHIVO_YA_IMPORTADO` | Avisar que ese archivo ya se cargó antes |
| 409 | `VERIFICACION_POR_SISTEMA_NO_HABILITADA` | Mostrar que la función aún no está activa |
| 422 | `DATOS_INVALIDOS` | Mostrar los errores de `detalle.campos` junto a cada campo |
| 422 | `IMPORTACION_RECHAZADA` | Mostrar la tabla de errores de `detalle.errores` |
| 423 | `USUARIO_BLOQUEADO` | Mostrar el bloqueo y la hora estimada de desbloqueo |
| 429 | `DEMASIADOS_INTENTOS` | Bloqueo por IP: pedir que espere |
| 500 | `ERROR_INTERNO` | Mensaje genérico; **nunca** mostrar detalles técnicos |

### 1.3 Formato único de paginación
```json
{
  "elementos": [ ... ],
  "pagina": 1,
  "tamano_pagina": 50,
  "total_elementos": 12873,
  "total_paginas": 258
}
```
Parámetros de consulta: `pagina` (desde 1) y `tamano_pagina` (por defecto 50, máximo 200).

### 1.4 Inactividad
Cada respuesta autenticada trae la cabecera `X-Sesion-Expira-En: <segundos>`. El front la usa para
mostrar un aviso **2 minutos antes** de que la sesión se cierre por inactividad.

---

## 2. Autenticación

### `GET /api/auth/captcha`
Sin autenticación. Genera un captcha nuevo de un solo uso (vence en 5 minutos).
```json
{ "captcha_id": "8c1f…", "imagen_base64": "iVBORw0KGgo…", "expira_en_segundos": 300 }
```

### `POST /api/auth/login`
```json
{ "nombre_usuario": "comandante.esart", "contrasena": "••••••",
  "captcha_id": null, "captcha_respuesta": null }
```
**200:**
```json
{
  "usuario": { "nombre_usuario": "comandante.esart", "nombre_completo": "…", "rol": "USUARIO",
               "requiere_cambio_contrasena": false },
  "expira_por_inactividad_segundos": 1800
}
```
`requiere_cambio_contrasena: true` = la contraseña es temporal (la puso un administrador). Mientras
lo sea, toda ruta responde **403** `CAMBIO_CONTRASENA_REQUERIDO`, salvo `/auth/yo`,
`/auth/cambiar-contrasena` y `/auth/cerrar-sesion`; el front lleva a "Cambiar contraseña".

Errores posibles: `CREDENCIALES_INVALIDAS`, `CAPTCHA_REQUERIDO`, `CAPTCHA_INVALIDO`, `USUARIO_BLOQUEADO`, `DEMASIADOS_INTENTOS`.

### `GET /api/auth/yo`
Datos del usuario en sesión. El front lo llama al cargar cada página para **armar el menú según permisos**.
```json
{
  "nombre_usuario": "comandante.esart",
  "nombre_completo": "…",
  "rol": "USUARIO",
  "requiere_cambio_contrasena": false,
  "permisos": ["DASHBOARD", "PERSONAL_MILITAR", "PERSONAL_VERIFICAR", "PERSONAL_HABILITADOS", "VER_DOCUMENTO_COMPLETO"],
  "menu": [
    { "codigo": "DASHBOARD", "nombre": "Panel principal", "ruta": "/dashboard", "operaciones": ["leer"], "hijos": [] },
    { "codigo": "PERSONAL_MILITAR", "nombre": "Personal militar", "ruta": "/personal", "operaciones": ["leer"],
      "hijos": [
        { "codigo": "PERSONAL_VERIFICAR", "nombre": "Verificar artillero", "ruta": "/personal/verificar", "operaciones": ["leer"], "hijos": [] },
        { "codigo": "PERSONAL_HABILITADOS", "nombre": "Habilitados", "ruta": "/personal/habilitados", "operaciones": ["leer"], "hijos": [] }
      ] }
  ],
  "expira_por_inactividad_segundos": 1800
}
```
`permisos`: códigos de los componentes a los que puede acceder (incluye permisos sin menú).
`menu`: módulos del sidebar con sus pestañas (`hijos`), ya filtrados por la malla (HU-09).
Las respuestas autenticadas traen `X-Sesion-Expira-En` (HU-08).

### `POST /api/auth/cerrar-sesion`
Revoca la sesión y borra la cookie. **204** sin cuerpo.

### `POST /api/auth/cambiar-contrasena`
CSRF. `{ "contrasena_actual": "…", "contrasena_nueva": "…" }` → **204**. La nueva: mínimo 10
caracteres, letras y números, máximo 72 bytes y distinta de la actual. Quita la marca de contraseña
temporal y cierra las **otras** sesiones del usuario. Errores **422**: `CONTRASENA_ACTUAL_INCORRECTA`,
`DATOS_INVALIDOS`. Queda auditado (`CONTRASENA_CAMBIADA`, también los intentos rechazados).

---

## 3. Verificación

**Regla vigente (2026-11-16):** `APTO` = militar **activo** y (**curso habilitante aprobado** o
**reentrenamiento vigente**). Los parámetros (cursos habilitantes —hoy SACLI y SACME—, meses de
vigencia —12— y días de alerta —60—) están en `esart.parametros_habilitacion` (migración `p0006`).
Un reentrenamiento expedido el 16-nov-2026 vence el 16-nov-2027 (vigente ese día inclusive).

Permisos de la malla (HU-09): verificar = `PERSONAL_VERIFICAR`; listados = `PERSONAL_HABILITADOS`;
resumen = `PERSONAL_MILITAR`. Sin `VER_DOCUMENTO_COMPLETO` la cédula sale como `******5678`.

### `GET /api/verificar/artillero/{numero_documento}`
El backend quita puntos, espacios y guiones; exige de 5 a 15 dígitos.

**200:**
```json
{
  "artillero": {
    "numero_documento": "9900000004",
    "nombre_completo": "Diana Carolina Ruiz Pardo",
    "grado": "SS",
    "categoria": "SUBOFICIAL",
    "unidad_militar": { "sigla": "BAART3", "nombre": "Batallón de Artillería No. 3" },
    "estado_servicio": "ACTIVO"
  },
  "resultado": "APTO",
  "fecha_verificacion": "2026-11-16T17:05:12Z",
  "criterios": [
    { "descripcion": "Estado de servicio activo", "tipo": "OBLIGATORIO", "cumple": true, "detalle": null, "motivo": null },
    { "descripcion": "Curso habilitante aprobado (SACLI o SACME)", "tipo": "ALTERNATIVO", "cumple": false,
      "detalle": null, "motivo": "No tiene curso SACLI o SACME aprobado." },
    { "descripcion": "Reentrenamiento vigente", "tipo": "ALTERNATIVO", "cumple": true,
      "detalle": "Vigente hasta el 16-dic-2026 (faltan 30 días).", "motivo": null }
  ],
  "motivos": [],
  "alerta": "El reentrenamiento vence el 16-dic-2026 (faltan 30 días). Planee el próximo reentrenamiento.",
  "cursos": [
    { "nombre": "Curso sistemas de artilleria liviana", "codigo": "SACLI", "institucion": "Escuela de Artillería",
      "fecha_inicio": "2024-01-05", "fecha_fin": "2024-03-16", "estado": "APROBADO", "habilitante": true }
  ],
  "reentrenamientos": [
    { "numero_certificado": "CERT-0912", "tipo": "OBUS", "calibre": "105MM",
      "fecha_expedicion": "2025-12-16", "fecha_vencimiento": "2026-12-16", "estado": "POR_VENCER" }
  ]
}
```
- `tipo`: `OBLIGATORIO` debe cumplirse; de los `ALTERNATIVO` basta uno.
- Cuando un curso habilitante está aprobado, `detalle` dice desde cuándo ("SACLI aprobado el 16-mar-2024 (hace 2 años y 8 meses).").
- `motivos`: por qué es `NO_APTO` (vacío si es `APTO`).
- Estado de cada reentrenamiento: `VIGENTE`, `POR_VENCER`, `VENCIDO` o `ANULADO`.

Errores: `ARTILLERO_NO_ENCONTRADO` (404), `DATOS_INVALIDOS` (422), `SIN_PERMISO` (403).

### `GET /api/verificar/habilitacion`, `/habilitados` y `/no-habilitados`
Paginados (§1.3; `tamano_pagina` hasta 200). Filtros opcionales: `estado` (`APTO`, `NO_APTO`,
`POR_VENCER`; solo en `/habilitacion`), `unidad_militar_id`, `grado`, `texto` (nombre o cédula).
`/habilitados` = solo `APTO`; `/no-habilitados` = solo `NO_APTO`.

Cada elemento:
```json
{
  "numero_documento": "9900000005",
  "nombre_completo": "Jorge Iván Díaz Moreno",
  "grado": "CP",
  "unidad_militar_sigla": "BAART3",
  "activo": true,
  "resultado": "NO_APTO",
  "motivos": ["No tiene curso SACLI o SACME aprobado.", "Reentrenamiento vencido el 17-sep-2026."],
  "curso_habilitante": null,
  "reentrenamiento_vence": "2026-09-17",
  "estado_reentrenamiento": "VENCIDO"
}
```

### `GET /api/verificar/resumen`
Indicadores del panel: `{ "total", "aptos", "no_aptos", "reentrenamiento_por_vencer", "activos", "unidades", "dias_alerta_vencimiento" }`.

### `GET /api/verificar/sistema/{sistema_id}/habilitados` y `/no-habilitados`
**Contempladas, no activas.** Mientras el sistema tenga `verificacion_habilitada = false`, responden
**409** `VERIFICACION_POR_SISTEMA_NO_HABILITADA`. Cuando se activen, la respuesta será igual a la de §3 (listados).

---

## 4. Catálogos (para selectores y filtros)

| Ruta | Respuesta |
|---|---|
| `GET /api/sistemas` | `[{ "id", "codigo", "nombre", "tipo_sistema", "verificacion_habilitada" }]` |
| `GET /api/catalogos/unidades` | `[{ "id", "sigla", "nombre" }]` (solo activas) |
| `GET /api/catalogos/grados` | `["SUBTENIENTE", "SARGENTO SEGUNDO", …]` |

---

## 5. Importación de Excel

### `GET /api/importaciones/plantilla`
Permiso: `IMPORTAR_EXCEL`. Descarga la plantilla oficial (`plantilla_esart.xlsx`).

### `POST /api/importaciones/excel`
Permiso: `IMPORTAR_EXCEL`. `multipart/form-data` con el campo `archivo` (.xlsx, máximo 20 MB).

**201 (aplicada):**
```json
{ "importacion_id": "…", "estado": "APLICADA", "filas_totales": 15230,
  "filas_validas": 15230, "filas_rechazadas": 0 }
```
**422 `IMPORTACION_RECHAZADA`:** no se aplicó nada (todo o nada).
```json
{ "error": { "codigo": "IMPORTACION_RECHAZADA", "mensaje": "El archivo tiene 3 errores. No se cargó ningún dato.",
  "detalle": { "filas_totales": 15230, "errores": [
    { "hoja": "CURSOS", "fila": 418, "columna": "numero_documento", "motivo": "La cédula no existe en la hoja PERSONAL" }
  ] } } }
```
Errores adicionales: `ARCHIVO_YA_IMPORTADO`, `DATOS_INVALIDOS` (no es .xlsx o supera el tamaño).

### `GET /api/importaciones`
Historial paginado: `{ "importacion_id", "fecha", "nombre_usuario", "nombre_archivo", "estado", "filas_totales", "filas_rechazadas" }`.

---

## 5b. Administración (malla de permisos, gestión de usuarios y auditoría)

Malla (componente `PERMISOS`: leer para consultar, actualizar + CSRF para guardar):
- `GET /api/administracion/permisos/roles` → `[{ "codigo", "nombre", "editable" }]` (ADMINISTRADOR: `editable=false`).
- `GET|PUT /api/administracion/permisos/roles/{codigo}` → filas por módulo con `permisos: { acceder, crear, leer, actualizar, eliminar }`.
  `PUT` recibe `{ "permisos": [{ "componente", "acceder", "crear", "leer", "actualizar", "eliminar" }] }`. ADMINISTRADOR → **409** `ROL_NO_EDITABLE`.
- `GET /api/administracion/permisos/usuarios?texto=` → usuarios con su rol.
- `GET|PUT /api/administracion/permisos/usuarios/{id}` → por módulo: `rol` (lo que da su rol), `modo` (`HEREDAR` / `CONCEDER` / `QUITAR`), `excepcion`, `efectivo`.
  `PUT` recibe `{ "cambios": [{ "componente", "modo", "crear", "leer", "actualizar", "eliminar" }] }`.
  Errores 409: `USUARIO_NO_EDITABLE` (es administrador), `AUTOBLOQUEO` (quitarse la malla a sí mismo), `SIN_ADMINISTRADOR_DE_MALLA`.

Gestión de usuarios (componente `USUARIOS`; todo `POST` con CSRF y auditado). Todo usuario corresponde
a un militar de `personal_militar` (la cédula es obligatoria; solo el administrador inicial del `.env`
no la tiene) y la contraseña que pone el administrador es **temporal**:
- `GET /api/administracion/usuarios?texto=` (leer) → `[{ "id", "usuario", "rol", "activo", "bloqueado", "bloqueado_hasta",
  "intentos_fallidos", "documento_identidad", "nombre_completo", "requiere_cambio_contrasena", "ultimo_acceso_en" }]`.
  `texto` busca en el usuario o la cédula.
- `GET /api/administracion/usuarios/militar/{cedula}` (crear) → `{ "documento_identidad", "grado", "nombres", "apellidos",
  "unidad", "activo", "usuario_existente", "nombre_usuario_sugerido" }`. **404** si la cédula no está en Personal militar.
  Sugerencia: inicial del primer nombre + primer apellido, sin tildes, + `.esart` (con número si ya existe).
- `POST /api/administracion/usuarios` (crear) `{ "documento_identidad", "nombre_usuario", "rol": "USUARIO|ADMINISTRADOR",
  "contrasena_temporal" }` → **201** con la fila. **409** `USUARIO_EXISTENTE` (nombre repetido o militar con usuario);
  **422** militar inexistente o inactivo, contraseña débil.
- `POST /api/administracion/usuarios/{id}/activar` · `/desactivar` · `/desbloquear` (actualizar) → la fila.
  Desactivar cierra sus sesiones; **409** `AUTOBLOQUEO` (a sí mismo) o `SIN_ADMINISTRADOR_DE_MALLA`.
- `POST /api/administracion/usuarios/{id}/restablecer-contrasena` (actualizar) `{ "contrasena_temporal" }` → la fila:
  queda temporal, sin bloqueo y con sus sesiones cerradas. **409** `AUTOBLOQUEO` para la propia (use §2).

Auditoría (componente `AUDITORIA`, solo lectura):
- `GET /api/administracion/auditoria?accion=&usuario=&documento=&desde=AAAA-MM-DD&hasta=AAAA-MM-DD` → paginado (§1.3) con
  `{ "id", "fecha", "usuario_id", "nombre_usuario", "accion", "numero_documento_consultado", "resultado", "direccion_ip", "detalle" }`.

---

## 6. Salud
`GET /api/salud` (sin autenticación; no expone versiones ni detalles técnicos):
- **200** `{ "estado": "ok", "base_datos": "ok" }`
- **503** `{ "estado": "degradado", "base_datos": "error" }` cuando la base de datos no responde.

---

## 7. Reglas para el front (seguridad)
El front es **Angular** (detalle en `frontend/README.md`).
- **Sin CDN:** fuentes, íconos y estilos dentro del proyecto (la red puede no tener internet).
- **Compatible con la CSP:** la compilación de producción no debe generar scripts ni estilos en línea
  (desactivar `inlineCritical` en `angular.json`).
- **Datos de la API solo por interpolación de Angular**; prohibido `innerHTML` con datos de la API y `bypassSecurityTrust*`.
- **Un único servicio de acceso a la API** y un interceptor que maneja los errores de §1.2.
- No guardar datos de artilleros en `localStorage` ni `sessionStorage`. Al cerrar sesión se limpia el estado.
- Nunca escribir tokens ni respuestas completas en `console.log`.

---

## 8. Control de cambios
| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-14 | Borrador inicial |
| 0.2 | 2026-11-14 | Decidido: sesión con JWT en cookie httpOnly + CSRF |
| 0.3 | 2026-11-14 | Códigos `RECURSO_NO_ENCONTRADO`, `METODO_NO_PERMITIDO`; respuesta 503 de salud |
| 0.4 | 2026-11-14 | Front en Angular: CSRF por doble cookie (`esart_csrf` + `X-CSRF-Token`), proxy de desarrollo, reglas de front para Angular; se quita `token_csrf` de `/api/auth/yo` |
| 0.5 | 2026-11-15 | Códigos de rol `ADMINISTRADOR` y `USUARIO` (contrato de esquema §10 punto 7) |
| 0.6 | 2026-11-15 | Implementados login, yo y cerrar-sesion (HU-05). `nombre_usuario` hasta 80 caracteres. `permisos` de `/auth/yo` va vacío hasta cerrar el punto 8 del contrato de esquema. Sesión vencida: 401 `SESION_EXPIRADA` |
| 0.7 | 2026-11-16 | `/api/auth/yo` devuelve `permisos` (códigos de componente) y `menu` (sidebar y pestañas) según la malla (HU-09). Cabecera `X-Sesion-Expira-En` implementada (HU-08) |
| 0.8 | 2026-11-16 | §3 implementado con la regla acordada (activo + SACLI/SACME aprobado o reentrenamiento vigente 12 meses, alerta 60 días): criterios OBLIGATORIO/ALTERNATIVO, `motivos`, `alerta`, `reentrenamientos`; listado `/habilitacion` con filtro `estado`; `/resumen` |
| 0.9 | 2026-11-16 | §5b: rutas de administración (malla de permisos por rol y por usuario, consulta de auditoría) |
| 0.10 | 2026-11-16 | HU-10 web: §5b gestión de usuarios (cédula obligatoria, contraseña temporal, activar/desactivar, desbloquear, restablecer); §2 `requiere_cambio_contrasena`, `POST /auth/cambiar-contrasena` y 403 `CAMBIO_CONTRASENA_REQUERIDO` |
