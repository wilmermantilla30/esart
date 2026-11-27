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

import { ErrorApi, leerErrorApi } from '../../../../nucleo/modelos/error-api';
import { NotaMinima } from '../../../../nucleo/modelos/parametros';
import { ParametrosService } from '../../../../nucleo/servicios/parametros.service';
import { SesionService } from '../../../../nucleo/servicios/sesion.service';
import { Totp } from '../../../totp/totp';

const COMPONENTE = 'PARAMETROS_HABILITACION';
/** Errores que se muestran dentro de la ventana del autenticador (el usuario reintenta ahí). */
const CODIGOS_TOTP = new Set(['TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);
/** Mismos límites que valida el backend (servicios/nota_minima.py). */
export const NOTA_MINIMA_PERMITIDA = 1;
export const NOTA_MAXIMA_PERMITIDA = 5;

/** La nota está entre 1,00 y 5,00 y tiene como máximo 2 decimales. */
export function notaValida(valor: number): boolean {
  return (
    Number.isFinite(valor) &&
    valor >= NOTA_MINIMA_PERMITIDA &&
    valor <= NOTA_MAXIMA_PERMITIDA &&
    Math.abs(Math.round(valor * 100) - valor * 100) < 1e-6
  );
}

/**
 * Tarjeta "Nota mínima de aprobación" (S2-10) de la pestaña Cursos y Capacitaciones.
 *
 * Flujo: editar -> confirmar -> guardar con el código del autenticador. Cada curso guarda la
 * nota vigente al crearse, así que un cambio solo aplica a los cursos nuevos: los resultados ya
 * aprobados por el Inspector de Estudios no se recalculan.
 */
@Component({
  selector: 'esart-nota-minima',
  imports: [DatePipe, DecimalPipe, FormsModule, Totp],
  templateUrl: './nota-minima.html',
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
export class NotaMinimaTarjeta {
  private readonly parametros = inject(ParametrosService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeEditar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));
  protected readonly minimo = NOTA_MINIMA_PERMITIDA;
  protected readonly maximo = NOTA_MAXIMA_PERMITIDA;

  protected readonly nota = signal<NotaMinima | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);

  /** Valor del formulario (copia editable del vigente). */
  protected readonly valor = signal(3);
  protected readonly guardando = signal(false);
  protected readonly confirmando = signal(false);

  protected readonly requiereTotp = signal(false);
  protected readonly errorTotp = signal('');
  private readonly ventanaTotp = viewChild<ElementRef<HTMLDialogElement>>('ventanaTotp');

  protected readonly valorValido = computed(() => notaValida(Number(this.valor())));
  protected readonly hayCambios = computed(() => {
    const vigente = this.nota();
    return !!vigente && Number(this.valor()) !== vigente.valor;
  });
  protected readonly puedeGuardar = computed(
    () => this.puedeEditar() && this.hayCambios() && this.valorValido() && !this.guardando(),
  );

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.parametros
      .obtenerNotaMinima()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (nota) => {
          this.aplicar(nota);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected descartar(): void {
    const vigente = this.nota();
    if (vigente) this.aplicar(vigente);
  }

  protected pedirConfirmacion(): void {
    if (!this.puedeGuardar()) return;
    this.aviso.set(null);
    this.confirmando.set(true);
  }

  /** Primer intento sin código: el backend responde 409 TOTP_REQUERIDO y se abre el autenticador. */
  protected guardar(): void {
    const vigente = this.nota();
    if (!vigente || !this.puedeGuardar()) return;
    this.confirmando.set(false);
    this.guardando.set(true);
    this.error.set(null);
    this.parametros
      .guardarNotaMinima(Number(this.valor()), vigente.actualizado_en)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (nota) => this.guardada(nota),
        error: (error: unknown) => {
          this.guardando.set(false);
          const fallo = leerErrorApi(error);
          if (fallo.codigo === 'TOTP_REQUERIDO') {
            this.abrirTotp();
            return;
          }
          this.error.set(fallo);
        },
      });
  }

  /** La ventana del autenticador reenvía la misma nota con el código. */
  protected readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    this.guardando.set(true);
    return this.parametros
      .guardarNotaMinima(Number(this.valor()), this.nota()?.actualizado_en ?? '', codigo)
      .pipe(
        tap((nota) => {
          this.cerrarTotp();
          this.guardada(nota);
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
    this.cerrarTotp();
    this.aviso.set('Verificación cancelada. La nota mínima no se modificó.');
  }

  protected cerrarTotp(): void {
    this.requiereTotp.set(false);
    this.errorTotp.set('');
    const ventana = this.ventanaTotp()?.nativeElement;
    if (ventana?.open) ventana.close();
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

  private guardada(nota: NotaMinima): void {
    this.guardando.set(false);
    this.aplicar(nota);
    this.aviso.set('Nota mínima actualizada. Aplica a los cursos que se creen desde ahora.');
  }

  private aplicar(nota: NotaMinima): void {
    this.nota.set(nota);
    this.valor.set(nota.valor);
  }
}
