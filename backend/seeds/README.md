# HU-04: segunda fase de población

Destino único: `esart_hu03_pruebas`, esquema `public`, revisión `0001`.
Los scripts rechazan otras bases y cuentas superusuario. No ejecutan migraciones,
no crean tablas, usuarios ni contraseñas, y no actualizan registros existentes.

## Inventario previo a las inserciones

| Catálogo | Destino real | Dependencias / contrato |
|---|---|---|
| 2 roles | `public.roles` | UUID generado; UNIQUE codigo; CHECK ADMINISTRADOR/USUARIO. Sin FK. |
| 36 permisos | `public.permisos` | UUID generado; UNIQUE codigo; descripcion obligatoria, hasta 200 caracteres. Sin FK. |
| 40 unidades | `public.unidades_militares` | UUID generado; UNIQUE codigo, hasta 20 caracteres; FK unidad_superior_id a unidades_militares.id. |
| 4 estados operacionales | Sin tabla compatible | Pendiente de una futura ampliación aprobada del contrato. |
| 8 estados logísticos | Sin tabla compatible | Pendiente de una futura ampliación aprobada del contrato. |
| 9 tipos de unidad | Sin tabla ni FK compatible | Pendiente de una futura ampliación aprobada del contrato. |

El orden militar es 12 raíces, 12 brigadas/CEMIL y 16 batallones/ESART.
Cada padre debe existir antes de insertar al hijo. Un padre ausente o una
jerarquía existente diferente provoca rollback de todo el script militar.
Las tablas roles/permisos/unidades son catálogos independientes entre sí.

`roles_permisos` exige roles y permisos; `rol_permisos` exige roles y componentes.
No se cargan asignaciones ni componentes en esta fase. Los permisos registrados
no conceden acceso por sí mismos ni implementan funcionalidades Vulcano.

## Origen y adaptación

- Roles: INSERT de `aplicacion/base_datos/esart_seguridad_roles_permisos.sql`.
  Se conserva codigo/nombre; se omite descripcion, inexistente en roles HU-03.
- Permisos y unidades: literales de `aplicacion/base_datos/initial_data.py`.
  El comentario heredado dice 33 permisos, pero contiene **36**, todos conservados.
  Los SQL existentes no aportan ese catálogo ni las filas de jerarquía militar.
- Permisos: se conservan codigo/descripcion; se omiten nombre/modulo, sin destino.
- Unidades: codigo/nombre; padre se resuelve por código a unidad_superior_id.
  No se trasladan tipo, lon, lat, ubicacion ni unidad_padre_id. `sigla` queda NULL
  y `activa` usa el default true. No se inventan equivalencias.
- Los 21 valores sin tabla se conservan como referencia en `catalogos.json`.

`generar.py` lee el heredado con AST y literal_eval, sin importarlo ni ejecutarlo.
No se debe ejecutar `initial_data.py`: usa modelos ajenos al contrato y contiene
creación de un administrador con contraseña predeterminada.

## Ejecución en Windows

Desde `backend`, con el Python 3.12 del proyecto y sus dependencias instaladas:

```powershell
.\.venv\Scripts\python.exe -m seeds.ejecutar --archivo-env .env --informe seeds/inspeccion.json
.\.venv\Scripts\python.exe -m seeds.ejecutar --archivo-env .env --aplicar --informe seeds/primera_carga.json
.\.venv\Scripts\python.exe -m seeds.ejecutar --archivo-env .env --aplicar --informe seeds/segunda_carga.json
```

La primera orden solo consulta. El ejecutor reutiliza servidor, puerto, cuenta y
contraseña de la configuración existente, cambiando el nombre de base **en memoria**
a esart_hu03_pruebas antes de conectar. No conecta a esart_db ni modifica el .env.
Se puede seleccionar un catálogo con `--catalogo roles`, `permisos` o `unidades_militares`.
El informe incluye identidad sin contraseña, inventario, insertados, omitidos,
errores, faltantes, diferencias conservadas y huellas de tablas ajenas antes/después.
Una diferencia de nombre/descripcion se informa y conserva; una diferencia de padre aborta.
La auditoría generada por triggers aprobados se excluye de la comparación de huellas.

También se pueden ejecutar los SQL individualmente con psql, sin Python:

```powershell
psql -X -W -h localhost -p 5432 -U esart_aplicacion -d esart_hu03_pruebas -v ON_ERROR_STOP=1 -f seeds/01_roles.sql
psql -X -W -h localhost -p 5432 -U esart_aplicacion -d esart_hu03_pruebas -v ON_ERROR_STOP=1 -f seeds/02_permisos.sql
psql -X -W -h localhost -p 5432 -U esart_aplicacion -d esart_hu03_pruebas -v ON_ERROR_STOP=1 -f seeds/03_unidades_militares.sql
```

Cada SQL emite un NOTICE JSON con conteos; solo se considera confirmado si COMMIT
termina satisfactoriamente. Cada archivo es una transacción independiente: si falla
uno, las cargas anteriores ya confirmadas permanecen y pueden repetirse sin duplicar.
Los bloqueos por tabla serializan estos cargadores; el índice UNIQUE protege códigos.
No se deshabilitan FK, UNIQUE, CHECK ni triggers. Los valores existentes se omiten.

## Validación

```powershell
python -m unittest seeds.test_seeds -v
python -m seeds.generar
```

Para demostrar idempotencia real, comparar primera_carga.json y segunda_carga.json:
la segunda debe insertar cero, omitir 2/36/40 y no presentar faltantes ni errores.
Los totales iniciales pueden incluir registros preexistentes: no se presupone una base vacía.
Las huellas deben confirmar que usuarios, credenciales, catálogos académicos y demás
tablas ajenas permanecieron iguales. No volver a ejecutar verificar_hu03: requiere
base inicialmente vacía y no corresponde a esta fase.

## Ejecutores Python separados y pruebas HU-04

Desde backend, cada modulo permite inspeccion (por defecto) o carga con --aplicar:

```powershell
.\.venv\Scripts\python.exe -m seeds.roles --aplicar --informe seeds/roles_ejecucion.json
.\.venv\Scripts\python.exe -m seeds.permisos --aplicar --informe seeds/permisos_ejecucion.json
.\.venv\Scripts\python.exe -m seeds.unidades_militares --aplicar --informe seeds/unidades_ejecucion.json
.\.venv\Scripts\python.exe -m pytest
$env:ESART_SEEDS_INTEGRACION='1'
.\.venv\Scripts\python.exe -m unittest seeds.test_integracion -v
Remove-Item Env:ESART_SEEDS_INTEGRACION
```

La prueba de integracion es aditiva: ejecuta dos cargas y comprueba registros,
jerarquia, integridad, conservacion de tablas ajenas e idempotencia. Guarda
carga_1.json y carga_2.json; al repetirla reemplaza esas evidencias.
Ejecutarla mediante unittest, separada de pruebas/conftest.py, que fija una URL
ficticia para las pruebas de la API. pytest omite la integracion por defecto.

validar.py comprueba codigos, duplicados, longitudes del modelo, CHECK de roles
y padres anteriores a hijos antes de abrir conexion. El ejecutor exige PostgreSQL
18, verifica la revision y evita ejecutar un SQL diferente al manifiesto validado.
Los SQL se regeneran con seeds.generar; no importar el cargador heredado.

sql/validaciones.sql contiene consultas de conteos, duplicados, huerfanos y ciclos,
en transaccion de solo lectura y con guardia de base. El ejecutor lo aplica
tambien durante la inspeccion y falla ante ciclos o unidades huerfanas.

### Columnas encontradas (modelos, revision 0001 e inspeccion real)

- roles: id UUID PK; codigo varchar(30) UNIQUE CHECK; nombre varchar(100);
  activo boolean default true; fecha_creacion y fecha_actualizacion timestamptz.
- permisos: id UUID PK; codigo varchar(50) UNIQUE; descripcion varchar(200);
  fecha_creacion y fecha_actualizacion timestamptz.
- unidades_militares: id UUID PK; codigo varchar(20) UNIQUE; nombre varchar(200);
  sigla varchar(30) nullable; unidad_superior_id UUID nullable FK a la misma tabla;
  activa boolean default true; fecha_creacion y fecha_actualizacion timestamptz.

Los UUID y las fechas se generan con los defaults aprobados. La migracion y
los modelos HU-03 permanecen intactos. El entorno requerido es backend/.venv;
no se incluyen sus binarios en los entregables.

## HU-04 fase 3 ejecutada

La fase 3 se limita a los 9 tipos de unidad militar; los estados de material
pertenecen a VULCANO. Ambas bases autorizadas quedaron en 0002 con nueve tipos.
Las 40 unidades de esart_hu03_pruebas conservaron todos sus valores y su nueva
FK opcional quedo NULL. La base temporal se conserva; las reversiones de 0002
solo se permiten alli. Consultar ../../docs/HU04_FASE3_EJECUCION.md para evidencias.
Los ejecutores de fase 2 permanecen fijados a 0001; usar seeds.fase3 para repetir
la carga de tipos. No repetir etapas que exigen base vacia o revision 0001.

## HU-04 fase 4 ejecutada

Se clasificaron 39 unidades seg?n la matriz aprobada; FUTOM conserva tipo NULL.
La ?nica excepci?n fue fecha_actualizacion, asignada autom?ticamente por el
trigger existente. La simulaci?n se revirti? y la segunda carga no modific?
ninguna fila ni fecha. Revisar ../../docs/HU04_FASE4_EJECUCION.md y las evidencias
fase4_simulacion.json, fase4_primera_carga.json, fase4_segunda_carga.json y
fase4_resultado_final.json. La repetici?n requiere el permiso expl?cito
--permitir-fecha-trigger; no hay UPDATE para las correspondencias ya correctas.
