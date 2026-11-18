import { read, utils, WorkBook, write } from 'xlsx';
import { analizarHoja } from './excel-analisis';
import { normalizar } from './excel-modelos';
import {
  indiceUnidades,
  normalizarGenero,
  resolverUnidad,
  UnidadExcel,
} from './excel-normalizacion';

export function leerLibro(buffer: ArrayBuffer, extension: string): WorkBook {
  const bytes = new Uint8Array(buffer);
  const zip = bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 3 && bytes[3] === 4;
  const ole = [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1].every((b, i) => bytes[i] === b);
  if (!(extension === 'xlsx' ? zip : extension === 'xls' && ole))
    throw new Error('El contenido no corresponde al formato Excel indicado por la extensión.');
  const libro = read(buffer, { type: 'array', cellFormula: true, bookFiles: true });
  const claves = (libro as WorkBook & { keys?: string[] }).keys ?? [];
  if (!libro.SheetNames.length || (extension === 'xlsx' && !claves.includes('xl/workbook.xml')))
    throw new Error('El archivo no contiene un libro Excel .xlsx válido.');
  return libro;
}

export function prepararHoja(
  libro: WorkBook,
  nombre: string,
  unidades: UnidadExcel[] | null,
): ArrayBuffer {
  const analisis = analizarHoja(libro.Sheets[nombre], true, unidades);
  if (analisis.incidencias.some((i) => i.nivel === 'Error'))
    throw new Error('La hoja contiene errores bloqueantes.');
  const indices = analisis.columnas.map((col, i) => (col.campo ? i : -1)).filter((i) => i >= 0);
  const matriz: (string | boolean | null)[][] = [indices.map((i) => analisis.columnas[i].campo!)];
  const indiceCatalogo = indiceUnidades(unidades ?? []);
  for (const fila of analisis.filas)
    matriz.push(
      indices.map((i) => {
        const valor = fila.valores[i];
        if (analisis.columnas[i].campo === 'genero') return normalizarGenero(valor);
        if (analisis.columnas[i].campo === 'unidad_actual_id' && valor) {
          return resolverUnidad(
            valor,
            indiceCatalogo,
            unidades,
            ['unidad_actual_id', 'unidad_id'].includes(normalizar(analisis.columnas[i].nombre)),
          );
        }
        if (analisis.columnas[i].campo === 'activo')
          return valor ? ['si', 'true', '1', 'verdadero'].includes(normalizar(valor)) : true;
        return valor || null;
      }),
    );
  const salida = utils.book_new();
  utils.book_append_sheet(salida, utils.aoa_to_sheet(matriz), nombre);
  return write(salida, { type: 'array', bookType: 'xlsx' });
}
