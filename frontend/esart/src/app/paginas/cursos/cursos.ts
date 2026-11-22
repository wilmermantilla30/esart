import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { estiloEstadoCurso, textoEstadoCurso } from '../../nucleo/estados-curso';
import { CursoListado, EstadoCurso, FiltrosCursos } from '../../nucleo/modelos/cursos';
import { ErrorApi, leerErrorApi } from '../../nucleo/modelos/error-api';
import { CursosService } from '../../nucleo/servicios/cursos.service';

export const ESTADOS_FILTRO: ReadonlyArray<{ valor: EstadoCurso | ''; texto: string }> = [
  { valor: '', texto: 'Todos' },
  { valor: 'EN_CURSO', texto: 'En curso' },
  { valor: 'APLAZADO', texto: 'Aplazados' },
  { valor: 'CULMINADO', texto: 'Culminados' },
  { valor: 'CANCELADO', texto: 'Cancelados' },
];

/** Texto del avance de asignación de instructores de un curso (por ejemplo, "3 de 11"). */
export function avanceAsignacion(curso: CursoListado): string {
  if (curso.version_malla === null) return 'Sin malla';
  return `${curso.asignadas} de ${curso.materias_con_nota}`;
}

/**
 * Módulo Cursos (S2-02, componente CURSOS): lista de cursos con filtros. Desde el detalle de
 * cada curso el Inspector de Estudios asigna el instructor titular de cada materia con nota.
 */
@Component({
  selector: 'esart-cursos',
  imports: [DatePipe, FormsModule, RouterLink],
  templateUrl: './cursos.html',
})
export class Cursos {
  private readonly servicio = inject(CursosService);
  private readonly destruir = inject(DestroyRef);

  protected readonly estados = ESTADOS_FILTRO;
  protected readonly textoEstado = textoEstadoCurso;
  protected readonly estiloEstado = estiloEstadoCurso;
  protected readonly avance = avanceAsignacion;
  /** Por defecto se ven los cursos en curso: son los que reciben instructores y notas. */
  protected filtros: FiltrosCursos = { estado: 'EN_CURSO', tipo: '', texto: '' };

  protected readonly cursos = signal<CursoListado[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.servicio
      .listar(this.filtros)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (cursos) => {
          this.cursos.set(cursos);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected limpiar(): void {
    this.filtros = { estado: 'EN_CURSO', tipo: '', texto: '' };
    this.cargar();
  }
}
