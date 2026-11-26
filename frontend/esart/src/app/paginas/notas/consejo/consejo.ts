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

import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import {
  CasoConsejo,
  DecisionConsejo,
  FiltroConsejo,
  SolicitudDecisionConsejo,
} from '../../../nucleo/modelos/notas';
import { NotasService } from '../../../nucleo/servicios/notas.service';
import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { Totp } from '../../totp/totp';

const COMPONENTE = 'CONSEJO_ACADEMICO';
/** Errores que se muestran dentro de la ventana del autenticador (el usuario reintenta ahí). */
const CODIGOS_TOTP = new Set(['TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);
/** Mismos límites que valida el backend (servicios/consejo.py). */
export const LONGITUD_MAXIMA_ACTA = 50;
export const LONGITUD_MAXIMA_OBSERVACION = 1000;

/** Decisiones posibles del Consejo (lista fija acordada con la Escuela, pregunta 5 del backlog). */
export const DECISIONES: { valor: DecisionConsejo; texto: string }[] = [
  { valor: 'APRUEBA_MATERIA', texto: 'Aprueba la materia' },
  { valor: 'REPITE_CURSO', texto: 'Repite el curso' },
  { valor: 'PIERDE_CURSO', texto: 'Pierde el curso' },
  { valor: 'OTRA', texto: 'Otra (con observación)' },
];

export const FILTROS_CONSEJO: { valor: FiltroConsejo; texto: string }[] = [
  { valor: 'PENDIENTES', texto: 'Pendientes' },
  { valor: 'DECIDIDOS', texto: 'Decididos' },
  { valor: 'TODOS', texto: 'Todos' },
];

export function textoDecision(decision: DecisionConsejo | null): string {
  return DECISIONES.find((opcion) => opcion.valor === decision)?.texto ?? 'Sin decisión';
}

/** Fecha de hoy (AAAA-MM-DD, hora local): tope del campo fecha del acta. */
export function hoyIso(hoy: Date = new Date()): string {
  const dos = (numero: number) => String(numero).padStart(2, '0');
  return `${hoy.getFullYear()}-${dos(hoy.getMonth() + 1)}-${dos(hoy.getDate())}`;
}

/** La decisión está completa: acta con número y fecha no futura; observación si es "Otra". */
export function decisionCompleta(datos: SolicitudDecisionConsejo, hoy = hoyIso()): boolean {
  const acta = datos.numero_acta.trim();
  const observacion = (datos.observacion ?? '').trim();
  return (
    DECISIONES.some((opcion) => opcion.valor === datos.decision) &&
    acta.length > 0 &&
    acta.length <= LONGITUD_MAXIMA_ACTA &&
    /^\d{4}-\d{2}-\d{2}$/.test(datos.fecha_acta) &&
    datos.fecha_acta <= hoy &&
    observacion.length <= LONGITUD_MAXIMA_OBSERVACION &&
    (datos.decision !== 'OTRA' || observacion.length > 0)
  );
}

/**
 * "Consejo Académico" (S2-14, componente CONSEJO_ACADEMICO).
 *
 * Lista de alumnos que perdieron la habilitación de una materia. Con permiso "crear" se registra
 * la decisión del Consejo (una sola por caso, con número y fecha del acta) confirmando con el
 * autenticador. "Aprueba la materia" la deja con la nota mínima del curso.
 */
@Component({
  selector: 'esart-consejo-academico',
  imports: [DatePipe, DecimalPipe, FormsModule, Totp],
  templateUrl: './consejo.html',
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
export class ConsejoAcademicoPagina {
  private readonly notas = inject(NotasService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeDecidir = computed(() => this.sesion.puede(COMPONENTE, 'crear'));
  protected readonly filtros = FILTROS_CONSEJO;
  protected readonly decisiones = DECISIONES;
  protected readonly textoDecision = textoDecision;
  protected readonly hoy = hoyIso();
  protected readonly maximoActa = LONGITUD_MAXIMA_ACTA;
  protected readonly maximoObservacion = LONGITUD_MAXIMA_OBSERVACION;

  protected readonly filtro = signal<FiltroConsejo>('PENDIENTES');
  protected readonly casos = signal<CasoConsejo[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);

  /** Caso con el formulario de decisión abierto y sus datos. */
  protected readonly idAbierto = signal<number | null>(null);
  protected readonly decision = signal<DecisionConsejo>('APRUEBA_MATERIA');
  protected readonly numeroActa = signal('');
  protected readonly fechaActa = signal(hoyIso());
  protected readonly observacion = signal('');
  protected readonly enviando = signal(false);
  protected readonly datos = computed<SolicitudDecisionConsejo>(() => ({
    decision: this.decision(),
    numero_acta: this.numeroActa(),
    fecha_acta: this.fechaActa(),
    observacion: this.observacion().trim() || null,
  }));
  protected readonly completa = computed(() => decisionCompleta(this.datos(), this.hoy));

  protected readonly requiereTotp = signal(false);
  protected readonly errorTotp = signal('');
  private readonly ventanaTotp = viewChild<ElementRef<HTMLDialogElement>>('ventanaTotp');

  constructor() {
    this.cargar();
  }

  protected elegirFiltro(valor: FiltroConsejo): void {
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
      .casosConsejo(this.filtro())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (casos) => {
          this.casos.set(casos);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected abrir(caso: CasoConsejo): void {
    if (this.idAbierto() === caso.id) {
      this.cerrar();
      return;
    }
    this.idAbierto.set(caso.id);
    this.decision.set('APRUEBA_MATERIA');
    this.numeroActa.set('');
    this.fechaActa.set(this.hoy);
    this.observacion.set('');
    this.aviso.set(null);
    this.error.set(null);
  }

  protected cerrar(): void {
    this.idAbierto.set(null);
  }

  /** Primer envío sin código: el backend responde TOTP_REQUERIDO y se abre el autenticador. */
  protected registrar(): void {
    const id = this.idAbierto();
    if (id === null || !this.completa() || this.enviando()) return;
    this.enviando.set(true);
    this.error.set(null);
    this.notas
      .registrarDecision(id, this.datos())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (caso) => this.registrado(caso),
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

  /** La ventana del autenticador reenvía la misma decisión con el código. */
  protected readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    const id = this.idAbierto();
    if (id === null) return EMPTY;
    this.enviando.set(true);
    return this.notas.registrarDecision(id, this.datos(), codigo).pipe(
      tap((caso) => {
        this.cerrarTotp();
        this.registrado(caso);
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
    this.aviso.set('Verificación cancelada. La decisión no se registró.');
  }

  protected cerrarTotp(): void {
    this.requiereTotp.set(false);
    this.errorTotp.set('');
    const ventana = this.ventanaTotp()?.nativeElement;
    if (ventana?.open) ventana.close();
  }

  private registrado(caso: CasoConsejo): void {
    this.enviando.set(false);
    this.cerrar();
    this.aviso.set(
      `Decisión registrada para ${caso.apellidos} ${caso.nombres} en ${caso.materia}: ${textoDecision(caso.decision)}.`,
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
