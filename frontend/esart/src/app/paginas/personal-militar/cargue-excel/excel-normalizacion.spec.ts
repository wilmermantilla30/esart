import { read, utils } from 'xlsx';
import { analizarHoja } from './excel-analisis';
import { prepararHoja } from './excel-libro';
import { indiceUnidades, normalizarGenero, resolverUnidad } from './excel-normalizacion';

const unidades = [
  { id: '712', codigo: 'ESART', nombre: 'Escuela de Artillería' },
  { id: '913', codigo: 'BAART1', nombre: 'Batallón de Artillería' },
  { id: '914', codigo: 'BAART2', nombre: 'Batallón de Artillería' },
];
describe('Normalización institucional de Excel', () => {
  it.each([
    ['MASCULINO', 'M'],
    [' femenino ', 'F'],
    ['m', 'M'],
    ['F', 'F'],
  ])('normaliza %s como %s', (valor, esperado) => {
    expect(normalizarGenero(valor)).toBe(esperado);
  });
  it('resuelve nombre o sigla exacta y no asigna coincidencias aproximadas o ambiguas', () => {
    const indice = indiceUnidades(unidades);
    expect(resolverUnidad(' escuela   de ARTILLERÍA ', indice, unidades)).toBe('712');
    expect(resolverUnidad('esart', indice, unidades)).toBe('712');
    expect(() => resolverUnidad('Escuela', indice, unidades)).toThrow('Unidad no encontrada');
    expect(() => resolverUnidad('Batallón de Artillería', indice, unidades)).toThrow(
      'sigla oficial',
    );
    expect(resolverUnidad('BAART2', indice, unidades)).toBe('914');
    expect(() => resolverUnidad('ESART', indiceUnidades([]), null)).toThrow('No se pudo consultar');
  });
  it('valida el género normalizado y exporta el ID real, conservando el texto en la vista previa', () => {
    const hoja = utils.aoa_to_sheet([
      ['Documento', 'Nombres', 'Apellidos', 'Grado', 'Género', 'Categoría', 'Unidad'],
      ['00001', 'Ana', 'Pérez', 'SL', 'FEMENINO', 'OFICIAL', ' esart '],
      ['00002', 'Juan', 'Díaz', 'SL', 'MASCULINO', 'OFICIAL', 'Escuela de Artillería'],
    ]);
    const analisis = analizarHoja(hoja, true, unidades);
    expect(analisis.incidencias).toEqual([]);
    expect(analisis.filas[0].valores[4]).toBe('FEMENINO');
    const libro = utils.book_new();
    utils.book_append_sheet(libro, hoja, 'PERSONAL');
    const salida = read(prepararHoja(libro, 'PERSONAL', unidades));
    const filas = utils.sheet_to_json<Record<string, unknown>>(salida.Sheets['PERSONAL']);
    expect(filas.map((f) => [f['genero'], f['unidad_actual_id']])).toEqual([
      ['F', '712'],
      ['M', '712'],
    ]);
  });
});
