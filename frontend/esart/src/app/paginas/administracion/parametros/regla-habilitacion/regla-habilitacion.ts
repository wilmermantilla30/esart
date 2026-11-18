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
  ReglaHabilitacion,
  SimulacionRegla,
  ValoresRegla,
} from '../../../../nucleo/modelos/parametros';
import { ParametrosService } from '../../../../nucleo/servicios/parametros.service';
import { SesionService } from '../../../../nucleo/servicios/sesion.service';
import { Totp } from '../../../totp/totp';

const COMPONENTE = 'PARAMETROS_HABILITACION';
/** Errores que se muestran dentro de la ventana del autenticador (el usuario reintenta ahí). */
const CODIGOS_TOTP = new Set(['TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);

/** Clave estable de una propuesta: sirve para saber si la simulación corresponde a lo que se ve. */
export function claveValores(valores: ValoresRegla): string {
  return JSON.stringify({
    ...valores,
    cursos_habilitantes: [...valores.cursos_habilitantes].sort(),
  });
}

/**
 * Pestaña "Cursos y Capacitaciones": la regla APTO / NO APTO.
 *
 * Flujo: editar -> simular el impacto -> guardar con el código del autenticador.
 * Guardar solo se habilita cuando la simulación corresponde exactamente a los valores en
 * pantalla: así nadie aplica un cambio sin haber visto a cuántos militares afecta.
 */
@Component({
  selector: 'esart-regla-habilitacion',
  imports: [DatePipe, FormsModule, Totp],
  templateUrl: './regla-habilitacion.html',
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
export class ReglaHabilitacionPestana {
  private readonly parametros = inject(ParametrosService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeEditar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));

  protected readonly regla = signal<ReglaHabilitacion | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);

  // Formulario (copia editable de los valores vigentes).
  protected readonly cursos = signal<string[]>([]);
  protected readonly meses = signal(12);
  protected readonly dias = signal(60);
  protected readonly exigeApto = signal(true);

  protected readonly simulacion = signal<SimulacionRegla | null>(null);
  private readonly claveSimulada = signal<string | null>(null);
  protected readonly simulando = signal(false);
  protected readonly guardando = signal(false);
  protected readonly confirmando = signal(false);

  protected readonly requiereTotp = signal(false);
  protected readonly errorTotp = signal('');
  private readonly ventanaTotp = viewChild<ElementRef<HTMLDialogElement>>('ventanaTotp');

  protected readonly valores = computed<ValoresRegla>(() => ({
    cursos_habilitantes: this.cursos(),
    meses_vigencia_reentrenamiento: Number(this.meses()),
    dias_alerta_vencimiento: Number(this.dias()),
    exige_apto_para_disparar: this.exigeApto(),
  }));
  protected readonly hayCambios = computed(() => {
    const vigente = this.regla();
    return !!vigente && claveValores(vigente.valores) !== claveValores(this.valores());
  });
  /** La simulación mostrada corresponde a lo que hay en pantalla. */
  protected readonly simulacionVigente = computed(
    () => !!this.simulacion() && this.claveSimulada() === claveValores(this.valores()),
  );
  protected readonly puedeGuardar = computed(
    () => this.puedeEditar() && this.hayCambios() && this.simulacionVigente() && !this.guardando(),
  );

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.parametros
      .obtenerRegla()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (regla) => {
          this.aplicarRegla(regla);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected alternarCurso(codigo: string): void {
    this.cursos.update((lista) =>
      lista.includes(codigo)
        ? lista.filter((actual) => actual !== codigo)
        : [...lista, codigo].sort(),
    );
  }

  protected descartar(): void {
    const vigente = this.regla();
    if (vigente) this.aplicarRegla(vigente);
  }

  protected simular(): void {
    if (this.simulando()) return;
    const clave = claveValores(this.valores());
    this.simulando.set(true);
    this.error.set(null);
    this.aviso.set(null);
    this.parametros
      .simularRegla(this.valores())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (simulacion) => {
          this.simulacion.set(simulacion);
          this.claveSimulada.set(clave);
          this.simulando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.simulando.set(false);
        },
      });
  }

  /** Primer intento sin código: el backend responde 409 TOTP_REQUERIDO y se abre el autenticador. */
  protected guardar(): void {
    if (!this.puedeGuardar()) return;
    this.confirmando.set(false);
    this.guardando.set(true);
    this.error.set(null);
    this.parametros
      .guardarRegla(this.valores(), this.regla()?.actualizado_en ?? null)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (regla) => this.guardado(regla),
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

  /** La ventana del autenticador reenvía la misma propuesta con el código. */
  protected readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    this.guardando.set(true);
    return this.parametros
      .guardarRegla(this.valores(), this.regla()?.actualizado_en ?? null, codigo)
      .pipe(
        tap((regla) => {
          this.cerrarTotp();
          this.guardado(regla);
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
    this.aviso.set('Verificación cancelada. La regla no se modificó.');
  }

  protected cerrarTotp(): void {
    this.requiereTotp.set(false);
    this.errorTotp.set('');
    const ventana = this.ventanaTotp()?.nativeElement;
    if (ventana?.open) ventana.close();
  }

  protected nombreCurso(codigo: string): string {
    return (
      this.regla()?.cursos_disponibles.find((curso) => curso.codigo === codigo)?.nombre ?? codigo
    );
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

  private guardado(regla: ReglaHabilitacion): void {
    this.guardando.set(false);
    this.aplicarRegla(regla);
    this.aviso.set('Regla de habilitación actualizada. Ya aplica en todas las consultas.');
  }

  private aplicarRegla(regla: ReglaHabilitacion): void {
    this.regla.set(regla);
    this.cursos.set([...regla.valores.cursos_habilitantes].sort());
    this.meses.set(regla.valores.meses_vigencia_reentrenamiento);
    this.dias.set(regla.valores.dias_alerta_vencimiento);
    this.exigeApto.set(regla.valores.exige_apto_para_disparar);
    this.simulacion.set(null);
    this.claveSimulada.set(null);
  }
}
