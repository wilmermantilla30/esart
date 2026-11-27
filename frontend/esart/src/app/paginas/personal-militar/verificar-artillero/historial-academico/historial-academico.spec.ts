import { TestBed } from '@angular/core/testing';

import { CursoAcademico } from '../../../../nucleo/modelos/verificacion';
import { ESTADOS_MATERIA, HistorialAcademico, resumenCurso } from './historial-academico';

describe('Historial académico del artillero (S2-17)', () => {
  const curso = (cambios: Partial<CursoAcademico>): CursoAcademico => ({
    codigo: 'SACLI 03',
    nombre: 'SACLI 2026-2',
    tipo_curso: 'SACLI',
    fecha_inicio: '2026-08-03',
    fecha_fin: '2026-11-20',
    estado_curso: 'CULMINADO',
    cerrado: true,
    nota_minima: 3,
    nota_final: 4.1,
    resultado: 'APROBADO',
    motivo: null,
    puesto: 3,
    aprobados_del_curso: 25,
    materias_con_nota: 2,
    materias: [
      { orden: 1, materia: 'Topografía', nota: 4.2, estado: null, instructor: 'SV Gómez' },
      { orden: 2, materia: 'Balística', nota: 4, estado: 'HABILITADA', instructor: null },
    ],
    ...cambios,
  });

  it('resume el curso cerrado con su nota final y el puesto', () => {
    expect(resumenCurso(curso({}))).toBe('Nota final 4,10 · Aprobado · Puesto 3 de 25');
    expect(resumenCurso(curso({ resultado: 'REPROBADO', puesto: null }))).toContain('Sin puesto');
  });

  it('marca el curso en curso como parcial', () => {
    expect(
      resumenCurso(curso({ cerrado: false, materias_con_nota: 1, nota_final: null, puesto: null })),
    ).toBe('En curso: 1 de 2 materias con nota aprobada');
  });

  it('dice en palabras cómo terminó cada materia habilitada', () => {
    expect(ESTADOS_MATERIA.HABILITADA.texto).toBe('Habilitada');
    expect(ESTADOS_MATERIA.HABILITACION_PERDIDA.estilo).toContain('text-error');
  });

  it('dibuja cada curso con sus materias y la marca de habilitada', () => {
    const fixture = TestBed.createComponent(HistorialAcademico);
    fixture.componentRef.setInput('cursos', [curso({})]);
    fixture.detectChanges();
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Historial académico');
    expect(texto).toContain('Nota final 4,10 · Aprobado · Puesto 3 de 25');
    expect(texto).toContain('Topografía');
    expect(texto).toContain('Habilitada');
  });

  it('avisa cuando no hay notas en la plataforma', () => {
    const fixture = TestBed.createComponent(HistorialAcademico);
    fixture.componentRef.setInput('cursos', []);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'No tiene notas registradas en la plataforma.',
    );
  });
});
