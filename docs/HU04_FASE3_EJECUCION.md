# HU-04 fase 3: informe de ejecucion

Estado: completada en las dos bases de pruebas autorizadas.
Fecha local: 14 de noviembre de 2026, America/Bogota, 23:38.
Entorno: backend/.venv, Python 3.12.10, PostgreSQL 18.7.

## Autorizacion y proteccion de destinos

El usuario autorizo la base temporal independiente esart_hu04_fase3_temporal para
preparacion, migraciones y reversiones. Se verifico su existencia, propietario
esart_aplicacion y ausencia inicial de tablas. No se elimino la base temporal.

Antes de cada migracion se verifico la base conectada. Las herramientas sustituyen
el nombre de base en memoria antes de abrir conexion y solo admiten los dos nombres
autorizados. La migracion 0002 tambien rechaza otras bases desde PostgreSQL; su
downgrade solo admite esart_hu04_fase3_temporal. No se modifico 0001: SHA-256
normalizado 4ce5b478f34fa2cf5e584f4a6cb69e9ecc986f56f129b6067fed991ebcca07e0.

El impedimento previo de CREATEDB quedo resuelto por el usuario mediante la
creacion administrativa de la temporal. No se cambiaron permisos ni credenciales.

## Revisiones iniciales y finales

| Base | Inicial | Ciclo realizado | Final |
|---|---|---|---|
| esart_hu04_fase3_temporal | Sin tablas/revision | base -> 0001; prueba 0001 -> 0002 -> 0001 -> 0002 con rollback externo; aplicacion persistente 0001 -> 0002 | 0002 |
| esart_hu03_pruebas | 0001 | Solo upgrade 0001 -> 0002 | 0002 |

La temporal recibio datos de prueba independientes: 2 roles, 36 permisos y 40
unidades con padres insertados antes que dependientes. No se copiaron usuarios,
credenciales ni datos personales. Las unidades temporales tienen UUID propios.

## Pruebas ejecutadas

- Suite local: 68 pruebas aprobadas, 2 integraciones omitidas por defecto.
- Integracion estructural: una prueba automatizada ejecutada y aprobada
  explicitamente en la temporal; no se ejecuto en esart_hu03_pruebas.
- UNIQUE: rechazo de codigo DIV duplicado.
- CHECK: rechazo de codigo en minusculas y nombre compuesto solo por espacios.
- FK: rechazo de unidad temporal que referencia un tipo inexistente.
- ON DELETE RESTRICT: rechazo de borrar un tipo usado por una unidad temporal.
- Reversion protegida: rechazo esperado de downgrade mientras existen tipos.
- Reversion valida: rollback de las semillas temporales de prueba, downgrade a
  0001 y nuevo upgrade a 0002. No se borraron datos originales para habilitarla.
- Rollback exterior de toda la prueba: huellas de las tablas originales iguales
  antes/despues, incluyendo la tabla de auditoria. Luego la temporal se dejo
  persistentemente en 0002 y se cargaron sus nueve tipos.
- Idempotencia: carga inicial 9/0 y segunda 0/9 en ambas bases.
- Verificacion posterior al commit: ambas bases en 0002; catalogo completo,
  FK opcional con ON DELETE RESTRICT, cero unidades huerfanas y cero ciclos.
- Ruff: sin errores en archivos de ejecucion, migracion y pruebas modificados.

Las excepciones de UNIQUE/CHECK/FK y downgrade con datos son rechazos esperados
comprobados dentro de savepoints; no son fallos del procedimiento.

## Estructuras creadas

- public.tipos_unidad: id UUID PK, codigo varchar(20) UNIQUE NOT NULL,
  nombre varchar(200) NOT NULL, activo boolean default true, fecha_creacion y
  fecha_actualizacion timestamptz con defaults now(). CHECK de formato de codigo
  y de nombre no vacio; trigger de actualizacion reutiliza la funcion de 0001.
- public.unidades_militares.tipo_unidad_id: UUID nullable, indice individual,
  FK a public.tipos_unidad.id con ON DELETE RESTRICT.

No se crearon tablas de estados operacionales ni logisticos. Esos estados
pertenecen a la gestion de material de VULCANO y quedan fuera de ESART.

## Inserciones y omisiones confirmadas

| Base | Primera carga: insertados | Primera: omitidos | Segunda: insertados | Segunda: omitidos |
|---|---:|---:|---:|---:|
| esart_hu04_fase3_temporal | 9 | 0 | 0 | 9 |
| esart_hu03_pruebas | 9 | 0 | 0 | 9 |

Estos conteos corresponden a las cargas persistentes. Las inserciones de la
prueba estructural se revirtieron dentro de su transaccion y no se suman.
No hubo diferencias de nombres conservadas ni referencias faltantes.

## Conservacion de unidades e informacion existente

Las 40 unidades de esart_hu03_pruebas se compararon campo por campo antes y
despues, incluyendo UUID, codigo, nombre, sigla, superior, activa y ambas fechas.
Tambien coincidieron con fase3_preflight_aprobado.json, generado antes de modificar.
La misma comparacion se repitio en una conexion nueva despues del commit.

Resultado: las 40 conservan todos sus valores originales y tipo_unidad_id es
NULL en todas. No se reclasificaron ni se altero su jerarquia. Las huellas de
las tablas ajenas permanecieron iguales; alembic_version cambia por la migracion
y unidades_militares se compara por sus campos anteriores a la nueva columna.

En cada base quedan 2 roles, 36 permisos, 40 unidades y 9 tipos. La base temporal
se conserva, propiedad de esart_aplicacion. No se ejecutaron reversiones en
esart_hu03_pruebas. No se establecio ninguna conexion a esart_db ni se emitieron
operaciones contra ella: no fue modificada por este procedimiento. Tampoco se
modificaron otras bases existentes ni se crearon usuarios o contrasenas.

## Incidencia de la consulta posterior

Una comprobacion adicional de lectura comparo el tipo interno char de pg_constraint
con una cadena Python y produjo un falso rechazo de RESTRICT. Se detuvieron nuevas
escrituras. Consultas de solo lectura con confdeltype::text confirmaron codigo r y
la definicion ON DELETE RESTRICT en ambas bases. Se repitio correctamente la
verificacion final sin cambiar el esquema ni los datos. No quedo inconsistencia.

## Evidencias y reproduccion

- backend/seeds/fase3_preflight_aprobado.json: unidades y huellas previas.
- backend/seeds/fase3_temporal_preparada.json: identidad y preparacion hasta 0001.
- backend/seeds/fase3_temporal_validada.json: integracion aprobada y cargas temporales.
- backend/seeds/fase3_aplicacion_validada.json: upgrade y cargas en esart_hu03_pruebas.
- backend/seeds/fase3_verificacion_final.json: lectura posterior al commit en ambas bases.
- backend/herramientas/ejecutar_hu04_fase3.py: ejecucion por etapas con precondiciones.
- backend/seeds/test_integracion_fase3.py: prueba estructural exclusiva de la temporal.

Las etapas de preparacion y aplicacion son intencionalmente estrictas: requieren
base vacia o revision 0001, respectivamente. No se deben repetir sobre las bases
que ya quedaron en 0002. Para repetir solo el seed de esart_hu03_pruebas:

```powershell
# Desde backend, usando el entorno Python 3.12:
.\.venv\Scripts\python.exe -m seeds.fase3 --aplicar --informe seeds/fase3_repeticion.json
```

Esa repeticion omitira los nueve codigos existentes y no asignara tipos a unidades.
No eliminar la base temporal sin una autorizacion posterior del usuario.
