import { DatePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Observable, of, switchMap } from 'rxjs';

import { ErrorApi, leerErrorApi } from '../../nucleo/modelos/error-api';
import {
  CursosDelInstructor,
  DatosInstructor,
  Especialidad,
  EstadoInstructores,
  Instructor,
  MilitarParaInstructor,
  TipoInstructor,
} from '../../nucleo/modelos/instructores';
import {
  InstructoresService,
  inicialesInstructor,
  urlFotoInstructor,
} from '../../nucleo/servicios/instructores.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';

const COMPONENTE = 'INSTRUCTORES';

/** Estados del curso (los del cargue por Excel) en palabras y con su color. */
const ESTADOS_CURSO: Record<string, { texto: string; estilo: string }> = {
  EN_CURSO: {
    texto: 'En curso',
    estilo: 'bg-azul-hielo text-azul-institucional border-azul-claro',
  },
  CULMINADO: { texto: 'Culminado', estilo: 'bg-success/10 text-success border-success/30' },
  CANCELADO: { texto: 'Cancelado', estilo: 'bg-error/10 text-error border-error/30' },
  APLAZADO: { texto: 'Aplazado', estilo: 'bg-warning/10 text-warning border-warning/40' },
};
export const TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024;
const TIPOS_FOTO = ['image/jpeg', 'image/png', 'image/webp'];

/** Valida la foto en el navegador (el backend vuelve a comprobarla y la reduce). */
export function errorDeFoto(archivo: File): string | null {
  if (!TIPOS_FOTO.includes(archivo.type)) return 'La foto debe ser JPG, PNG o WebP.';
  if (archivo.size > TAMANO_MAXIMO_FOTO) return 'La foto supera el tamaño máximo de 5 MB.';
  return null;
}

/** Fecha de hoy en formato del campo date (AAAA-MM-DD), hora local. */
function hoyIso(): string {
  const hoy = new Date();
  return new Date(hoy.getTime() - hoy.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/**
 * Instructores de la Escuela de Artillería (componente INSTRUCTORES).
 *
 * Directorio con foto y especialidades. Un instructor MILITAR se busca por cédula en
 * Personal militar (nombre, grado y unidad salen de allí); uno CIVIL se registra con sus datos.
 * Registrar exige el permiso "crear"; editar, la foto y activar/desactivar, "actualizar".
 */
@Component({
  selector: 'esart-instructores',
  imports: [DatePipe, FormsModule],
  templateUrl: './instructores.html',
})
export class Instructores {
  private readonly servicio = inject(InstructoresService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeCrear = computed(() => this.sesion.puede(COMPONENTE, 'crear'));
  protected readonly puedeEditar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));
  protected readonly urlFoto = urlFotoInstructor;
  protected readonly iniciales = inicialesInstructor;
  protected readonly hoy = hoyIso();

  // --- Directorio ---
  protected texto = '';
  protected especialidadFiltro = '';
  protected estado: EstadoInstructores = 'ACTIVOS';
  protected readonly instructores = signal<Instructor[]>([]);
  protected readonly especialidades = signal<Especialidad[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);
  protected readonly ocupado = signal<number | null>(null);

  // --- Formulario (nuevo o edición) ---
  protected readonly formularioAbierto = signal(false);
  /** null = registrar uno nuevo; si no, el instructor que se edita. */
  protected readonly editando = signal<Instructor | null>(null);
  protected readonly tipo = signal<TipoInstructor>('MILITAR');
  protected readonly documento = signal('');
  protected readonly militar = signal<MilitarParaInstructor | null>(null);
  protected readonly buscando = signal(false);
  protected readonly nombres = signal('');
  protected readonly apellidos = signal('');
  protected readonly profesion = signal('');
  protected readonly fechaIngreso = signal(hoyIso());
  protected readonly seleccion = signal<string[]>([]);
  protected readonly foto = signal<File | null>(null);
  protected readonly vistaFoto = signal<string | null>(null);
  protected readonly quitarFotoActual = signal(false);
  protected readonly guardando = signal(false);
  protected readonly errorFormulario = signal<string | null>(null);

  // --- Detalle (cursos del instructor) ---
  protected readonly detalle = signal<Instructor | null>(null);
  protected readonly cursos = signal<CursosDelInstructor | null>(null);
  protected readonly errorCursos = signal<string | null>(null);

  protected readonly puedeGuardar = computed(() => {
    if (this.guardando() || !this.fechaIngreso()) return false;
    if (this.editando()) {
      return this.editando()!.tipo === 'MILITAR' || this.datosCivilesCompletos();
    }
    if (this.tipo() === 'MILITAR') {
      const militar = this.militar();
      return !!militar && militar.activo && !militar.ya_es_instructor;
    }
    return /^\d{5,15}$/.test(this.documento().trim()) && this.datosCivilesCompletos();
  });

  constructor() {
    this.servicio
      .especialidades()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({ next: (lista) => this.especialidades.set(lista) });
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.servicio
      .listar(this.texto.trim(), this.especialidadFiltro, this.estado)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (lista) => {
          this.instructores.set(lista);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected abrirDetalle(instructor: Instructor): void {
    this.detalle.set(instructor);
    this.cursos.set(null);
    this.errorCursos.set(null);
    this.servicio
      .cursos(instructor.id)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (cursos) => this.cursos.set(cursos),
        error: (error: unknown) => this.errorCursos.set(leerErrorApi(error).mensaje),
      });
  }

  protected cerrarDetalle(): void {
    this.detalle.set(null);
    this.cursos.set(null);
  }

  protected nombresEspecialidades(instructor: Instructor): string {
    return instructor.especialidades.map((especialidad) => especialidad.nombre).join(', ');
  }

  protected textoEstado(estado: string): string {
    return ESTADOS_CURSO[estado]?.texto ?? estado;
  }

  protected estiloEstado(estado: string): string {
    return ESTADOS_CURSO[estado]?.estilo ?? 'bg-gris-claro text-azul-pizarra border-gris-bordes';
  }

  protected limpiarFiltros(): void {
    this.texto = '';
    this.especialidadFiltro = '';
    this.estado = 'ACTIVOS';
    this.cargar();
  }

  protected cambiarEstado(instructor: Instructor): void {
    const activar = !instructor.activo;
    if (
      !activar &&
      !confirm(
        `¿Desactivar a ${instructor.nombre_completo}? Dejará de aparecer como instructor activo.`,
      )
    ) {
      return;
    }
    this.ocupado.set(instructor.id);
    this.error.set(null);
    this.servicio
      .cambiarEstado(instructor.id, activar)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (actualizado) => {
          this.ocupado.set(null);
          this.aviso.set(`${actualizado.nombre_completo} ${activar ? 'activado' : 'desactivado'}.`);
          this.cargar();
        },
        error: (error: unknown) => {
          this.ocupado.set(null);
          this.error.set(leerErrorApi(error));
        },
      });
  }

  // --- Formulario ---

  protected abrirNuevo(): void {
    this.editando.set(null);
    this.tipo.set('MILITAR');
    this.documento.set('');
    this.militar.set(null);
    this.nombres.set('');
    this.apellidos.set('');
    this.profesion.set('');
    this.fechaIngreso.set(hoyIso());
    this.seleccion.set([]);
    this.prepararFormulario();
  }

  protected abrirEdicion(instructor: Instructor): void {
    this.editando.set(instructor);
    this.tipo.set(instructor.tipo);
    this.documento.set(instructor.documento);
    this.militar.set(null);
    this.nombres.set(instructor.nombres ?? '');
    this.apellidos.set(instructor.apellidos ?? '');
    this.profesion.set(instructor.profesion ?? '');
    this.fechaIngreso.set(instructor.fecha_ingreso_escuela);
    this.seleccion.set(instructor.especialidades.map((especialidad) => especialidad.codigo));
    this.prepararFormulario();
  }

  protected cerrarFormulario(): void {
    this.formularioAbierto.set(false);
    this.elegirFoto(null);
  }

  protected cambiarTipo(tipo: TipoInstructor): void {
    this.tipo.set(tipo);
    this.militar.set(null);
    this.errorFormulario.set(null);
  }

  protected buscarMilitar(): void {
    const cedula = this.documento().replace(/[\s.-]/g, '');
    this.militar.set(null);
    if (!/^\d{5,15}$/.test(cedula)) {
      this.errorFormulario.set('Escriba la cédula solo con números (5 a 15 dígitos).');
      return;
    }
    this.buscando.set(true);
    this.errorFormulario.set(null);
    this.servicio
      .buscarMilitar(cedula)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (militar) => {
          this.militar.set(militar);
          this.buscando.set(false);
        },
        error: (error: unknown) => {
          this.errorFormulario.set(leerErrorApi(error).mensaje);
          this.buscando.set(false);
        },
      });
  }

  protected alternarEspecialidad(codigo: string): void {
    this.seleccion.update((lista) =>
      lista.includes(codigo) ? lista.filter((actual) => actual !== codigo) : [...lista, codigo],
    );
  }

  protected fotoElegida(evento: Event): void {
    const entrada = evento.target as HTMLInputElement;
    const archivo = entrada.files?.[0] ?? null;
    entrada.value = '';
    if (!archivo) return;
    const error = errorDeFoto(archivo);
    if (error) {
      this.errorFormulario.set(error);
      return;
    }
    this.errorFormulario.set(null);
    this.quitarFotoActual.set(false);
    this.elegirFoto(archivo);
  }

  protected marcarQuitarFoto(): void {
    this.elegirFoto(null);
    this.quitarFotoActual.set(true);
  }

  /** Guarda los datos y después la foto (si se eligió una nueva o se pidió quitarla). */
  protected guardar(): void {
    if (!this.puedeGuardar()) return;
    const datos: DatosInstructor = {
      fecha_ingreso_escuela: this.fechaIngreso(),
      especialidades: this.seleccion(),
      profesion: this.profesion().trim() || null,
      nombres: this.nombres().trim() || null,
      apellidos: this.apellidos().trim() || null,
    };
    const editando = this.editando();
    const guardarDatos: Observable<Instructor> = editando
      ? this.servicio.actualizar(editando.id, datos)
      : this.servicio.registrar({
          ...datos,
          tipo: this.tipo(),
          documento: this.documento().replace(/[\s.-]/g, ''),
        });
    const foto = this.foto();
    const quitar = this.quitarFotoActual();

    this.guardando.set(true);
    this.errorFormulario.set(null);
    guardarDatos
      .pipe(
        switchMap((instructor) => {
          if (foto) return this.servicio.cambiarFoto(instructor.id, foto);
          if (quitar && instructor.tiene_foto) return this.servicio.quitarFoto(instructor.id);
          return of(instructor);
        }),
        takeUntilDestroyed(this.destruir),
      )
      .subscribe({
        next: (instructor) => {
          this.guardando.set(false);
          this.cerrarFormulario();
          this.aviso.set(
            `${instructor.nombre_completo} ${editando ? 'actualizado' : 'registrado'}.`,
          );
          this.cargar();
        },
        error: (error: unknown) => {
          this.guardando.set(false);
          this.errorFormulario.set(leerErrorApi(error).mensaje);
          // Si los datos se guardaron pero falló la foto, la lista debe mostrar lo guardado.
          this.cargar();
        },
      });
  }

  private datosCivilesCompletos(): boolean {
    return (
      this.tipo() !== 'CIVIL' ||
      (this.nombres().trim().length >= 2 && this.apellidos().trim().length >= 2)
    );
  }

  private prepararFormulario(): void {
    this.elegirFoto(null);
    this.quitarFotoActual.set(false);
    this.errorFormulario.set(null);
    this.aviso.set(null);
    this.formularioAbierto.set(true);
  }

  /** Cambia la foto elegida y libera la vista previa anterior (URL temporal en memoria). */
  private elegirFoto(archivo: File | null): void {
    const anterior = this.vistaFoto();
    if (anterior) URL.revokeObjectURL(anterior);
    this.foto.set(archivo);
    this.vistaFoto.set(archivo ? URL.createObjectURL(archivo) : null);
  }
}
