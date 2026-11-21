# Contrato de esquema de base de datos — ESART

**Proyecto:** ESART — Verificación de habilitación de artilleros (Escuela de Artillería)
**Base de datos:** `esart_db` (PostgreSQL, independiente de Vulcano)
**Versión del contrato:** 1.4 — aprobada por SS.Mantilla y SV.Valbuena (HU-02); actualizada tras HU-04 y HU-05
**Fecha:** 2026-11-14

> **Propósito de este documento.** Fijar *antes de programar* los nombres de tablas, columnas,
> tipos, relaciones y reglas que backend y base de datos van a respetar. Así cada desarrollador
> trabaja en paralelo contra el mismo acuerdo. Cualquier cambio a este contrato se hace por
> Pull Request a este archivo y lo aprueban ambos desarrolladores.
>
> El archivo `docs/esquema_referencia.sql` es la traducción a SQL de este contrato. La fuente
> de verdad en ejecución serán las **migraciones de Alembic**; el SQL es solo referencia.

---

## 1. Convenciones generales

| Tema | Convención | Por qué |
|---|---|---|
| Idioma | Tablas y columnas en español, `snake_case`, nombres completos sin abreviaturas | Convención obligatoria del proyecto y de Vulcano |
| Tablas | Plural (`personal_militar`, `tipos_curso`) | Coherente con la lista inicial de tablas |
| Llave primaria | `id UUID DEFAULT gen_random_uuid()` | Al migrar a Vulcano no hay choque de IDs entre bases distintas. **Validar contra Vulcano** (ver §10) |
| Llaves foráneas | `<entidad_en_singular>_id` (ej. `unidad_militar_id`) | Legible y predecible |
| Fechas de auditoría de fila | `fecha_creacion`, `fecha_actualizacion` (`TIMESTAMPTZ`, en UTC) | Trazabilidad mínima en todas las tablas de negocio |
| Valores de lista (estados, categorías) | `VARCHAR` + restricción `CHECK`, **no** `ENUM` de PostgreSQL | Agregar un valor nuevo con `ENUM` exige migraciones delicadas; con `CHECK` es trivial en Alembic |
| Borrado | Lógico (`activo BOOLEAN`) en catálogos; nunca se borra historia académica | La hoja de vida es evidencia; no se pierde |
| Fechas de negocio | `DATE` (fecha_inicio, fecha_vencimiento) | No requieren hora |
| Notas | `NUMERIC(4,2)` en escala 0.00 – 5.00 | Escala colombiana; **confirmar escala de la Escuela** (ver §10) |
| Cédula | `VARCHAR(10)`, solo dígitos (`CHECK (numero_documento ~ '^[0-9]{6,10}$')`) | Solo cédula de ciudadanía; se guarda sin puntos ni espacios |

---

## 2. Mapa de tablas y alcance

| # | Tabla | Grupo | Entrega |
|---|---|---|---|
| 1 | `unidades_militares` | Organización | Sprint 1 (núcleo) |
| 2 | `personal_militar` | Personal | Sprint 1 |
| 3 | `hoja_vida_artillero` | Personal | Sprint 1 |
| 4 | `tipos_curso` | Formación | Sprint 1 |
| 5 | `artillero_cursos` | Formación | Sprint 1 |
| 6 | `tipos_certificacion` | Formación | Sprint 1 — **tabla agregada** (catálogo para relacionar certificaciones con requisitos) |
| 7 | `artillero_certificaciones` | Formación | Sprint 1 |
| 8 | `sistemas_artilleria` | Material | Sprint 1 (tabla creada, **funcionalidad por sistema contemplada pero deshabilitada**) |
| 9 | `requisitos_habilitacion` | Habilitación | Sprint 1 — **tabla agregada** (criterios de APTO configurables sin tocar código) |
| 10 | `tipos_cargo` | Hoja de vida | Tabla en Sprint 1, uso en Segunda entrega |
| 11 | `artillero_cargos` | Hoja de vida | Tabla en Sprint 1, uso en Segunda entrega |
| 12 | `roles` | Seguridad | Sprint 1 — agregada |
| 13 | `permisos` | Seguridad | Sprint 1 — agregada |
| 14 | `roles_permisos` | Seguridad | Sprint 1 — agregada |
| 15 | `usuarios` | Seguridad | Sprint 1 — agregada |
| 16 | `intentos_inicio_sesion` | Seguridad | Sprint 1 — agregada |
| 17 | `sesiones_usuario` | Seguridad | Sprint 1 — agregada |
| 18 | `auditoria_eventos` | Auditoría | Sprint 1 — agregada |
| 19 | `importaciones_excel` | Importación | Sprint 1 — agregada |
| 20 | `instructores` | Formación | Segunda entrega |
| 21 | `materias_curso` | Formación | Segunda entrega |
| 22 | `artillero_notas_materia` | Formación | Segunda entrega |

Las tablas 1–11 son las nueve pedidas originalmente más dos catálogos necesarios.
Las tablas 12–19 las exige que el sistema sea **de producción** (usuarios, bloqueo, auditoría).
Las tablas 20–22 se crean en la segunda entrega; se documentan ya para no rediseñar después.

---

## 3. Organización y personal

### 3.1 `unidades_militares`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| codigo | VARCHAR(20) | No | Único |
| nombre | VARCHAR(200) | No | |
| sigla | VARCHAR(30) | Sí | Ej. `ESART` |
| unidad_superior_id | UUID | Sí | FK → `unidades_militares.id` (jerarquía) |
| activa | BOOLEAN | No | Default `true` |
| fecha_creacion / fecha_actualizacion | TIMESTAMPTZ | No | |

### 3.2 `personal_militar`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| numero_documento | VARCHAR(10) | No | **Único**, solo dígitos (cédula de ciudadanía) |
| primer_nombre | VARCHAR(60) | No | |
| segundo_nombre | VARCHAR(60) | Sí | |
| primer_apellido | VARCHAR(60) | No | |
| segundo_apellido | VARCHAR(60) | Sí | |
| grado | VARCHAR(40) | No | Ej. `SARGENTO SEGUNDO`. **Confirmar catálogo de grados** (§10) |
| categoria | VARCHAR(20) | No | `CHECK IN ('OFICIAL','SUBOFICIAL','SOLDADO_PROFESIONAL','CIVIL')` |
| arma | VARCHAR(40) | Sí | Ej. `ARTILLERIA` |
| unidad_militar_id | UUID | Sí | FK → `unidades_militares.id` |
| estado_servicio | VARCHAR(20) | No | `CHECK IN ('ACTIVO','RETIRADO','SUSPENDIDO','COMISION','LICENCIA')` |
| fecha_creacion / fecha_actualizacion | TIMESTAMPTZ | No | |

### 3.3 `hoja_vida_artillero`
Una por militar que pertenece (o perteneció) al arma de artillería.

| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| personal_militar_id | UUID | No | FK → `personal_militar.id`, **único** (relación 1 a 1) |
| especialidad | VARCHAR(100) | Sí | |
| fecha_ingreso_arma | DATE | Sí | |
| observaciones | TEXT | Sí | |
| fecha_creacion / fecha_actualizacion | TIMESTAMPTZ | No | |

**Universo de los listados "habilitados / no habilitados":** militares con `hoja_vida_artillero`
y `estado_servicio = 'ACTIVO'`. Un militar sin hoja de vida de artillero no aparece en esos listados;
si se consulta su cédula directamente, el resultado es NO APTO con motivo "sin hoja de vida de artillero".

---

## 4. Formación y certificaciones

### 4.1 `tipos_curso`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| codigo | VARCHAR(30) | No | Único |
| nombre | VARCHAR(200) | No | |
| descripcion | TEXT | Sí | |
| tipo_sistema | VARCHAR(50) | Sí | **Contemplado, no usado aún.** Tipo de sistema al que aplica el curso |
| vigencia_meses | INTEGER | Sí | `NULL` = el curso aprobado no vence |
| nota_minima_aprobacion | NUMERIC(4,2) | Sí | Si es `NULL` manda el campo `estado` del curso |
| activo | BOOLEAN | No | Default `true` |

### 4.2 `artillero_cursos`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| hoja_vida_artillero_id | UUID | No | FK → `hoja_vida_artillero.id` |
| tipo_curso_id | UUID | No | FK → `tipos_curso.id` |
| numero_cohorte | VARCHAR(30) | Sí | Ej. `2025-II` |
| fecha_inicio | DATE | Sí | |
| fecha_fin | DATE | Sí | `CHECK (fecha_fin >= fecha_inicio)` |
| estado | VARCHAR(20) | No | `CHECK IN ('EN_CURSO','APROBADO','REPROBADO','RETIRADO','ANULADO')` |
| nota_final | NUMERIC(4,2) | Sí | `CHECK (nota_final BETWEEN 0 AND 5)` |
| numero_acta | VARCHAR(50) | Sí | Soporte documental del resultado |
| institucion | VARCHAR(200) | Sí | Default lógico: Escuela de Artillería |
| importacion_excel_id | UUID | Sí | FK → `importaciones_excel.id` (de qué carga vino el dato) |
| fecha_creacion / fecha_actualizacion | TIMESTAMPTZ | No | |

Restricción única: `(hoja_vida_artillero_id, tipo_curso_id, numero_cohorte)` para evitar duplicados al reimportar.

### 4.3 `tipos_certificacion` *(agregada)*
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| codigo | VARCHAR(30) | No | Único |
| nombre | VARCHAR(200) | No | |
| entidad_emisora | VARCHAR(200) | Sí | |
| tipo_sistema | VARCHAR(50) | Sí | **Contemplado, no usado aún** |
| activo | BOOLEAN | No | |

### 4.4 `artillero_certificaciones`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| hoja_vida_artillero_id | UUID | No | FK |
| tipo_certificacion_id | UUID | No | FK → `tipos_certificacion.id` |
| numero_certificado | VARCHAR(50) | Sí | |
| fecha_expedicion | DATE | No | |
| fecha_vencimiento | DATE | Sí | `NULL` = no vence. `CHECK (fecha_vencimiento >= fecha_expedicion)` |
| estado | VARCHAR(20) | No | `CHECK IN ('ACTIVA','SUSPENDIDA','REVOCADA')` |
| importacion_excel_id | UUID | Sí | FK |
| fecha_creacion / fecha_actualizacion | TIMESTAMPTZ | No | |

**"Vencida" no se guarda en la base**: se calcula en cada consulta (`fecha_vencimiento < CURRENT_DATE`).
Guardarlo obligaría a un proceso nocturno y podría quedar desactualizado.

---

## 5. Habilitación

### 5.1 `sistemas_artilleria`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| codigo | VARCHAR(30) | No | Único |
| nombre | VARCHAR(200) | No | |
| tipo_sistema | VARCHAR(50) | No | Ej. `OBUS`, `MORTERO`, `COHETES` |
| calibre_milimetros | NUMERIC(6,2) | Sí | |
| verificacion_habilitada | BOOLEAN | No | Default **`false`**. La verificación por sistema queda contemplada; se enciende por dato, no por código |
| activo | BOOLEAN | No | |

### 5.2 `requisitos_habilitacion` *(agregada)*
Cada fila es **un criterio** que el artillero debe cumplir. El backend evalúa todos los
requisitos activos y devuelve el detalle por criterio (cumple / no cumple + motivo).

| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| sistema_artilleria_id | UUID | Sí | `NULL` = **requisito general** (el único que se usa en el Sprint 1) |
| tipo_requisito | VARCHAR(20) | No | `CHECK IN ('CURSO','CERTIFICACION')` |
| tipo_curso_id | UUID | Sí | Obligatorio si `tipo_requisito = 'CURSO'` |
| tipo_certificacion_id | UUID | Sí | Obligatorio si `tipo_requisito = 'CERTIFICACION'` |
| descripcion | VARCHAR(300) | No | Texto que ve el comandante en el criterio |
| activo | BOOLEAN | No | |

`CHECK` de coherencia: exactamente uno de `tipo_curso_id` / `tipo_certificacion_id` según `tipo_requisito`.

### 5.3 Regla de evaluación (contrato de comportamiento)
Un artillero es **APTO** cuando se cumplen **todas** estas condiciones:

1. Existe en `personal_militar` y tiene `hoja_vida_artillero`.
2. `estado_servicio = 'ACTIVO'`.
3. Por cada requisito activo de tipo **CURSO**: tiene un `artillero_cursos` de ese tipo con
   `estado = 'APROBADO'` (y, si el tipo de curso tiene `nota_minima_aprobacion`, `nota_final >= nota_minima`;
   si tiene `vigencia_meses`, `fecha_fin + vigencia_meses >= hoy`).
4. Por cada requisito activo de tipo **CERTIFICACION**: tiene una certificación de ese tipo con
   `estado = 'ACTIVA'` y (`fecha_vencimiento IS NULL` o `fecha_vencimiento >= hoy`).

Si falla cualquiera, es **NO APTO** y se devuelve cada motivo, por ejemplo:
- `"Le falta el curso Básico de Artillería de Campaña"`
- `"Certificación de Dirección de Tiro vencida el 2026-03-01"`
- `"Estado de servicio: SUSPENDIDO"`

> ⚠️ **Pendiente:** los requisitos reales los define la Escuela. Mientras no estén, la tabla
> `requisitos_habilitacion` queda vacía y el sistema debe responder **NO APTO con motivo
> "No hay requisitos de habilitación configurados"** — nunca APTO por defecto.

---

## 6. Hoja de vida (segunda entrega, tablas desde ya)

### 6.1 `tipos_cargo`
`id`, `codigo` (único), `nombre`, `descripcion`, `activo`.

### 6.2 `artillero_cargos`
`id`, `hoja_vida_artillero_id` (FK), `tipo_cargo_id` (FK), `unidad_militar_id` (FK, nulo),
`fecha_inicio` (DATE), `fecha_fin` (DATE, nulo = cargo actual), `numero_resolucion`, `observaciones`.
**Solo informativo:** no interviene en la habilitación.

### 6.3 `instructores` *(segunda entrega)*
`id`, `personal_militar_id` (FK, nulo — puede ser instructor externo), `numero_documento`,
`nombre_completo`, `grado`, `activo`.

### 6.4 Malla curricular *(segunda entrega, S2-01, migración `p0017_malla_curricular`)*
Reemplaza la propuesta `materias_curso` / `artillero_notas_materia`: se usan las tablas reales de la fase 1.
- `materias`: catálogo único. `codigo` (`MAT-001`...), `nombre` único sin distinguir mayúsculas
  (`uq_materias_nombre`). Una materia se reutiliza en todas las mallas que la tengan.
- `versiones_malla`: `tipo_curso_id`, `numero` (1, 2...), `anio`, `estado` `VIGENTE` | `HISTORICA`,
  `observacion`, `creado_por_id`. Solo una `VIGENTE` por tipo de curso (`uq_versiones_malla_vigente`).
- `malla_curricular`: `version_id`, `tipo_curso_id`, `materia_id`, `orden` (≥ 1, único en la versión),
  `area`, `modulo`, `evaluable` (Tiempo del comandante y Entrenamiento físico = `false`: no cuentan en el
  promedio). Se eliminó `nota_minima_aprobacion`: la nota mínima será un parámetro general (S2-10).
- `cursos.malla_version_id`: la asigna el trigger `tg_cursos_asignar_malla` al crear el curso (versión
  vigente de su tipo) y rechaza una versión de otro tipo de curso. Los cursos anteriores quedan en `NULL`.
- Escala de notas **0 a 5 con 2 decimales** en `notas_materia`, `habilitaciones`, `notas_finales_egresado`,
  `egresados_curso` e `inscripciones_curso`. Una sola habilitación por materia (`numero_habilitacion = 1`).
- Carga inicial: `python -m herramientas.cargar_malla_curricular cargar <Excel> --anio 2026 --ejecutar`
  (formato de `docs/backlog_sprint2_esart.xlsx`, hojas *Materias* y *Malla por curso*).

---

## 7. Seguridad

### 7.1 `roles`, `permisos`, `roles_permisos`
- `roles`: `id`, `codigo` (único: `ADMINISTRADOR`, `USUARIO`; CHECK `ck_esart_roles_codigo`), `nombre`, `activo`.
  Lo que cada rol puede hacer lo definen sus permisos, no el código del rol.
- `permisos`: `id`, `codigo` (único), `descripcion`. Permisos iniciales:
  `VERIFICAR_ARTILLERO`, `VER_DOCUMENTO_COMPLETO`, `LISTAR_HABILITACION`, `IMPORTAR_EXCEL`,
  `GESTIONAR_USUARIOS`, `CONSULTAR_AUDITORIA`.
- `roles_permisos`: `rol_id`, `permiso_id` (PK compuesta).

Sin `VER_DOCUMENTO_COMPLETO`, el backend devuelve la cédula enmascarada (`******5678`).

### 7.2 `usuarios`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | UUID | No | PK |
| nombre_usuario | VARCHAR(60) | No | Único (comparación sin mayúsculas: índice único sobre `lower(nombre_usuario)`) |
| nombre_completo | VARCHAR(200) | No | |
| hash_contrasena | VARCHAR(100) | No | **bcrypt**. Nunca se expone por API ni en logs |
| rol_id | UUID | No | FK → `roles.id` |
| activo | BOOLEAN | No | |
| intentos_fallidos_consecutivos | INTEGER | No | Default 0. Se reinicia en login exitoso |
| bloqueado_hasta | TIMESTAMPTZ | Sí | Bloqueo temporal (3 horas) |
| fecha_ultimo_acceso | TIMESTAMPTZ | Sí | |
| fecha_creacion / fecha_actualizacion | TIMESTAMPTZ | No | |

El usuario administrador inicial **se crea al arrancar** a partir de las variables de entorno
(`ADMIN_USUARIO`, `ADMIN_HASH_CONTRASENA`) si no existe. No se guarda contraseña en texto plano en ningún lado.

**Reglas de bloqueo (contrato de comportamiento):**
- Intentos fallidos 1–3: error genérico "Usuario o contraseña incorrectos".
- A partir del 3.º fallo: el login exige captcha.
- Al 7.º fallo: `bloqueado_hasta = ahora + 3 horas`. Desbloqueo automático al vencer, o manual por el administrador.
- El mensaje nunca revela si el usuario existe.

### 7.3 `intentos_inicio_sesion`
`id` (BIGINT identity), `nombre_usuario_intentado`, `usuario_id` (FK, nulo si el usuario no existe),
`direccion_ip` (INET), `exitoso` (BOOLEAN), `motivo_fallo` (VARCHAR(40)), `fecha` (TIMESTAMPTZ).
Permite limitar también por IP los intentos con usuarios inexistentes. **Nunca** guarda la contraseña intentada.

### 7.4 `sesiones_usuario`
`id` (UUID — es el `jti` del JWT), `usuario_id` (FK), `fecha_inicio`, `fecha_ultima_actividad`,
`direccion_ip`, `agente_usuario`, `revocada` (BOOLEAN), `fecha_revocacion`.
Sirve para cerrar la sesión tras **30 minutos sin actividad** y para que el administrador pueda revocar sesiones.

---

## 8. Auditoría e importación

### 8.1 `auditoria_eventos`
| Columna | Tipo | Nulo | Regla |
|---|---|---|---|
| id | BIGINT identity | No | PK |
| fecha | TIMESTAMPTZ | No | Default `now()` |
| usuario_id | UUID | Sí | FK (nulo en intentos de login de usuario inexistente) |
| nombre_usuario | VARCHAR(60) | Sí | Copia del nombre, por si el usuario cambia |
| accion | VARCHAR(40) | No | `LOGIN_EXITOSO`, `LOGIN_FALLIDO`, `USUARIO_BLOQUEADO`, `USUARIO_DESBLOQUEADO`, `CONSULTA_ARTILLERO`, `CONSULTA_HABILITADOS`, `CONSULTA_NO_HABILITADOS`, `IMPORTACION_EXCEL`, `CIERRE_SESION` |
| numero_documento_consultado | VARCHAR(10) | Sí | |
| resultado | VARCHAR(20) | Sí | Ej. `APTO`, `NO_APTO`, `EXITOSO`, `RECHAZADO` |
| direccion_ip | INET | Sí | |
| agente_usuario | VARCHAR(300) | Sí | |
| detalle | JSONB | Sí | Datos adicionales. **Prohibido** incluir contraseñas o tokens |

**Inmutable:** un *trigger* impide `UPDATE` y `DELETE` sobre esta tabla, y el usuario de base de datos
de la aplicación solo tiene permiso `INSERT` y `SELECT` sobre ella.
Índices: `(fecha)`, `(usuario_id, fecha)`, `(numero_documento_consultado)`.

### 8.2 `importaciones_excel`
`id`, `usuario_id` (FK), `nombre_archivo`, `hash_sha256_archivo` (evita cargar dos veces el mismo archivo),
`fecha`, `filas_totales`, `filas_validas`, `filas_rechazadas`,
`estado` (`CHECK IN ('PROCESANDO','APLICADA','RECHAZADA')`), `errores` (JSONB: fila, columna, motivo).

**Regla:** la importación es **todo o nada**. Si una sola fila es inválida, no se aplica nada y se
devuelve el reporte de errores. Así nunca quedan datos a medias que generen un APTO falso.

---

## 9. Índices obligatorios (decenas de miles de registros)
- `personal_militar(numero_documento)` único.
- `personal_militar(estado_servicio)`, `personal_militar(unidad_militar_id)`.
- `artillero_cursos(hoja_vida_artillero_id, tipo_curso_id, estado)`.
- `artillero_certificaciones(hoja_vida_artillero_id, tipo_certificacion_id, estado, fecha_vencimiento)`.
- Todas las FK con índice propio.

Los listados de habilitados / no habilitados se resuelven **en SQL** (no cargando todo a Python) y
siempre **paginados**.

---

## 10. Puntos abiertos y decisiones

Al cerrar HU-02 el contrato se aprobó **tal como está escrito**. Las decisiones de esta tabla
reflejan esa aprobación; cualquier cambio posterior se hace por Pull Request a este archivo.

| # | Punto | Responsable | Estado |
|---|---|---|---|
| 1 | Requisitos reales de habilitación (cursos y certificaciones obligatorios) | Escuela / Product owner | Pendiente |
| 2 | Tipo de PK en Vulcano (UUID vs entero) para garantizar compatibilidad | SV.Valbuena | **Cerrado:** UUID, como define el contrato |
| 3 | Escala de notas de la Escuela (0–5, 0–100) | Product owner | **Cerrado:** 0.00 – 5.00, como define el contrato |
| 4 | Catálogo oficial de grados | Product owner | **Cerrado por ahora:** `grado` como texto (`VARCHAR(40)`); un catálogo formal puede venir en otra entrega |
| 5 | Nombres exactos de columnas en Vulcano para estas tablas (si difieren, se ajusta aquí) | SV.Valbuena | **Cerrado:** se usan los nombres de este contrato |
| 6 | Quién escribe modelos SQLAlchemy y migraciones Alembic | Ambos | **Cerrado (actualizado en v1.3):** el modelo vigente es el de HU-04 (`modelos/persistencia.py`, BIGINT, esquemas `esart`/`esart_ref`). Alembic principal: `p0000` (instalación desde cero) → `p0001_real` (validación) → `p0002` (sesiones, intentos y bloqueo, HU-05). Todo cambio de estructura va en una revisión nueva; revisión cruzada por Pull Request |
| 7 | Códigos de rol: el contrato definía `ADMINISTRADOR`, `COMANDANTE`, `CONSULTA`; la base solo admite `ADMINISTRADOR`, `USUARIO` | SS.Mantilla y SV.Valbuena | **Cerrado (opción B, 2026-11-15):** se conservan `ADMINISTRADOR` y `USUARIO` de la base; se corrige el contrato (§7.1) |
| 8 | Permisos: por código o por componente | SS.Mantilla | **Cerrado (v1.4, 2026-11-16):** por **componente** (`componentes` + `rol_permisos` + `usuario_permisos`). La excepción del usuario sustituye a su rol; sin fila se niega. Los permisos finos sin menú son componentes sin ruta (`VER_DOCUMENTO_COMPLETO`). Malla inicial en la migración `p0005`; se puede modificar y ampliar |

---

## 11. Control de cambios
| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-11-14 | Borrador inicial |
| 1.0 | 2026-11-14 | Aprobado en HU-02. Decisiones del §10 cerradas, salvo los requisitos de habilitación (pendientes de la Escuela) |
| 1.1 | 2026-11-14 | §10: la migración `0001` (HU-03) incluye las tablas de seguridad; HU-05 ya no crea migración. Nuevos puntos 7 (códigos de rol) y 8 (permisos por componente) |
| 1.2 | 2026-11-15 | Punto 7 cerrado: códigos de rol `ADMINISTRADOR` y `USUARIO` (§7.1) |
| 1.3 | 2026-11-15 | Modelo vigente de HU-04 y cadena Alembic p0000→p0001→p0002 (§10 punto 6). Login: usuario por `esart_ref.usuarios.usuario`; rol informado ADMINISTRADOR si lo tiene, si no USUARIO; nombre visible desde `personal_militar` |
| 1.4 | 2026-11-16 | Punto 8 cerrado: permisos por componente. `p0005`: componentes (Personal militar con pestañas hijas), módulos de segunda entrega inactivos y malla inicial ADMINISTRADOR/USUARIO (USUARIO ve la cédula completa) |
| 1.5 | 2026-11-21 | §6.4: malla curricular versionada por tipo de curso, escala de notas 0 a 5 y una sola habilitación (S2-01, `p0017`) |
