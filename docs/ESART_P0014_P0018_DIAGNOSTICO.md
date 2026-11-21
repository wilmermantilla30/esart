# Diagnóstico de actualización Alembic p0014–p0018

Fecha: 2026-11-19. Alcance: preparación de desarrollo; no se ejecutaron escrituras en `esart_db`.

## Estado verificado

- El operador confirmó que `esart.alembic_version` indica `p0014_cursos_del_instructor`; la cuenta de aplicación no pudo leer esa tabla para confirmarlo independientemente.
- El grafo local es `p0014` → `p0015` → `p0016` → `p0017` → `p0018`, con `p0018_firma_documental` como head.
- Los propietarios informados para `esart.alembic_version` y `esart.auditoria_eventos` son `postgres`.
- La consulta de catálogo detectó que `esart_firma` ya existe con 21 tablas heredadas, propiedad de `postgres`. Entre ellas están `autorizaciones_firmantes`, `solicitudes_firma`, `consentimientos_firma`, `eventos_auditoria` y `evidencias`, además de tablas de sesiones, TOTP, certificados, auditoría e identidades; también hay secuencias, índices, restricciones, triggers y la función `bloquear_mutacion_evidencia`.
- No fue posible consultar el contenido de las tablas heredadas con `esart_aplicacion`; no se puede asumir que estén vacías.
- Las señales de deriva manual indican que p0015 parece aplicado parcialmente: el CHECK de auditoría ya incluye `PERSONAL_REGISTRADO`. Los permisos requeridos por p0016 parecen presentes y no se detectaron filas académicas faltantes según la consulta previa. p0017 parece pendiente: el CHECK no incluye `TOTP_RESTABLECIDO` y falta la política `USUARIO_RESTABLECER_TOTP`.
- No existen los roles `esart_migrador` ni `esart_respaldo`.
- La URL de superusuario fue retirada de `backend/.env`, pero la contraseña expuesta no ha sido rotada. No se muestra ni se reutiliza aquí.

## Riesgos y compatibilidad

1. **No ejecutar p0018 tal como está.** Su guarda detectará `esart_firma` y abortará. Si se elimina la guarda, intentará crear tablas que ya existen. Retirar la guarda o borrar/renombrar el esquema podría perder el acceso al historial heredado y no es una solución segura.
2. **p0015 y p0017 requieren propiedad de auditoría.** Ambos reemplazan el CHECK de `esart.auditoria_eventos`; PostgreSQL no ofrece un privilegio `GRANT ALTER`. `esart_migrador` no puede ejecutarlos sobre la base original con los permisos mínimos actuales.
3. **p0016 puede modificar datos académicos.** Inserta filas derivadas en `esart.artillero_cursos` si faltan y concede permisos a la aplicación. La operación es idempotente, pero debe medirse y verificarse en la copia restaurada antes de aceptar el resultado.
4. `preparar_roles_firma.sql` cubre solo p0018 si la revisión anterior es p0017; no es suficiente para la cadena p0015–p0017 en `esart_db`. No cambiar propietarios de tablas operativas para sortearlo.
5. El dump antiguo `backend/respaldos/esart_db_pre_alembic.dump` es legible por `pg_restore --list`, pero no es un respaldo actualizado y no se restauró.

## Respaldo, restauración y pruebas

No se creó un respaldo nuevo, no se restauró una copia aislada y no se ejecutaron migraciones en esta revisión. La credencial administrativa disponible previamente fue expuesta y no se usó; la cuenta de respaldo aún no existe. Por tanto no hay resultados verificables de integridad del dump, restauración, claves foráneas, persistencia documental ni auditoría en una copia migrada.

Las pruebas de unidad reportadas en la preparación anterior no prueban la compatibilidad de PostgreSQL. Para completar el objetivo hace falta, en este orden:

1. Rotar interactivamente la contraseña expuesta mediante `psql` (`\password postgres`), sin escribirla en comandos, `.env`, Git o informes.
2. Crear roles de respaldo y migración con credenciales ingresadas interactivamente. El archivo actual `backend/migraciones_principal/preparar_roles_firma.sql` debe revisarse/ampliarse para el diseño real; no otorgar membresía de `postgres`.
3. Consultar el marcador Alembic, obtener inventario y conteos de las tablas heredadas con acceso administrativo controlado, y crear un dump actualizado en el directorio privado.
4. Restaurar el dump en `esart_db_p0018_restore_test` aislada y verificar tablas académicas, usuarios, roles, permisos, hashes/contadores, secuencias e integridad referencial antes de migrar.
5. Diseñar una conciliación aditiva de p0018 que reutilice o extienda las tablas existentes sin borrar registros. Ejecutar p0015–p0018 únicamente en la copia restaurada; comparar datos académicos y de seguridad antes/después y revisar el esquema, permisos, documentos, hashes y auditoría.
6. Solo tras aprobar esos resultados se podrán preparar comandos para la base original. No se ha autorizado migrar `esart_db`.

No hay actualmente un comando seguro para `alembic upgrade p0018_firma_documental`: el código de p0018 no es compatible con el esquema manual y todavía no existe una copia restaurada validada. No usar `alembic stamp`, editar `alembic_version`, ejecutar como `postgres`, ni aplicar la migración a la base original.

## Pruebas backend ejecutadas

Se ejecutó `.venv\Scripts\python.exe -m pytest backend\pruebas -q`. La suite terminó con fallos previos/de compatibilidad del repositorio: los tests de `test_clasificacion_fase4.py` fallan al cargar por `ValueError: Migracion alterada`, y `test_persistencia_principal.py::test_historial_operativo_unico_y_sin_stamp` espera que p0016 sea el head cuando el grafo actual tiene p0018. No se corrigieron esos tests porque son ajenos a esta preparación y requieren resolver la discrepancia de expectativas/integridad primero. Los tests no validan una migración PostgreSQL restaurada.
