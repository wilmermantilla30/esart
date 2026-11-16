# HU-04, fase 4 — Ejecución de la clasificación de unidades

**Estado: completada conforme a la autorización condicionada.**
Fecha local: 14 de noviembre de 2026, America/Bogota, 23:50–23:51.
Entorno: Python 3.12, `backend/.venv`, PostgreSQL 18.7.

## Alcance autorizado y resultado

Se trabajó exclusivamente en `esart_hu03_pruebas`, verificando Alembic `0002`
antes de las operaciones. La revisión final sigue siendo `0002`.
La matriz aprobada conserva su SHA-256:
`0604808f4576d92f25d48fcf05cc2baf459b1b73d2c398e402d555db58b21f83`.

Se clasificaron exactamente 39 unidades; FUTOM conserva `tipo_unidad_id = NULL`.
No se creó un tipo para Fuerza de Tarea ni se la equiparó a División.
El catálogo conserva sus nueve tipos sin cambios.

| Tipo | Unidades clasificadas |
|---|---:|
| BAACA | 13 |
| BAADA | 2 |
| BR | 11 |
| CEDOC | 1 |
| CEM | 1 |
| DIV | 10 |
| ESART | 1 |
| **Total clasificadas** | **39** |
| FUTOM, sin clasificar | 1 |

BATAR y CECFU siguen disponibles en el catálogo, sin unidades asignadas en este conjunto.

## Procedimiento y comprobaciones

1. Se verificaron destino, revisión, 40 UUID, nombres, códigos, superiores, nueve
   tipos activos, fechas de referencia y huellas de `0001` y `0002`.
2. Se contrastaron las 39 correspondencias con la matriz explícita aprobada.
   No se clasificó por prefijos en tiempo de ejecución ni se usaron etiquetas
   históricas del cargador heredado como sustituto de la matriz.
3. Se verificó que el trigger y su función coincidieran con la inspección original
   y que el trigger estuviera habilitado. No se modificaron ni deshabilitaron.
4. Se ejecutaron las 39 actualizaciones simuladas dentro de un savepoint. Se
   comprobaron los tipos finales y que solo cambiaran `tipo_unidad_id` y la fecha
   automática exacta de la transacción. Las demás tablas conservaron sus huellas.
5. Se hizo rollback del savepoint y se verificó la igualdad exacta de las 40 filas
   con su estado anterior, incluidas sus fechas. La simulación no dejó cambios
   persistentes. Se guardó su evidencia antes de iniciar la aplicación real.
6. La carga real verificó que la evidencia de simulación correspondiera a la misma
   matriz, snapshot, catálogo, autorización de fecha y estado inicial de unidades.
   Las 39 actualizaciones se confirmaron en una transacción, con bloqueos de tabla
   para evitar escrituras concurrentes durante su validación.
7. Se repitió el seed en otra transacción. Omitió las 39 correspondencias ya correctas:
   no se ejecutó ningún UPDATE ni se volvió a disparar el trigger.
8. Una conexión posterior de solo lectura confirmó el estado persistido, las 39
   asignaciones, FUTOM pendiente, el catálogo intacto y cero tipos huérfanos.

## Actualizaciones e idempotencia

| Operación | Actualizaciones intentadas | Confirmadas | Omitidas | Fechas modificadas persistentemente |
|---|---:|---:|---:|---:|
| Simulación con rollback | 39 | 0 | 0 | 0 |
| Primera carga | 39 | 39 | 0 | 39 |
| Segunda carga | 0 | 0 | 39 | 0 |

La simulación comprobó 39 cambios automáticos de fecha dentro del savepoint y los
revirtió. La primera carga es la única que confirmó cambios persistentes.
FUTOM es un pendiente excluido de la carga, no una correspondencia omitida.

La huella de las 40 filas después de la primera carga, antes de la segunda y después
de la segunda es idéntica:
`fa2eccb0645ae0b829d3347ec38ed7914b3e6c2e1ee94a68c6b7fd94ace549e0`.
Esta comparación incluye `fecha_actualizacion` y demuestra que la repetición no la cambió.

## Conservación de datos e integridad

- Las 40 unidades conservan sus UUID, nombres, códigos, siglas, superiores,
  indicador `activa` y `fecha_creacion` originales.
- Solo las 39 filas de la matriz cambiaron `tipo_unidad_id` y `fecha_actualizacion`.
  La fecha fue asignada exclusivamente por el trigger existente con `now()`;
  la sentencia UPDATE no incluye ninguna fecha en su cláusula SET.
- FUTOM conserva toda su fila original, incluida su fecha de actualización.
- La jerarquía se conserva; la validación del conjunto detecta ciclos y huérfanos.
  No se detectaron inconsistencias ni asignaciones a tipos inexistentes.
- La FK permanece opcional; no se alteraron tablas, índices, restricciones ni funciones.
- Las huellas de todas las demás tablas de `public` permanecieron iguales durante
  la simulación y ambas cargas; el catálogo también coincide con el snapshot original.
- `0001` y `0002` conservan las huellas guardadas al iniciar la propuesta.
- No se conectó ni se emitieron operaciones contra `esart_db` o la base temporal.
  Ninguna de esas bases fue modificada por esta fase.

## Pruebas y validaciones

La suite completa pasa con **93 pruebas aprobadas y 2 integraciones omitidas por
defecto**. Las pruebas nuevas cubren la excepción de fecha, la igualdad con la fecha
de la transacción, la protección de FUTOM, la conservación de otros campos y la
repetición sin ejecutar UPDATE. Ruff pasa sin errores en los archivos modificados.

Además de las pruebas locales con conexiones simuladas, se ejecutaron la simulación,
las dos cargas y la lectura final en PostgreSQL sobre la única base autorizada.
No se ejecutaron pruebas estructurales, migraciones ni reversiones en esta fase.

## Evidencias

- `backend/seeds/fase4_inspeccion.json`: snapshot original, tipos, trigger y huellas de migraciones.
- `backend/seeds/fase4_matriz.json`: las 40 filas de la matriz aprobada y sus motivos.
- `backend/seeds/fase4_preflight_autorizado.json`: revisión inicial sin actualizaciones.
- `backend/seeds/fase4_simulacion.json`: 39 actualizaciones simuladas y rollback verificado.
- `backend/seeds/fase4_primera_carga.json`: 39 actualizaciones confirmadas.
- `backend/seeds/fase4_segunda_carga.json`: cero actualizaciones y cero cambios de fecha.
- `backend/seeds/fase4_resultado_final.json`: lectura posterior, cambios por columna y estado de las 40 unidades.
- `backend/pruebas/test_clasificacion_fase4.py`: pruebas automatizadas.

Los snapshots previos y la matriz no se reemplazaron con los resultados de la carga.

## Repetición del seed

Desde `backend`, utilizando el entorno Python 3.12:

```powershell
.\.venv\Scripts\python.exe -m seeds.fase4 --aplicar --permitir-fecha-trigger --informe seeds/fase4_repeticion.json
```

El permiso de fecha es explícito; aun así, la repetición no programa UPDATE para las
filas ya correctas. Una clasificación incompatible, cambio ajeno a las columnas
autorizadas, migración alterada o matriz distinta provoca la interrupción y rollback.
