# Preflight ESART: resultados y autorización pendiente

Fecha: 16 de noviembre de 2026. Alcance: inspección de fuentes y catálogo real en una transacción REPEATABLE READ, READ ONLY, terminada con ROLLBACK. No se invocó env.py ni se ejecutaron migraciones, GRANT, DML, cambios de esquema, commit o push. Se reutilizó la conexión autorizada de la aplicación; no se dispone de conexión del propietario configurada.

Evidencia actual: [ESART_ALEMBIC_PREFLIGHT_ACTUAL.json](ESART_ALEMBIC_PREFLIGHT_ACTUAL.json). Destino: 127.0.0.1:5432/esart_db, PostgreSQL 18.7, rol esart_aplicacion. El inventario ejecuta las comprobaciones de catálogo y los conteos permitidos, sin exponer secretos. **No equivale a haber ejecutado íntegramente el SQL del propietario.**

## Matriz de decisión

Actualización del propietario comunicada por el usuario el 16 de noviembre de 2026: DBCode devolvió cero huérfanos en las cinco tablas y cero contextos incompatibles. Se incorpora como evidencia reportada por el operador; no se alteró el JSON del inventario previo ni se repitieron consultas desde esta sesión. No se recibieron todavía las salidas completas de identidad de conexión, historial y catálogo del propietario.

| Comprobación | Resultado | Evidencia y alcance |
|---|---|---|
| Destino y modo de consulta | APROBADO | Base correcta; transacción de solo lectura y rollback. |
| Versión aplicada p0004_captcha_local | ADVERTENCIA | Confirmada por el usuario; no verificada independientemente: el rol no puede leer esart.alembic_version. |
| Grafo de revisiones | APROBADO | Dos ramas con IDs distintos confluyen en p0010_merge_hu10_totp. p0004 es la base, no debe reaplicarse. |
| Siete tablas existentes y tipos | APROBADO | PK y tipos compatibles con las nuevas relaciones; no se recrean las tablas. Esto no certifica todos sus datos. |
| Huérfanos usuario_totp | APROBADO | Último resultado del propietario: 0; existe discrepancia histórica 1→0 pendiente de explicación. |
| Huérfanos totp_recuperacion | APROBADO | Propietario reporta 0; coincide con inventario previo. |
| Huérfanos desafios | APROBADO | Propietario reporta 0; coincide con inventario previo. |
| Huérfanos autorizaciones y auditoria | APROBADO | Propietario reporta 0 en cada tabla; elimina el bloqueo anterior por falta de lectura del rol de aplicación. |
| Contexto compuesto de autorizaciones | APROBADO | Propietario reporta contextos_incompatibles=0. |
| Discrepancia usuario_totp 1→0 | ADVERTENCIA | No se ha determinado causa ni se ha recibido evidencia comparable; repetir bajo escritores detenidos antes de autorizar ejecución. Si reaparece un huérfano, es BLOQUEANTE. |
| Restricciones actuales | APROBADO | Las restricciones inventariadas figuran validadas; no aparecen los nombres nuevos de FK/UQ propuestos ni los triggers/función TOTP. No prueba ausencia de datos incompatibles con las nuevas FK. |
| Colisiones HU-10 | ADVERTENCIA | No aparecen parametros_habilitacion ni auditoria_eventos como tablas. Revisar destino/historial con propietario antes de CREATE; p0009 presupone el CHECK creado por p0007. |
| Políticas TOTP | APROBADO | LOGIN_TOTP y DESBLOQUEO_TOTP existentes, activas, TOTP requerido y 120 segundos; INSERT ON CONFLICT DO NOTHING las conserva. |
| Cambios de datos HU-10 | ADVERTENCIA | UPSERT modifica componentes existentes; inserta roles y permisos ausentes. Requiere revisar la malla destino. |
| Privilegios ampliados TOTP | BLOQUEANTE | Autorizaciones aún sin permiso expreso; también se amplía lectura de auditoría y acceso a secuencias. |
| CAPTCHA y bloqueo: revisión de upgrade | APROBADO | Desde las sucesoras de p0004 hasta p0010 no hay escrituras de contadores de acceso, bloqueado_hasta ni desafíos CAPTCHA. No cambia el umbral de siete intentos ni las tres horas. |
| Conservación después del despliegue | ADVERTENCIA | Aún no se ejecutó migración; la comparación antes/después y las pruebas reales son futuras. No confundir revisión estática con validación funcional posterior. |

## Permisos exactos sobre seguridad.autorizaciones

La propuesta p0005_integracion_totp concede a esart_aplicacion únicamente lo siguiente sobre esta tabla:

Las sentencias siguientes son transcripción para revisión, **no ejecutadas**:

```sql
GRANT SELECT, INSERT ON seguridad.autorizaciones TO esart_aplicacion;
GRANT UPDATE (resultado, consumida_en)
  ON seguridad.autorizaciones TO esart_aplicacion;
```

| Permiso | Justificación en el código | Límites/riesgo |
|---|---|---|
| SELECT sobre toda la tabla | El ORM carga la autorización para comprobar titular, desafío, política, huella de operación, vencimiento y consumo; posteriormente usa SELECT FOR UPDATE. | La concesión permite leer todas las filas; el filtro por actor lo aplica el backend, no RLS (deshabilitado en esta tabla). |
| INSERT sobre toda la tabla | Registra la autorización de una operación después de verificar TOTP y contexto. | SQL no impide por sí solo que el rol inserte otra autorización; depende del servicio y las restricciones. |
| UPDATE(resultado) | Transición AUTORIZADA → CONSUMIDA al ejecutar la operación. SELECT FOR UPDATE también necesita UPDATE de alguna columna. | No concede UPDATE de actor, desafío, política ni huella. |
| UPDATE(consumida_en) | Marca el instante de consumo en la misma transacción; rechaza reutilizaciones. | No concede UPDATE de vencimiento. |

No solicita DELETE, TRUNCATE, REFERENCES ni UPDATE general sobre autorizaciones. Su ID es UUID generado por el servicio: no solicita una secuencia para esta tabla.

Fuentes: p0005_integracion_totp.py; AutorizacionAcciones.verificar/ejecutar_autorizada en servicios/autorizacion_acciones.py; verificar_integridad_acciones en servicios/totp.py.

**Estos permisos corresponden a autorizaciones de operaciones sensibles, no al login, QR o desbloqueo TOTP.** requisitos_totp.py excluye esta tabla de los requisitos del login. La comprobación adicional de integridad/permisos se invoca desde el servicio de acciones sensibles; conceder permisos tampoco registra automáticamente adaptadores de negocio. No justificar este acceso como imprescindible para autenticar usuarios. Si no se aprueba, no ejecutar la propuesta actual sin revisar previamente su alcance; este preflight no ha editado la migración.

## Datos y permisos incorporados por HU-10 y sus antecesoras

- p0005_componentes_y_malla: conserva roles existentes y permisos ya presentes mediante DO NOTHING, pero incorpora los faltantes. El UPSERT de componentes sobrescribe nombre, ruta, orden, padre y activo. Puede desactivar módulos de segunda entrega ya habilitados. Agrega VER_DOCUMENTO_COMPLETO (AL) a ADMINISTRADOR y USUARIO si falta; amplía visibilidad de identificación militar. El rol ADMINISTRADOR recibe por defecto USUARIOS=ACLUD, PARAMETROS_HABILITACION=ALU, PERMISOS=ALU y AUDITORIA=AL, además de módulos de personal; USUARIO recibe dashboard y consultas de personal. La lista exacta está en COMPONENTES/MALLA de esa revisión. La aplicación obtiene SELECT de componentes y mallas.
- p0006: crea parámetros con SACLI/SACME, vigencia de 12 meses, alerta de 60 días y aptitud exigida; añade lectura académica y UPDATE limitado de parámetros. No actualiza estados de usuarios.
- p0007: crea auditoria_eventos, índices, CHECK y triggers inmutables; CREATE OR REPLACE de la función de protección; concede SELECT/INSERT y USAGE de su secuencia, revoca mutación de PUBLIC. No borra auditoría en upgrade.
- p0008: concede SELECT/INSERT/UPDATE/DELETE de ambas mallas al rol de aplicación; no ejecuta DELETE sobre sus datos en upgrade. Las restricciones de actor se aplican en el servicio.
- p0009: amplía el CHECK de acciones y concede UPDATE de contrasena_hash, activo, requiere_cambio_contrasena y actualizado_en. No modifica contraseñas, banderas, intentos ni bloqueos por sí misma; la columna requerida ya existe en el catálogo.
- p0010: merge sin operaciones; no vuelve inocuos los efectos de sus antecesoras.

No se ejecutaron downgrades ni sus borrados. Los permisos SQL nuevos no son cambios inmediatos de los datos de usuarios, pero habilitan futuras modificaciones desde la aplicación y requieren aprobación.

## Controles de seguridad preservados y evidencia pendiente

### Incidencia de integridad: usuario_totp 1→0

El operador informa que el primer preflight mostró un huérfano y la consulta posterior devolvió cero. Los inventarios de esta sesión disponibles previamente devolvían cero en esta tabla; no se debe atribuirles el resultado inicial informado ni sobrescribirlos para homogeneizar la evidencia. No se conoce el identificador afectado ni se proporcionaron horas, consulta exacta, identidad de conexión o límites de transacción de ambas ejecuciones.

Con las mismas tablas, consulta y visibilidad, dentro de una sola transacción REPEATABLE READ, READ ONLY, el conteo no debería variar por commits concurrentes. Si ambas ejecuciones pertenecieron realmente a esa misma transacción y produjeron 1 y 0, la discrepancia de consulta, conexión o evidencia debe investigarse antes de aprobar. Entre transacciones distintas, son hipótesis posibles una escritura concurrente que creó el usuario referenciado o cambió/eliminó la referencia, una transacción propia de DBCode con visibilidad distinta, o un destino/consulta diferente. **Ninguna causa está confirmada; no se realizó ni se recomienda una corrección de datos para explicar el resultado.**

Conservar las dos salidas originales y comprobar base, servidor, puerto, rol, fecha/hora, SQL exacto y transacción. Antes de la ventana de actualización, detener escritores y repetir el SQL de preflight completo como propietario; todos los conteos deben seguir en cero en un mismo snapshot. Si no se puede reproducir cero de forma controlada, no autorizar el upgrade. El resultado posterior cero habilita la evaluación de integridad actual reportada, pero no demuestra por sí solo cómo desapareció el huérfano.

La inspección de los cuerpos upgrade pendientes no encontró UPDATE/DELETE sobre esart.desafios_captcha ni escrituras de intentos_fallidos_consecutivos/bloqueado_hasta. TOTP sí concede UPDATE del campo intentos de **seguridad.desafios**: este es el contador del desafío TOTP, diferente al contador de contraseñas/CAPTCHA; concederlo no actualiza sus valores. Tampoco se reescriben secretos TOTP ni se emiten JWT mediante migraciones.

La aplicación puede seguir recibiendo tráfico durante una lectura; por eso una huella posterior diferente no demuestra por sí sola un efecto de migración. Capturar el baseline completo del SQL de propietario con escritores detenidos, y compararlo después antes de abrir tráfico. Este paso aún no se ha completado. Las pruebas futuras deben verificar CAPTCHA, 7 intentos/3 horas, contraseña temporal→MFA y ausencia de JWT definitivo antes del factor.

## Autorizaciones y siguiente paso

Requieren autorización expresa del propietario antes del despliegue:

1. La ampliación de privilegios sobre autorizaciones, lectura completa de auditorías y USAGE/SELECT de secuencias identity (estos últimos exceden lo necesario para inserción identity ordinaria).
2. El UPSERT de componentes y las nuevas entradas de malla, especialmente visibilidad de documento completo; los permisos de edición de malla y administración de usuarios.
3. La ejecución de DDL (FK, UQ, validaciones, índices, tablas, CHECK, funciones y triggers) y sus bloqueos durante una ventana acordada.
4. El acceso/ubicación del respaldo completo que contiene datos sensibles y el ensayo de restauración aislada; la posterior ejecución de upgrade con cuenta propietaria en el destino comprobado.

**Es seguro preparar el procedimiento y la ventana del respaldo**, sin modificar la base. El procedimiento ya está en ESART_ALEMBIC_P0010_DIAGNOSTICO_Y_PLAN.md. No se ha ejecutado ningún respaldo. **Todavía no es seguro recomendar la ejecución de migraciones**: faltan las salidas completas del propietario, la comprobación controlada de la discrepancia 1→0 y las decisiones de privilegios/malla. Los seis conteos reportados en cero eliminan los bloqueos anteriores de integridad no verificable, pero no autorizan por sí mismos permisos ni DDL. La autorización final de upgrade debe esperar al preflight completo y al respaldo/restauración de ensayo aceptados. No usar stamp ni borrar filas para resolver discrepancias.

Para completar la evidencia pendiente, conservar las salidas completas de ESART_ALEMBIC_PREFLIGHT_PROPIETARIO.sql en la conexión autorizada (READ ONLY y ROLLBACK), sin conceder privilegios adicionales a la aplicación y sin compartir credenciales. La versión p0004 sigue confirmada por declaración del usuario; falta adjuntar la salida del historial. La repetición final con escritores detenidos debe mantener los seis conteos en cero.
