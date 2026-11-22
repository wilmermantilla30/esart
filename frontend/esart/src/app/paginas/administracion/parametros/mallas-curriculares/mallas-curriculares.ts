import { DatePipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { EMPTY, Observable, catchError, tap, throwError } from 'rxjs';

import { ErrorApi, leerErrorApi } from '../../../../nucleo/modelos/error-api';
import {
  DetalleMalla,
  FilaMallaEditada,
  MallaEditada,
  MateriaCatalogo,
  ModalidadCurso,
  NuevoTipoCurso,
  TipoCursoMalla,
  TipoDeCurso,
} from '../../../../nucleo/modelos/parametros';
import { ParametrosService } from '../../../../nucleo/servicios/parametros.service';
import { SesionService } from '../../../../nucleo/servicios/sesion.service';
import { Totp } from '../../../totp/totp';

const COMPONENTE = 'MALLAS_CURRICULARES';
/** Errores que se muestran dentro de la ventana del autenticador (el usuario reintenta ahí). */
const CODIGOS_TOTP = new Set(['TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);

export const TIPOS_DE_CURSO: ReadonlyArray<{ valor: TipoDeCurso; texto: string }> = [
  { valor: 'EDUCACION_MILITAR', texto: 'Educación militar' },
  { valor: 'ESPECIALIZACION', texto: 'Especialización del arma' },
  { valor: 'EDUCACION_SUPERIOR', texto: 'Educación superior' },
];
export const MODALIDADES: ReadonlyArray<ModalidadCurso> = ['PRESENCIAL', 'VIRTUAL', 'MIXTA'];

/** Fila del editor: `clave` identifica la fila en pantalla aunque cambie de posición. */
export interface FilaEditor {
  clave: number;
  materia: string;
  evaluable: boolean;
  area: string;
  modulo: string;
}

/** Nombre normalizado como lo compara el backend (espacios simples y mayúsculas). */
export function normalizarMateria(nombre: string): string {
  return nombre.replace(/\s+/g, ' ').trim().toUpperCase();
}

/**
 * Problemas de la malla en edición, en el mismo orden de las reglas del backend
 * (validar_filas): así el usuario los ve antes de gastar un código del autenticador.
 */
export function problemasDeMalla(filas: ReadonlyArray<FilaEditor>): string[] {
  const problemas: string[] = [];
  if (!filas.length) problemas.push('Agregue al menos una materia.');
  if (filas.some((fila) => !normalizarMateria(fila.materia))) {
    problemas.push('Hay materias sin nombre.');
  }
  const nombres = filas.map((fila) => normalizarMateria(fila.materia)).filter(Boolean);
  const repetidas = [...new Set(nombres.filter((nombre, i) => nombres.indexOf(nombre) !== i))];
  if (repetidas.length) problemas.push(`Materias repetidas: ${repetidas.join(', ')}.`);
  if (filas.length && !filas.some((fila) => fila.evaluable)) {
    problemas.push('Debe haber al menos una materia con nota.');
  }
  return problemas;
}

/** Lo que se envía al guardar: el orden es la posición en la tabla (1, 2, 3...). */
export function filasParaGuardar(filas: ReadonlyArray<FilaEditor>): FilaMallaEditada[] {
  return filas.map((fila, posicion) => ({
    orden: posicion + 1,
    materia: fila.materia.replace(/\s+/g, ' ').trim(),
    evaluable: fila.evaluable,
    area: fila.area.trim() || null,
    modulo: fila.modulo.trim() || null,
  }));
}

/**
 * Pestaña "Mallas curriculares" del panel de Parámetros (S2-09, componente MALLAS_CURRICULARES).
 *
 * - Lista los tipos de curso con su versión vigente; TECNICA y los tipos nuevos aparecen sin malla.
 * - Muestra la malla vigente y el historial (cada versión con cuántos cursos la usan).
 * - Editar la malla y guardar crea una VERSIÓN NUEVA (los cursos ya creados conservan la suya).
 * - Crear un tipo de curso. Guardar y crear piden el código del autenticador y quedan auditados.
 */
@Component({
  selector: 'esart-mallas-curriculares',
  imports: [DatePipe, FormsModule, Totp],
  templateUrl: './mallas-curriculares.html',
  styles: `
    .ventana-totp {
      width: 100vw;
      height: 100dvh;
      max-width: none;
      max-height: none;
      margin: 0;
      padding: 0;
      border: 0;
      background: none;
    }
    .ventana-totp::backdrop {
      background: none;
    }
  `,
})
export class MallasCurricularesPestana {
  private readonly parametros = inject(ParametrosService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeEditar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));
  protected readonly puedeCrear = computed(() => this.sesion.puede(COMPONENTE, 'crear'));
  protected readonly tiposDeCurso = TIPOS_DE_CURSO;
  protected readonly modalidades = MODALIDADES;

  // --- Listado y detalle ---
  protected readonly tipos = signal<TipoCursoMalla[]>([]);
  protected readonly cargando = signal(true);
  protected readonly seleccionado = signal<string | null>(null);
  protected readonly detalle = signal<DetalleMalla | null>(null);
  protected readonly cargandoDetalle = signal(false);
  protected readonly materias = signal<MateriaCatalogo[]>([]);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);
  /** Se está viendo una versión histórica (solo consulta). */
  protected readonly viendoHistorica = computed(
    () => this.detalle()?.version?.estado === 'HISTORICA',
  );

  // --- Editor de la malla ---
  protected readonly editando = signal(false);
  protected readonly filas = signal<FilaEditor[]>([]);
  protected readonly anio = signal(new Date().getFullYear());
  protected readonly observacion = signal('');
  private siguienteClave = 1;
  protected readonly problemas = computed(() => problemasDeMalla(this.filas()));
  protected readonly confirmando = signal(false);
  protected readonly guardando = signal(false);

  // --- Nuevo tipo de curso ---
  protected readonly creandoTipo = signal(false);
  protected readonly nuevoTipo = signal<NuevoTipoCurso>(this.tipoVacio());

  // --- Autenticador (una sola ventana para guardar malla o crear tipo) ---
  protected readonly operacionTotp = signal<'malla' | 'tipo' | null>(null);
  protected readonly errorTotp = signal('');
  private readonly ventanaTotp = viewChild<ElementRef<HTMLDialogElement>>('ventanaTotp');

  constructor() {
    this.cargarTipos();
    this.parametros
      .listarMaterias()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({ next: (lista) => this.materias.set(lista), error: () => this.materias.set([]) });
  }

  protected cargarTipos(seleccionar: string | null = this.seleccionado()): void {
    this.cargando.set(true);
    this.parametros
      .listarMallas()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (tipos) => {
          this.tipos.set(tipos);
          this.cargando.set(false);
          const codigo = seleccionar ?? tipos[0]?.codigo ?? null;
          if (codigo) this.seleccionar(codigo);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected seleccionar(codigo: string, version: number | null = null): void {
    if (this.editando() && !confirm('Hay cambios sin guardar en la malla. ¿Descartarlos?')) return;
    this.editando.set(false);
    this.seleccionado.set(codigo);
    this.cargandoDetalle.set(true);
    this.error.set(null);
    this.parametros
      .obtenerMalla(codigo, version)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (detalle) => {
          this.detalle.set(detalle);
          this.cargandoDetalle.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargandoDetalle.set(false);
        },
      });
  }

  // --- Editor ---

  /** Empieza a editar desde la versión vigente (o vacía si el tipo no tiene malla). */
  protected editar(): void {
    const detalle = this.detalle();
    if (!detalle || this.viendoHistorica()) return;
    this.aviso.set(null);
    this.filas.set(
      detalle.filas.map((fila) => ({
        clave: this.siguienteClave++,
        materia: fila.materia,
        evaluable: fila.evaluable,
        area: fila.area ?? '',
        modulo: fila.modulo ?? '',
      })),
    );
    if (!detalle.filas.length) this.agregarFila();
    this.anio.set(new Date().getFullYear());
    this.observacion.set('');
    this.editando.set(true);
  }

  protected cancelarEdicion(): void {
    this.editando.set(false);
    this.confirmando.set(false);
  }

  protected agregarFila(): void {
    this.filas.update((lista) => [
      ...lista,
      { clave: this.siguienteClave++, materia: '', evaluable: true, area: '', modulo: '' },
    ]);
  }

  protected quitarFila(clave: number): void {
    this.filas.update((lista) => lista.filter((fila) => fila.clave !== clave));
  }

  /** Sube (-1) o baja (+1) una materia en el orden de la malla. */
  protected mover(posicion: number, direccion: -1 | 1): void {
    const destino = posicion + direccion;
    this.filas.update((lista) => {
      if (destino < 0 || destino >= lista.length) return lista;
      const copia = [...lista];
      [copia[posicion], copia[destino]] = [copia[destino], copia[posicion]];
      return copia;
    });
  }

  protected cambiarFila(clave: number, campo: 'materia' | 'area' | 'modulo', valor: string): void {
    this.filas.update((lista) =>
      lista.map((fila) => (fila.clave === clave ? { ...fila, [campo]: valor } : fila)),
    );
  }

  protected alternarEvaluable(clave: number): void {
    this.filas.update((lista) =>
      lista.map((fila) => (fila.clave === clave ? { ...fila, evaluable: !fila.evaluable } : fila)),
    );
  }

  protected pedirConfirmacion(): void {
    if (this.problemas().length || this.guardando()) return;
    this.confirmando.set(true);
  }

  private mallaEditada(): MallaEditada {
    return {
      anio: Number(this.anio()),
      filas: filasParaGuardar(this.filas()),
      observacion: this.observacion().trim() || null,
      version: this.detalle()?.version?.numero ?? null,
    };
  }

  /** Primer intento sin código: el backend responde 409 TOTP_REQUERIDO y se abre el autenticador. */
  protected guardar(): void {
    const codigo = this.seleccionado();
    if (!codigo || this.problemas().length) return;
    this.confirmando.set(false);
    this.guardando.set(true);
    this.error.set(null);
    this.parametros
      .guardarMalla(codigo, this.mallaEditada())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (detalle) => this.mallaGuardada(detalle),
        error: (error: unknown) => this.falloSinCodigo(error, 'malla'),
      });
  }

  // --- Nuevo tipo de curso ---

  protected abrirNuevoTipo(): void {
    this.nuevoTipo.set(this.tipoVacio());
    this.aviso.set(null);
    this.creandoTipo.set(true);
  }

  protected cambiarNuevoTipo<K extends keyof NuevoTipoCurso>(
    campo: K,
    valor: NuevoTipoCurso[K],
  ): void {
    this.nuevoTipo.update((tipo) => ({ ...tipo, [campo]: valor }));
  }

  protected readonly nuevoTipoValido = computed(() => {
    const tipo = this.nuevoTipo();
    return (
      /^[A-Za-z0-9_]{2,20}$/.test(tipo.codigo.trim()) &&
      tipo.nombre.trim().length >= 3 &&
      Number(tipo.duracion_semanas) >= 1 &&
      Number(tipo.duracion_semanas) <= 104
    );
  });

  protected crearTipo(): void {
    if (!this.nuevoTipoValido() || this.guardando()) return;
    this.guardando.set(true);
    this.error.set(null);
    this.parametros
      .crearTipoCurso(this.tipoParaEnviar())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (detalle) => this.tipoCreado(detalle),
        error: (error: unknown) => this.falloSinCodigo(error, 'tipo'),
      });
  }

  // --- Autenticador ---

  /** La ventana del autenticador reenvía la misma operación con el código. */
  protected readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    this.guardando.set(true);
    const operacion = this.operacionTotp();
    const peticion =
      operacion === 'tipo'
        ? this.parametros.crearTipoCurso(this.tipoParaEnviar(), codigo)
        : this.parametros.guardarMalla(this.seleccionado() ?? '', this.mallaEditada(), codigo);
    return peticion.pipe(
      tap((detalle) => {
        this.cerrarTotp();
        if (operacion === 'tipo') this.tipoCreado(detalle);
        else this.mallaGuardada(detalle);
      }),
      catchError((error: unknown) => {
        this.guardando.set(false);
        if (CODIGOS_TOTP.has(leerErrorApi(error).codigo)) {
          return throwError(() => error);
        }
        this.cerrarTotp();
        this.error.set(leerErrorApi(error));
        return EMPTY;
      }),
    );
  };

  protected cancelarTotp(): void {
    const operacion = this.operacionTotp();
    this.cerrarTotp();
    this.aviso.set(
      operacion === 'tipo'
        ? 'Verificación cancelada. El tipo de curso no se creó.'
        : 'Verificación cancelada. La malla no se guardó; sus cambios siguen en pantalla.',
    );
  }

  protected cerrarTotp(): void {
    this.operacionTotp.set(null);
    this.errorTotp.set('');
    const ventana = this.ventanaTotp()?.nativeElement;
    if (ventana?.open) ventana.close();
  }

  private falloSinCodigo(error: unknown, operacion: 'malla' | 'tipo'): void {
    this.guardando.set(false);
    const fallo = leerErrorApi(error);
    if (fallo.codigo === 'TOTP_REQUERIDO') {
      this.errorTotp.set('');
      this.operacionTotp.set(operacion);
      // La ventana se abre después de que Angular pinte el componente del autenticador.
      queueMicrotask(() => {
        const ventana = this.ventanaTotp()?.nativeElement;
        if (ventana && !ventana.open) ventana.showModal();
      });
      return;
    }
    this.error.set(fallo);
  }

  private mallaGuardada(detalle: DetalleMalla): void {
    this.guardando.set(false);
    this.editando.set(false);
    this.detalle.set(detalle);
    this.aviso.set(
      `Versión ${detalle.version?.numero} de ${detalle.tipo_curso.codigo} guardada. ` +
        'Aplica a los cursos que se creen desde ahora.',
    );
    this.cargarTipos(detalle.tipo_curso.codigo);
  }

  private tipoCreado(detalle: DetalleMalla): void {
    this.guardando.set(false);
    this.creandoTipo.set(false);
    this.aviso.set(
      `Tipo de curso ${detalle.tipo_curso.codigo} creado. Ahora puede cargar su malla.`,
    );
    this.cargarTipos(detalle.tipo_curso.codigo);
  }

  private tipoParaEnviar(): NuevoTipoCurso {
    const tipo = this.nuevoTipo();
    return {
      ...tipo,
      codigo: tipo.codigo.trim().toUpperCase(),
      nombre: tipo.nombre.replace(/\s+/g, ' ').trim(),
      duracion_semanas: Number(tipo.duracion_semanas),
    };
  }

  private tipoVacio(): NuevoTipoCurso {
    return {
      codigo: '',
      nombre: '',
      tipo: 'ESPECIALIZACION',
      modalidad: 'PRESENCIAL',
      duracion_semanas: 4,
    };
  }
}
