/**
 * Entrega al navegador un archivo recibido del backend con un enlace temporal en memoria: el
 * archivo nunca se abre dentro de la página. Lo usan las plantillas, los documentos del
 * artillero y la plantilla de notas.
 */
export function guardarArchivo(nombre: string, contenido: Blob): void {
  const enlace = document.createElement('a');
  enlace.href = URL.createObjectURL(contenido);
  enlace.download = nombre;
  enlace.click();
  URL.revokeObjectURL(enlace.href);
}
