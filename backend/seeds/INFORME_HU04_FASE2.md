# HU-04 fase 2: informe de ejecucion

Fecha local: 14 de noviembre de 2026, America/Bogota.
Ejecucion completada en esart_hu03_pruebas, esquema public, revision 0001,
PostgreSQL 18.7, cuenta de aplicacion sin superusuario.

## Resultados confirmados

| Catalogo | Primera carga: insertados | Primera: omitidos | Segunda: insertados | Segunda: omitidos |
|---|---:|---:|---:|---:|
| roles | 2 | 0 | 0 | 2 |
| permisos | 36 | 0 | 0 | 36 |
| unidades_militares | 40 | 0 | 0 | 40 |
| Total | 78 | 0 | 0 | 78 |

Evidencias: inspeccion.json (antes), carga_1.json, carga_2.json y
validacion_final.json (consulta posterior). Sin faltantes, diferencias de textos,
unidades huerfanas o asignaciones huerfanas. Cada superior militar coincide con
el codigo de referencia. Orden: 12 raices, 12 brigadas/CEMIL, 16 batallones/ESART.
Las huellas de tablas ajenas coinciden antes/despues; auditoria_eventos se excluye
porque los triggers aprobados pueden registrar las inserciones.

## Entorno y verificacion

Se creo backend/.venv con Python 3.12.10 y se instalaron las dependencias fijadas.
pip check: sin dependencias rotas. Antes de cambios: 51 pruebas existentes y
6 pruebas de semillas aprobadas. Despues: 58 pruebas aprobadas y 1 integracion
omitida por defecto; esa integracion se ejecuto aparte con unittest y aprobo.
La integracion realizo las dos cargas registradas y verifico los datos reales.
Se agregaron casos de rechazo de duplicados, longitudes excesivas, CHECK de roles,
codigos invalidos, padres ausentes y ciclos/orden incorrecto antes de insertar.

La validacion SQL de solo lectura se ejecuto en PostgreSQL; incluye conteos,
duplicados, integridad y deteccion de ciclos. La inspeccion final esta registrada
en validacion_final.json. Ruff se aplica a seeds/. No se ejecutaron migraciones,
no se cambiaron modelos ni la revision HU-03 aprobada. No se crearon usuarios,
contrasenas, tablas o columnas; no se borraron ni actualizaron datos existentes.
La URL se lee sin imprimirla y el nombre de base se sustituye en memoria antes
de conectar. Ninguna conexion de estas herramientas se dirige a esart_db.

## Inventario pendiente

| Catalogo | Valores de referencia | Motivo |
|---|---:|---|
| Estados operacionales | 4 | Sin tabla ni columnas en modelos/migracion HU-03 |
| Estados logisticos | 8 | Sin tabla ni columnas en modelos/migracion HU-03 |
| Tipos de unidad | 9 | Sin tabla ni FK en modelos/migracion HU-03 |

Los 21 valores permanecen en catalogos.json, sin inventar destinos. Su carga
requiere una ampliacion futura del contrato. No se concedieron permisos por rol:
roles_permisos necesita una matriz institucional; rol_permisos/usuario_permisos
son permisos CRUD por componentes y no equivalen al catalogo permisos.
Los catalogos academicos no forman parte de esta fase y se conservaron.

## Implementacion

roles.py, permisos.py y unidades_militares.py son ejecutores Python separados,
con inspeccion por defecto y --aplicar para insertar. Comparten ejecutar.py,
validar.py y SQL idempotente por catalogo. Se reutilizaron los literales del
archivo heredado mediante AST, sin ejecutarlo ni importar su administrador.
Cada catalogo usa una transaccion y bloqueo de tabla; ON CONFLICT omite codigos
existentes. Un padre incompatible aborta la transaccion militar. Una carga
posterior puede fallar sin revertir catalogos previamente confirmados.

El inventario de columnas y dependencias se presento en la conversacion antes
de insertar y queda documentado en README.md e inspeccion.json.
