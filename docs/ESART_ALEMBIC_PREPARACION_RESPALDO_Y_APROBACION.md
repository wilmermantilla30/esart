# ESART: preparación del respaldo y aprobación de migraciones

Fecha: 16 de noviembre de 2026. Base de origen: esart_db, estado comunicado p0004_captcha_local. Destino de código: p0010_merge_hu10_totp. **No se han ejecutado respaldo, restauración, migraciones ni cambios de permisos en esta fase.**

Actualización de alcance: el operador confirmó que no dispone todavía de respaldo ni destino aislado confirmados y solicita únicamente comandos, sin ejecutar operaciones. La guía concreta es [comandos del operador](ESART_RESPALDO_RESTAURACION_COMANDOS_OPERADOR.md); propone esart_restauracion_pruebas en otra instancia para una prueba de restauración sin migraciones. Las referencias de este documento a esart_db en otra instancia corresponden solo al futuro ensayo Alembic, aún no autorizado.

## Estado verificable

| Elemento | Estado | Evidencia/condición |
|---|---|---|
| Herramientas locales | APROBADO | pg_dump, pg_restore y psql presentes en C:\Program Files\PostgreSQL\18\bin; pg_dump informa 18.7. |
| Integridad actual comunicada | APROBADO | Operador propietario reporta cinco conteos de huérfanos y contexto compuesto en cero. Evidencia comunicada, no nueva consulta desde esta sesión. |
| Discrepancia usuario_totp 1→0 | ADVERTENCIA | Conservar ambos resultados; causa desconocida. Repetir sin escritores y con identidad registrada. |
| Acceso para respaldo completo | PENDIENTE | La cuenta propietaria solo está disponible al operador mediante DBCode. No se alteró .env ni se solicitaron contraseñas. |
| Respaldo completo | PENDIENTE | Falta ruta privada aprobada y ejecución por propietario. No hay dump identificado para este ensayo. |
| Restauración aislada | PENDIENTE | Faltan servidor/puerto, destino limpio y archivo. No se puede afirmar restaurabilidad mediante un listado. |
| Diferencias reales HU-10 | PENDIENTE | Preparado SQL de comparación; rol de aplicación no puede consultar las mallas. |
| Permisos y migraciones | NO AUTORIZADOS | La autorización actual permite preparación y validación, no ampliación de permisos ni upgrade. |

El procedimiento detallado de respaldo y recuperación está en [diagnóstico y plan](ESART_ALEMBIC_P0010_DIAGNOSTICO_Y_PLAN.md). Este documento fija las condiciones de ejecución y la evidencia que debe acompañarlo; no lo sustituye por una afirmación de pruebas realizadas.

## Respaldo completo: procedimiento del operador

1. Designar directorio privado **fuera del repositorio**, con espacio suficiente, acceso restringido y retención acordada. Respaldar claves AES TOTP/JWT originales por el gestor seguro; el dump no sustituye esas claves. No imprimirlas ni versionarlas.
2. Verificar con la conexión autorizada base, servidor, puerto, rol y versión. No cambiar la conexión de FastAPI a postgres. Usar psql/pg_dump con credenciales del operador mediante un canal local seguro; no introducir secretos en comandos, documentos ni historial. No reutilizar el rol de aplicación para un respaldo incompleto.
3. En la ventana acordada, detener escritores según el apartado siguiente. Capturar preflight completo y comparación HU-10, con fecha e identidad, antes de cualquier actualización. Guardar resultados privados fuera del repositorio.
4. Ejecutar pg_dump 18 con formato custom y --create sobre toda esart_db, sin filtros de tablas/esquemas, sin --schema-only, --no-owner ni --no-acl. El comando completo y comprobación de código de salida están en el plan enlazado. El dump maestro conserva ownership y ACL. Capturar stderr y rechazar cualquier error; no aceptar fallback estructural.
5. Capturar globales con pg_dumpall --globals-only --no-role-passwords. Incluye definiciones de roles, membresías y tablespaces; no incluye las contraseñas excluidas. No ejecutar ese SQL global en ningún destino durante esta fase. Revisarlo para rutas/membresías y secretos en configuraciones personalizadas antes de compartirlo.
6. Obtener SHA-256 y TOC mediante pg_restore --list. Registrar versiones de herramientas, tamaño, inicio/fin y códigos de salida. Un hash demuestra integridad del archivo respecto de esa captura, no restaurabilidad.

Se puede preparar/ejecutar un respaldo sin escrituras en origen. Un snapshot pg_dump con tráfico activo es consistente, pero no representa necesariamente el mismo instante del preflight anterior. Para comparar contadores exactamente y explicar 1→0 se requiere la ventana sin escritores. No se ha detenido ningún servicio de forma automática.

## Repetición del preflight sin escritores

1. Acordar ventana y responsable. Cerrar el acceso que crea nuevas operaciones y detener las instancias FastAPI/uvicorn, workers, tareas programadas y herramientas de prueba que escriben. En este entorno lanzador.txt usa uvicorn con --reload: detener el proceso supervisor y sus hijos mediante el mecanismo normal del operador. Cerrar editores DBCode con transacciones de escritura pendientes. No matar sesiones desconocidas ni cambiar privilegios para simular mantenimiento.
2. El propietario comprueba pg_stat_activity, transacciones abiertas y posibles clientes externos. Una captura sin transacciones activas no garantiza ausencia de futuros escritores; mantener detenido su origen y vigilar durante la ventana. No ejecutar pruebas de login, QR o CAPTCHA entre baseline y postflight.
3. Abrir una transacción nueva, sin reutilizar una sesión con escrituras no confirmadas. Ejecutar [preflight del propietario](ESART_ALEMBIC_PREFLIGHT_PROPIETARIO.sql), que comienza READ ONLY y acaba ROLLBACK. Guardar todas las salidas, incluida identidad de servidor/puerto/base/rol, inicio de instancia e historial p0004. Registrar hora de inicio/fin y transaction_read_only=on en esa misma sesión.
4. Repetir los seis conteos dentro del mismo snapshot y conservar resultados; todos deben ser cero. Si usuario_totp vuelve a dar 1, detener aprobación e identificar la referencia con el propietario en privado; no borrar ni cambiar registros. Comparar las dos evidencias originales de la discrepancia (SQL, destino, horas y transacciones). No atribuir la desaparición a una corrección que no se ha demostrado.
5. Ejecutar [impacto HU-10](ESART_ALEMBIC_IMPACTO_HU10_SOLO_LECTURA.sql), también READ ONLY/ROLLBACK. Guardar resultados en la misma ventana sin escritores. La consulta registra identidad y compara valores, sin aplicar UPSERT.
6. Conservar huella de contadores/bloqueos, conteos de CAPTCHA/factores y secuencias del preflight. Congelar los archivos de migración con el manifiesto de hashes ya preparado. Si no se actualiza en esta ventana, reabrir el servicio mediante el procedimiento habitual y repetir baseline durante la ventana definitiva.

## Restauración aislada: alcance y prueba pendiente

La autorización para verificar restauración **no incluye ampliación de permisos**. Una restauración completa normalmente reproduce CREATE/ALTER, ACL y definiciones de roles. Por tanto, no se ejecutará el SQL de globales ni se reproducirán ACL mediante pg_restore bajo la restricción actual. No mezclar esta prueba con producción ni interpretar el permiso de preparar como permiso de cambiar roles.

Dos posibilidades que deben quedar acordadas con el operador:

- Ensayo limitado de datos/esquema en una instancia aislada ya provisionada, con pg_restore --no-owner --no-privileges: no prueba ownership, membresías ni ACL originales. Todavía puede haber dependencias de roles en políticas u otros objetos; no ignorar errores. No es evidencia suficiente de recuperación completa.
- Ensayo completo con ownership/ACL: requiere autorización específica **solo en la instancia aislada** para reproducir los roles/privilegios respaldados. No equivale a autorizar los GRANT nuevos de las migraciones ni el upgrade. Esta opción es la necesaria para certificar la recuperación completa prevista.

Antes de cualquier ensayo, identificar por escrito host/puerto y directorio de datos del destino, asegurando que no son el clúster productivo ni comparten almacenamiento. Usar esart_db dentro de esa instancia diferente; psql contra su base postgres debe confirmar servidor/puerto/versión e inicio de instancia. Destino vacío, sin --clean ni borrados automáticos. No usar 5432 por defecto. Desactivar integraciones externas, trabajos automáticos y acceso de usuarios reales a la copia.

Con el alcance del ensayo aprobado, usar el comando pg_restore --create --exit-on-error --dbname=postgres del plan, fijando explícitamente host/puerto/rol del destino aislado. No combinar --create con --single-transaction. No ejecutar ninguna migración en la copia en esta fase: el ensayo debe restaurar p0004 tal cual.

Criterios para marcar restauración APROBADA:

- Código de salida cero, sin errores ignorados; TOC y hash del archivo coinciden.
- Identidad inequívoca de la instancia aislada; historial restaurado p0004.
- Conteos exactos de todas las tablas de aplicación y las siete tablas de seguridad comparados con origen sin escritores; no usar estimaciones pg_class.reltuples.
- PK, FK, UNIQUE, CHECK, índices, funciones/triggers, owners y ACL comparados con catálogo del origen para el ensayo completo; diferencias explicadas y aprobadas. La versión actual aún no contiene las nuevas FK TOTP.
- Cinco huérfanos y contexto compuesto permanecen en cero; baseline de contadores/bloqueos, CAPTCHA y estados TOTP coincide.
- Secuencias: nombre, propiedad, identidad, incrementos y estado restaurado comparados sin nextval ni setval manual. No probar escrituras de usuarios para verificar secuencias.
- Verificación controlada de descifrado TOTP con la clave original, sin revelar secretos ni provocar login/cambios de factor. Si no se realiza, registrar ese límite en lugar de darlo por aprobado.

Registrar duración de recuperación y conservar logs privados. El tiempo de upgrade sigue desconocido: su ensayo necesita autorización posterior independiente.

## Privilegios TOTP: mínimos y excesos de la propuesta

| Capacidad | Necesidad real | Dictamen |
|---|---|---|
| USAGE seguridad | Resolver objetos del esquema | Necesario. |
| SELECT usuario_totp, totp_recuperacion, politicas_accion, desafios | ORM carga entidades y valida estado/contexto/política | Necesario para los flujos implementados. |
| INSERT usuario_totp, totp_recuperacion, desafios, auditoria, auditoria_cambios | Vinculación, recuperación, desafíos y trazabilidad | Necesario según flujo implementado. |
| UPDATE por columnas en factor, recuperación y desafío | Activación/revocación, protección contra replay, intentos y consumo | Necesario; conservar las listas limitadas de requisitos_totp.py. No implica UPDATE de usuarios ni CAPTCHA. |
| SELECT auditoria(id,fecha_evento), auditoria_cambios(id,creado_en) | RETURNING del ORM | Necesario para estas inserciones. El SELECT completo de ambas tablas que pide la migración excede este mínimo. |
| SELECT/INSERT autorizaciones; UPDATE(resultado,consumida_en) | Emitir y consumir autorizaciones de operaciones sensibles | Necesario para ese módulo; no para login/QR/desbloqueo. Requiere aprobación expresa independiente. No DELETE/TRUNCATE ni UPDATE general. |
| USAGE/SELECT de cuatro secuencias identity TOTP | No son necesarios para generación interna de identity y RETURNING actuales | Exceso respecto del flujo mínimo; no confundir con serial ni con permisos de la secuencia HU-10. |
| Revocación de mutación de auditoría | Endurecimiento acompañado de triggers inmutables | La propuesta ejecuta REVOKE; también está excluido de la autorización actual. Revisar privilegios heredados/PUBLIC/por columna antes de afirmar que elimina toda vía de mutación. |

Las listas exactas y justificación de autorizaciones están en [matriz preflight](ESART_ALEMBIC_PREFLIGHT_RESULTADOS.md) y requisitos_totp.py. Las migraciones actuales no se han editado para retirar excesos. Si se decide reducirlos, revisar una propuesta no aplicada, regenerar hashes y volver a validar; no aprobar los archivos actuales como si ya hubieran sido corregidos.

## Impacto HU-10 sobre configuraciones existentes

El SQL preparado obtiene de las constantes revisadas 17 componentes y 16 pares rol/componente. Clasifica cada componente como INSERTAR, SOBRESCRIBIR o SIN_CAMBIO_LOGICO; muestra valores actuales y previstos. Clasifica los permisos como INSERTAR_PREDETERMINADO o CONSERVAR_EXISTENTE y muestra sus cinco capacidades actuales. La clasificación SIN_CAMBIO_LOGICO no significa que el UPSERT no ejecute UPDATE o no pueda activar triggers existentes.

Riesgos concretos: sobrescritura de nombre/ruta/orden/padre/activo; desactivación de HOJAS_VIDA, CURSOS, NOTAS, REENTRENAMIENTOS, CERTIFICACIONES y DOCTRINA si estaban activos; incorporación de VER_DOCUMENTO_COMPLETO para USUARIO/ADMINISTRADOR si el par falta; concesiones administrativas nuevas si faltan. DO NOTHING conserva una fila de permiso ya existente, incluso una denegación explícita. Las excepciones de usuario no se modifican en ese upgrade, aunque el permiso efectivo también depende del estado del componente y del servicio.

p0008 concede edición SQL de ambas mallas; p0009 concede cambio de hash, estado y marca de cambio obligatorio. Esas concesiones no escriben por sí mismas contadores de login ni bloqueado_hasta. La auditoría nueva y su CHECK deben estar disponibles para que las operaciones HU-10 funcionen. No conocemos aún cuántas filas serán sobrescritas o qué permisos serán nuevos en la base: faltan resultados de comparación del propietario.

## Ejecución futura, verificación y recuperación

La autorización futura debe identificar hashes exactos, destino propietario, ventana, límites de espera efectivos, cambios de datos/componentes y matriz de privilegios aceptados. Solo entonces ensayar upgrade sobre la copia restaurada; nunca stamp ni SQL offline. Medir duración/bloqueos y verificar el postflight y los flujos funcionales HU-10+MFA. No conceder permisos manualmente como sustituto del ensayo ni saltar revisiones.

Después de aprobar el ensayo, nueva ventana de origen sin escritores, preflight y respaldo final validado. Ejecutar online con configuración principal y cuenta propietaria temporal, sin escribirla en .env de API. Confirmar una cabeza p0010, restricciones validadas, triggers activos y ACL exactamente aprobadas; comparar baseline antes de reabrir tráfico. Validar contraseña temporal→MFA, QR, replay, no JWT antes del segundo factor, CAPTCHA, siete fallos/tres horas, desbloqueo, autorización y auditoría.

Ante error: detenerse, conservar evidencia y verificar rollback desde una conexión nueva; no reintentar a ciegas. Las secuencias no garantizan ausencia de huecos. No hay downgrade general seguro: varias revisiones lo rechazan o eliminan datos/auditoría. Tras un upgrade confirmado, una restauración exige decisión explícita de destino, RPO y preservación de actividad posterior; no sobrescribir automáticamente la base activa.

## Decisiones aún necesarias

1. Destino privado del respaldo y ejecución del operador con acceso completo; archivo, hash y logs.
2. Destino aislado identificado y alcance de restauración: completo con ACL requiere permiso expreso para reproducir privilegios allí, manteniendo prohibición en origen.
3. Ventana para detener escritores; evidencia completa del preflight y explicación/repetición controlada de 1→0.
4. Aprobación de diferencias concretas de componentes/malla tras recibir el SELECT comparativo.
5. Aprobación o reducción de privilegios propuestos, especialmente autorizaciones, auditoría completa y secuencias; tratamiento de REVOKE.
6. Autorización posterior independiente para ensayo de migraciones en la copia y, tras aceptación, upgrade en producción con plan de recuperación. Ninguna de ambas se ha solicitado como acción ejecutable ni realizado ahora.

**Resultado: preparación documental lista; restaurabilidad todavía no demostrada; actualización aún no aprobable.** No se eliminó el respaldo Git, no se modificó PostgreSQL ni se hicieron commits/push.
