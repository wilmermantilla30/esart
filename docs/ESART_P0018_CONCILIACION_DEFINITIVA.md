# P0018 conciliada con el esquema heredado `esart_firma`

Fecha: 2026-11-19.

**Estado:** la migración y el código están rediseñados y probados en PostgreSQL 18 aislado. **No se
ejecutó nada sobre `esart_db`**: ninguna migración, consulta, respaldo ni restauración.

Este documento reemplaza la matriz preliminar de `ESART_P0014_P0018_CONCILIACION.md`.

## 1. Punto de partida

| Hecho | Fuente |
|---|---|
| `esart_firma` existe con 21 tablas, todas propiedad de `postgres` | `ESART_FIRMA_INVENTARIO.json` (catálogo) |
| 13 registros: `roles_firma` = 5, `permisos_firma` = 8; las otras 19 tablas están vacías | Conteo exacto del operador |
| Revisión Alembic en `esart_db`: `p0014_cursos_del_instructor`; pendientes p0015 → p0016 → p0017 → p0018 | Operador |
| La p0018 anterior se detenía si existía `esart_firma` y, sin esa guarda, habría chocado con las tablas existentes | Revisión de código |

**Corrección a la matriz preliminar:** las colisiones *de nombre* son cuatro:

- `autorizaciones_firmantes`
- `solicitudes_firma`
- `consentimientos_firma`
- `evidencias`

La quinta es una **duplicación semántica**, no de nombre: la p0018 anterior creaba
`eventos_auditoria`, mientras que el esquema heredado ya tiene `auditoria_eventos`, con cadena de
hashes. Las cinco se resolvieron igual: comparando estructura, no nombres.

## 2. Matriz definitiva de compatibilidad (las 5 colisiones)

| Tabla | Columnas y tipos | PK / FK | Índices y restricciones | Dependencias | Decisión |
|---|---|---|---|---|---|
| `autorizaciones_firmantes` | Heredada: `identidad_id`, `tipo_certificado` (text), `cargo`, `grado`, vigencia, `documento_autorizacion_sha256`, concesión y revocación. La p0018 anterior pedía `usuario_id` y `tipo_documento`. | PK uuid. FK `identidad_id` y `concedido_por` → `identidades` | `ix_autorizaciones_firmante`; CHECK de vigencia | `solicitudes_firma.autorizacion_id` | **Reutilizar sin cambios.** El firmante es la identidad enlazada al usuario ESART (punto 3.1). `tipo_certificado` guarda el tipo documental (`CERTIFICACION`, `OFICIO_REMISORIO`). |
| `solicitudes_firma` | Heredada: `certificado_id` y `version_id` obligatorios, FK compuesta a `versiones_certificado`; firmante, autorización, orden, estado, hash QR, tiempos | PK uuid; FK a `versiones_certificado`, `identidades` y `autorizaciones_firmantes` | UNIQUE (cert, versión, firmante, orden), UNIQUE `token_qr_hash`, CHECKs de estado y hash | `consentimientos_firma`, `firmas_certificado` | **Extender.** Se agregan `documento_id` y `documento_version_id`, con FK compuesta a `versiones_documento`. `certificado_id` y `version_id` pasan a opcionales, y `ck_solicitudes_objeto_unico` exige exactamente un objeto: certificado o documento. Se agrega un índice único parcial para documentos. |
| `consentimientos_firma` | Heredada: solicitud, texto y versión, `documento_sha256`, IP, agente, `desafio_id` obligatorio; la anterior pedía `usuario_id` | FK a `solicitudes_firma` y a `desafios_autenticacion` | UNIQUE `solicitud_id` y `desafio_id`; trigger inmutable | `firmas_certificado` | **Reutilizar sin cambios.** El usuario se deduce de solicitud → firmante (identidad). El desafío registra la verificación TOTP de ESART (propósito `FIRMAR`). |
| `evidencias` | Heredada: `certificado_id`, `evento_id`, `clase`, `archivo_sha256`, `ubicacion_segura`, `retener_hasta`; la anterior usaba `documento_id`, `sha256` y `ubicacion_privada` | FK a `certificados` y a `auditoria_eventos(evento_id)` | CHECK (certificado o evento); CHECK sha256; trigger inmutable | — | **Extender.** Se agrega `documento_id` → `documentos`. El código usa los nombres heredados (`archivo_sha256`, `ubicacion_segura`). |
| `auditoria_eventos` (frente a `eventos_auditoria` nueva) | Heredada: `evento_id`, actor (identidad), sesión, correlación, acción, `recurso_tipo`, `recurso_id` (text), resultado, IP, JSON y la cadena `hash_anterior` → `hash_evento` | FK `actor_id` → `identidades`, `sesion_id` → `sesiones_firma` | 3 índices; CHECKs de hash y resultado; trigger inmutable | `evidencias`, `auditoria_cambios` | **Reutilizar sin cambios; `eventos_auditoria` no se crea.** El código agrega eslabones a la cadena (`hash_evento_firma`, serializado con `pg_advisory_xact_lock`). |

## 3. Registro de objetos

### 3.1 Extendidos (solo adiciones)

| Objeto | Cambio | Motivo |
|---|---|---|
| `identidades` | + `usuario_id bigint`, `fk_identidades_usuario` → `esart_ref.usuarios`, índice único parcial `uq_identidades_usuario` | Enlace 1:1 entre la identidad de firma y el usuario real de ESART. No crea otra cuenta: no tiene contraseña, TOTP ni sesión. |
| `evidencias` | + `documento_id`, `fk_evidencias_documento`, `ix_evidencias_documento` | Evidencias de documentos ESART. |
| `solicitudes_firma` | + `documento_id`, `documento_version_id`, `fk_solicitudes_version_documento`, `ck_solicitudes_objeto_unico`, `uq_solicitudes_documento_firmante`; `certificado_id` y `version_id` admiten NULL | Firmar documentos ESART con la misma cadena heredada. Las 0 filas existentes cumplen el CHECK. |
| `desafios_autenticacion` | + `ck_desafios_solo_firma` (`proposito = 'FIRMAR'`) | Un solo mecanismo de login/MFA: el de ESART. |
| `totp_factores`, `totp_recuperacion`, `sesiones_firma` | + trigger `trg_autenticacion_heredada` (rechaza INSERT/UPDATE), función `rechazar_autenticacion_heredada()`; `REVOKE ALL` a `esart_aplicacion` | Las tablas se conservan, pero no pueden recibir secretos TOTP ni sesiones paralelas. |

### 3.2 Creados (no existían)

| Objeto | Descripción |
|---|---|
| `documentos` | Certificaciones y oficios de ESART: FK a `esart.personal_militar`, `esart.cursos` y `esart_ref.usuarios`; CHECK de tipo y estado; número único. |
| `versiones_documento` | PDF privado (sha256, ruta, tamaño, MIME); UNIQUE (documento, número) y (documento, id); inmutable con el trigger **heredado** `bloquear_mutacion_evidencia()`. |
| Componente `FIRMA_DOCUMENTOS` | Malla ESART: acceso, crear y leer solo para ADMINISTRADOR (igual que antes). |
| Permisos de `esart_aplicacion` | SELECT/INSERT en `documentos`, `versiones_documento`, `evidencias` y `auditoria_eventos`. UPDATE (`estado`, `version_actual`, `emitido_en`) en `documentos`. SELECT/INSERT por columnas en `identidades`. USAGE de las secuencias de `identidades` y `auditoria_eventos`. |

### 3.3 Reutilizados sin cambios de estructura

`autorizaciones_firmantes`, `consentimientos_firma`, `firmas_certificado` (la firma se liga a la
solicitud, sirva para certificado o documento), `auditoria_eventos`, `auditoria_cambios`,
`certificados`, `versiones_certificado`, `plantillas_certificado`, `validaciones_criptograficas`,
`verificaciones_publicas`, `roles_firma`, `permisos_firma`, `rol_permiso` y `asignaciones_rol`.

Dentro de `esart_firma` no se borra, trunca ni renombra nada heredado, y no se reinicia ninguna
secuencia.

### 3.4 Descartados de la p0018 anterior

`eventos_auditoria`, `firmas_documento` y la función `bloquear_cambio_inmutable`. Ya hay
equivalentes heredados: `auditoria_eventos`, `firmas_certificado` y `bloquear_mutacion_evidencia`.

## 4. Guardas de la migración

1. **Entorno** (sin cambios): `ENTORNO=desarrollo`, PostgreSQL local, cuenta `esart_migrador` no
   superusuario, base `esart_db` o `esart_db_p0018_restore_test` (esta última con
   `ESART_VALIDAR_P0018_COPIA=1`).
2. **Huella exacta del esquema heredado:** las 21 tablas, con sus columnas en orden, tipos,
   nulabilidad, todas sus restricciones y la función `bloquear_mutacion_evidencia()`. La referencia es
   `migraciones_principal/datos/p0018_esart_firma_heredado.json`, sacado del inventario. Si algo
   difiere, la migración aborta sin cambios.
3. **Precondiciones:**
   - no existen todavía `documentos`, `versiones_documento`, las columnas o restricciones nuevas,
     la función nueva ni `FIRMA_DOCUMENTOS`;
   - `totp_factores`, `totp_recuperacion` y `sesiones_firma` están vacías (si no, hay que decidir a
     mano qué hacer con esos datos);
   - no hay desafíos heredados de LOGIN/MFA.
4. **Preservación:**
   - antes y después se comparan los conteos exactos de las 21 tablas y el contenido completo (md5)
     de `roles_firma`, `permisos_firma`, `rol_permiso` y `asignaciones_rol`;
   - al final se verifica que cada tabla heredada conserve sus columnas originales, más solo las
     nuevas.

   Cualquier diferencia aborta la transacción completa.
5. **Downgrade:** falla cerrado si ya hay documentos, evidencias o solicitudes de documentos, o
   identidades enlazadas. Si procede, retira solo lo que agregó p0018. **Nunca** borra el esquema ni
   las tablas heredadas.
6. **Instalación nueva** (sin `esart_firma`: otros desarrolladores, laboratorio): crea primero las 21
   tablas tal como están en `esart_db` (sin datos) y después aplica la misma conciliación. Así todas
   las bases quedan con la misma estructura.

## 5. Pruebas en PostgreSQL aislado

`backend/herramientas/probar_p0018_aislada.py` crea un clúster PostgreSQL 18 efímero en un puerto
aleatorio. No usa `.env` ni `esart_db`. La copia queda a nombre de `esart_migrador`, igual que una
restauración `--no-owner`, y se migra con Alembic y sus guardas reales. Resultado: **25/25
comprobaciones correctas.**

| Grupo | Comprobaciones |
|---|---|
| Punto de partida | Copia en p0014; 21 tablas heredadas; 13 registros (5 roles y 8 permisos de ejemplo) |
| Migración p0015 → p0018 | Revisión final p0018; existen las 21 tablas; conteos idénticos; roles y permisos idénticos (ids, códigos y descripciones); solo se crearon `documentos` y `versiones_documento` (no `eventos_auditoria`); `FIRMA_DOCUMENTOS` presente |
| Downgrade limpio | Vuelve a 21 tablas con los mismos datos; después se puede volver a subir |
| Funcional (como `esart_aplicacion`) | Ver detalle abajo |
| Downgrade con datos | Falla cerrado; la base sigue en p0018; roles y permisos intactos |
| Guardas | Esquema heredado alterado → aborta en p0017 sin crear nada; sesión heredada con datos → aborta sin cambios |
| Instalación nueva | Sin `esart_firma`: queda con las 21 + 2 tablas en p0018 |

Pruebas funcionales, como `esart_aplicacion`:
- **Persistencia:** certificación y oficio persistidos con `registrar_documento`; una versión por
  documento.
- **Identidad y auditoría:** una sola identidad, enlazada al usuario ESART; dos eventos de auditoría
  encadenados y verificables (`hash_anterior` = `hash_evento` del evento previo; se recalcula el hash);
  evidencias `PDF_ORIGINAL` ligadas a documento y evento.
- **Inmutabilidad:** las versiones y la auditoría no admiten UPDATE ni DELETE.
- **Autenticación heredada:** el TOTP heredado rechaza registros nuevos; la API no puede leerlo; un
  desafío de LOGIN heredado se rechaza.
- **Cadena de firma completa sobre un documento ESART:** autorización → solicitud → desafío `FIRMAR`
  → consentimiento → firma. Una solicitud sin certificado ni documento se rechaza.

Además, la suite completa de `backend/pruebas` pasa. `test_persistencia_principal.py` ahora exige
además que todo id de revisión quepa en `alembic_version`.

## 6. Defectos encontrados y corregidos durante la prueba

| Defecto | Efecto en `esart_db` | Corrección |
|---|---|---|
| La guarda comparaba `inet_server_addr()::text` con `127.0.0.1`, pero PostgreSQL devuelve `127.0.0.1/32` | `env.py`, p0018 y `respaldo_previo_firma_documental.py` habrían rechazado **toda** conexión, incluido el respaldo del runbook | `host(inet_server_addr())` en los tres; la guarda se mantiene |
| El id de revisión de p0016 (`p0016_cursos_artilleros_importacion`) tenía 35 caracteres y `alembic_version.version_num` es `varchar(32)` | p0016 habría fallado al registrar la versión y revertido toda la actualización | Id `p0016_cursos_artilleros` (el archivo conserva su nombre); prueba nueva que lo vigila |

## 7. Procedimiento pendiente para el operador

No hay autorización para migrar `esart_db`. Antes de pedirla:

1. Rotar la contraseña expuesta de `postgres` (`\password postgres`).
2. Ejecutar `preparar_roles_firma.sql` y generar el respaldo con
   `herramientas/respaldo_previo_firma_documental.py` (ya corregido).
3. Restaurar en `esart_db_p0018_restore_test` con `--no-owner --no-privileges` y dueño
   `esart_migrador`, y ejecutar `docs/ESART_P0018_CONTEOS_EXACTOS_SOLO_LECTURA.sql`: deben salir 13
   registros.
4. En la copia: `ESART_VALIDAR_P0018_COPIA=1` y `alembic upgrade head` como `esart_migrador`. Si la
   estructura real difiere del inventario, p0018 se detendrá y dirá en qué tabla.
5. Comparar otra vez los conteos, roles y permisos, y probar la generación de documentos contra la
   copia.
6. Con resultados aprobados, solicitar la autorización expresa para `esart_db`.

## 8. Riesgos pendientes

| Riesgo | Impacto | Mitigación / decisión requerida |
|---|---|---|
| En `esart_db` las tablas son de `postgres`; `ALTER TABLE` exige ser el dueño | p0015, p0017 y p0018 no pueden ejecutarse como `esart_migrador` sobre la base original (en la copia sí, porque es su dueño) | Decidir antes de migrar `esart_db`: transferir la propiedad de los esquemas a un rol propietario no superusuario del que `esart_migrador` sea miembro, o ejecutar con ese rol propietario. No usar `postgres` como migrador. |
| Los valores reales de los 5 roles y 8 permisos no se conocen (la cuenta de la API no los puede leer) | El laboratorio usó valores de ejemplo; solo prueba que no cambian | Revisarlos en la copia restaurada; p0018 no los modifica. Queda por definir si `roles_firma`/`asignaciones_rol` serán la fuente de los roles de firma o si basta la malla ESART (`FIRMA_DOCUMENTOS`). |
| El cuerpo real de `bloquear_mutacion_evidencia()` no está en el inventario | En instalaciones nuevas se crea una versión que rechaza UPDATE/DELETE; en `esart_db` se usa la real sin tocarla | Comparar `pg_get_functiondef` en la copia. |
| El inventario no distingue serial de IDENTITY en las 7 columnas `id` con secuencia | Solo afecta a instalaciones nuevas (se crean como IDENTITY BY DEFAULT); la huella no compara defaults | Revisar en la copia si se quiere igualar exactamente. |
| La fórmula de `hash_evento` heredada es desconocida | La tabla está vacía: la cadena empieza con la fórmula de ESART (`hash_evento_firma`) | Si aparecen eventos heredados en la copia, p0018 no los altera, pero la verificación de la cadena histórica necesitaría la fórmula original. |
| p0015 parece aplicada a mano y p0016 se ejecutó con el SQL manual | p0015 reemplaza el mismo CHECK y p0016 es idempotente; en el laboratorio corrieron sobre una base limpia | Verificar en la copia que p0015/p0016 terminan sin cambios inesperados (conteos de `artillero_cursos` antes y después). |
| `firmas_certificado` guarda también las firmas de documentos | El nombre ya no describe todo su uso | Es solo nombre; la relación correcta pasa por la solicitud. Si se desea, se puede crear después una vista con un nombre genérico. |

## 9. Archivos

| Archivo | Cambio |
|---|---|
| `backend/migraciones_principal/versions/p0018_firma_documental.py` | Migración conciliada (reemplaza la anterior) |
| `backend/migraciones_principal/datos/p0018_esart_firma_heredado.json` | Huella y estructura de las 21 tablas heredadas |
| `backend/aplicacion/servicios/almacenamiento_documental.py` | Auditoría encadenada heredada, identidad enlazada y nombres heredados de evidencias |
| `backend/herramientas/probar_p0018_aislada.py` | Laboratorio de la cadena p0015 → p0018 |
| `backend/migraciones_principal/env.py`, `backend/herramientas/respaldo_previo_firma_documental.py` | Corrección de la guarda de servidor local |
| `backend/migraciones_principal/versions/p0016_*.py`, `p0017_*.py` | Id de revisión de p0016 acortado |
| `backend/pruebas/test_persistencia_principal.py` | Cadena p0016 corregida; los ids de revisión deben caber en 32 caracteres |
