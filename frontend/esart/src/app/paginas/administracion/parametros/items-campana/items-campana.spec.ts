import { ItemCampanaPropuesto } from '../../../../nucleo/modelos/parametros';
import { itemsValidos, leerPuntaje, repartirIgual, sumaPuntajes } from './items-campana';

describe('Ítems de la fase de campaña (S2-16)', () => {
  const items = (puntajes: string[]): ItemCampanaPropuesto[] =>
    puntajes.map((puntaje, posicion) => ({ id: null, nombre: `Ítem ${posicion + 1}`, puntaje }));

  it('lee el puntaje con coma o punto y hasta 4 decimales', () => {
    expect(leerPuntaje('0,2632')).toBe(0.2632);
    expect(leerPuntaje(' 2.5 ')).toBe(2.5);
    expect(leerPuntaje('0.26315')).toBeNaN();
    expect(leerPuntaje('abc')).toBeNaN();
  });

  it('reparte 5,00 en partes iguales y suma exacto', () => {
    const partes = repartirIgual(19);
    expect(partes[0]).toBe('0.2631');
    expect(partes).toHaveLength(19);
    expect(Math.round(sumaPuntajes(items(partes)) * 10000)).toBe(50000);
    expect(repartirIgual(0)).toEqual([]);
  });

  it('acepta los 19 ítems iniciales (5,0008 redondea a 5,00) y rechaza lo que no suma', () => {
    expect(itemsValidos(items(Array(19).fill('0.2632')))).toBe(true);
    expect(itemsValidos(items(['2', '2']))).toBe(false);
    expect(itemsValidos(items(['5', '0']))).toBe(false);
    expect(
      itemsValidos([
        { id: null, nombre: 'Tiro', puntaje: '2.5' },
        { id: null, nombre: ' tiro ', puntaje: '2.5' },
      ]),
    ).toBe(false);
  });
});
