import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { estiloEstadoCurso, textoEstadoCurso } from '../../../nucleo/estados-curso';
import {
  DetalleCurso,
  InstructorDisponible,
  MateriaDelCurso,
} from '../../../nucleo/modelos/cursos';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import { CursosService } from '../../../nucleo/servicios/cursos.service';
import { SesionService } from '../../../nucleo/servicios/sesion.service';

const COMPONENTE = 'CURSOS';

/** Cuántas materias con nota tienen instructor (las sin nota no llevan). */
export function resumenAsignacion(materias: ReadonlyArray<MateriaDelCurso>): {
  asignadas: number;
  conNota: number;
} {
  const conNota = materias.filter((materia) => materia.evaluable);
  return {
    asignadas: conNota.filter((materia) => materia.instructor_id !== null).length,
    conNota: conNota.length,
  };
}

/**
 * Detalle de un curso (S2-02): datos, malla con que se creó y el instructor titular de cada
 * materia con nota. Quien tiene CURSOS "actualizar" (el Inspector de Estudios, por excepción)
 * asigna, cambia o quita instructores y, si el curso se creó sin malla, le asigna la vigente.
 * Cada cambio queda en la auditoría.
 */
@Component({
  selector: 'esart-detalle-curso',
  imports: [DatePipe, DecimalPipe, FormsModule, RouterLink],
  templateUrl: './detalle-curso.html',
})
export class DetalleCursoPagina {
  private readonly servicio = inject(CursosService);
  private readonly sesion = inject(SesionService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly destruir = inject(DestroyRef);

  protected readonly textoEstado = textoEstadoCurso;
  protected readonly estiloEstado = estiloEstadoCurso;
  protected readonly puedeAsignar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));

  protected readonly curso = signal<DetalleCurso | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);
  protected readonly instructores = signal<InstructorDisponible[]>([]);
  /** Materia (malla_id) con un cambio en curso: deshabilita su selector. */
  protected readonly ocupada = signal<number | null>(null);
  protected readonly asignandoMalla = signal(false);
  /** Cambia para volver a dibujar las filas (deshace en pantalla un cambio cancelado o fallido). */
  protected readonly vuelta = signal(0);

  protected readonly resumen = computed(() => resumenAsignacion(this.curso()?.materias ?? []));
  protected readonly puedeEditar = computed(
    () => this.puedeAsignar() && (this.curso()?.editable ?? false),
  );

  private readonly cursoId = Number(this.ruta.snapshot.paramMap.get('id'));

  constructor() {
    this.cargar();
    if (this.puedeAsignar()) {
      this.servicio
        .instructoresDisponibles()
        .pipe(takeUntilDestroyed(this.destruir))
        .subscribe({
          next: (lista) => this.instructores.set(lista),
          error: () => this.instructores.set([]),
        });
    }
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.servicio
      .detalle(this.cursoId)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (curso) => {
          this.curso.set(curso);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  /** El selector cambió: '' quita al instructor; un id lo pone o lo cambia. */
  protected asignar(materia: MateriaDelCurso, valor: string): void {
    const instructorId = valor === '' ? null : Number(valor);
    if (instructorId === materia.instructor_id) return;
    if (
      instructorId === null &&
      !confirm(`¿Quitar a ${materia.instructor} de ${materia.materia}?`)
    ) {
      this.recargarFila();
      return;
    }
    this.ocupada.set(materia.malla_id);
    this.error.set(null);
    this.aviso.set(null);
    this.servicio
      .asignarInstructor(this.cursoId, materia.malla_id, instructorId)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (curso) => {
          this.curso.set(curso);
          this.ocupada.set(null);
          this.aviso.set(
            instructorId === null
              ? `Se quitó el instructor de ${materia.materia}.`
              : `Instructor asignado a ${materia.materia}.`,
          );
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.ocupada.set(null);
          this.recargarFila();
        },
      });
  }

  protected asignarMalla(): void {
    const curso = this.curso();
    if (!curso?.version_vigente_disponible || this.asignandoMalla()) return;
    if (
      !confirm(
        `¿Asignar a ${curso.codigo} la versión ${curso.version_vigente_disponible} de la malla de ` +
          `${curso.tipo_curso}? El curso la conservará aunque después se creen versiones nuevas.`,
      )
    ) {
      return;
    }
    this.asignandoMalla.set(true);
    this.error.set(null);
    this.servicio
      .asignarMallaVigente(this.cursoId)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (detalle) => {
          this.curso.set(detalle);
          this.asignandoMalla.set(false);
          this.aviso.set('Malla asignada. Ahora puede asignar el instructor de cada materia.');
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.asignandoMalla.set(false);
        },
      });
  }

  /** El instructor asignado sigue activo (si no, el selector lo muestra como inactivo). */
  protected estaDisponible(instructorId: number): boolean {
    return this.instructores().some((instructor) => instructor.id === instructorId);
  }

  /** Vuelve a dibujar las filas con lo guardado (deshace el cambio del selector en pantalla). */
  private recargarFila(): void {
    this.vuelta.update((valor) => valor + 1);
  }
}
