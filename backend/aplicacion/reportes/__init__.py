"""
Documentos PDF del artillero generados con ReportLab.

Estructura:
- comun.py            → datos de entrada (DatosDocumento), estilos, membrete y pie comunes.
- diploma.py          → Diploma del último curso aprobado.
- oficio_remisorio.py → Oficio que remite el resultado de la verificación a la unidad.
- certificacion.py    → Certificación del estado de habilitación (APTO / NO APTO) con su detalle.
- maestro.py          → Script maestro: recibe la opción de reporte y llama al script que corresponde.

Uso desde el backend:
    from aplicacion.reportes.maestro import generar_documento
    pdf_bytes, nombre_archivo = generar_documento("DIPLOMA", datos)

Uso desde la línea de comandos (genera un PDF de ejemplo, sin base de datos):
    python -m aplicacion.reportes.maestro CERTIFICACION salida.pdf
"""
