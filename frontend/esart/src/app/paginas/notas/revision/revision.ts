import { DatePipe, DecimalPipe } from '@angular/common';
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

import { ESTADOS_ENTREGA } from '../../../nucleo/estados-entrega';
import { estiloEstadoCurso, textoEstadoCurso } from '../../../nucleo/estados-curso';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import {
  DetalleEntrega,
  EntregaEnBandeja,
  FiltroBandeja,
  NotaEnRevision,
} from '../../../nucleo/modelos/notas';
import { NotasService } from '../../../nucleo/servicios/notas.service';
import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { Totp } from '../../totp/totp';

const COMPONENTE = 'NOTAS_REVISION';
/** Errores que se muestran dentro de la ventana del autenticador (el usuario reintenta ahí). */
const CODIGOS_TOTP = new Set(['TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);
/** Mismos límites que valida el backend (servicios/revision_notas.py). */
export const LONGITUD_MINIMA_OBSERVACION = 5;
export const LONGITUD_MAXIMA_OBSERVACION = 1000;

/** Pestañas de la bandeja, en el orden en que se muestran. */
export const FILTROS: { valor: FiltroBandeja; texto: string }[] = [
  { valor: 'EN_REVISION', texto: 'Pendientes' },
  { valor: 'DEVUELTA', texto: 'Devueltas' },
  { valor: 'APROBADA', texto: 'Aprobadas' },
  { valor: 'TODAS', texto: 'Todas' },
];

/** Acción que el Inspector está confirmando sobre la entrega abierta. */
export type AccionRevision = 'aprobar' | 'devolver' | 'reabrir';

/** La observación (sin espacios de más) tiene el largo que exige el backend. */
export function observacionValida(texto: string): boolean {
  const limpia = texto.split(/\s+/).filter(Boolean).join(' ');
  return (
    limpia.length >= LONGITUD_MINIMA_OBSERVACION && limpia.length <= LONGITUD_MAXIMA_OBSERVACION
  );
}

/** En una corrección, la nota cambió respecto a la oficial vigente (o el alumno no tenía). */
export function notaCambiada(nota: NotaEnRevision, hayOficiales: boolean): boolean {
  return hayOficiales && nota.nota_oficial !== nota.nota;
}

/**
 * "Revisión de notas" del Inspector de Estudios (S2-13, componente NOTAS_REVISION).
 *
 * Bandeja de entregas por estado. Al abrir una se ve la nota de cada alumno (y la oficial
 * vigente si es una corrección). Con permiso "actualizar":
 * - Aprobar (con confirmación, sin autenticador desde 2026-11-27): las notas pasan a ser las
 *   oficiales.
 * - Devolver (con observación): el instructor corrige y vuelve a subir.
 * - Reabrir una aprobada (observación y autenticador): el instructor sube la corrección; las
 *   notas oficiales siguen vigentes hasta la nueva aprobación.
 */
@Component({
  selector: 'esart-revision-notas',
  imports: [DatePipe, DecimalPipe, FormsModule, Totp],
  templateUrl: './revision.html',
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
export class RevisionNotasPagina {
  private readonly notas = inject(NotasService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeRevisar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));
  protected readonly filtros = FILTROS;
  protected readonly estados = ESTADOS_ENTREGA;
  protected readonly textoEstadoCurso = textoEstadoCurso;
  protected readonly estiloEstadoCurso = estiloEstadoCurso;
  protected readonly notaCambiada = notaCambiada;
  protected readonly maximoObservacion = LONGITUD_MAXIMA_OBSERVACION;

  protected readonly filtro = signal<FiltroBandeja>('EN_REVISION');
  protected readonly entregas = signal<EntregaEnBandeja[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);

  /** Entrega abierta con la nota de cada alumno. */
  protected readonly abierta = signal<DetalleEntrega | null>(null);
  protected readonly idAbierta = signal<number | null>(null);

  /** Acción que se está confirmando, su observación y si ya se envió. */
  protected readonly accion = signal<AccionRevision | null>(null);
  protected readonly observacion = signal('');
  protected readonly enviando = signal(false);
  protected readonly observacionValida = computed(() => observacionValida(this.observacion()));

  protected readonly requiereTotp = signal(false);
  protected readonly errorTotp = signal('');
  private readonly ventanaTotp = viewChild<ElementRef<HTMLDialogElement>>('ventanaTotp');

  constructor() {
    this.cargar();
  }

  protected elegirFiltro(valor: FiltroBandeja): void {
    if (valor === this.filtro()) return;
    this.filtro.set(valor);
    this.cerrar();
    this.aviso.set(null);
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.notas
      .bandeja(this.filtro())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (entregas) => {
          this.entregas.set(entregas);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected abrir(entrega: EntregaEnBandeja): void {
    if (this.idAbierta() === entrega.id) {
      this.cerrar();
      return;
    }
    this.cerrar();
    this.idAbierta.set(entrega.id);
    this.recargarDetalle(entrega.id);
  }

  protected recargarDetalle(entregaId: number): void {
    this.abierta.set(null);
    this.error.set(null);
    this.notas
      .detalleEntrega(entregaId)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (detalle) => this.abierta.set(detalle),
        error: (error: unknown) => this.error.set(leerErrorApi(error)),
      });
  }

  protected cerrar(): void {
    this.idAbierta.set(null);
    this.abierta.set(null);
    this.cancelarAccion();
  }

  protected iniciarAccion(accion: AccionRevision): void {
    this.aviso.set(null);
    this.error.set(null);
    this.observacion.set('');
    this.accion.set(accion);
  }

  protected cancelarAccion(): void {
    this.accion.set(null);
    this.observacion.set('');
  }

  /** Primer envío sin código: reabrir responde TOTP_REQUERIDO y se abre el autenticador. */
  protected confirmar(): void {
    const accion = this.accion();
    if (!accion || this.enviando()) return;
    if (accion !== 'aprobar' && !this.observacionValida()) return;
    this.enviando.set(true);
    this.error.set(null);
    this.ejecutar(accion, '')
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (detalle) => this.hecha(accion, detalle),
        error: (error: unknown) => {
          this.enviando.set(false);
          const fallo = leerErrorApi(error);
          if (fallo.codigo === 'TOTP_REQUERIDO') {
            this.abrirTotp();
            return;
          }
          this.error.set(fallo);
        },
      });
  }

  /** La ventana del autenticador reenvía la misma acción con el código. */
  protected readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    const accion = this.accion();
    if (!accion) return EMPTY;
    this.enviando.set(true);
    return this.ejecutar(accion, codigo).pipe(
      tap((detalle) => {
        this.cerrarTotp();
        this.hecha(accion, detalle);
      }),
      catchError((error: unknown) => {
        this.enviando.set(false);
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
    this.cerrarTotp();
    this.aviso.set('Verificación cancelada. La entrega no cambió.');
  }

  protected cerrarTotp(): void {
    this.requiereTotp.set(false);
    this.errorTotp.set('');
    const ventana = this.ventanaTotp()?.nativeElement;
    if (ventana?.open) ventana.close();
  }

  /** Etiqueta de la operación que muestra la ventana del autenticador. */
  protected etiquetaTotp(): string {
    return 'Reabrir notas aprobadas';
  }

  private ejecutar(accion: AccionRevision, codigo: string): Observable<DetalleEntrega> {
    const entrega = this.abierta();
    if (!entrega) return EMPTY;
    const observacion = this.observacion().trim();
    switch (accion) {
      case 'aprobar':
        return this.notas.aprobar(entrega.id, entrega.subido_en);
      case 'devolver':
        return this.notas.devolver(entrega.id, entrega.subido_en, observacion);
      case 'reabrir':
        return this.notas.reabrir(entrega.id, observacion, codigo);
    }
  }

  private hecha(accion: AccionRevision, detalle: DetalleEntrega): void {
    this.enviando.set(false);
    this.cancelarAccion();
    this.abierta.set(detalle);
    const materia = `${detalle.materia} (curso ${detalle.codigo_curso})`;
    this.aviso.set(
      accion === 'aprobar'
        ? `Notas de ${materia} aprobadas: ya son las oficiales.`
        : accion === 'devolver'
          ? `Notas de ${materia} devueltas al instructor con su observación.`
          : `Entrega de ${materia} reabierta: el instructor puede subir la corrección. Las notas oficiales siguen vigentes hasta que apruebe la nueva.`,
    );
    this.cargar();
  }

  private abrirTotp(): void {
    this.errorTotp.set('');
    this.requiereTotp.set(true);
    // La ventana se abre después de que Angular pinte el componente del autenticador.
    queueMicrotask(() => {
      const ventana = this.ventanaTotp()?.nativeElement;
      if (ventana && !ventana.open) ventana.showModal();
    });
  }
}
