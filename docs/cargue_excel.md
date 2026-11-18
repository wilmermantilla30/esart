# Cargue masivo de personal

La documentación técnica vigente de la integración está en
[ESART_IMPORTACION_MASIVA_PERSONAL.md](ESART_IMPORTACION_MASIVA_PERSONAL.md).

El contrato actual envía el archivo original (.xlsx o .xls) y el nombre de la
hoja por multipart. El backend solo importa esa hoja, usando la fila 1 como
encabezado y conservando los números originales para las incidencias.

Se conservan la ventana redimensionable, Drag & Drop global, selección de hojas,
diagnóstico, vista previa y confirmación. La documentación enlazada describe
validación, transacciones, seguridad, pruebas PostgreSQL aisladas y el permiso
INSERT pendiente en la cuenta SQL del entorno operativo.
