import { read, utils, write } from 'xlsx';
import { leerLibro, prepararHoja } from './excel-libro';

function libroEjemplo() {
  const libro = utils.book_new();
  utils.book_append_sheet(
    libro,
    utils.aoa_to_sheet([
      ['Documento', 'Nombres', 'Apellidos', 'Grado', 'Género', 'Categoría', 'Activo', 'Extra'],
      ['00001', 'Ana', 'Pérez', 'SL', 'F', 'OFICIAL', 'No', 'No enviar'],
    ]),
    'ELEGIDA',
  );
  utils.book_append_sheet(libro, utils.aoa_to_sheet([['No enviar esta hoja']]), 'OTRA');
  return libro;
}

describe('Formato real y exportación de Excel', () => {
  it.each(['xlsx', 'biff8'] as const)('lee un libro real %s y detecta sus hojas', (bookType) => {
    const buffer = write(libroEjemplo(), { type: 'array', bookType });
    expect(leerLibro(buffer, bookType === 'biff8' ? 'xls' : 'xlsx').SheetNames).toEqual([
      'ELEGIDA',
      'OTRA',
    ]);
  });
  it('rechaza CSV renombrado, extensión incorrecta y un ZIP de formato ODS', () => {
    const texto = new TextEncoder().encode('Documento,Nombres\n123,Ana').buffer;
    expect(() => leerLibro(texto, 'xlsx')).toThrow('formato');
    expect(() =>
      leerLibro(write(libroEjemplo(), { type: 'array', bookType: 'xlsx' }), 'xls'),
    ).toThrow('formato');
    expect(() =>
      leerLibro(write(libroEjemplo(), { type: 'array', bookType: 'ods' }), 'xlsx'),
    ).toThrow('válido');
  });
  it('genera únicamente la hoja seleccionada con atributos canónicos y booleanos', () => {
    const buffer = prepararHoja(libroEjemplo(), 'ELEGIDA', null);
    const salida = read(buffer, { type: 'array' });
    expect(salida.SheetNames).toEqual(['ELEGIDA']);
    const filas = utils.sheet_to_json<Record<string, unknown>>(salida.Sheets['ELEGIDA']);
    expect(filas).toEqual([
      {
        documento_identidad: '00001',
        nombres: 'Ana',
        apellidos: 'Pérez',
        grado: 'SL',
        genero: 'F',
        categoria: 'OFICIAL',
        activo: false,
      },
    ]);
  });
  it('impide exportar una hoja con errores aunque el cliente pida exportarla', () => {
    expect(() => prepararHoja(libroEjemplo(), 'OTRA', null)).toThrow('bloqueantes');
  });
});
