import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { guardarArchivo } from '../../../nucleo/descargas';
import { estiloEstadoCurso, textoEstadoCurso } from '../../../nucleo/estados-curso';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import {
  EntregaDeMateria,
  ErrorPlanilla,
  EstadoEntrega,
  MateriaDelInstructor,
} from '../../../nucleo/modelos/notas';
import { NotasService } from '../../../nucleo/servicios/notas.service';
import { SesionService } from '../../../nucleo/servicios/sesion.service';

const COMPONENTE = 'NOTAS_CARGA';
/** El backend acepta hasta 25 MB; la plantilla de notas pesa unos pocos KB. */
const TAMANO_MAXIMO_PLANILLA = 25 * 1024 * 1024;

/** Estado de la entrega en palabras y con su color. */
export const ESTADOS_ENTREGA: Record<
  EstadoEntrega | 'SIN_ENTREGA',
  { texto: string; estilo: string }
> = {
  SIN_ENTREGA: { texto: 'Sin notas', estilo: 'bg-gris-claro text-azul-pizarra border-gris-bordes' },
  EN_REVISION: { texto: 'En revisión', estilo: 'bg-warning/10 text-warning border-warning/40' },
  APROBADA: { texto: 'Aprobada', estilo: 'bg-success/10 text-success border-success/30' },
  DEVUELTA: { texto: 'Devuelta', estilo: 'bg-error/10 text-error border-error/30' },
};

export function estadoEntrega(materia: MateriaDelInstructor): { texto: string; estilo: string } {
  return ESTADOS_ENTREGA[materia.estado_entrega ?? 'SIN_ENTREGA'];
}

/** Clave de una materia en un curso (identifica la tarjeta en pantalla). */
export function claveMateria(materia: { curso_id: number; malla_id: number }): string {
  return `${materia.curso_id}-${materia.malla_id}`;
}

/** Errores por fila que el backend devuelve cuando la planilla no se puede aceptar. */
export function erroresDePlanilla(error: ErrorApi): ErrorPlanilla[] {
  const lista = (error.detalle as { errores?: ErrorPlanilla[] } | null)?.errores;
  return Array.isArray(lista) ? lista : [];
}

/**
 * "Carga de notas" del instructor (S2-12, componente NOTAS_CARGA).
 *
 * Muestra las materias que el usuario dicta como titular. Por cada una: descargar la plantilla
 * con los alumnos del curso, subirla con las notas y ver lo enviado. Las notas quedan "En
 * revisión" y no cuentan hasta que el Inspector de Estudios las apruebe.
 */
@Component({
  selector: 'esart-mis-materias',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './mis-materias.html',
})
export class MisMateriasPagina {
  private readonly notas = inject(NotasService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeSubir = computed(() => this.sesion.puede(COMPONENTE, 'crear'));
  protected readonly textoEstadoCurso = textoEstadoCurso;
  protected readonly estiloEstadoCurso = estiloEstadoCurso;
  protected readonly estadoEntrega = estadoEntrega;
  protected readonly clave = claveMateria;

  protected readonly esInstructor = signal(true);
  protected readonly materias = signal<MateriaDelInstructor[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);
  /** Errores por fila de la última planilla rechazada, con la materia a la que pertenecen. */
  protected readonly erroresPlanilla = signal<{ clave: string; errores: ErrorPlanilla[] } | null>(
    null,
  );
  /** Materia con una descarga o carga en curso. */
  protected readonly ocupada = signal<string | null>(null);
  /** Entrega abierta para ver sus notas. */
  protected readonly abierta = signal<EntregaDeMateria | null>(null);
  protected readonly claveAbierta = signal<string | null>(null);

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.notas
      .misMaterias()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (respuesta) => {
          this.esInstructor.set(respuesta.es_instructor);
          this.materias.set(respuesta.materias);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected descargar(materia: MateriaDelInstructor): void {
    this.ocupada.set(claveMateria(materia));
    this.error.set(null);
    this.notas
      .descargarPlantilla(materia.curso_id, materia.malla_id)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: ({ nombre, contenido }) => {
          guardarArchivo(nombre, contenido);
          this.ocupada.set(null);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.ocupada.set(null);
        },
      });
  }

  /** El instructor eligió el archivo: se sube de una vez (el backend valida todo). */
  protected subir(materia: MateriaDelInstructor, entrada: HTMLInputElement): void {
    const archivo = entrada.files?.[0];
    entrada.value = '';
    if (!archivo) return;
    const clave = claveMateria(materia);
    this.error.set(null);
    this.aviso.set(null);
    this.erroresPlanilla.set(null);
    if (!archivo.name.toLowerCase().endsWith('.xlsx') || archivo.size > TAMANO_MAXIMO_PLANILLA) {
      this.error.set({
        codigo: 'ARCHIVO_INVALIDO',
        mensaje: 'Suba la plantilla descargada de la plataforma (.xlsx).',
        detalle: null,
        estadoHttp: 0,
      });
      return;
    }
    if (
      materia.estado_entrega === 'EN_REVISION' &&
      !confirm(`Ya envió notas de ${materia.materia}. ¿Reemplazarlas con este archivo?`)
    ) {
      return;
    }
    this.ocupada.set(clave);
    this.notas
      .subir(materia.curso_id, materia.malla_id, archivo)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (entrega) => {
          this.ocupada.set(null);
          this.aviso.set(
            `Notas de ${entrega.materia} (curso ${entrega.codigo_curso}) enviadas: quedan en revisión del Inspector de Estudios.`,
          );
          if (this.claveAbierta() === clave) this.abierta.set(entrega);
          this.cargar();
        },
        error: (error: unknown) => {
          this.ocupada.set(null);
          const fallo = leerErrorApi(error);
          this.error.set(fallo);
          const errores = erroresDePlanilla(fallo);
          if (errores.length) this.erroresPlanilla.set({ clave, errores });
        },
      });
  }

  protected verNotas(materia: MateriaDelInstructor): void {
    const clave = claveMateria(materia);
    if (this.claveAbierta() === clave) {
      this.claveAbierta.set(null);
      this.abierta.set(null);
      return;
    }
    this.claveAbierta.set(clave);
    this.abierta.set(null);
    this.notas
      .entrega(materia.curso_id, materia.malla_id)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (entrega) => this.abierta.set(entrega),
        error: (error: unknown) => this.error.set(leerErrorApi(error)),
      });
  }
}
