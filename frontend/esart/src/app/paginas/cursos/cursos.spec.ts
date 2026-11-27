import { estiloEstadoCurso, textoEstadoCurso } from '../../nucleo/estados-curso';
import { CursoListado, MateriaDelCurso } from '../../nucleo/modelos/cursos';
import { avanceAsignacion } from './cursos';
import { resumenAsignacion } from './detalle-curso/detalle-curso';

describe('Módulo Cursos (S2-02)', () => {
  const curso = (cambios: Partial<CursoListado>): CursoListado => ({
    id: 1,
    codigo: 'SIM-01',
    nombre: 'Curso de prueba',
    tipo_curso: 'SACLI',
    fecha_inicio: '2026-09-01',
    fecha_fin: '2026-11-10',
    estado: 'EN_CURSO',
    alumnos: 20,
    comandante: null,
    version_malla: 1,
    materias_con_nota: 11,
    asignadas: 3,
    ...cambios,
  });

  it('muestra el avance de instructores asignados o "Sin malla"', () => {
    expect(avanceAsignacion(curso({}))).toBe('3 de 11');
    expect(avanceAsignacion(curso({ version_malla: null }))).toBe('Sin malla');
  });

  it('cuenta solo las materias con nota al resumir la asignación', () => {
    const materia = (
      evaluable: boolean,
      instructorId: number | null,
      porItems = false,
    ): MateriaDelCurso => ({
      malla_id: Math.random(),
      orden: 1,
      codigo_materia: 'MAT-001',
      materia: 'X',
      area: null,
      modulo: null,
      evaluable,
      por_items: porItems,
      instructor_id: instructorId,
      instructor: null,
      tipo_instructor: null,
      asignado_en: null,
      asignado_por: null,
    });
    expect(
      resumenAsignacion([materia(true, 7), materia(true, null), materia(false, null)]),
    ).toEqual({ asignadas: 1, conNota: 2 });
    // S2-16: la fase de campaña la registra el comandante: cuenta como asignada.
    expect(resumenAsignacion([materia(true, null, true), materia(true, null)])).toEqual({
      asignadas: 1,
      conNota: 2,
    });
  });

  it('traduce y colorea los estados del curso en un solo lugar', () => {
    expect(textoEstadoCurso('EN_CURSO')).toBe('En curso');
    expect(estiloEstadoCurso('CANCELADO')).toContain('text-error');
    expect(textoEstadoCurso('OTRO')).toBe('OTRO');
  });
});
