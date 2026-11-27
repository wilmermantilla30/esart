import { ErrorApi } from '../../../nucleo/modelos/error-api';
import { MateriaDelInstructor } from '../../../nucleo/modelos/notas';
import { claveMateria, erroresDePlanilla, estadoEntrega, puedeHabilitar } from './mis-materias';

describe('Carga de notas del instructor (S2-12)', () => {
  const materia = (cambios: Partial<MateriaDelInstructor>): MateriaDelInstructor => ({
    curso_id: 18,
    codigo_curso: 'SIM-CUR-08',
    nombre_curso: 'SACLI 2026-2',
    tipo_curso: 'SACLI',
    estado_curso: 'EN_CURSO',
    fecha_inicio: '2026-10-14',
    fecha_fin: '2026-12-23',
    malla_id: 42,
    orden: 1,
    codigo_materia: 'MAT-001',
    materia: 'PLANEAMIENTO Y R.S.O.P',
    nota_minima: 3,
    alumnos: 12,
    estado_entrega: null,
    subido_en: null,
    revisado_en: null,
    observacion_revision: null,
    notas_entregadas: 0,
    tiene_notas_oficiales: false,
    alumnos_a_habilitar: 0,
    estado_habilitacion: null,
    observacion_habilitacion: null,
    puede_subir: true,
    ...cambios,
  });

  it('muestra el estado de la entrega en palabras', () => {
    expect(estadoEntrega(materia({})).texto).toBe('Sin notas');
    expect(estadoEntrega(materia({ estado_entrega: 'EN_REVISION' })).texto).toBe('En revisión');
    expect(estadoEntrega(materia({ estado_entrega: 'DEVUELTA' })).estilo).toContain('text-error');
  });

  it('identifica cada materia por curso y fila de la malla', () => {
    expect(claveMateria(materia({}))).toBe('18-42');
  });

  it('lee los errores por fila que devuelve el backend', () => {
    const error: ErrorApi = {
      codigo: 'NOTAS_INVALIDAS',
      mensaje: 'La planilla tiene 2 error(es).',
      detalle: {
        errores: [
          { fila: 9, mensaje: 'Falta la nota.' },
          { fila: null, mensaje: 'Falta el alumno 123.' },
        ],
      },
      estadoHttp: 422,
    };
    expect(erroresDePlanilla(error).map((e) => e.fila)).toEqual([9, null]);
    expect(erroresDePlanilla({ ...error, detalle: null })).toEqual([]);
  });

  it('permite registrar la habilitación solo con las notas aprobadas y sin habilitación aprobada', () => {
    const aprobada = { estado_entrega: 'APROBADA' as const, alumnos_a_habilitar: 2 };
    expect(puedeHabilitar(materia(aprobada))).toBe(true);
    expect(puedeHabilitar(materia({ ...aprobada, estado_habilitacion: 'DEVUELTA' }))).toBe(true);
    expect(puedeHabilitar(materia({ ...aprobada, estado_habilitacion: 'APROBADA' }))).toBe(false);
    expect(puedeHabilitar(materia({ ...aprobada, alumnos_a_habilitar: 0 }))).toBe(false);
    expect(puedeHabilitar(materia({ ...aprobada, estado_entrega: 'EN_REVISION' }))).toBe(false);
    expect(puedeHabilitar(materia({ ...aprobada, estado_curso: 'CANCELADO' }))).toBe(false);
  });
});
