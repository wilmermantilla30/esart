> Propuesta hist?rica aprobada con excepci?n para la fecha autom?tica. La ejecuci?n y las evidencias actuales est?n en [HU04_FASE4_EJECUCION.md](HU04_FASE4_EJECUCION.md).

# HU-04 fase 4: propuesta de clasificacion de unidades

Estado: pendiente de aprobacion; no se ejecutaron actualizaciones.

## Analisis y fuentes

Se consultaron exclusivamente las 40 unidades y los nueve tipos de esart_hu03_pruebas,
revision 0002, en transaccion REPEATABLE READ READ ONLY. Las 40 FK de tipo siguen NULL.
La propuesta usa nombres, codigos y superiores registrados; no acredita organigramas
externos ni certifica la vigencia institucional de los datos heredados.
No se importo initial_data.py ni se asumio que sus etiquetas historicas fueran oficiales.

## Resumen

| Tipo | Unidades propuestas |
|---|---:|
| BAACA | 13 |
| BAADA | 2 |
| BR | 11 |
| CEDOC | 1 |
| CEM | 1 |
| DIV | 10 |
| ESART | 1 |
| PENDIENTE | 1 |

39 correspondencias propuestas; una pendiente. Los tipos BATAR y CECFU no tienen
unidades equivalentes identificadas entre estos 40 registros. No se inventan unidades.

## Matriz completa

| Unidad | Nombre registrado | Superior | Tipo propuesto | Estado / fundamento |
|---|---|---|---|---|
| BAACA1 | Batallón de Artillería de Campaña N°1 | BR01 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA10 | Batallón de Artillería de Campaña N°10 | BR10 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA13 | Batallón de Artillería de Campaña N°13 | BR13 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA18 | Batallón de Artillería de Campaña N°18 | BR18 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA2 | Batallón de Artillería de Campaña N°2 | BR10 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA27 | Batallón de Artillería de Campaña N°27 | BR27 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA3 | Batallón de Artillería de Campaña N°3 | BR03 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA30 | Batallón de Artillería de Campaña N°30 | BR30 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA4 | Batallón de Artillería de Campaña N°4 | BR04 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA5 | Batallón de Artillería de Campaña N°5 | BR05 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA6 | Batallón de Artillería de Campaña N°6 | BR05 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA8 | Batallón de Artillería de Campaña N°8 | BR08 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAACA9 | Batallón de Artillería de Campaña N°9 | BR09 | BAACA | propuesta: El nombre identifica un Batallon de Artilleria de Campana y depende de una Brigada; BAACA es el tipo disponible de Batallon de Artilleria. |
| BAADA1 | Batallón de Artillería de Defensa Aérea N°1 | BR10 | BAADA | propuesta: Codigo y nombre identifican un Batallon de Artilleria de Defensa Aerea; depende de una Brigada. |
| BAADA2 | Batallón de Artillería de Defensa Aérea N°2 | BR05 | BAADA | propuesta: Codigo y nombre identifican un Batallon de Artilleria de Defensa Aerea; depende de una Brigada. |
| BR01 | Primera Brigada | DIV05 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR03 | Tercera Brigada | DIV03 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR04 | Cuarta Brigada | DIV07 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR05 | Quinta Brigada | DIV02 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR08 | Octava Brigada | DIV05 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR09 | Novena Brigada | DIV05 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR10 | Décima Brigada | DIV01 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR13 | Décimo Tercera Brigada | DIV05 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR18 | Décimo Octava Brigada | DIV08 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR27 | Vigésimo Séptima Brigada | DIV06 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| BR30 | Trigésima Brigada | DIV02 | BR | propuesta: El nombre identifica una Brigada y su superior registrado es una Division. |
| CEDOC | Centro de Educación y Doctrina | Raiz | CEDOC | propuesta: Codigo y nombre coinciden con Centro de Educacion y Doctrina; es raiz jerarquica. |
| CEMIL | Centro de Educación Militar | CEDOC | CEM | propuesta: El nombre coincide con Centro de Educacion Militar y depende de CEDOC. CEMIL es el codigo de la unidad; CEM, el del tipo. |
| DAAVA | División de Aviación y Asalto Aéreo | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV01 | Primera División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV02 | Segunda División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV03 | Tercera División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV04 | Cuarta División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV05 | Quinta División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV06 | Sexta División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV07 | Séptima División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIV08 | Octava División | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| DIVFE | División de Fuerzas Especiales | Raiz | DIV | propuesta: El nombre registrado identifica expresamente una Division; es una raiz jerarquica. |
| ESART | Escuela de Artillería | CEMIL | ESART | propuesta: Codigo y nombre coinciden con Escuela de Artilleria y depende del Centro de Educacion Militar. |
| FUTOM | Fuerza de Tarea Omega | Raiz | NULL | pendiente: Fuerza de Tarea Omega no corresponde literalmente a ninguno de los nueve tipos. Ser raiz no acredita tipo DIV; se requiere decision institucional. |

## Pendientes e inconsistencias

- FUTOM permanece NULL. Fuerza de Tarea no es un tipo del catalogo. La posicion de
  raiz y la etiqueta DIV del archivo heredado no bastan para equipararla a Division.
- CEMIL -> CEM es una correspondencia por nombre, no una igualdad de codigos.
- BAACA agrupa los batallones de campana bajo el tipo disponible Batallon de Artilleria;
  BAADA se mantiene en su tipo especifico. No se crean subtipos adicionales.
- No se detectaron huerfanos, ciclos ni discordancias de superior en estas propuestas.
  Que una unidad comparta tipo con otra no impone ni cambia relaciones jerarquicas.
- Existe un bloqueo tecnico real: tr_unidades_militares_fecha ejecuta la funcion
  actualizar_fecha_actualizacion(), que asigna now() a fecha_actualizacion antes de
  cualquier UPDATE. Por tanto, actualizar solo tipo_unidad_id en el SET no garantiza
  que solo esa columna cambie en el registro persistido.

## Script de revision y protecciones

backend/seeds/fase4.py se prepara con inspeccion por defecto y --aplicar como opcion
reservada a una aprobacion posterior. Se utiliza una matriz explicita de UUID/codigo;
no clasifica por prefijos en tiempo de ejecucion. Verifica base, revision, integridad,
huellas de 0001/0002, snapshot, tipos activos y equivalencia exacta de la matriz revisada.
Bloquea cualquier clasificacion existente incompatible y cambios inesperados en los
datos originales. Una segunda ejecucion omite tipos ya iguales y conserva pendientes.

La ejecucion estricta bloquea antes del UPDATE si el trigger de fechas esta activo.
Incluso sin ese trigger, compara las filas completas antes/despues y revierte si cambia
alguna columna distinta de tipo_unidad_id. No modifica, elimina ni deshabilita triggers.
No crea tablas ni ejecuta DDL. Las pruebas locales no ejecutan UPDATE en PostgreSQL.

## Decision requerida antes de escribir

Se solicita revisar las 39 correspondencias, mantener FUTOM pendiente y decidir si
se autoriza que fecha_actualizacion cambie automaticamente por el trigger existente.
Esa excepcion no se considera aprobada. Si se exige preservar tambien esa fecha,
la carga queda bloqueada y se requiere otra decision tecnica expresa; no se alteraran
las migraciones ni los triggers como solucion implicita.

La aprobacion de esta fase debe ser nueva y explicita; las autorizaciones de fase 3
no autorizan clasificar las unidades ni cambiar sus fechas.

## Evidencias

- backend/seeds/fase4_inspeccion.json: snapshot de las 40 unidades, nueve tipos, triggers y huellas de migraciones.
- backend/seeds/fase4_matriz.json: matriz completa con UUID reales, motivos y referencia al snapshot.
- backend/seeds/fase4.py: script idempotente preparado, sin ejecutar actualizaciones.
- backend/pruebas/test_clasificacion_fase4.py: validaciones y pruebas de conservacion.

## Resultado de las comprobaciones

- Antes de la fase: 68 pruebas aprobadas, dos integraciones omitidas por defecto.
- Despues: 88 pruebas aprobadas, dos integraciones omitidas por defecto.
- Revision real ejecutada: python -m seeds.fase4 --informe seeds/fase4_revision.json,
  sin --aplicar, exclusivamente con consultas de solo lectura. Detecto 39 propuestas,
  FUTOM pendiente, trigger incompatible con la conservacion estricta y cero cambios.
- Verificacion final: las 40 filas completas y los nueve tipos coinciden con el
  snapshot, incluidas fechas y UUID; todas las clasificaciones siguen NULL.
- 0001 y 0002 conservan sus huellas de inicio. No se toco la base temporal ni esart_db.
- Las nuevas pruebas usan objetos en memoria y conexiones simuladas. La idempotencia
  de la actualizacion se verifico en memoria; su ejecucion real no esta autorizada.
- Ruff revisa sin errores los dos archivos Python nuevos.

Para repetir solo la revision, desde backend:

```powershell
.\.venv\Scripts\python.exe -m seeds.fase4 --informe seeds/fase4_revision.json
```

No se proporciona una instruccion de ejecucion aprobada de actualizaciones.
La opcion --aplicar del script queda reservada para una autorizacion posterior y
ademas esta bloqueada en el estado actual por el trigger de fecha. Ni siquiera
una aprobacion de la matriz resolveria por si sola esa incompatibilidad tecnica.
