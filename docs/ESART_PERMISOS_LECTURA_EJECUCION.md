# Permisos mínimos de lectura: revisión y estado

Las dos sentencias autorizadas cumplen exactamente el alcance solicitado:

```sql
GRANT USAGE ON SCHEMA esart, esart_ref TO esart_aplicacion;
GRANT SELECT ON esart_ref.unidades_militares,
                esart.tipos_unidad, esart.tipos_cargo, esart.tipos_curso TO esart_aplicacion;
```

El archivo `backend/sql/ESART_PERMISOS_LECTURA_PENDIENTES.sql` las contiene dentro de una transacción y comprueba que la base sea esart_db. No incluye concesiones de escritura, creación, administración, acceso a otras tablas ni privilegios globales. No modifica filas, clasificaciones, identificadores, fechas o historial Alembic.

## Estado de ejecución

**No aplicadas desde Codex.** Se confirmó nuevamente una conexión real a esart_db como esart_aplicacion. Los cuatro catálogos todavía carecen de USAGE/SELECT. La conexión del propietario postgres confirmada en DBCode no es una conexión disponible para este proceso. No hay una conexión administrativa local configurada en su entorno; no se solicitaron nuevos archivos ni credenciales, ni se intentó ampliar privilegios con la cuenta de aplicación.

El propietario puede ejecutar el archivo completo desde su conexión administrativa actual de DBCode. La autorización de estas dos sentencias ya fue recibida: no requiere otra confirmación general. Verificar antes `SELECT current_database(), current_user;` y comprobar que la transacción termine en COMMIT.

## Comprobación posterior preparada

Desde backend:

```powershell
.venv/Scripts/python.exe -m herramientas.verificar_persistencia_principal
```

La herramienta solo consulta los cuatro catálogos autorizados; no necesita lectura de personal. Exige los conteos 40/9/5/14, 39 unidades clasificadas y FUTOM sin tipo, sin insertar ni actualizar registros. Guarda evidencia en `docs/ESART_VERIFICACION_PRINCIPAL.json`. Ante falta de permisos o diferencias no informa éxito ni fuerza los datos.

La comprobación actual terminó bloqueada por permisos; los conteos son desconocidos para este proceso. No se atribuyen a PostgreSQL los valores esperados sin haberlos consultado.

## FastAPI y autenticación

La lectura SQL como esart_aplicacion y la prueba HTTP autenticada son verificaciones distintas. No se ha realizado una petición HTTP autenticada exitosa. Persisten la clave JWT de ejemplo y la ausencia de un proveedor de identidad funcional; no se reemplazó la clave, no se desactivó autenticación y no se sustituyó la identidad por un mock para simular una prueba real.

El siguiente paso inmediato es aplicar estos permisos desde la conexión propietaria disponible y comprobar lectura real. Las pruebas de endpoints protegidos y de Angular requieren después configurar e integrar correctamente la autenticación. La integración completa permanece pendiente.
