# Conciliación preliminar del esquema de firma

> **Reemplazada** por [ESART_P0018_CONCILIACION_DEFINITIVA.md](ESART_P0018_CONCILIACION_DEFINITIVA.md) (matriz definitiva, migración conciliada y pruebas en PostgreSQL aislado). Se conserva como registro del diagnóstico.

Fecha: 2026-11-19. Inspección de catálogos en transacción `READ ONLY` contra PostgreSQL local de desarrollo con la cuenta de aplicación. No se hicieron cambios SQL.

## Inventario disponible

La captura de catálogo de 21 tablas está en [ESART_FIRMA_INVENTARIO.json](ESART_FIRMA_INVENTARIO.json). Incluye columnas, tipos, nulabilidad, defaults, PK/FK/CHECK/UNIQUE, índices, secuencias asociadas, triggers, propietarios y estimación de filas de estadísticas. Las 21 tablas son propiedad de `postgres`.

La cuenta no tiene `SELECT` sobre esas tablas: los conteos exactos están marcados `not_selectable`. `pg_stat_user_tables.n_live_tup` es una estimación no confiable para este propósito (la mayoría aparece como cero); no demuestra que estén vacías. No se inspeccionaron valores, firmas, documentos ni identidades. Los triggers relevantes usan `esart_firma.bloquear_mutacion_evidencia()` para rechazar UPDATE/DELETE en registros de auditoría y evidencia.

El inventario contiene estas tablas: `asignaciones_rol`, `auditoria_cambios`, `auditoria_eventos`, `autorizaciones_firmantes`, `certificados`, `consentimientos_firma`, `desafios_autenticacion`, `evidencias`, `firmas_certificado`, `identidades`, `permisos_firma`, `plantillas_certificado`, `rol_permiso`, `roles_firma`, `sesiones_firma`, `solicitudes_firma`, `totp_factores`, `totp_recuperacion`, `validaciones_criptograficas`, `verificaciones_publicas` y `versiones_certificado`.

## Matriz preliminar: colisiones directas de p0018

| Tabla existente | Estructura actual | Estructura requerida por p0018 | Diferencias / riesgo | Acción propuesta |
| --- | --- | --- | --- | --- |
| `autorizaciones_firmantes` | UUID; `identidad_id`, `tipo_certificado`, cargo/grado, vigencia, concedente/revocación; referencias a identidades internas | `usuario_id`, `tipo_documento`, cargo y concedente referidos a `esart_ref.usuarios` | No equivalentes: modelo de identidad y semántica de autorización difieren; cambios directos podrían romper autorizaciones históricas. | Conservar. Definir una relación explícita y validada entre identidad interna y usuario ESART; añadir soporte de tipo documental solo tras inventariar valores/reglas. |
| `solicitudes_firma` | `certificado_id`, `version_id`, firmante por identidad, autorización, orden, estado, hash QR y tiempos; FK compuesta a `versiones_certificado` | `documento_id`, `version_id`, firmante por usuario y FK compuesta a `versiones_documento` | Certificado obligatorio y versión antigua; el oficio remisorio no cabe sin nueva relación y no hay equivalencia demostrada de IDs. | Conservar solicitudes. Añadir relaciones documentales nullable o una tabla puente nueva; no reinterpretar `version_id`. |
| `consentimientos_firma` | solicitud, texto y versión, hash del documento, fecha, IP/agente y desafío; trigger inmutable | campos comunes más `usuario_id` referido al usuario ESART | La tabla ya tiene datos de contexto extra y vínculo al desafío; falta la identidad ESART explícita en el esquema requerido. | Conservar e inmutar. Relacionar usuario solo después de validar la correspondencia solicitud–firmante; preferir dato añadido nullable con backfill auditado. |
| `eventos_auditoria` | cadena hash con `evento_id`, actor/sesión, tipo/recurso, resultado, IP, JSON y trigger inmutable | UUID, usuario, correlación, acción, recurso UUID y resultado | No equivalentes: la actual es una auditoría encadenada de seguridad; reemplazarla o recrearla rompe trazabilidad y semántica. | Reutilizar el registro inmutable existente para nuevas acciones mediante campos actuales/JSON; no crear segunda auditoría con nombre colisionante ni alterar el hash histórico. |
| `evidencias` | certificado, evento, clase, `archivo_sha256`, ubicación segura y retención; trigger inmutable | documento/evento, clase, `sha256`, ubicación privada | FK certificado en vez de documento; hash/ubicación con nombres distintos; falta inspección de filas y rutas privadas. | Conservar. Agregar FK documental nullable (o tabla enlace) sin reescribir evidencias; validar rutas y hashes en copia. |

El término «of icio» en la fila de solicitudes se refiere a oficio remisorio; no existe actualmente un enlace genérico para ese tipo documental.

## Objetos requeridos que no tienen colisión de nombre

| Objeto p0018 | Estado/relación con legado | Diferencia / acción propuesta |
| --- | --- | --- |
| `documentos` | No existe con ese nombre; hay `certificados` con datos emitidos, persona/curso como referencias de texto, plantilla y estado. | Crear entidad genérica aditiva para certificados y oficios, manteniendo `certificados` intacta. Evaluar puente de certificado existente a documento y conservar IDs. |
| `versiones_documento` | No existe con ese nombre; existe `versiones_certificado`, FK a `certificados` con hash, ruta segura, tamaño, MIME e integridad de versión. | Crear tabla genérica o extensión compatible; no renombrar ni copiar archivos hasta comparar hash y verificar almacenamiento. |
| `firmas_documento` | No existe con ese nombre; existe `firmas_certificado`, solicitud/consentimiento, métodos, hashes de rúbrica, certificado y PDF, con trigger inmutable. | No duplicar firmas históricas. Definir la tabla genérica para firmas futuras y/o relación a firma antigua; sin migrar filas hasta verificar relaciones y contenido. |
| Índice de documentos, auditoría/recurso e índices de solicitud | El legado ya tiene índices en sus tablas; nombres y expresiones están en el JSON. | Crear solo índices faltantes sobre tablas nuevas; no intentar crear duplicados ni renombrar índices existentes. |
| Función y triggers de inmutabilidad | Ya existen `bloquear_mutacion_evidencia()` y triggers legados. | Mantenerlos. Revisar equivalencia funcional antes de instalar cualquier nuevo trigger. |
| Componente y permisos `FIRMA_DOCUMENTOS` | p0018 hace `INSERT ... ON CONFLICT DO NOTHING` en catálogos `esart`. | Antes, inspeccionar filas y permisos existentes en la copia; el `DO NOTHING` no valida que un registro preexistente tenga la configuración esperada. |

## Revisión de las migraciones pendientes

| Revisión | Operaciones | Riesgo / privilegios |
| --- | --- | --- |
| p0015 | Reemplaza CHECK de `esart.auditoria_eventos` para añadir `PERSONAL_REGISTRADO`; no inserta filas. | Requiere propiedad de la tabla. La acción ya existe en el CHECK observado, por posible aplicación manual; no conviene repetir ciegamente. |
| p0016 | Otorga SELECT/INSERT/uso de secuencia a la aplicación y repara filas faltantes de `artillero_cursos` desde historial de cursos. | Puede insertar datos académicos válidos; requiere DML y capacidad de conceder permisos. Comparar conteos y conjuntos en el dump restaurado. |
| p0017 | Reemplaza CHECK para añadir `TOTP_RESTABLECIDO`; upsert de política administrativa de recuperación TOTP. | Requiere dueño de auditoría y DML en `seguridad.politicas_accion`. Se corrigió la lista de acciones: la versión inicial omitía acciones de p0015 y podía bloquear el CHECK o restringir auditorías válidas. |
| p0018 actual | Rechaza cualquier esquema `esart_firma` existente y crea ocho tablas, función/triggers, grants y componente/permisos. | Se detiene con el estado actual. Colisiona directamente en cinco tablas; no es conciliatoria. El downgrade también intenta retirar objetos y el esquema entero, por lo que no debe ejecutarse contra el legado. |

## Estrategia aditiva recomendada, aún no aplicada

1. Obtener respaldo actualizado y restaurarlo de forma aislada; dar acceso de lectura del dump al equipo de migración sin exponer secretos.
2. Completar conteos exactos, valores distintos relevantes (tipos/estados/acciones), restricciones, owners, grants, secuencias, triggers, vínculos de usuario e inventario de archivos en la copia. El JSON actual es metadato de catálogo, no sustituye esa revisión.
3. Conservar las 21 tablas y su historial. Crear en p0018 solo las entidades genéricas nuevas (`documentos`, `versiones_documento`, `firmas_documento`) y los índices/relaciones necesarios, con nombres que no choquen.
4. Para las cinco colisiones, diseñar cambios aditivos específicos, preferiblemente columnas/FK nullable o tablas puente. No modificar ni backfill de filas existentes hasta probar correspondencias y restricciones en la copia. Mantener intacta la cadena hash de auditoría y los triggers de inmutabilidad.
5. Ajustar la lógica de downgrade para que nunca borre el esquema heredado ni las tablas preexistentes; un downgrade debe fallar cerrado si la revisión crea objetos mezclados con objetos legados.
6. Resolver p0015–p0017 en la copia restaurada con sus operaciones reales, comparar antes/después y ejecutar los tests de PostgreSQL/documentos/auditoría.
7. Solo después de resultados aprobados puede prepararse un procedimiento para `esart_db`. Sigue prohibido ejecutar allí migraciones sin autorización expresa.

No se hizo respaldo, restauración ni prueba de migración. La contraseña PostgreSQL expuesta sigue sin rotar y no se utilizó; los conteos exactos están bloqueados por permisos. JWT, TOTP, módulos académicos y datos no fueron modificados.

## Correcciones de pruebas

`backend/seeds/fase4.py` valida la huella cruda y la forma LF normalizada, porque el snapshot registra unas migraciones con CRLF y otras con LF. Esto evita falsos positivos por checkout sin aceptar cambios de contenido. `test_persistencia_principal.py` ahora comprueba p0018 como head y los enlaces p0017→p0016; la expectativa anterior p0016 era obsoleta respecto a la cadena actual.

La suite `pytest backend/pruebas -q --tb=short` completó al 100% sin fallos; hubo tests omitidos según configuración. Se añadió una aserción que compara las acciones de p0017 con el conjunto completo de p0015 más `TOTP_RESTABLECIDO`. No se ejecutaron pruebas contra una base restaurada porque esa base no existe todavía.
