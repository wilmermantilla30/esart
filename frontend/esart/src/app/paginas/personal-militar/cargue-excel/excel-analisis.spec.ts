import { read, utils, write } from 'xlsx';
import { analizarHoja } from './excel-analisis';

const cabecera = [
  'Documento',
  'Nombres',
  'Apellidos',
  'Grado',
  'Género',
  'Categoría',
  'Unidad',
  'Especialidad',
  'Activo',
];
const valido = ['00123', 'Ana', 'Pérez', 'SL', 'F', 'OFICIAL', '42', 'Artillería', 'Sí'];
const unidades = [{ id: '42', codigo: '42', nombre: 'Escuela de Artillería' }];

describe('Análisis de Excel de personal', () => {
  it('conserva ceros del documento, omite filas vacías y calcula el diligenciamiento real', () => {
    const hoja = utils.aoa_to_sheet([
      cabecera,
      valido,
      [],
      ['00456', 'Juan', 'Díaz', 'SL', 'M', 'OFICIAL', '', '', 'No'],
    ]);
    const resultado = analizarHoja(hoja, true, unidades);
    expect(resultado.filas.map((f) => f.numero)).toEqual([2, 4]);
    expect(resultado.filas[0].valores[0]).toBe('00123');
    expect(resultado.columnas[6]).toMatchObject({
      campo: 'unidad_actual_id',
      llenos: 1,
      vacios: 1,
      porcentaje: 50,
    });
    expect(resultado.incidencias).toEqual([]);
  });
  it('detecta columnas requeridas ausentes y atributos duplicados', () => {
    const resultado = analizarHoja(
      utils.aoa_to_sheet([
        ['Documento', 'Cédula'],
        ['12', '12'],
      ]),
      true,
    );
    expect(resultado.incidencias.some((i) => i.columna === 'nombres' && i.nivel === 'Error')).toBe(
      true,
    );
    expect(resultado.incidencias.some((i) => i.motivo.includes('mismo atributo'))).toBe(true);
  });
  it('marca ambos registros duplicados y valida unidades, booleanos y longitudes', () => {
    const resultado = analizarHoja(
      utils.aoa_to_sheet([
        cabecera,
        valido,
        ['00123', '', 'Díaz', 'X'.repeat(21), 'Masculino', 'OFICIAL', '999', '', 'Tal vez'],
      ]),
      true,
      unidades,
    );
    expect(
      resultado.incidencias
        .filter((i) => i.motivo.includes('duplicado'))
        .map((i) => i.fila)
        .sort(),
    ).toEqual([2, 3]);
    for (const indice of [1, 3, 6, 8])
      expect(
        resultado.incidencias.some(
          (i) => i.fila === 3 && i.indice === indice && i.nivel === 'Error',
        ),
      ).toBe(true);
  });
  it('no combina hojas al cambiar de selección y limpia la validación', () => {
    const libro = utils.book_new();
    utils.book_append_sheet(libro, utils.aoa_to_sheet([cabecera, valido]), 'ACTIVO');
    utils.book_append_sheet(libro, utils.aoa_to_sheet([cabecera, ['999']]), 'RETIRADO');
    const reabierto = read(write(libro, { type: 'array', bookType: 'xlsx' }), { type: 'array' });
    expect(analizarHoja(reabierto.Sheets['ACTIVO'], true, unidades).incidencias).toEqual([]);
    const otro = analizarHoja(reabierto.Sheets['RETIRADO']);
    expect(otro.validado).toBe(false);
    expect(otro.incidencias).toEqual([]);
    expect(otro.filas).toHaveLength(1);
    expect(otro.filas[0].valores[0]).toBe('999');
  });
  it('lee libros .xls reales y rechaza hojas vacías o excesivas', () => {
    const libro = utils.book_new();
    utils.book_append_sheet(libro, utils.aoa_to_sheet([cabecera, valido]), 'PERSONAL');
    const reabierto = read(write(libro, { type: 'array', bookType: 'biff8' }), { type: 'array' });
    expect(analizarHoja(reabierto.Sheets['PERSONAL'], true, unidades).incidencias).toEqual([]);
    expect(() => analizarHoja({})).toThrow('vacía');
    expect(() => analizarHoja({ '!ref': 'A1:A100001' })).toThrow('límite');
  });
  it('separa advertencias y bloquea fórmulas y errores de Excel', () => {
    const hoja = utils.aoa_to_sheet([
      [...cabecera, 'Observación'],
      [...valido, 'Texto'],
    ]);
    hoja['B2'] = { t: 's', v: 'Ana', f: '"Ana"' };
    hoja['C2'] = { t: 'e', v: 7 };
    const resultado = analizarHoja(hoja, true);
    expect(
      resultado.incidencias.some((i) => i.motivo.includes('fórmula') && i.nivel === 'Error'),
    ).toBe(true);
    expect(resultado.incidencias.some((i) => i.motivo.includes('error de Excel'))).toBe(true);
    expect(resultado.incidencias.filter((i) => i.nivel === 'Advertencia')).toHaveLength(1);
    expect(resultado.incidencias.some((i) => i.indice === 6 && i.nivel === 'Error')).toBe(true);
  });
});
