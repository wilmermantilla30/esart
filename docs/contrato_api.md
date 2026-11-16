# Contrato de API (backend ↔ front) — ESART

**Versión:** 0.6 (borrador para acordar entre SS.Mantilla y SV.Valbuena)
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
  "usuario": { "nombre_usuario": "comandante.esart", "nombre_completo": "…", "rol": "USUARIO" },
  "expira_por_inactividad_segundos": 1800
}
```
Errores posibles: `CREDENCIALES_INVALIDAS`, `CAPTCHA_REQUERIDO`, `CAPTCHA_INVALIDO`, `USUARIO_BLOQUEADO`, `DEMASIADOS_INTENTOS`.

### `GET /api/auth/yo`
Datos del usuario en sesión. El front lo llama al cargar cada página para **armar el menú según permisos**.
```json
{
  "nombre_usuario": "comandante.esart",
  "nombre_completo": "…",
  "rol": "USUARIO",
  "permisos": ["VERIFICAR_ARTILLERO", "VER_DOCUMENTO_COMPLETO", "LISTAR_HABILITACION"],
  "expira_por_inactividad_segundos": 1800
}
```

### `POST /api/auth/cerrar-sesion`
Revoca la sesión y borra la cookie. **204** sin cuerpo.

---

## 3. Verificación

### `GET /api/verificar/artillero/{numero_documento}`
Permiso: `VERIFICAR_ARTILLERO`. El backend limpia puntos y espacios de la cédula.

**200:**
```json
{
  "artillero": {
    "numero_documento": "******5678",
    "nombre_completo": "Juan Carlos Pérez Gómez",
    "grado": "SARGENTO SEGUNDO",
    "categoria": "SUBOFICIAL",
    "unidad_militar": { "sigla": "BAART3", "nombre": "Batallón de Artillería No. 3" },
    "estado_servicio": "ACTIVO"
  },
  "resultado": "NO_APTO",
  "fecha_verificacion": "2026-11-18T14:05:12Z",
  "criterios": [
    { "descripcion": "Estado de servicio activo", "cumple": true,  "motivo": null },
    { "descripcion": "Curso Básico de Artillería de Campaña", "cumple": false,
      "motivo": "Le falta el curso Básico de Artillería de Campaña" },
    { "descripcion": "Certificación de Dirección de Tiro vigente", "cumple": false,
      "motivo": "Certificación de Dirección de Tiro vencida el 2026-03-01" }
  ],
  "cursos": [
    { "tipo_curso": "Curso de Observador Adelantado", "numero_cohorte": "2024-I",
      "fecha_inicio": "2024-02-05", "fecha_fin": "2024-05-30",
      "estado": "APROBADO", "nota_final": 4.35, "numero_acta": "ACT-2024-118" }
  ],
  "certificaciones": [
    { "tipo_certificacion": "Dirección de Tiro", "numero_certificado": "CERT-0912",
      "fecha_expedicion": "2024-03-01", "fecha_vencimiento": "2026-03-01",
      "estado": "ACTIVA", "vigente": false }
  ]
}
```
`resultado` es `"APTO"` o `"NO_APTO"`. Si no hay requisitos configurados, es `"NO_APTO"` con el
motivo "No hay requisitos de habilitación configurados".
Errores: `ARTILLERO_NO_ENCONTRADO`, `DATOS_INVALIDOS` (cédula con formato incorrecto), `SIN_PERMISO`.

### `GET /api/verificar/no-habilitados` y `GET /api/verificar/habilitados`
Permiso: `LISTAR_HABILITACION`. Paginados (§1.3).
Filtros opcionales: `unidad_militar_id`, `grado`, `texto` (busca por nombre o cédula).

Cada elemento:
```json
{
  "numero_documento": "******5678",
  "nombre_completo": "Juan Carlos Pérez Gómez",
  "grado": "SARGENTO SEGUNDO",
  "unidad_militar_sigla": "BAART3",
  "motivos": [ "Le falta el curso Básico de Artillería de Campaña" ]
}
```
En `habilitados`, `motivos` viene vacío.

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
