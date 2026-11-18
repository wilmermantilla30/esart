import { archivoExcelNoDisponible, conservarArchivoExcel } from './archivo-excel';

function leer(archivo: File): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const lector = new FileReader();
    lector.onload = () => resolve(new Uint8Array(lector.result as ArrayBuffer));
    lector.onerror = reject;
    lector.readAsArrayBuffer(archivo);
  });
}

describe('Archivo Excel estable', () => {
  it('copia exactamente los bytes antes de transferirlos y conserva los metadatos originales', async () => {
    const bytes = new Uint8Array([1, 2, 3, 4]);
    const original = new File([bytes], 'original.xlsx', {
      type: 'application/test',
      lastModified: 12345,
    });
    const estable = conservarArchivoExcel(original, bytes.buffer);
    bytes.fill(0); // modificar el buffer del lector no modifica el archivo preparado
    expect([...(await leer(estable))]).toEqual([1, 2, 3, 4]);
    expect(estable).not.toBe(original);
    expect([estable.name, estable.size, estable.type, estable.lastModified]).toEqual([
      'original.xlsx',
      4,
      'application/test',
      12345,
    ]);
  });
  it('rechaza tamaños cambiados y distingue archivos no disponibles de un fallo genérico de red', () => {
    expect(() => conservarArchivoExcel(new File(['abc'], 'a.xlsx'), new ArrayBuffer(2))).toThrow();
    expect(archivoExcelNoDisponible(new DOMException('Cambió', 'NotReadableError'))).toBe(true);
    expect(archivoExcelNoDisponible({ error: { message: 'net::ERR_UPLOAD_FILE_CHANGED' } })).toBe(
      true,
    );
    expect(archivoExcelNoDisponible({ status: 0, error: new ProgressEvent('error') })).toBe(false);
  });
});
