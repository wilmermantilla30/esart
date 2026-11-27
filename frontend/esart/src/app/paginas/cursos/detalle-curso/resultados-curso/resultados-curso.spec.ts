import { ResultadoAlumno, ResultadosCurso } from '../../../../nucleo/modelos/cursos';
import { pendientesDelCierre, resumenResultados } from './resultados-curso';

describe('Resultados del curso (S2-15)', () => {
  const alumno = (cambios: Partial<ResultadoAlumno>): ResultadoAlumno => ({
    cedula: '1012345678',
    grado: 'SV',
    apellidos: 'Pérez',
    nombres: 'Juan',
    nota_final: 4.1,
    materias_evaluadas: 2,
    materias_habilitadas: 0,
    pendientes: [],
    resultado: 'APROBADO',
    motivo: null,
    puesto: 1,
    ...cambios,
  });

  it('cuenta aprobados, reprobados y alumnos sin resultado', () => {
    expect(
      resumenResultados([
        alumno({}),
        alumno({ resultado: 'REPROBADO', puesto: null }),
        alumno({ resultado: null, puesto: null }),
        alumno({ puesto: 2 }),
      ]),
    ).toEqual({ aprobados: 2, reprobados: 1, pendientes: 1 });
  });

  it('junta lo que falta del curso y de cada alumno', () => {
    const datos = {
      pendientes: ['Topografía: notas en revisión.'],
      alumnos: [
        alumno({ pendientes: ['Balística: debe habilitar.'], resultado: null }),
        alumno({ apellidos: 'Gómez' }),
      ],
    } as ResultadosCurso;
    expect(pendientesDelCierre(datos)).toEqual([
      'Topografía: notas en revisión.',
      'Pérez Juan: Balística: debe habilitar.',
    ]);
  });
});
