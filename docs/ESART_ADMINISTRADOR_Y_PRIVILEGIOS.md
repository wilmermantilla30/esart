# ADMINISTRADOR y privilegios PostgreSQL

## Política funcional vigente

Un usuario activo con asignación vigente al rol activo ADMINISTRADOR tiene acceso,
lectura, creación, actualización y eliminación en todos los componentes existentes
y activos. La comprobación consulta esart_ref.usuarios, esart.usuario_roles y
esart.roles en el backend. No depende de filas en rol_permisos ni usuario_permisos,
del nombre admin.esart, de un rol en el formulario ni de una etiqueta del navegador.

Las excepciones antiguas no restringen a un administrador: se conservan sin borrar,
pero no se aplican a su política fija. La malla muestra todos sus permisos y no
permite editarlos; la vista individual muestra HEREDAR y los efectivos completos.
Retirar la asignación o desactivar el rol/usuario elimina esta concesión.

Los demás roles mantienen la precedencia excepción individual > rol activo >
denegación. Sus códigos granulares sin catálogo implementado siguen denegados.
El administrador tiene autoridad funcional para esos códigos, manteniendo los
controles de seguridad de las operaciones que los utilizan.

No se activan componentes deshabilitados ni se inventan endpoints inexistentes.
La autorización para eliminar no permite borrar auditoría inmutable ni omitir
reglas de negocio o integridad.

## Controles que permanecen

Las dependencias conservan JWT firmado, sesión vigente, MFA/TOTP obligatorio,
cuentas activas/no bloqueadas, cambio de contraseña inicial y CSRF. Se mantienen
los límites y consumo de códigos TOTP, auditoría, validación de datos, duplicados,
FOREIGN KEY, UNIQUE, CHECK y transacciones completas. No se modificaron CAPTCHA,
la implementación productiva de TOTP, políticas de bloqueo o migraciones anteriores.

## Angular

El backend aplica la misma política al construir permisos y menu[].operaciones
de /api/auth/yo. SesionService y exigirPermiso ya utilizan esa respuesta. No se
añadió un bypass local basado en rol === ADMINISTRADOR ni se alteró el diseño.
Después del despliegue debe recargarse la página o renovarse la sesión para
recibir el menú actualizado. La autorización de cada endpoint no depende de
ese menú en caché y vuelve a comprobar los roles vigentes.

## Dos autorizaciones independientes

| Capa | Identidad | Alcance |
| --- | --- | --- |
| Aplicación | Usuario autenticado con ADMINISTRADOR activo | Operaciones funcionales existentes sin asignaciones CRUD individuales. |
| PostgreSQL | Cuenta técnica esart_aplicacion | Solo consultas y escrituras que permitan sus privilegios SQL. |

Un administrador funcional puede superar la autorización y recibir 503 si la
cuenta técnica carece de INSERT. No se transforma ese error en una confirmación.

## SQL mínimo para el DBA

Archivo revisado: backend/propuestas/habilitar_insert_personal.sql.
**No se ejecutó en la base operativa.** Se probó solo sobre un rol nuevo y limitado
en un clúster PostgreSQL efímero identificado y marcado para pruebas.

| Objeto | Permiso y motivo |
| --- | --- |
| Esquemas esart y esart_ref | USAGE, sin CREATE. |
| personal_militar | INSERT solo en los nueve atributos de entrada. SELECT en id y documento_identidad para RETURNING y duplicados. |
| unidades_militares | SELECT en id, codigo y nombre; sin crear ni modificar unidades. |
| auditoria_eventos | INSERT en campos utilizados por registrar_evento; SELECT en id y fecha para valores generados. |
| Secuencia SERIAL concreta, si existe | USAGE exclusivamente para id de personal_militar o auditoria_eventos cuando utiliza nextval. |

IDENTITY genera internamente sus IDs y no requiere USAGE explícito de secuencia.
La inspección de solo lectura confirmó personal_militar.id con identidad d
(BY DEFAULT) y auditoria_eventos.id con identidad a (ALWAYS). En este esquema
el bloque condicional no concede privilegios innecesarios sobre sus secuencias.

No se otorga SUPERUSER, CREATEDB, CREATEROLE, BYPASSRLS, GRANT ALL, acceso global
a secuencias, UPDATE de secuencias ni UPDATE/DELETE de personal. Los privilegios
preexistentes del resto de la aplicación no se revocan: esta propuesta es un
complemento mínimo para importación, no un reemplazo de los permisos de sesión/MFA.

## Comprobación operativa de solo lectura

El diagnóstico confirmó admin.esart activo y autorizado funcionalmente para
CREATE de PERSONAL_CARGUE_EXCEL. La cuenta técnica tiene USAGE en ambos esquemas,
lectura del catálogo y no posee atributos globales peligrosos, pero sigue sin
INSERT en los nueve campos. Se observaron cero registros de personal y cero
importaciones aplicadas. No se cambiaron asignaciones ni privilegios operativos.

Para repetir: desde backend ejecutar python herramientas/diagnosticar_importacion.py.
La herramienta solo consulta metadatos y contadores agregados, sin credenciales
ni datos de personas.

## Archivos modificados

- aplicacion/seguridad/permisos.py: política central y permisos efectivos por roles vigentes.
- aplicacion/servicios/malla_permisos.py: representación de la política fija en rol y usuario.
- propuestas/habilitar_insert_personal.sql: USAGE, permisos por columna y secuencias condicionales.
- herramientas/diagnosticar_importacion.py: diagnóstico de privilegios y atributos técnicos.
- herramientas/probar_importacion_aislada.py: incluye las pruebas administrativas nuevas.
- pruebas/test_administrador_aislado.py: autorización, sesiones, importación y SQL mínimo.
- pruebas/test_diagnostico_importacion.py: secreto de MFA criptográficamente suficiente en la fixture; sin cambios al mecanismo productivo.
- Pruebas Angular de sesion.service.spec.ts y permiso.guard.spec.ts: menú efectivo y navegación.
- Documentación técnica de importación, alta inicial y autorización: política actualizada.

Las rutas anteriores son relativas a backend salvo los archivos Angular y docs.

## Pruebas

El lanzador python herramientas/probar_importacion_aislada.py crea su propio
PostgreSQL temporal, comprueba el directorio y la marca de la base y limpia el
clúster al terminar. Nunca usa la conexión operativa para escribir o aplicar SQL.
La prueba del GRANT utiliza exclusivamente el propietario del laboratorio.

Se verifican:

- Todos los CRUD de administrador sin filas rol_permisos ni excepciones individuales.
- Excepciones negativas ignoradas para administrador y malla/menú coherentes.
- Revocación, rol inactivo y usuario inactivo eliminan la concesión.
- Nombre admin.esart o rol declarado por cliente no elevan privilegios.
- Los demás roles conservan sus herencias y excepciones.
- admin.esart con JWT, MFA y TOTP válido importa 200 filas reales en PostgreSQL aislado y queda auditado.
- Falta de código TOTP, sesión expirada, cuenta bloqueada y datos inválidos siguen rechazados.
- Un usuario sin sesión recibe 401; uno sin permisos recibe 403 con auditoría.
- SQL mínimo suficiente con una cuenta no superusuario: importación y auditoría sin UPDATE/DELETE, creación de unidades u objetos, ni USAGE innecesario de secuencia IDENTITY.
- Se conservan commit comprobado desde otra conexión y rollback completo ante errores.

Las pruebas Angular comprueban las operaciones completas devueltas por el servidor
y que una etiqueta de rol aislada no invente concesiones. No se cambió el diseño.

Resultado final: **50 pruebas Python y 94 Angular aprobadas**; compilación de
producción correcta, con los avisos conocidos de CSS y qrcode. Se verificaron
200 registros importados por admin.esart con JWT/MFA/TOTP reales en la base
aislada, además de la suficiencia del SQL mínimo bajo el rol técnico limitado.
Los clústeres de pruebas se detuvieron y eliminaron al finalizar. No se ejecutó
el SQL en la base operativa ni se insertaron personas ficticias en ella.

## Ejecución pendiente por el propietario/DBA

1. Revisar el diagnóstico y la propuesta en la base operativa correcta.
2. **Se solicita al propietario o DBA autorizado revisar y ejecutar manualmente
   backend/propuestas/habilitar_insert_personal.sql con una conexión propietaria.**
3. Repetir el diagnóstico y comprobar los privilegios efectivos.
4. Desplegar el backend actualizado y recargar el menú de admin.esart.
5. Confirmar una importación autorizada y consultar su resumen y auditoría reales.

FastAPI no ejecuta GRANT al arrancar. La entrega no modifica automáticamente
los permisos PostgreSQL del entorno operativo.
