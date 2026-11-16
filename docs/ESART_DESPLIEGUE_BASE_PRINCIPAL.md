# ESART — Despliegue en la base principal

**Estado: respaldo restaurable verificado; despliegue en esart_db todavía NO ejecutado.**
Fecha: 15 de noviembre de 2026.

## Autorizacion y alcance

Esta vigente la autorizacion para cambios compatibles y no destructivos tras verificar
el respaldo. No se solicita de nuevo esa autorizacion general. El operador confirmó
una conexión administrativa en DBCode y pidió ejecutar personalmente el SQL.
El paquete preparado y sus instrucciones están en
[ESART_DBCODE_INTEGRACION_HU03_HU04.md](ESART_DBCODE_INTEGRACION_HU03_HU04.md).
No se han ejecutado los scripts de este paquete ni se declara completado el despliegue.
FastAPI debe conservar esart_aplicacion; la conexion administrativa no sera permanente.

## Respaldo suministrado y validacion real

Archivo: D:\2026\esart\respaldos\esart_db_pre_hu04.backup

- Tamano: 147.987 bytes, formato custom, generado con pg_dump 18.7 desde PostgreSQL 18.7.
- SHA-256: 4d6ecc85006e37b16e92d6fdc0cafd577384fc842e49b6efcd3cd03e0f99dfcb.
- pg_restore --list y decodificacion completa: correctos.
- Restauracion REAL con pg_restore --exit-on-error en un cluster nuevo, puerto
  local libre distinto del operativo, directorio de datos nuevo y autenticacion
  SCRAM con secreto efimero. Se verifico data_directory antes de crear el destino.
- Se conservaron UTF8 y locale Spanish_Colombia.1252 de la base origen.
- Recuperadas las 42 tablas y 42 filas del respaldo. Los conteos de cada COPY
  decodificado coinciden exactamente con los de las tablas restauradas.
- Revisadas 75 FK: cero huerfanos. Cero indices invalidos y cero restricciones
  pendientes de validar. La restauracion con propietarios/ACL termino sin errores;
  los roles locales necesarios se crearon solo en ese cluster, sin copiar claves.
- Las instancias aisladas de validacion quedaron detenidas y se conservan localmente;
  no se usa ninguna como fuente operativa de FastAPI o Angular.

Evidencia segura: [ESART_RESPALDO_VERIFICACION.json](ESART_RESPALDO_VERIFICACION.json).
Los detalles y archivos de recuperacion estan en backend/respaldos/, excluido de Git.
El respaldo original no se modifico. Las contrasenas no se imprimieron ni se
incorporaron al codigo. El verificador crea sus secretos efimeros fuera del repositorio
bajo TEMP y los elimina al terminar.

## Datos verificados en el respaldo

| Tabla | Filas recuperadas |
|---|---:|
| esart.tipos_cargo | 5 |
| esart.tipos_curso | 14 |
| esart.roles | 2 |
| esart.componentes | 10 |
| esart.rol_permisos | 11 |
| esart_ref.unidades_militares | 0 |
| Resto de tablas | 0 |

Estos son datos del snapshot respaldado, no una comprobacion de los datos actuales
con una cuenta administrativa en la principal. Antes de modificar se comparara
el estado vivo y se detendra ante cambios o IDs heredados sin correspondencia.
Los cargos, cursos, roles y mallas existentes deben conservarse, no duplicarse.

## Prueba de integracion de unidades en una recuperacion independiente

Adicionalmente se ensayaron los SQL propuestos en otra restauracion nueva aislada:

1. Ampliacion de la tabla canonica BIGINT, sin duplicar unidades en public.
2. Carga de nueve tipos y cuarenta unidades con identificadores nuevos del destino.
3. Comprobacion exacta por codigo, nombre, sigla, activa, superior y tipo contra
   datos_aprobados.json: 39 clasificadas y FUTOM pendiente.
4. Conservacion de las cinco FK entrantes originales y sus definiciones; la nueva
   FK autorreferente se comprueba como una adicion, no como una alteracion de aquellas.
5. Huellas iguales para todas las tablas originales ajenas a unidades.
6. Segunda ejecucion sin cambios en filas, fechas o secuencia de identidad.

Resultado final de esa prueba: correcto. No es una migracion aplicada en la principal,
ni prueba la integracion HU-03 completa, sus endpoints o Angular. Se corrigio un error
de sintaxis CASE del SQL preparado durante el ensayo; los errores quedaron confinados
a las recuperaciones nuevas. Tambien se corrigieron el lanzador de PostgreSQL en
Windows y la comprobacion que debia distinguir la FK nueva de las cinco originales.
Ninguna correccion altero la principal o el respaldo original.

La propuesta sigue en [ESART_PLAN_DEFINITIVO_INTEGRACION.md](ESART_PLAN_DEFINITIVO_INTEGRACION.md)
y backend/propuestas/integracion_principal. No esta instalada como un historial Alembic.
Los archivos 0001 y 0002 historicos no se cambiaron.

## Estado de la conexion operativa y del operador

La conexion disponible a esart_db sigue siendo esart_aplicacion. Se confirmo en
transaccion READ ONLY que carece de USAGE sobre esart/esart_ref, lectura e insercion/
actualizacion de la tabla de unidades, y no puede asumir el rol propietario postgres.
La tabla sigue siendo propiedad de postgres. No se ejecutaron GRANT, cambios de
propiedad ni ampliaciones globales de privilegios.

Se recibio como ubicacion de la conexion administrativa:
%APPDATA%\postgresql\pgpass.conf

Ruta resuelta con el perfil Windows de Codex:
C:\Users\USUARIO\AppData\Roaming\postgresql\pgpass.conf

**El archivo no existe en esa ruta.** Se verifico tanto dentro como fuera del sandbox,
con identidad Windows DESKTOP-3NQRHG9\USUARIO y el mismo valor de APPDATA/GetFolderPath.
No existe tampoco el directorio postgresql consultado. No se pudo seleccionar una
entrada ni probar la autenticacion administrativa; no se inventaron credenciales.

Para continuar hace falta crear localmente ese archivo protegido o indicar su ruta
real o un servicio libpq existente. Indicar solo nombre/ruta, nunca la contrasena en
el chat. No modificar backend/.env para conectar FastAPI como administrador.
La autorizacion de uso de esa conexion ya fue recibida; falta su disponibilidad.

## Operaciones en la principal y estado posterior

| Operacion | Resultado |
|---|---|
| Consultas de identidad/permisos/metadatos | Ejecutadas en READ ONLY sobre esart_db |
| Tablas creadas o modificadas | Ninguna |
| Migraciones registradas | Ninguna; no hay historial Alembic encontrado |
| Filas insertadas o actualizadas | Ninguna |
| Cambios de permisos o de propietario | Ninguno |
| Conexion operativa o secretos cambiados | Ninguno |
| Cambios en bases de pruebas existentes | Ninguno |
| Endpoints FastAPI consultando 40 unidades de la principal | Pendiente |
| Visualizacion Angular conectada a esos endpoints | Pendiente |

Evidencia de acceso actual: [ESART_DESPLIEGUE_ACCESO_ACTUAL.json](ESART_DESPLIEGUE_ACCESO_ACTUAL.json).
El resultado SQL de la recuperacion no se presenta como evidencia de datos desplegados.
No hay fixtures, replicas ni lecturas de esart_hu03_pruebas sirviendo datos operativos.

## Pasos pendientes, sin nueva autorizacion general

1. Localizar y autenticar la conexion administrativa protegida. Verificar identidad,
   privilegios y destino esart_db antes de escribir; conservar respaldo validado.
2. Comparar el estado vivo con el snapshot, preservar los catalogos existentes y
   detenerse ante un conflicto real. El stub vacio del respaldo no autoriza asumir
   que sigue vacio al ejecutar.
3. Completar y registrar las migraciones operativas compatibles y no destructivas,
   sin marcar falsamente 0002 ni modificar las revisiones historicas de pruebas.
4. Instalar estructuras faltantes, cargar los 36 permisos y las unidades/tipos,
   conservar los 5 cargos/14 cursos/2 roles verificados si siguen coincidiendo,
   validar cuarenta correspondencias, treinta y nueve tipos y FUTOM NULL.
5. Verificar permisos de objeto minimos para esart_aplicacion, sin privilegios globales
   y sin utilizar la cuenta administrativa en FastAPI.
6. Adaptar modelos, repositorios y controles de acceso al esquema real. Resolver
   configuracion/secretos validos, implementar endpoints autenticados y servicio
   Angular real. No eludir las incompatibilidades de usuarios/roles BIGINT frente
   a los modelos UUID existentes ni publicar un endpoint sin autenticacion.
7. Probar SQL directo en esart_db, integridad e idempotencia; comprobar la API y
   visualizacion Angular reales antes de declarar terminado.

## Pruebas del repositorio

99 pruebas aprobadas; dos integraciones omitidas por defecto. Ruff de la herramienta
nueva de recuperacion y sus pruebas: correcto. El Ruff global conserva las 50
incidencias preexistentes documentadas; no se declara cumplido el lint global.
No se declaran aprobadas la API o la UI contra la principal.

**El despliegue permanece incompleto.** El requisito de respaldo recuperable esta
cumplido; el acceso del operador sigue pendiente. No se modifica la base principal
hasta disponer de esa conexion y verificar las precondiciones vivas.
