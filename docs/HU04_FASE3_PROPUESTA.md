> Documento de propuesta historica. La ejecucion autorizada y el estado actual de ambas bases estan en [HU04_FASE3_EJECUCION.md](HU04_FASE3_EJECUCION.md). Las reversiones solo se permiten en la base temporal.

# HU-04 fase 3: tipos de unidad militar

Estado: propuesta implementada en archivos, pendiente de aprobacion para DDL.
Fecha: 14 de noviembre de 2026 (America/Bogota).

## Arquitectura y alcance confirmado

El usuario selecciono exclusivamente tipos de unidad. Se revisaron los 22 modelos,
las migraciones, los contratos y la base esart_hu03_pruebas en modo de solo lectura.
No existe un catalogo equivalente. tipos_cargo clasifica funciones del personal;
la jerarquia de unidades no identifica su clase. El inventario completo y la
justificacion estan en HU04_FASE3_ANALISIS.md.

0002 propone una tabla tipos_unidad y una columna nullable tipo_unidad_id en
unidades_militares. Cada unidad puede tener cero o un tipo; un tipo puede ser
compartido por muchas unidades. FK ON DELETE RESTRICT e indice individual.
La relacion unidad_superior_id permanece intacta y no depende del tipo.
No se actualizan las 40 unidades ni sus fechas. Sus nuevas FK quedan NULL.

Columnas del catalogo: id UUID PK generado, codigo varchar(20) UNIQUE NOT NULL,
nombre varchar(200) NOT NULL, activo boolean default true y dos fechas timestamptz
NOT NULL default now(). CHECK de codigo en mayusculas y nombre no vacio; trigger
para fecha_actualizacion reutiliza la funcion de 0001. El codigo es la identidad
institucional; nombres visibles no necesitan una segunda restriccion UNIQUE.

## Datos reutilizados

| Codigo | Tipo |
|---|---|
| DIV | Division |
| BR | Brigada |
| BAACA | Batallon de Artilleria |
| BATAR | Bateria de Artilleria |
| CECFU | Centro de Coordinacion de Fuegos |
| CEDOC | Centro de Educacion y Doctrina |
| CEM | Centro de Educacion Militar |
| BAADA | Batallon de Artilleria de Defensa Aerea |
| ESART | Escuela de Artilleria |

Los seeds preservan exactamente la ortografia de catalogos.json, derivado mediante
AST del archivo heredado. No se importa ni ejecuta initial_data.py. La lista se
valida antes de conectar. Solo se insertan codigo/nombre; UUID, activo y fechas
usan defaults. ON CONFLICT(codigo) DO NOTHING mantiene filas existentes; cualquier
diferencia de nombre se informa sin sobrescribirla. El informe solo confirma
resultados despues del commit. Se bloquea la tabla durante la carga.

## Separacion de responsabilidades

ESART administra formacion, capacitacion, certificacion, experiencia y habilitacion
del personal de artilleria, ademas de su contexto organizacional. VULCANO administra
operacion, mantenimiento, abastecimiento y baja de material. Los 4 estados
operacionales y 8 logisticos no se implementan en modelos, 0002 ni seeds de fase 3.
Permanecen como referencia historica en el manifiesto de fase 2.

Una futura integracion debe definir identidad UUID/BIGINT, propiedad del material,
instancia operativa, historial y contrato de sincronizacion. No debe atribuir estados
de una pieza a toda una unidad ni confundirlos con estado_servicio de una persona.
Los permisos historicos tampoco habilitan modulos por si solos.

## Archivos preparados

- aplicacion/modelos/catalogos_organizacion.py: TipoUnidad.
- aplicacion/modelos/nucleo.py: FK nullable y relacion desde UnidadMilitar.
- migraciones/versions/0002_tipos_unidad.py: upgrade aditivo y downgrade protegido.
- herramientas/migrar_fase3.py: genera SQL sin conectar por defecto; sustituye
  siempre el destino en memoria por esart_hu03_pruebas, incluso si .env dice otra base.
- seeds/fase3.py: carga idempotente, requiere revision 0002 ya aplicada.
- seeds/sql/fase3_upgrade_propuesto.sql y fase3_downgrade_propuesto.sql: DDL revisable.
- seeds/sql/validaciones_fase3.sql: conteos, presencia de los 9 tipos e integridad.
- pruebas/test_catalogos_fase3.py: contrato, SQL offline, destinos y precondiciones.
- seeds/test_integracion_fase3.py: ciclo online optativo tras aprobacion.

La revision 0001 esta intacta; una prueba verifica su SHA-256 normalizado. Las
pruebas que comparan modelos con migraciones ahora reconstruyen 0001 + 0002 y
verifican que 0001 no contenia esta ampliacion. Los contratos aprobados no se editaron.

## Validacion realizada y limites

Antes de cambios: Python 3.12.10, pip check correcto, 58 pruebas aprobadas.
Despues: 67 pruebas aprobadas, dos integraciones omitidas por defecto. Ruff revisa
los archivos de implementacion y pruebas modificados. Se genero el SQL de subida
y bajada sin abrir conexion. La inspeccion de solo lectura conserva 2 roles,
36 permisos y 40 unidades, sin faltantes, huerfanos ni ciclos.

No se ejecuto 0002, no se insertaron tipos, no se modifico esart_db ni usuarios,
credenciales o datos existentes. Migracion, insercion real, repeticion y reversion
0002 en PostgreSQL siguen pendientes de aprobacion y ejecucion. Los modelos nuevos
requieren 0002: no desplegar esta propuesta sobre un servicio con esquema 0001.
Los seeds de fase 2 siguen fijados a 0001 y no se modificaron para esta propuesta.

## Secuencia posterior a la aprobacion

Desde backend, utilizar exclusivamente .venv/Scripts/python.exe (Python 3.12).
No ejecutar Alembic directamente con la URL de .env, que puede nombrar otra base.

Generacion offline ya realizada; puede repetirse sin DDL:

```powershell
.\.venv\Scripts\python.exe -m herramientas.migrar_fase3
.\.venv\Scripts\python.exe -m herramientas.migrar_fase3 --revertir --salida seeds/sql/fase3_downgrade_propuesto.sql
.\.venv\Scripts\python.exe -m pytest
```

Solo despues de aprobacion expresa, probar primero el ciclo dentro de una
transaccion externa con rollback completo (requiere que la base siga en 0001):

```powershell
$env:ESART_FASE3_DDL_APROBADO='1'
.\.venv\Scripts\python.exe -m unittest seeds.test_integracion_fase3 -v
Remove-Item Env:ESART_FASE3_DDL_APROBADO
```

Esta prueba comprueba subida, nueve inserciones, segunda carga sin inserciones,
UNIQUE, CHECK, FK, RESTRICT, rechazo de downgrade con datos, reversion vacia y
nuevo upgrade. Finalmente revierte todo y compara huellas de todas las tablas
originales, incluida auditoria. No confirma filas temporales ni borra datos previos.

Aplicacion persistente, tambien condicionada a aprobacion:

```powershell
.\.venv\Scripts\python.exe -m herramientas.migrar_fase3 --aplicar
.\.venv\Scripts\python.exe -m seeds.fase3 --aplicar --informe seeds/fase3_primera_carga.json
.\.venv\Scripts\python.exe -m seeds.fase3 --aplicar --informe seeds/fase3_segunda_carga.json
```

Validar luego con seeds/sql/validaciones_fase3.sql en la misma base de pruebas.
El downgrade preparado rechaza catalogos con filas o clasificaciones presentes,
con bloqueo para evitar carreras. No elimina semillas ni clasificaciones: la
reversion de una base poblada requiere una estrategia de conservacion aprobada.
No se incluye un comando automatico que borre esa informacion.

## Decision solicitada

Aprobar o ajustar la nueva tabla tipos_unidad y la FK nullable propuesta, y
autorizar explicitamente las pruebas estructurales y aplicacion de 0002 unicamente
en esart_hu03_pruebas. La exigencia de aprobacion procede de la instruccion del
usuario de no ejecutar migraciones estructurales sin aprobacion.
