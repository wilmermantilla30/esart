import { NotaEnRevision } from '../../../nucleo/modelos/notas';
import { FILTROS, notaCambiada, observacionValida } from './revision';

describe('Revisión de notas del Inspector (S2-13)', () => {
  const nota = (valor: number, oficial: number | null): NotaEnRevision => ({
    cedula: '1012345678',
    grado: 'SV',
    apellidos: 'Pérez',
    nombres: 'Juan',
    nota: valor,
    nota_oficial: oficial,
    nota_ordinaria: null,
  });

  it('empieza por las entregas pendientes', () => {
    expect(FILTROS[0]).toEqual({ valor: 'EN_REVISION', texto: 'Pendientes' });
    expect(FILTROS.map((f) => f.valor)).toContain('TODAS');
  });

  it('exige una observación con el largo que pide el backend', () => {
    expect(observacionValida('Revise la nota de Pérez')).toBe(true);
    expect(observacionValida('  ok  ')).toBe(false);
    expect(observacionValida('   ')).toBe(false);
    expect(observacionValida('x'.repeat(1001))).toBe(false);
  });

  it('resalta solo las notas que cambian en una corrección', () => {
    expect(notaCambiada(nota(3.5, 2.9), true)).toBe(true);
    expect(notaCambiada(nota(3.5, 3.5), true)).toBe(false);
    expect(notaCambiada(nota(3.5, null), true)).toBe(true);
    // Primera entrega (sin notas oficiales): nada se resalta.
    expect(notaCambiada(nota(3.5, null), false)).toBe(false);
  });
});
