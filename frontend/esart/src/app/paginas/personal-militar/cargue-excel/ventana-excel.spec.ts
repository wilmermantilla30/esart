import { ajustarRectangulo, redimensionarRectangulo, BordeVentana } from './ventana-excel';

const rect = { x: 100, y: 100, ancho: 800, alto: 500 };
const viewport = { ancho: 1400, alto: 1000 };
const casos: [BordeVentana, number, number, number, number][] = [
  ['n', 100, 130, 800, 470],
  ['s', 100, 100, 800, 530],
  ['e', 100, 100, 840, 500],
  ['o', 140, 100, 760, 500],
  ['ne', 100, 130, 840, 470],
  ['no', 140, 130, 760, 470],
  ['se', 100, 100, 840, 530],
  ['so', 140, 100, 760, 530],
];
describe('Geometría de la ventana de Excel', () => {
  it.each(casos)(
    'redimensiona desde %s conservando el lado opuesto',
    (borde, x, y, ancho, alto) => {
      expect(redimensionarRectangulo(rect, borde, 40, 30, viewport)).toEqual({ x, y, ancho, alto });
    },
  );
  it('limita todos los bordes al viewport y al mínimo utilizable', () => {
    expect(redimensionarRectangulo(rect, 'no', -5000, -5000, viewport)).toEqual({
      x: 8,
      y: 8,
      ancho: 892,
      alto: 592,
    });
    expect(redimensionarRectangulo(rect, 'se', 5000, 5000, viewport)).toEqual({
      x: 100,
      y: 100,
      ancho: 1292,
      alto: 892,
    });
    expect(redimensionarRectangulo(rect, 'no', 5000, 5000, viewport)).toEqual({
      x: 260,
      y: 180,
      ancho: 640,
      alto: 420,
    });
    expect(redimensionarRectangulo(rect, 'se', -5000, -5000, viewport)).toEqual({
      x: 100,
      y: 100,
      ancho: 640,
      alto: 420,
    });
  });
  it('ajusta una ventana guardada si la pantalla se reduce, incluso por debajo del mínimo', () => {
    expect(ajustarRectangulo(rect, { ancho: 375, alto: 300 })).toEqual({
      x: 8,
      y: 8,
      ancho: 359,
      alto: 284,
    });
  });
});
