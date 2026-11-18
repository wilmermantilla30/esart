/// <reference lib="webworker" />
import { utils, WorkBook } from 'xlsx';
import { analizarHoja } from './excel-analisis';
import { leerLibro } from './excel-libro';

let libro: WorkBook;
addEventListener('message', ({ data }) => {
  try {
    if (data.tipo === 'abrir') {
      libro = leerLibro(data.buffer, data.extension);
      const hojas = libro.SheetNames.map((nombre) => {
        const rango = utils.decode_range(libro.Sheets[nombre]['!ref'] || 'A1');
        return {
          nombre,
          filas: Math.max(0, rango.e.r - rango.s.r),
          columnas: rango.e.c - rango.s.c + 1,
        };
      });
      postMessage({ tipo: 'hojas', hojas });
    } else if (data.tipo === 'analizar') {
      postMessage({
        tipo: 'analisis',
        analisis: analizarHoja(libro.Sheets[data.hoja], data.validar, data.unidades),
      });
    }
  } catch (error) {
    postMessage({
      tipo: 'error',
      mensaje: error instanceof Error ? error.message : 'No se pudo procesar el libro Excel.',
    });
  }
});
