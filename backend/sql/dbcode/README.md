# ESART: ejecución manual desde DBCode

Ejecutar únicamente `01_integrar_esart_db.sql` y luego `02_verificar_esart_db.sql`, completos, en la conexión administrativa de **esart_db**.

Leer antes el [informe e instrucciones](../../../docs/ESART_DBCODE_INTEGRACION_HU03_HU04.md). No ejecutar las plantillas ni `_ddl_generado.sql` por separado.

Este paquete fue generado y analizado estáticamente. No se ha ejecutado en PostgreSQL. No contiene credenciales ni requiere conexión desde Python.

Para reproducirlo desde `backend`, usar `.venv/Scripts/python.exe -m herramientas.generar_sql_dbcode`. Cualquier cambio modifica el manifiesto y requiere revisar nuevamente ambos archivos antes de usarlos.
