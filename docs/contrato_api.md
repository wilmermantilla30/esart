# Contrato de API (backend ↔ front) — ESART

**Versión:** 0.25 (borrador para acordar entre SS.Mantilla y SV.Valbuena)
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
  "operaciones": { "DASHBOARD": ["leer"], "PERSONAL_MILITAR": ["leer"], "VER_DOCUMENTO_COMPLETO": ["leer"] },
  "expira_por_inactividad_segundos": 1800
}
```
`permisos`: códigos de los componentes a los que puede acceder (incluye permisos sin menú).
`menu`: módulos del sidebar con sus pestañas (`hijos`), ya filtrados por la malla (HU-09). Un permiso
especial (sin ruta) que es hijo de un módulo da entrada a ese módulo aunque el usuario no tenga el padre
(S2-09: `MALLAS_CURRICULARES` abre Parámetros, donde solo se ve la pestaña de mallas).
`operaciones` (S2-09): lo que puede hacer en cada componente accesible, incluidos los permisos sin menú;
el front lo usa para mostrar u ocultar botones.
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
- `historial_academico` *(S2-17)*: cursos con notas en la plataforma, del más reciente al más antiguo: los **cerrados** (§5j) y
  el **en curso o aplazado** con alguna nota oficial (parcial). `[{ "codigo", "nombre", "tipo_curso", "fecha_inicio",
  "fecha_fin", "estado_curso", "cerrado", "nota_minima", "nota_final", "resultado", "motivo", "puesto", "aprobados_del_curso",
  "materias_con_nota", "materias": [{ "orden", "materia", "nota", "estado" (HABILITADA | APROBADA_POR_CONSEJO |
  HABILITACION_PERDIDA | null), "instructor" }] }]`. `nota` es la que cuenta en la nota final (la de habilitación si la
  perdió sin aprobación del Consejo); null si aún no tiene nota aprobada. El puesto se lee "`puesto` de
  `aprobados_del_curso`"; sin cerrar, `nota_final`, `resultado` y `puesto` van en null. Los cursos anteriores o cargados por
  Excel no aparecen aquí: siguen en `cursos` solo con aprobado / no aprobado. La **Certificación** en PDF incluye esta sección.

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

### `GET /api/verificar/artillero/{numero_documento}/documento?tipo=DIPLOMA|OFICIO_REMISORIO|CERTIFICACION`
Permiso `PERSONAL_VERIFICAR` (leer). Devuelve el PDF (ReportLab) como descarga; cédula enmascarada sin
`VER_DOCUMENTO_COMPLETO`. **409** `DOCUMENTO_NO_DISPONIBLE` (diploma sin curso aprobado), **422** opción inválida.
Auditado como `CONSULTA_ARTILLERO` con resultado `DOC_<OPCION>`. Opciones del selector: `GET /api/verificar/documentos`.
Detalle en `ESART_DOCUMENTOS_ARTILLERO.md`.

### `GET /api/verificar/resumen`
Indicadores del panel: `{ "total", "aptos", "no_aptos", "reentrenamiento_por_vencer", "activos", "unidades", "dias_alerta_vencimiento" }`.

### `GET /api/verificar/sistema/{sistema_id}/habilitados` y `/no-habilitados`
**Contempladas, no activas.** Mientras el sistema tenga `verificacion_habilitada = false`, responden
**409** `VERIFICACION_POR_SISTEMA_NO_HABILITADA`. Cuando se activen, la respuesta será igual a la de §3 (listados).

---

## 3b. Estadísticas del panel principal
`GET /api/estadisticas/panel?anio=AAAA&semestre=1|2` (componente `DASHBOARD`, leer; todos los roles). Sin parámetros = todo el histórico.
Los cursos se ubican por su **fecha de inicio**; semestre 1 = enero a junio, 2 = julio a diciembre. Solo cifras agregadas.

```json
{
  "periodo": { "anio": 2026, "semestre": 2 }, "hoy": "2026-11-18", "anios_disponibles": [2024, 2025, 2026],
  "indicadores": { "cursos_periodo": 5, "alumnos_periodo": 35, "egresados": 3, "cursos_culminados": 1,
                   "cursos_en_curso": 3, "alumnos_en_curso": 27 },
  "habilitacion": { "total": 243, "aptos": 30, "no_aptos": 213, "reentrenamiento_por_vencer": 2 },
  "cursos_por_anio": [{ "anio": 2026, "semestre_1": 3, "semestre_2": 5 }],
  "grados": [{ "sigla": "CS", "nombre": "Cabo Segundo", "categoria": "SUBOFICIAL" }],
  "cursos": [{ "id", "codigo", "nombre", "tipo_curso", "estado", "fecha_inicio", "fecha_fin", "comandante", "alumnos",
               "grados": { "CS": 2 }, "genero": { "M": 4, "F": 1 } }],
  "en_curso": [{ "...curso", "dias_totales", "dias_transcurridos", "porcentaje", "dias_restantes", "vencido" }]
}
```
- **Alumno** de un curso: fila de `hoja_vida_artillero` con ese curso (grado al ingresar). **Egresado**: alumno de un curso `CULMINADO`.
- `en_curso` y los indicadores `cursos_en_curso` / `alumnos_en_curso` son el estado de **hoy** (no dependen del filtro).
- `vencido`: ya pasó `fecha_fin` y el curso sigue `EN_CURSO`. `grados` viene en orden jerárquico (oficiales, suboficiales, soldados).

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
  "unidad", "activo", "usuario_existente", "nombre_usuario_sugerido", "tipo_persona" }`. `tipo_persona`: `MILITAR` o
  `CIVIL` (S2-11: instructor civil activo del panel de Instructores; llega `grado: "Civil"` y `unidad: null`; el civil no
  entra a Personal militar). **404** si la cédula no está en Personal militar ni en los instructores civiles.
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

## 5c. Parámetros (regla de habilitación, nota mínima, mallas curriculares, plantillas y seguridad)
Todo bajo el componente `PARAMETROS_HABILITACION` de la malla (leer, crear, actualizar, eliminar según la ruta).
Las rutas que cambian datos exigen CSRF.

Cursos y Capacitaciones — regla APTO / NO APTO:
- `GET /api/parametros/habilitacion` (leer) → `{ "valores": { "cursos_habilitantes", "meses_vigencia_reentrenamiento",
  "dias_alerta_vencimiento", "exige_apto_para_disparar" }, "actualizado_en", "actualizado_por", "cursos_disponibles": [{ "codigo", "nombre" }],
  "resumen": { "total", "aptos", "no_aptos", "reentrenamiento_por_vencer" } }`.
- `POST /api/parametros/habilitacion/simular` (leer) cuerpo = `valores` → `{ "actual", "propuesto", "pasan_a_no_apto", "pasan_a_apto" }`.
  No guarda nada.
- `PUT /api/parametros/habilitacion` (actualizar) cuerpo = `valores` + `{ "version": <actualizado_en leído>, "codigo_totp" }`:
  **409** `TOTP_REQUERIDO` sin código (política `PARAMETROS_MODIFICAR`), **422** `TOTP_INVALIDO`, **409** `PARAMETROS_DESACTUALIZADOS`
  si otro administrador guardó antes, **422** `SIN_CAMBIOS` o `DATOS_INVALIDOS` (vigencia 1–60 meses, alerta 1–365 días y menor que la
  vigencia, cursos existentes y activos). Éxito: la regla guardada (misma forma del GET); auditoría `PARAMETROS_ACTUALIZADOS` con antes y después.

Cursos y Capacitaciones — nota mínima de aprobación (S2-10):
- `GET /api/parametros/nota-minima` (leer) → `{ "valor": 3.0, "actualizado_en", "actualizado_por", "cursos_en_curso" }`.
  `cursos_en_curso` = cursos `EN_CURSO` que ya tienen su nota guardada (no cambian al guardar otra).
- `PUT /api/parametros/nota-minima` (actualizar) cuerpo `{ "valor": 3.5, "version": <actualizado_en leído>, "codigo_totp" }`:
  mismos errores que la regla (**409** `TOTP_REQUERIDO`, **422** `TOTP_INVALIDO`, **409** `PARAMETROS_DESACTUALIZADOS`,
  **422** `SIN_CAMBIOS`) y **422** `DATOS_INVALIDOS` si no está entre 1,00 y 5,00 o tiene más de 2 decimales.
  Solo aplica a los cursos que se creen después (cada curso guarda la nota vigente al crearse). Auditoría
  `PARAMETROS_ACTUALIZADOS` con `cambios.NOTA_MINIMA_APROBACION = { "anterior", "nuevo" }` (texto con 2 decimales).
  Cambiar la nota no altera la `version` de la regla de habilitación ni al revés.

Mallas curriculares (S2-09) — componente propio `MALLAS_CURRICULARES` (hijo de Parámetros; se puede dar por excepción):
- `GET /api/parametros/mallas` (leer) → `[{ "codigo", "nombre", "tipo", "modalidad", "duracion_semanas", "activo", "version", "anio",
  "materias", "evaluables" }]` (`version` null = sin malla, como TECNICA).
- `GET /api/parametros/mallas/materias` (leer) → `[{ "codigo", "nombre" }]`: catálogo para sugerir nombres.
- `GET /api/parametros/mallas/{tipo}?version=N` (leer) → `{ "tipo_curso", "version": { "numero", "anio", "estado", "observacion",
  "creado_en", "creado_por", "materias", "cursos" } | null, "filas": [{ "orden", "codigo_materia", "materia", "area", "modulo",
  "evaluable" }], "versiones": [...] }`. Sin `version`, la vigente. **404** `TIPO_CURSO_NO_ENCONTRADO` / `VERSION_NO_ENCONTRADA`.
- `PUT /api/parametros/mallas/{tipo}` (actualizar) cuerpo `{ "anio", "filas": [{ "orden", "materia", "evaluable", "area", "modulo" }],
  "observacion", "version": <número vigente editado o null>, "codigo_totp" }` → crea la **versión nueva** (la anterior queda HISTORICA;
  los cursos ya creados conservan la suya). Antes de pedir el código: **422** `MALLA_INVALIDA` (vacía, materia repetida, sin materias con
  nota...), **422** `SIN_CAMBIOS`, **409** `MALLA_DESACTUALIZADA` (otro usuario guardó antes). Luego **409** `TOTP_REQUERIDO`
  (política `MALLAS_MODIFICAR`) y **422** `TOTP_INVALIDO`. Éxito: el detalle nuevo; auditoría `MALLA_CURRICULAR_CARGADA` con
  `origen: PARAMETROS`, `antes`, `despues` y `cambios` (agregadas, quitadas, cambian_evaluable, orden_cambiado).
- `POST /api/parametros/mallas` (crear) cuerpo `{ "codigo", "nombre", "tipo": EDUCACION_MILITAR|ESPECIALIZACION|EDUCACION_SUPERIOR,
  "modalidad": PRESENCIAL|VIRTUAL|MIXTA, "duracion_semanas": 1–104, "codigo_totp" }` → **201** el detalle (sin malla). **409**
  `TIPO_CURSO_DUPLICADO`, **422** `DATOS_INVALIDOS`, TOTP igual que arriba. Auditoría `TIPO_CURSO_CREADO`.

Plantillas y Formatos:
- `GET /api/parametros/plantillas?formato=XLSX|XLS|PDF|DOCX` (leer) → `[{ "id", "nombre_oficial", "nombre_archivo", "formato", "version",
  "descripcion", "tamano_bytes", "sha256", "subido_en", "subido_por" }]` (solo vigentes, sin el contenido).
- `POST /api/parametros/plantillas` (crear) multipart: `archivo`, `nombre_oficial` (3–200), `version` (1–30), `descripcion` → **201** la fila.
  **422** `ARCHIVO_INVALIDO`: extensión no admitida, más de 25 MB, contenido que no corresponde a la extensión, macros o PDF con JavaScript.
  **409** `PLANTILLA_DUPLICADA` (mismo nombre y versión vigentes).
- `GET /api/parametros/plantillas/{id}/descarga` (leer) → el archivo como adjunto (`Content-Disposition: attachment`, `nosniff`); queda auditado.
- `POST /api/parametros/plantillas/{id}/retirar` (eliminar) → **204**. No se borra: deja de ofrecerse y queda en el historial.

Parámetros de Seguridad (solo consulta):
- `GET /api/parametros/seguridad` (leer) → `{ "totp_habilitado", "usuarios_activos", "usuarios_con_autenticador", "minutos_inactividad_sesion",
  "intento_captcha", "intento_bloqueo", "horas_bloqueo", "politicas": [{ "codigo", "nombre", "modulo", "requiere_totp", "activa" }] }`.

## 5d. Instructores
Componente `INSTRUCTORES` (ADMINISTRADOR: acceder, crear, leer, actualizar; USUARIO: acceder y leer). Las rutas que cambian datos exigen CSRF.
El documento sale enmascarado sin `VER_DOCUMENTO_COMPLETO`.

Instructor: `{ "id", "tipo": "MILITAR"|"CIVIL", "documento", "grado", "nombres", "apellidos", "nombre_completo", "unidad", "profesion",
"fecha_ingreso_escuela", "activo", "tiene_foto", "version", "nombre_usuario", "especialidades": [{ "codigo", "nombre" }] }`.
Del MILITAR, nombre, grado y unidad salen de Personal militar; el CIVIL guarda los suyos. `version` cambia con cada edición.

- `GET /api/instructores?texto=&especialidad=&estado=ACTIVOS|INACTIVOS|TODOS` (leer) → `[Instructor]` (por defecto activos).
- `GET /api/instructores/especialidades` (leer) → `[{ "codigo", "nombre" }]` (catálogo provisional: OA, ACL, ACM, RSOP, CDT, TP).
- `GET /api/instructores/militar/{cedula}` (crear) → `{ "documento", "nombre_completo", "unidad", "activo", "ya_es_instructor" }`; **404** `MILITAR_NO_ENCONTRADO`.
- `POST /api/instructores` (crear) `{ "tipo", "documento", "fecha_ingreso_escuela", "especialidades": [codigos], "profesion"?, "nombres"?, "apellidos"? }`
  (nombres y apellidos obligatorios si es CIVIL) → **201** Instructor. **409** `INSTRUCTOR_EXISTENTE`, `MILITAR_INACTIVO`, `ES_MILITAR`
  (documento civil que pertenece a un militar); **422** fecha futura, especialidad inexistente o datos incompletos.
- `PUT /api/instructores/{id}` (actualizar) `{ "fecha_ingreso_escuela", "especialidades", "profesion"?, "nombres"?, "apellidos"? }` → Instructor.
  Las especialidades quitadas se desactivan (queda su historial).
- `PUT /api/instructores/{id}/foto` (actualizar) multipart `archivo` (JPG, PNG o WebP, hasta 5 MB) → Instructor. Se guarda como JPEG de
  máximo 800 px y sin metadatos; **422** `FOTO_INVALIDA`. `DELETE /api/instructores/{id}/foto` (actualizar) la quita.
- `GET /api/instructores/{id}/foto` (leer) → `image/jpeg` (`Cache-Control: private`); **404** `FOTO_NO_ENCONTRADA`. El front agrega `?v=<version>`.
- `POST /api/instructores/{id}/activar` y `/desactivar` (actualizar) → Instructor. Los instructores no se borran.
- `GET /api/instructores/{id}/cursos` (leer) → `{ "comandante": [Curso], "participa": [Curso + "rol_en_curso"], "materias": [...] }` con
  Curso = `{ "id", "codigo", "nombre", "tipo_curso", "fecha_inicio", "fecha_fin", "estado", "alumnos" }` (más recientes primero).
  `comandante` sale de `cursos.comandante_id` (cargue por Excel); `participa`, de `cursos_instructores`. Migración p0014.
  `materias` (S2-02): `[{ "curso_id", "curso", "nombre_curso", "estado", "tipo_curso", "materia", "fecha_inicio" }]`, las que dicta
  como titular (se asignan en §5f).

## 5e. Registro manual de personal militar

Componente `PERSONAL_CARGUE_MANUAL`, operación **crear** (sesión + CSRF). Detalle en `ESART_REGISTRO_MANUAL_PERSONAL.md`.

- `GET /api/personal/opciones-registro` → `{ "categorias": [{ "codigo", "nombre", "grados": [{ "codigo", "nombre" }] }], "unidades": [{ "id", "codigo", "nombre" }] }`.
- `POST /api/personal` con `{ "documento_identidad", "nombres", "apellidos", "grado", "genero": "M"|"F", "categoria", "unidad_actual_id"?, "especialidad_actual"?, "activo" }`
  → **201** con el registro + `"nombre_completo"`, `"unidad_nombre"`. **409** `DOCUMENTO_EXISTENTE`, **422** `DATOS_INVALIDOS`
  (grado fuera de la categoría, unidad inexistente o inactiva), **503** `REGISTRO_NO_DISPONIBLE` (falta p0015). Auditoría `PERSONAL_REGISTRADO`.

## 5f. Cursos (S2-02)

Componente `CURSOS` (ruta `/cursos`, activado en p0021): **leer** para ver; **actualizar** para asignar. Al Inspector de Estudios
se le da por excepción. Las rutas que cambian datos exigen CSRF; los cursos CULMINADO o CANCELADO no se modifican (**409**
`CURSO_NO_EDITABLE`).

- `GET /api/cursos?estado=EN_CURSO|APLAZADO|CULMINADO|CANCELADO&tipo=SACLI&texto=…` (leer) → `[{ "id", "codigo", "nombre", "tipo_curso",
  "fecha_inicio", "fecha_fin", "estado", "alumnos", "comandante", "version_malla", "materias_con_nota", "asignadas" }]` (máximo 500,
  más recientes primero). `version_malla` null = curso creado sin malla.
- `GET /api/cursos/{id}` (leer) → el curso con `nombre_tipo_curso`, `nota_minima_aprobacion`, `version_malla`, `anio_malla`,
  `estado_malla`, `editable`, `version_vigente_disponible` y `materias: [{ "malla_id", "orden", "codigo_materia", "materia", "area",
  "modulo", "evaluable", "instructor_id", "instructor", "tipo_instructor", "asignado_en", "asignado_por" }]`. **404** `CURSO_NO_ENCONTRADO`.
- `GET /api/cursos/instructores-disponibles` (actualizar) → `[{ "id", "tipo", "nombre" }]`: instructores activos para el selector.
- `PUT /api/cursos/{id}/materias/{malla_id}/instructor` (actualizar) cuerpo `{ "instructor_id": 7 | null }`: pone, cambia o quita
  (null) el instructor **titular** (uno por materia). **404** `MATERIA_NO_ENCONTRADA` (no es de la malla del curso), **422**
  `MATERIA_SIN_NOTA`, `INSTRUCTOR_NO_DISPONIBLE` (inactivo o inexistente) o `SIN_CAMBIOS`. Éxito: el detalle; auditoría
  `INSTRUCTOR_MATERIA_ASIGNADO` con `curso`, `materia`, `anterior` y `nuevo`.
- `POST /api/cursos/{id}/malla` (actualizar): liga la versión VIGENTE de su tipo a un curso EN_CURSO o APLAZADO creado sin malla y
  le copia la nota mínima vigente si no tenía. **409** `CURSO_CON_MALLA`, **422** `TIPO_SIN_MALLA`. Auditoría `CURSO_MALLA_ASIGNADA`.

## 5g. Carga de notas del instructor (S2-12)

Componente `NOTAS_CARGA` (ruta `/notas/mis-materias` desde p0022; se da por excepción al instructor): **leer** para ver sus
materias, descargar la plantilla y ver su entrega; **crear** para subir. Además del permiso, el usuario debe ser el instructor
**titular** de la materia en ese curso (§5f), reconocido por su cédula: si no, **403** `NO_ES_INSTRUCTOR` o `MATERIA_NO_ASIGNADA`.
Curso CANCELADO: **409** `CURSO_NO_EDITABLE`.

- `GET /api/notas/mis-materias` → `{ "es_instructor", "materias": [{ "curso_id", "codigo_curso", "nombre_curso", "tipo_curso",
  "estado_curso", "fecha_inicio", "fecha_fin", "malla_id", "orden", "codigo_materia", "materia", "nota_minima", "alumnos",
  "estado_entrega" (null | EN_REVISION | APROBADA | DEVUELTA), "subido_en", "revisado_en", "observacion_revision",
  "notas_entregadas", "tiene_notas_oficiales", "alumnos_a_habilitar", "estado_habilitacion",
  "observacion_habilitacion", "por_items", "puede_subir" }] }` (campos de habilitación desde S2-14, §5i; `por_items`
  desde S2-16, §5k).
- `GET /api/notas/plantilla/{curso_id}/{malla_id}` → XLSX como adjunto: hoja "Notas" (alumnos del curso, columna Nota editable con
  validación 0–5) y hoja oculta "control" con la **firma** HMAC del curso, la materia y los alumnos. **409** `CURSO_SIN_ALUMNOS`.
- `POST /api/notas/entregas/{curso_id}/{malla_id}` (CSRF, multipart `archivo`) → la entrega (`EntregaDeMateria`, abajo), estado
  **EN_REVISION**. No guarda nada si algo falla:
  **422** `ARCHIVO_INVALIDO` (no es XLSX seguro), `PLANTILLA_ALTERADA` (sin firma o firma que no coincide), `PLANTILLA_DE_OTRA_MATERIA`,
  `NOTAS_INVALIDAS` con `detalle.errores: [{ "fila", "mensaje" }]` (falta la nota, no es número, fuera de 0–5, más de 2 decimales,
  cédula ajena al curso, alumno repetido o faltante: se exige la nota de **todos** los alumnos); **409** `PLANTILLA_DESACTUALIZADA`
  (cambió la lista de alumnos) y `ENTREGA_APROBADA` (ya aprobada por el Inspector: solo cambia si la reabre, §5h).
  En revisión o devuelta, una nueva carga **reemplaza** la anterior. Auditoría `NOTAS_ENTREGADAS` (curso, materia, alumnos,
  promedio, cuántas por debajo de la mínima, a qué estado reemplazó y sha256 del archivo).
- `GET /api/notas/entregas/{curso_id}/{malla_id}` → `{ "curso_id", "codigo_curso", "materia", "nota_minima", "entrega": null |
  { "estado", "nombre_archivo", "subido_en", "subido_por", "revisado_en", "observacion_revision", "notas": [{ "cedula", "grado",
  "apellidos", "nombres", "nota" }] } }`.

## 5h. Revisión de notas por el Inspector de Estudios (S2-13)

Componente `NOTAS_REVISION` (ruta `/notas/revision` desde p0023; se da por excepción al Inspector): **leer** para la bandeja y
el detalle; **actualizar** para aprobar, devolver o reabrir. **Reabrir** exige el código del autenticador (política
`NOTAS_APROBAR`: sin código **409** `TOTP_REQUERIDO`, inválido **422** `TOTP_INVALIDO`); **aprobar no** lo pide desde 0.23
(decisión de la Escuela: es la tarea más repetida del Inspector; la sesión ya exige TOTP y todo queda auditado). Las notas **oficiales** (las que cuentan
para la habilitación y la nota final) son las de la última entrega aprobada de cada curso y materia.

- `GET /api/notas/revision/entregas?estado=EN_REVISION|DEVUELTA|APROBADA|TODAS` (por defecto EN_REVISION; otro valor **422**) →
  `[EntregaEnBandeja]`: `{ "id", "tipo" (ORDINARIA | HABILITACION, §5i), "estado", "nombre_archivo", "subido_en", "subido_por", "revisado_en", "revisado_por",
  "observacion_revision", "curso_id", "codigo_curso", "nombre_curso", "estado_curso", "tipo_curso", "malla_id", "orden",
  "codigo_materia", "materia", "nota_minima", "instructor", "alumnos", "promedio", "por_debajo_de_la_minima",
  "tiene_notas_oficiales" }`, de la más antigua a la más reciente.
- `GET /api/notas/revision/entregas/{id}` → `EntregaEnBandeja` + `"notas": [{ "cedula", "grado", "apellidos", "nombres", "nota",
  "nota_oficial" }]` (`nota_oficial` = la vigente, null si no había). **404** `ENTREGA_NO_ENCONTRADA`.
- `POST /api/notas/revision/entregas/{id}/aprobar` (CSRF) `{ "version" }` → el detalle, estado **APROBADA**; sus notas
  reemplazan a las oficiales. `version` es el `subido_en` revisado: si el instructor subió otra planilla, **409** `ENTREGA_CAMBIO`.
  Solo EN_REVISION (si no, **409** `ESTADO_NO_PERMITE`); curso CANCELADO **409** `CURSO_NO_EDITABLE`; si cambió la lista de alumnos
  del curso **409** `ENTREGA_DESACTUALIZADA`. Auditoría `NOTAS_APROBADAS` (curso, materia, instructor, alumnos, promedio, cuántas
  por debajo de la mínima, `es_correccion` y, en una corrección, `cambios: [{ "cedula", "antes", "despues" }]`).
- `POST /api/notas/revision/entregas/{id}/devolver` (CSRF) `{ "version", "observacion" }` → estado **DEVUELTA** con la observación
  (5 a 1000 caracteres; si no, **422** `DATOS_INVALIDOS`). Solo EN_REVISION. Auditoría `NOTAS_DEVUELTAS`.
- `POST /api/notas/revision/entregas/{id}/reabrir` (CSRF) `{ "observacion", "codigo_totp" }` → una entrega **APROBADA** queda
  DEVUELTA para que el instructor suba la corrección; las notas oficiales **siguen vigentes** hasta la nueva aprobación.
  Auditoría `NOTAS_REABIERTAS`.

## 5i. Habilitación y Consejo Académico (S2-14)

Debe **habilitar** el alumno cuya nota oficial **ordinaria** de una materia quedó por debajo de la nota mínima del curso; una
sola habilitación por materia. La nota que cuenta para el promedio queda en `notas_oficiales.nota` con su `origen`: ORDINARIA,
HABILITACION (alcanzó la mínima en la habilitación: materia "Habilitada") o CONSEJO ("Aprueba la materia": la nota mínima).

**Instructor** (componente `NOTAS_CARGA`, titular de la materia, §5g):
- `GET /api/notas/habilitaciones/{curso_id}/{malla_id}` → `{ "curso_id", "codigo_curso", "materia", "nota_minima", "alumnos": [{
  "cedula", "grado", "apellidos", "nombres", "nota_ordinaria", "nota_habilitacion" }], "estado", "subido_en", "revisado_en",
  "observacion_revision" }` (`estado` null si aún no se registró).
- `POST /api/notas/habilitaciones/{curso_id}/{malla_id}` (CSRF, **crear**) `{ "notas": [{ "cedula", "nota" }] }` → lo mismo, con la
  entrega de tipo **HABILITACION** EN_REVISION (pasa por la revisión del Inspector, §5h). Exige la nota de **todos** los alumnos a
  habilitar (0–5, 2 decimales, número o texto con coma): si no, **422** `NOTAS_INVALIDAS` con `detalle.errores`. Sin alumnos a
  habilitar (o sin notas ordinarias aprobadas) **409** `SIN_HABILITACIONES`; ya aprobada **409** `ENTREGA_APROBADA`. Auditoría
  `NOTAS_ENTREGADAS` con `"tipo": "HABILITACION"`.

**Inspector** (§5h): al **aprobar** una entrega HABILITACION, quien alcanza la mínima queda con la nota de habilitación y quien no,
pasa al Consejo; la auditoría `NOTAS_APROBADAS` agrega `habilitaron` y `al_consejo_academico`. El detalle trae además
`"nota_ordinaria"` por alumno y, en una habilitación, `nota_oficial` es la de la habilitación anterior. **Reabrir**: la ordinaria
de una materia con habilitación **409** `MATERIA_CON_HABILITACION`; una habilitación con decisiones del Consejo **409**
`HABILITACION_CON_DECISION`. Aprobar de nuevo una habilitación reabierta deshace la anterior y aplica la nueva.

**Consejo Académico** (componente `CONSEJO_ACADEMICO`, ruta `/notas/consejo`: **leer** para los casos, **crear** para decidir):
- `GET /api/notas/consejo/casos?filtro=PENDIENTES|DECIDIDOS|TODOS` (por defecto PENDIENTES; otro valor **422**) → `[{ "id",
  "curso_id", "codigo_curso", "nombre_curso", "estado_curso", "tipo_curso", "malla_id", "codigo_materia", "materia",
  "nota_minima", "cedula", "grado", "apellidos", "nombres", "nota_ordinaria", "nota_habilitacion", "habilitacion_aprobada_en",
  "decision", "numero_acta", "fecha_acta", "observacion", "registrado_en", "registrado_por" }]` (alumnos que perdieron la
  habilitación; `id` es el de la habilitación).
- `POST /api/notas/consejo/casos/{id}/decision` (CSRF) `{ "decision": APRUEBA_MATERIA | REPITE_CURSO | PIERDE_CURSO | OTRA,
  "numero_acta", "fecha_acta", "observacion", "codigo_totp" }` → el caso con su decisión. Política TOTP `CONSEJO_REGISTRAR`.
  Acta obligatoria (máx. 50) y fecha no futura; `OTRA` exige observación (**422** `DATOS_INVALIDOS`). Una sola decisión por caso
  (**409** `CASO_DECIDIDO`; no se edita); **404** `CASO_NO_ENCONTRADO`; curso cancelado **409** `CURSO_NO_EDITABLE`.
  `APRUEBA_MATERIA` deja la materia con la nota mínima del curso (origen CONSEJO); las demás no cambian la nota (las aplica el
  cierre del curso, S2-15). Auditoría `CONSEJO_DECISION_REGISTRADA`.

## 5j. Nota final, puesto y cierre del curso (S2-15)

Componente `CURSOS` (§5f): **leer** para ver los resultados, **actualizar** para cerrar el curso.

- **Nota final** = promedio de las notas oficiales (`notas_oficiales.nota`) de las materias **evaluables** de la malla del curso,
  con 2 decimales; si el alumno perdió la habilitación y el Consejo no aprobó la materia, cuenta la nota de habilitación.
  **Aprueba** con nota final ≥ nota mínima del curso. "Repite el curso" o "Pierde el curso" del Consejo lo dejan **REPROBADO**.
- **Puesto** solo para los aprobados: primero quienes no habilitaron ninguna materia; en cada grupo, por la nota final con todos
  sus decimales, luego menos materias habilitadas y luego el promedio del área "Profesional Específica". Si aún empatan,
  comparten el puesto (1, 2, 2, 4).
- `GET /api/cursos/{id}/resultados` → `{ "curso_id", "codigo_curso", "estado_curso", "nota_minima", "cerrado", "cerrado_en",
  "cerrado_por", "materias_evaluables", "completo", "puede_cerrar", "pendientes": [texto], "alumnos": [{ "cedula", "grado",
  "apellidos", "nombres", "nota_final", "materias_evaluadas", "materias_habilitadas", "pendientes": [texto], "resultado"
  (APROBADO | REPROBADO | null), "motivo", "puesto" }] }`. Sin cerrar, **provisionales** con las notas oficiales de hoy (lo que
  falta: notas sin aprobar, entregas en revisión o devueltas, habilitaciones o decisiones del Consejo pendientes); cerrado, los
  **guardados**. Sin malla o nota mínima **409** `CURSO_SIN_MALLA`; **404** `CURSO_NO_ENCONTRADO`.
- `POST /api/cursos/{id}/cerrar` (CSRF) `{ "codigo_totp" }` → los resultados ya guardados. Política TOTP `CURSO_CERRAR`. Solo
  EN_CURSO (**409** `CURSO_NO_EDITABLE`), con alumnos (**409** `CURSO_SIN_ALUMNOS`) y completo (**409** `RESULTADOS_INCOMPLETOS`
  con `detalle.pendientes`). El curso pasa a **CULMINADO**, se guardan los resultados y el curso de los aprobados queda
  `aprobado` en su historial (`artillero_cursos`), que alimenta APTO / NO APTO. Auditoría `CURSO_CERRADO` (alumnos, aprobados,
  reprobados, primer puesto e historial actualizado).

## 5k. Fase de campaña del CAPINTE por ítems (S2-16)

Una materia se califica **por ítems** cuando tiene ítems activos (hoy MAT-074 "FASE DE CAMPAÑA CAPINTE"). Es una materia más de la
malla: su nota entra a la nota final (§5j).

- **Quién la registra:** el **comandante del curso** (`cursos.comandante_id`), con `NOTAS_CARGA` y usuario con su misma cédula. En
  `GET /api/notas/mis-materias` le aparece con `"por_items": true`. No lleva instructor titular: en Cursos (§5f) la materia trae
  `"por_items": true` y asignarle instructor da **422** `MATERIA_POR_ITEMS`.
- **Plantilla** (`GET /api/notas/plantilla/{curso}/{malla}`, §5g): un alumno por fila, una columna por ítem (título con su puntaje)
  donde se marca **X** en los aprobados, y una columna "Nota (calculada)" solo de ayuda. La firma incluye los ítems y puntajes.
- **Carga** (`POST /api/notas/entregas/{curso}/{malla}`, §5g): nota = suma de los puntajes aprobados, 2 decimales, tope 5,00.
  Otra marca que no sea X o vacío: **422** `NOTAS_INVALIDAS` ("Ítem N: …"). Si cambiaron los ítems o puntajes desde la descarga:
  **409** `PLANTILLA_DESACTUALIZADA`. Se guarda qué ítem aprobó cada alumno y con qué puntaje; la auditoría `NOTAS_ENTREGADAS`
  lleva `"por_items": true`. Después sigue la revisión del Inspector (§5h) y, si aplica, la habilitación (§5i).
- **Parámetros** (componente `PARAMETROS_HABILITACION`):
  - `GET /api/parametros/campana` → `{ "codigo_materia", "materia", "items": [{ "id", "orden", "nombre", "puntaje" }], "total",
    "actualizado_en", "actualizado_por" }`. Sin la materia MAT-074 **409** `SIN_MATERIA_CAMPANA`.
  - `PUT /api/parametros/campana` (CSRF, **actualizar**) `{ "items": [{ "id" | null, "nombre", "puntaje" }], "version",
    "codigo_totp" }` en el orden final → la configuración nueva. Política TOTP `PARAMETROS_MODIFICAR`. Nombres de 3 a 200 sin
    repetir; puntajes > 0 con hasta 4 decimales que suman 5,00 al redondear (**422** `DATOS_INVALIDOS`); iguales **422**
    `SIN_CAMBIOS`; versión vieja **409** `PARAMETROS_DESACTUALIZADOS`. Los ítems que no vienen quedan inactivos (las entregas
    anteriores los conservan). Auditoría `PARAMETROS_ACTUALIZADOS` con `cambios.FASE_CAMPANA_CAPINTE` (anterior y nuevo).

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
| 0.11 | 2026-11-17 | §5c panel de Parámetros: regla de habilitación (leer, simular, guardar con TOTP y control de concurrencia), repositorio de plantillas (publicar, descargar, retirar) y parámetros de seguridad (solo consulta). Migración p0012 |
| 0.12 | 2026-11-17 | §5d panel de instructores (militares y civiles, foto y especialidades) y cursos del instructor. Migraciones p0013 y p0014 |
| 0.13 | 2026-11-18 | §5e registro manual de personal militar y accesos a Instructores / Usuarios con `?cedula=`. Migración p0015 |
| 0.14 | 2026-11-18 | §3 documentos PDF del artillero (diploma, oficio remisorio, certificación) con ReportLab |
| 0.15 | 2026-11-18 | §3b estadísticas del panel principal (cursos por año y semestre, grados y género por curso, egresados, seguimiento de cursos en curso) |
| 0.16 | 2026-11-21 | S2-11: §5b usuario para instructores civiles (`tipo_persona`); permisos especiales MALLAS_CURRICULARES, NOTAS_CARGA, NOTAS_REVISION y CONSEJO_ACADEMICO en la malla (sin menú hasta sus pantallas). Migración p0018 |
| 0.17 | 2026-11-21 | S2-10: §5c nota mínima de aprobación (leer y guardar con TOTP), solo para cursos nuevos. Migración p0019 |
| 0.18 | 2026-11-21 | S2-09: §5c mallas curriculares y tipos de curso en Parámetros (versiones con TOTP y auditoría); §2 `operaciones` por componente en `/auth/yo` y permiso especial hijo que abre su módulo. Migración p0020 |
| 0.19 | 2026-11-21 | S2-02: §5f módulo Cursos (lista, detalle, instructor titular por materia con nota, malla vigente para cursos sin malla); §5d materias que dicta el instructor. Migración p0021 |
| 0.20 | 2026-11-24 | S2-12: §5g carga de notas del instructor (mis materias, plantilla firmada, entrega EN_REVISION con validación completa y reemplazo). Migración p0022 |
| 0.21 | 2026-11-26 | S2-13: §5h revisión de notas (bandeja, aprobar con TOTP, devolver con observación, reabrir una aprobada; notas oficiales con antes y después en la auditoría). Migración p0023 |
| 0.22 | 2026-11-26 | S2-14: §5i habilitación (formulario del instructor, revisión del Inspector) y decisiones del Consejo Académico; tipo de entrega en §5h. Migración p0024 |
| 0.23 | 2026-11-26 | S2-15: §5j nota final, puesto (reglas de desempate) y cierre del curso con TOTP; aprobar notas (§5h) ya no pide TOTP. Migración p0025 |
| 0.24 | 2026-11-27 | S2-16: §5k fase de campaña del CAPINTE por ítems (plantilla del comandante, nota = suma de puntajes aprobados) e ítems editables en Parámetros con TOTP. Migración p0026 |
| 0.25 | 2026-11-27 | S2-17: §3 `historial_academico` en la verificación (notas por materia, nota final y puesto) y sección en la Certificación PDF |
