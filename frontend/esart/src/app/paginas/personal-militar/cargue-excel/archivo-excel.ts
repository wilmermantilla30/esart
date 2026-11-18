/** Copia los bytes ya leídos; no reconstruye el libro ni conserva un vínculo al disco. */
export function conservarArchivoExcel(original: File, bytes: ArrayBuffer): File {
  if (bytes.byteLength !== original.size) {
    throw new DOMException('El tamaño del archivo cambió durante la lectura.', 'NotReadableError');
  }
  return new File([bytes], original.name, {
    type: original.type,
    lastModified: original.lastModified,
  });
}

/** Chromium no siempre expone su código interno: solo clasifica señales explícitas. */
export function archivoExcelNoDisponible(error: unknown): boolean {
  if (
    error instanceof DOMException &&
    ['NotReadableError', 'NotFoundError', 'SecurityError'].includes(error.name)
  )
    return true;
  if (!error || typeof error !== 'object') return false;
  const dato = error as { message?: unknown; error?: unknown };
  return (
    (typeof dato.message === 'string' && dato.message.includes('ERR_UPLOAD_FILE_CHANGED')) ||
    (typeof dato.error === 'string' && dato.error.includes('ERR_UPLOAD_FILE_CHANGED')) ||
    (!!dato.error && dato.error !== error && archivoExcelNoDisponible(dato.error))
  );
}
