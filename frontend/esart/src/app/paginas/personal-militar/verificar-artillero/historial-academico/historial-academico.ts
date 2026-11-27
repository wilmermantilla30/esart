import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, input } from '@angular/core';

import { CursoAcademico, MateriaAcademica } from '../../../../nucleo/modelos/verificacion';

/** Cómo terminó una materia que pasó por habilitación, en palabras y con su color. */
export const ESTADOS_MATERIA: Record<
  NonNullable<MateriaAcademica['estado']>,
  { texto: string; estilo: string }
> = {
  HABILITADA: { texto: 'Habilitada', estilo: 'bg-warning/10 text-warning border-warning/40' },
  APROBADA_POR_CONSEJO: {
    texto: 'Aprobada por el Consejo',
    estilo: 'bg-azul-hielo text-azul-institucional border-azul-claro',
  },
  HABILITACION_PERDIDA: {
    texto: 'Habilitación perdida',
    estilo: 'bg-error/10 text-error border-error/30',
  },
};

/** Resumen del curso: nota final, resultado y puesto ("3 de 25"), o que está en curso. */
export function resumenCurso(curso: CursoAcademico): string {
  if (!curso.cerrado) {
    return `En curso: ${curso.materias_con_nota} de ${curso.materias.length} materias con nota aprobada`;
  }
  const nota = curso.nota_final === null ? '—' : curso.nota_final.toFixed(2).replace('.', ',');
  const resultado = curso.resultado === 'APROBADO' ? 'Aprobado' : 'Reprobado';
  const puesto =
    curso.puesto !== null ? `Puesto ${curso.puesto} de ${curso.aprobados_del_curso}` : 'Sin puesto';
  return `Nota final ${nota} · ${resultado} · ${puesto}`;
}

/**
 * Historial académico del artillero (S2-17) dentro de "Verificar artillero".
 *
 * Por cada curso con notas en la plataforma: materias, nota, si fue habilitada o aprobada por el
 * Consejo, instructor, y la nota final y el puesto (definitivos si el curso se cerró, S2-15). El
 * curso en curso aparece como parcial. Los cursos anteriores o cargados por Excel siguen en la
 * tabla de cursos solo con aprobado / no aprobado.
 */
@Component({
  selector: 'esart-historial-academico',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './historial-academico.html',
})
export class HistorialAcademico {
  readonly cursos = input.required<CursoAcademico[]>();

  protected readonly estados = ESTADOS_MATERIA;
  protected readonly resumenCurso = resumenCurso;
}
