import { SolicitudDecisionConsejo } from '../../../nucleo/modelos/notas';
import { DECISIONES, decisionCompleta, hoyIso, textoDecision } from './consejo';

describe('Consejo Académico (S2-14)', () => {
  const datos = (cambios: Partial<SolicitudDecisionConsejo>): SolicitudDecisionConsejo => ({
    decision: 'APRUEBA_MATERIA',
    numero_acta: 'Acta 014',
    fecha_acta: '2026-11-20',
    observacion: null,
    ...cambios,
  });

  it('ofrece la lista fija de decisiones de la Escuela', () => {
    expect(DECISIONES.map((d) => d.valor)).toEqual([
      'APRUEBA_MATERIA',
      'REPITE_CURSO',
      'PIERDE_CURSO',
      'OTRA',
    ]);
    expect(textoDecision('REPITE_CURSO')).toBe('Repite el curso');
    expect(textoDecision(null)).toBe('Sin decisión');
  });

  it('exige número y fecha del acta, y observación cuando la decisión es "Otra"', () => {
    const hoy = '2026-11-26';
    expect(decisionCompleta(datos({}), hoy)).toBe(true);
    expect(decisionCompleta(datos({ numero_acta: '  ' }), hoy)).toBe(false);
    expect(decisionCompleta(datos({ fecha_acta: '2026-11-27' }), hoy)).toBe(false);
    expect(decisionCompleta(datos({ fecha_acta: '' }), hoy)).toBe(false);
    expect(decisionCompleta(datos({ decision: 'OTRA' }), hoy)).toBe(false);
    expect(
      decisionCompleta(datos({ decision: 'OTRA', observacion: 'Curso de nivelación' }), hoy),
    ).toBe(true);
  });

  it('escribe la fecha de hoy en formato AAAA-MM-DD', () => {
    expect(hoyIso(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});
