# Importación masiva de personal ESART

## 1. Objetivo

Registrar personal militar desde la hoja elegida de un libro Excel original en
`esart.personal_militar`. La importación es completa o rechazada: ninguna fila
válida se aplica si hay errores bloqueantes en otra. No se crean unidades ni
tablas de importación. Se conserva el esquema existente.

## 2. Arquitectura

```text
Botón superior de Personal militar → CargueExcel
  → bytes originales conservados como File en memoria, sin vínculo posterior al disco
  → Worker: hojas, diagnóstico y validación local
  → confirmación explícita
  → ImportacionExcelService → ClienteApiService → interceptores existentes
  → POST /api/importaciones/excel (archivo + hoja)
  → dependencias de sesión, CSRF y permiso CREATE
  → leer_excel (openpyxl / xlrd, en hilo separado)
  → guardar_personal (validadores y catálogo PostgreSQL)
  → INSERT por lotes + auditoría → único COMMIT
  → resumen real → actualización reactiva del listado
```

La organización se mantiene en `rutas/`, `esquemas/`, `servicios/` y los modelos
SQLAlchemy existentes. El proyecto consulta desde servicios; no se añadió una
capa de repositorios paralela. El router ya registrado en `principal.py` se
reutiliza, sin un segundo endpoint de importación.

## 3. Archivos y responsabilidades

| Archivo | Función |
| --- | --- |
| `backend/aplicacion/rutas/importaciones.py` | Recibe multipart, aplica seguridad y coordina lectura/guardado. |
| `backend/aplicacion/esquemas/importaciones.py` | Esquema Pydantic de respuesta, con UUID y contadores no negativos. |
| `backend/aplicacion/servicios/importacion_personal.py` | Lectura del original, mapeo, validación, resolución de unidades y transacción. |
| `backend/requirements.txt` | Conserva openpyxl y añade xlrd 2.0.2 para XLS. |
| `backend/pruebas/test_importacion_personal.py` | Pruebas unitarias, HTTP y reutilización del laboratorio aislado. |
| `backend/pruebas/test_importacion_personal_aislada.py` | Inserción real, permisos, catálogo y rollback en PostgreSQL efímero. |
| `backend/pruebas/fixtures/personal_importacion.xls` | Libro XLS ficticio con varias hojas para probar el formato real. |
| `backend/herramientas/probar_importacion_aislada.py` | Crea, marca, prueba, detiene y elimina exclusivamente su propio clúster temporal. |
| `backend/herramientas/diagnosticar_importacion.py` | Diagnóstico de solo lectura: ruta, conexión, privilegios y contadores agregados, sin credenciales ni personas. |
| `backend/pruebas/test_diagnostico_importacion.py` | Sesión JWT real con MFA, expiración, logs seguros y commit de 200 registros consultado desde otra conexión. |
| `backend/aplicacion/seguridad/sesion_http.py` | Solo añade logs seguros por etapa del rechazo de sesión; conserva todas sus reglas. |
| `frontend/esart/src/app/paginas/personal-militar/cargue-excel/cargue-excel.ts` | Conserva File/hoja y envía tras confirmar; bloquea doble clic y muestra resultados/incidencias. |
| `.../cargue-excel/importacion-excel.service.ts` | Construye FormData con el archivo original y `hoja`. |
| `.../cargue-excel/archivo-excel.ts` | Conserva una copia exacta en memoria y reconoce señales explícitas de archivo modificado/no disponible. |
| `.../cargue-excel/excel.worker.ts` | Detecta hojas y analiza sin enviar ni reconstruir el archivo de importación. |
| `.../cargue-excel/excel-analisis.ts` | Usa la fila 1 como encabezado y valida localmente. |
| `.../cargue-excel/excel-normalizacion.ts` | Normalización local de documentos, género y unidades. |
| `frontend/esart/src/app/nucleo/servicios/verificacion.service.ts` | Publica la notificación de personal actualizado tras éxito confirmado. |
| `frontend/esart/src/app/paginas/personal-militar/habilitados/habilitados.ts` | Recarga los datos si el listado está montado; al navegar también realiza una consulta nueva. |
| Archivos `*.spec.ts` correspondientes | Prueban envío original, selección, doble clic, incidencias y actualización. |

Los modelos `PersonalMilitar` y `UnidadMilitar`, el cliente HTTP y los mecanismos
de autenticación se reutilizan. No se cambiaron migraciones, CAPTCHA, login ni
la implementación global de TOTP.

## 4. Endpoint y solicitud

**`POST /api/importaciones/excel`**

| Campo multipart | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `archivo` | UploadFile | Sí | Excel original `.xlsx` o `.xls`, máximo 20 MiB (20 × 1024 × 1024 bytes). |
| `hoja` | string | Sí | Nombre exacto de la hoja seleccionada, de 1 a 31 caracteres. |
| `codigo_totp` | string | Cuando lo exige la configuración | Código del autenticador; se conserva el flujo de confirmación existente. |

Ejemplo Angular implementado:

```ts
const datos = new FormData();
datos.append('archivo', archivoOriginal);
datos.append('hoja', hojaSeleccionada);
```

Se conserva el nombre y el contenido originales en una copia estable en memoria;
no se genera un libro reducido
ni se convierte el documento a JSON para importarlo. No se fija manualmente
`Content-Type`: el navegador añade el límite multipart. Seleccionar un archivo,
cambiar de hoja o validar localmente no realiza este POST.

## 5. Respuesta

Se conserva el contrato `APLICADA` de ESART,
en lugar de introducir el estado ilustrativo COMPLETADO de otra API.

HTTP **201**:

```json
{
  "importacion_id": "78dd3409-899d-4a81-aa7a-1d069d2fbd97",
  "estado": "APLICADA",
  "mensaje": "Importación realizada correctamente.",
  "filas_totales": 200,
  "filas_validas": 200,
  "filas_rechazadas": 0
}
```

El UUID se registra en la auditoría existente `IMPORTACION_EXCEL`. Los contadores
corresponden a las filas de datos de la hoja seleccionada, sin encabezado ni
filas vacías. La respuesta solo confirma éxito después del commit.

## 6. Lectura y límites

- XLSX: openpyxl 3.1.5, modo read-only, sin vínculos externos. Se verifica firma
  ZIP, documento `xl/workbook.xml` y un máximo de 100 MiB descomprimidos.
- XLS: xlrd 2.0.2, firma OLE, lectura de la hoja pedida. No ejecuta macros.
  xlrd obtiene valores almacenados de fórmulas; no calcula fórmulas. El frontend
  rechaza fórmulas en la validación local. En XLSX el backend también las rechaza.
- Solo se procesan los registros de `hoja`; otras hojas pueden existir y no se
  combinan ni se importan automáticamente.
- Límites por hoja: 100.000 filas de rango y 200 columnas. La fila 1 es siempre
  el encabezado. Si está vacía no se busca silenciosamente otra fila de cabecera.
- Los datos empiezan en fila 2. Una fila vacía se omite conservando los números
  originales de todas las demás filas.
- Debe almacenarse Documento como texto para conservar ceros iniciales. También
  se respeta el formato numérico sencillo compuesto solo por ceros (`000000`).

Referencia de la dependencia XLS:
[documentación oficial de xlrd](https://xlrd.readthedocs.io/en/stable/).

## 7. Validaciones definitivas

El backend no confía en los contadores ni en la validación del cliente. Comprueba
archivo, hoja, cabecera, campos obligatorios, longitudes, cédula, género, booleanos,
catálogo de unidades, duplicados internos normalizados y documentos ya presentes.
No sobrescribe registros existentes.

La cédula reutiliza `habilitacion.normalizar_cedula`: quita puntos, espacios y
guiones y exige de 5 a 15 dígitos. Por ejemplo `99.000-00001` se convierte a
`9900000001`; dos documentos que normalizan al mismo valor se consideran duplicados.

En el modelo vigente, grado, categoría y especialidad son textos, sin FK ni
catálogo asociado. Se aplican sus límites reales; no se inventó una lista de
valores válidos ni se reutilizó el catálogo distinto de especialidades de instructores.
Las restricciones UNIQUE, CHECK y FK existentes siguen siendo verificadas por
PostgreSQL durante la inserción.

## 8. Mapeo de columnas

Los encabezados se normalizan por espacios, mayúsculas y acentos. Los alias se
resuelven explícitamente; dos columnas para el mismo atributo bloquean el libro.

| Encabezado/alias admitido | Destino | Reglas |
| --- | --- | --- |
| Documento, Cédula, numero_documento, documento_identidad | documento_identidad | Obligatorio; validador institucional de cédula, UNIQUE. |
| Nombres, Nombre | nombres | Obligatorio; espacios normalizados, máximo 150. |
| Apellidos, Apellido | apellidos | Obligatorio; espacios normalizados, máximo 150. |
| Grado | grado | Obligatorio; máximo 20. |
| Género, Sexo | genero | Obligatorio; MASCULINO/M → M, FEMENINO/F → F, antes de longitud 1. |
| Categoría | categoria | Obligatorio; máximo 30. |
| Unidad, Unidad actual, nombre_unidad, sigla_unidad | unidad_actual_id | Nombre o sigla inequívoca del catálogo; nullable según el modelo. |
| unidad_actual_id, unidad_id | unidad_actual_id | Compatibilidad con plantillas anteriores; si se proporciona un ID se comprueba contra el catálogo real. |
| Especialidad, especialidad_actual | especialidad_actual | Nullable; máximo 100. |
| Activo | activo | Sí/no, true/false, verdadero/falso, 1/0. Vacío usa true, el valor por defecto del modelo real. |

Los campos `id`, `creado_en` y `actualizado_en` no se reciben como atributos de
entrada. Las columnas desconocidas se omiten; el diagnóstico local lo advierte.

## 9. Resolución de unidades

El backend consulta `esart_ref.unidades_militares.id`, `codigo` y `nombre`.
Construye un índice que conserva todas las coincidencias, normalizando caso y
espacios repetidos. Solo un resultado único proporciona la FK.

- Nombre o sigla única: se usa el ID obtenido de PostgreSQL.
- Sin resultado: `Unidad no encontrada en el catálogo institucional`, con fila y valor.
- Varias unidades: se pide corregir el Excel usando una sigla oficial única.
- Nunca se crea una unidad, se aproxima un nombre ni se elige el primer resultado.

El original conserva el nombre/sigla, de modo que la resolución definitiva se
realiza en el servidor con el catálogo actual, antes del INSERT.

## 10. Transacciones

Se usa la dependencia `obtener_sesion_base_datos` y AsyncSession existente. La
sesión abre su transacción al consultar. Se validan todas las filas y los
documentos existentes antes de insertar. El usuario confirma explícitamente.

Los registros se insertan en lotes de 500 dentro de la misma transacción. La
auditoría se añade con `confirmar=False`; solo existe un commit de datos al final.
Un fallo de inserción, FK, UNIQUE o auditoría ejecuta rollback de toda la operación,
incluidos los lotes anteriores. No se hace commit por fila o por lote.

Si falla la comunicación durante la confirmación, se muestra un error de base de
datos y se pide consultar el personal antes de reintentar; no se simula éxito.
La unicidad del documento protege frente a reintentos y carreras de inserción.

## 11. Manejo de errores

Se conserva `{ "error": { "codigo", "mensaje", "detalle" } }`.

```json
{
  "error": {
    "codigo": "IMPORTACION_RECHAZADA",
    "mensaje": "El archivo contiene errores. No se guardó ningún registro.",
    "detalle": {
      "filas_totales": 2,
      "errores": [{
        "hoja": "CARGUE_PERSONAL", "fila": 4, "columna": "unidad_actual_id",
        "valor": "UNIDAD-INEXISTENTE",
        "motivo": "Unidad no encontrada en el catálogo institucional"
      }]
    }
  }
}
```

Angular conserva el número original, marca la celda y la columna, permite ubicar
la incidencia y descargar errores, y mantiene abierta la ventana.

| Código | Tratamiento |
| --- | --- |
| DATOS_INVALIDOS / HOJA_NO_ENCONTRADA (422) | Corregir archivo o selección. |
| IMPORTACION_RECHAZADA (422) | Corregir incidencias; no se importan filas parciales. |
| SIN_PERMISO (403) / NO_AUTENTICADO (401) | Se aplican guardas e interceptores existentes. |
| TOTP_REQUERIDO (409) / TOTP_INVALIDO (422) | Continúa la confirmación existente del autenticador. |
| IMPORTACION_NO_DISPONIBLE (503) | La cuenta SQL no tiene INSERT; requiere administrador. |
| IMPORTACION_BD_NO_DISPONIBLE (503) | Error de base de datos; no se expone SQL ni credenciales. |

## 12. Seguridad y habilitación del entorno

Se exigen sesión firmada existente, CSRF y CREATE de PERSONAL_CARGUE_EXCEL.
ADMINISTRADOR activo tiene todas las operaciones funcionales, verificadas mediante
roles vigentes del servidor sin depender de filas CRUD individuales. Los demás
roles conservan su malla. La política no omite JWT, MFA ni controles de seguridad.
Véase [Administrador y privilegios](ESART_ADMINISTRADOR_Y_PRIVILEGIOS.md).

No se modificaron permisos ni el esquema de la base operativa. La comprobación
de solo lectura del entorno configurado confirmó que `esart_aplicacion` todavía
carece de INSERT en personal_militar. Por eso el guardado operativo permanece
bloqueado, aunque las inserciones y rollback ya fueron probados en el laboratorio.

La propuesta `backend/propuestas/habilitar_insert_personal.sql` está preparada
para revisión/ejecución por el DBA: INSERT en los nueve campos de entrada, USAGE
de esquemas y lectura/escritura mínima de catálogo, duplicados y auditoría.
Las secuencias SERIAL se tratan individualmente; IDENTITY no recibe USAGE innecesario.
Solo se probó en PostgreSQL aislado. No se ejecutó en la base operativa; no concede
UPDATE, DELETE ni escritura en unidades.

## 13. Pruebas automatizadas y aislamiento

Desde `backend/`, con las dependencias instaladas:

```powershell
..\.venv\Scripts\python.exe herramientas/probar_importacion_aislada.py
```

El lanzador usa PostgreSQL instalado (PG_BIN permite otra ubicación), crea un
clúster temporal en un puerto local libre, comprueba su data_directory y marca
la base `esart_importacion_pruebas`. No lee la conexión operativa del .env ni
acepta el puerto operativo. Solo crea tablas a partir de los modelos existentes
en esa base aislada. Los datos de cada prueba se revierten mediante una transacción
exterior. Una prueba adicional hace un commit real y comprueba 200 registros
desde otra conexión independiente antes de limpiar sus datos, siempre dentro
del clúster efímero. Después se detiene el servidor y se elimina su directorio verificado.

Cobertura: 200 filas, hoja explícita y exclusión de otra hoja, encabezado no
insertado, XLS original, género, unidad/FK real, documentos duplicados, unidad
inexistente, columnas ausentes, hoja inexistente, archivo vacío/incorrecto,
numeración con filas vacías, permiso denegado y auditoría, fallo de segundo lote
y violación UNIQUE real después de 500 inserciones (rollback completo).

Desde `frontend/esart/`:

```powershell
npm.cmd test -- --watch=false `
  --include='src/app/paginas/personal-militar/**/*.spec.ts' `
  --include='src/app/nucleo/servicios/sesion.service.spec.ts' `
  --include='src/app/nucleo/guardas/permiso.guard.spec.ts' `
  --include='src/app/nucleo/interceptores/sesion-expirada.interceptor.spec.ts'
npm.cmd run build
```

Las pruebas Angular verifican File original + hoja en FormData, bloqueo del doble
clic, resultados reales, número original de incidencias y refresco del listado,
además de las funciones previas de arrastre, tamaño y selección de hojas.

La fixture XLS ficticia fue generada con SheetJS del proyecto en formato BIFF8;
no contiene personal real ni IDs manuales de unidades.

## 14. Procedimiento de uso

1. Instalar dependencias backend actualizadas (`python -m pip install -r requirements.txt`).
2. Verificar con el administrador los permisos de la aplicación y la cuenta SQL.
3. Abrir «Cargue masivo por Excel» desde la barra de Personal militar.
4. Buscar o arrastrar el archivo original; elegir CARGUE_PERSONAL u otra hoja válida.
5. Revisar estadísticas, diagnóstico y vista previa; pulsar «Validar Excel».
6. Corregir bloqueos, recargar si cambió el archivo y volver a validar.
7. Pulsar «Confirmar importación» y aceptar la confirmación; aportar TOTP si se pide.
8. Esperar el resumen del servidor. El listado activo se recarga tras éxito; al
   navegar al listado se consultan los datos nuevamente.

## 15. Ejemplos

Fila válida conceptual (ESART debe existir de forma única en el catálogo del entorno):

| Documento | Nombres | Apellidos | Grado | Género | Categoría | Unidad | Activo |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 9900000001 | Persona | Ejemplo | SL | FEMENINO | OFICIAL | ESART | Sí |

En el laboratorio se usa exclusivamente SIM-ESART, creada por el test con ID
generado por PostgreSQL. Ninguna fila ficticia se escribe en la base operativa.

Ejemplos rechazados: Documento `ABC`, unidad `UNIDAD-INEXISTENTE`, dos documentos
iguales después de normalizar, género `OTRO`, cabecera ausente o dos columnas
equivalentes como Documento y Cédula. Las longitudes y FK se verifican otra vez
en el servidor. La fila 1 nunca se guarda como personal.

## 16. Límites de lo verificado

Resultado de la comprobación administrativa actual: **50 pruebas Python aprobadas**
mediante el lanzador PostgreSQL aislado y **94 pruebas Angular aprobadas**, incluyendo
Personal militar, servicio de sesión, guard de permisos e interceptor de sesión expirada.
La compilación de producción terminó correctamente. Persisten avisos del
presupuesto CSS de cargue-excel/TOTP y la dependencia CommonJS qrcode. Los
clústeres temporales usados se detuvieron y eliminaron al finalizar.

El flujo HTTP y la persistencia se verifican en PostgreSQL aislado, no mediante
respuestas simuladas para las pruebas de inserción. Las pruebas unitarias de
fallos también usan dobles cuando corresponde. No se realizaron inserciones
de prueba en la base operativa ni se modificaron sus privilegios. Su falta de
INSERT sigue siendo una condición de despliegue pendiente del DBA.

No se realizó una comprobación visual manual en navegador. No se añadieron
catálogos de grado/categoría/especialidad inexistentes ni una tabla de historial
duplicada: el historial de esta operación permanece en la auditoría existente.

## 17. Diagnóstico de 401, 503 y ERR_UPLOAD_FILE_CHANGED

### Hechos comprobados en el entorno configurado

`python herramientas/diagnosticar_importacion.py` abre una transacción
`READ ONLY` y no envía archivos ni modifica registros. El diagnóstico realizado
confirmó:

- Ruta POST de importación registrada y conexión PostgreSQL funcional.
- Cookie segura desactivada para el entorno HTTP local y TOTP habilitado.
- Falta INSERT en los nueve atributos de entrada de personal_militar.
- **0 registros en personal_militar y 0 importaciones aplicadas en auditoría.**

No se proporcionó el Excel del incidente para comparar documentos específicos;
el contador cero permite descartar filas de personal parcialmente guardadas
en esta base durante esta comprobación. No se reintentó una importación operativa.

### 503

Existe un bloqueo verificable de privilegios SQL: la cuenta conectada puede
consultar, pero no insertar personal. El servicio detecta esa condición antes
de escribir y devuelve `IMPORTACION_NO_DISPONIBLE` con HTTP 503. La ruta registrada
y la conexión funcional descartan que este bloqueo se deba a una ruta ausente
o a PostgreSQL detenido.

Los 503 de otras etapas siguen distinguiéndose por el código del contrato:
`IMPORTACION_BD_NO_DISPONIBLE` para fallos SQL y los códigos TOTP existentes para
configuración/autorización del autenticador. No se asume que todos los 503 tengan
el mismo origen. No se cambió ningún estado HTTP a 200 ni se concedieron privilegios.

Los logs nuevos identifican recepción, lectura, consulta de catálogo, validación,
privilegios, autorización, inserción y commit. Para errores SQL registran solo
el tipo y SQLSTATE; nunca sentencias, parámetros, credenciales, nombre del Excel,
nombre de hoja, documentos o nombres de personas. Una prueba comprueba que los
valores privados de una excepción no se filtren al registro.

### 401

ESART utiliza JWT en la cookie HttpOnly `esart_sesion`, no una cabecera Bearer.
Angular usa rutas relativas `/api`, el proxy conserva el mismo origen y la
cookie CSRF tiene la configuración correspondiente. No se añadió Bearer ni se
desactivaron restricciones de cookies, expiración, cuentas o MFA.

El backend rechaza correctamente: ausencia de cookie, JWT inválido/vencido,
sesión revocada, usuario inactivo/bloqueado, sesión anterior a la activación del
autenticador, MFA no vinculado, inactividad o ausencia de rol. Los logs de la
dependencia distinguen cookie ausente, token no válido y rechazo de la validación
del servidor, sin imprimir la cookie ni identificadores.

La prueba con cookie JWT firmada, sesión vigente, rol y MFA activo obtiene **200**
en `/api/auth/yo`. La sesión expirada obtiene **401 SESION_EXPIRADA**, se revoca
y no puede importar. Una sesión anterior a la activación de MFA obtiene **401**
y pide completar el autenticador. Las reglas no se modificaron para hacer pasar
estas pruebas.

No fue posible inspeccionar la cookie del navegador del incidente. Por ello no
se atribuye su 401 específico a expiración sin evidencia. Una consulta inicial
sin login es un 401 esperado; un token por sí solo tampoco demuestra sesión válida.

### ERR_UPLOAD_FILE_CHANGED

La causa estructural encontrada era conservar para el POST el File respaldado
por el disco, después de leerlo para el diagnóstico. El selector también se
limpiaba antes de finalizar esa lectura asíncrona. Una modificación, reemplazo
o pérdida de disponibilidad del archivo entre lectura y envío podía invalidar
esa referencia del navegador. No se identificó qué proceso externo modificó el
archivo del incidente; no se recibió su traza de DevTools.

La corrección lee una sola vez y construye un File en memoria con exactamente
esos bytes, nombre, tipo y lastModified, antes de transferir el buffer al Worker.
La vista previa y el POST usan el mismo contenido. La respuesta del Worker ya
no restaura el File respaldado por disco. El selector se limpia solo después
de conservar los bytes. No se reconstruye el Excel ni se intenta recuperar
silenciosamente otro contenido del sistema de archivos.

NotReadableError, NotFoundError y señales explícitas ERR_UPLOAD_FILE_CHANGED
invalidan la selección y piden volver a seleccionar y validar. No hay reintentos
automáticos. Un HTTP status 0 genérico no permite distinguir con fiabilidad red
de archivo cambiado: se muestra esa limitación sin etiquetar todos los fallos de
conexión como cambios de archivo. La copia estable evita depender del disco al enviar.

Pruebas adicionales: copia de bytes y metadatos, modificación del buffer original
sin alterar la copia, error de lectura, necesidad de reselección, no limpiar el
selector prematuramente, ausencia de reintentos y conservación del bloqueo de doble clic.

### Cantidad realmente verificada

Se insertaron y confirmaron **200 personas ficticias** en PostgreSQL aislado;
otra conexión SQL, abierta después de cerrar la sesión de inserción, contó
esas 200 filas con la unidad y género correctos. Luego se limpiaron los datos
y se destruyó el clúster. No se dejaron registros ficticios persistentes.
En la base operativa se observaron **0 personas** y no se insertó ninguna
durante el diagnóstico. Su guardado continúa pendiente de la habilitación
de INSERT por el DBA, fuera del alcance autorizado de cambiar código.

## 18. Curso de la importación e historial de grados (p0011)

Cada importación crea un curso y registra a cada persona de la hoja en ese curso.

### Formulario "Datos del curso" (ventana de cargue)

| Campo | Origen | Envío |
|---|---|---|
| Tipo de curso | `esart.tipos_curso` activos (sigla — nombre) | `tipo_curso_id` |
| Nombre del curso | Se precarga con el nombre del tipo; editable | `nombre_curso` |
| Número del curso | Último `cursos.codigo` numérico + 1; solo lectura | No se envía: el servidor lo recalcula al guardar |
| Comandante del curso | `esart.instructores` activos (nombre desde `personal_militar` por documento del usuario) | `comandante_id` |
| Fecha inicial / final | Fechas; la final no puede ser anterior | `fecha_inicio`, `fecha_fin` |
| Estado | En curso, Culminado, Cancelado, Aplazado | `estado_curso` |
| Observación | Texto libre, máx. 2000 | `observacion_curso` |

`GET /api/importaciones/datos-curso` entrega los catálogos y el número siguiente (mismo permiso
`PERSONAL_CARGUE_EXCEL`). "Confirmar importación" queda deshabilitado mientras el curso esté incompleto.

### Reglas al guardar (una sola transacción)

1. Se valida la hoja como antes, el tipo de curso y el comandante (activos) y el orden de fechas.
2. Documento nuevo → se inserta en `personal_militar`.
3. Documento existente:
   - mismo grado (sin distinguir mayúsculas/espacios) → error de la fila, no se guarda nada;
   - grado distinto, pero la persona ya está en un curso del **mismo tipo con fechas que se cruzan** → error;
   - grado distinto → se actualiza `personal_militar.grado`.
4. Se crea el curso con código consecutivo (bloqueo `pg_advisory_xact_lock`, sin `LOCK TABLE`).
5. Se inserta una fila por persona en `hoja_vida_artillero` (`artillero_id`, `grado`, `curso_id`, `unidad_id`).
6. La respuesta y la auditoría incluyen `curso_codigo`, `registros_nuevos` y `grados_actualizados`.

### Cambios de base de datos

Revisión `p0011_cursos_importacion` y su equivalente manual
`backend/propuestas/p0011_cursos_importacion.sql` (la base local no tiene `alembic_version`):

- `esart.instructores` (se crea si falta) + `foto BYTEA` y `foto_tipo` (JPEG/PNG/WEBP, máx. 2 MB).
- `esart.cursos` (se crea si falta): `semestre_id` opcional; estados `EN_CURSO`, `CULMINADO`, `CANCELADO`,
  `APLAZADO` (los anteriores se convierten: EN_EJECUCION→EN_CURSO, FINALIZADO→CULMINADO, PLANEADO→APLAZADO).
- `esart.hoja_vida_artillero`: columnas `grado`, `curso_id` (FK cursos), `unidad_id` (FK unidades);
  se elimina el único por persona y se agrega único (`artillero_id`, `curso_id`).
- `esart_aplicacion`: solo privilegios de columna (SELECT/INSERT necesarios y `UPDATE (grado, actualizado_en)`
  en `personal_militar`); no recibe UPDATE/DELETE de tabla.

Mientras la estructura o los privilegios falten, el formulario y la importación responden 503
`IMPORTACION_NO_DISPONIBLE` mencionando la migración p0011. Sin instructores activos no se puede
elegir comandante; la carga de instructores (y de su foto) no forma parte de esta pantalla.
