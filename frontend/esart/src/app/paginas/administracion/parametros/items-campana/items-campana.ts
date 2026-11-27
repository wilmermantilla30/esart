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
import { EMPTY, Observable, catchError, tap, throwError } from 'rxjs';

import { ErrorApi, leerErrorApi } from '../../../../nucleo/modelos/error-api';
import { ConfiguracionCampana, ItemCampanaPropuesto } from '../../../../nucleo/modelos/parametros';
import { ParametrosService } from '../../../../nucleo/servicios/parametros.service';
import { SesionService } from '../../../../nucleo/servicios/sesion.service';
import { Totp } from '../../../totp/totp';

const COMPONENTE = 'PARAMETROS_HABILITACION';
/** Errores que se muestran dentro de la ventana del autenticador (el usuario reintenta ahí). */
const CODIGOS_TOTP = new Set(['TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);
/** Mismas reglas que valida el backend (servicios/campana.py). */
export const NOTA_TOTAL = 5;
export const MAXIMO_ITEMS = 40;

/** Puntaje escrito (coma o punto) como número; NaN si no lo es o tiene más de 4 decimales. */
export function leerPuntaje(texto: string): number {
  const limpio = texto.trim().replace(',', '.');
  if (!/^\d+(\.\d{1,4})?$/.test(limpio)) return Number.NaN;
  return Number(limpio);
}

/** Suma de los puntajes válidos (los inválidos cuentan como 0). */
export function sumaPuntajes(items: ReadonlyArray<ItemCampanaPropuesto>): number {
  return items.reduce((total, item) => {
    const puntaje = leerPuntaje(item.puntaje);
    return total + (Number.isNaN(puntaje) ? 0 : puntaje);
  }, 0);
}

/** Lista válida: nombres de 3 a 200 letras sin repetir, puntajes > 0 y suma 5,00 al redondear. */
export function itemsValidos(items: ReadonlyArray<ItemCampanaPropuesto>): boolean {
  const nombres = items.map((item) => item.nombre.trim().replace(/\s+/g, ' ').toUpperCase());
  return (
    items.length > 0 &&
    items.length <= MAXIMO_ITEMS &&
    nombres.every((nombre) => nombre.length >= 3 && nombre.length <= 200) &&
    new Set(nombres).size === nombres.length &&
    items.every((item) => leerPuntaje(item.puntaje) > 0) &&
    Math.round(sumaPuntajes(items) * 100) === NOTA_TOTAL * 100
  );
}

/** Reparte 5,00 en partes iguales con 4 decimales; el último ítem ajusta para sumar exacto. */
export function repartirIgual(cantidad: number): string[] {
  if (cantidad <= 0) return [];
  const parte = Math.floor((NOTA_TOTAL / cantidad) * 10000) / 10000;
  const ultimo = Math.round((NOTA_TOTAL - parte * (cantidad - 1)) * 10000) / 10000;
  return [...Array(cantidad - 1).fill(parte.toFixed(4)), ultimo.toFixed(4)];
}

/**
 * Tarjeta "Fase de campaña del CAPINTE" (S2-16) de la pestaña Cursos y Capacitaciones.
 *
 * Ítems que el comandante califica aprobado / no aprobado y su puntaje (la nota de la fase es la
 * suma de los aprobados). Se agregan, quitan, ordenan y reparten; guardar pide el autenticador.
 * Solo afecta a las plantillas que se descarguen después: las entregas guardan su puntaje.
 */
@Component({
  selector: 'esart-items-campana',
  imports: [DatePipe, DecimalPipe, Totp],
  templateUrl: './items-campana.html',
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
export class ItemsCampanaTarjeta {
  private readonly parametros = inject(ParametrosService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  protected readonly puedeEditar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));
  protected readonly vigente = signal<ConfiguracionCampana | null>(null);
  protected readonly items = signal<ItemCampanaPropuesto[]>([]);
  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);

  protected readonly suma = computed(() => sumaPuntajes(this.items()));
  protected readonly validos = computed(() => itemsValidos(this.items()));
  protected readonly hayCambios = computed(() => {
    const vigente = this.vigente();
    if (!vigente) return false;
    const actuales = vigente.items.map((item) => `${item.id}|${item.nombre}|${item.puntaje}`);
    const editados = this.items().map(
      (item) => `${item.id}|${item.nombre.trim()}|${leerPuntaje(item.puntaje)}`,
    );
    return actuales.join('\n') !== editados.join('\n');
  });

  protected readonly requiereTotp = signal(false);
  protected readonly errorTotp = signal('');
  private readonly ventanaTotp = viewChild<ElementRef<HTMLDialogElement>>('ventanaTotp');

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.parametros
      .obtenerCampana()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (datos) => {
          this.aplicar(datos);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected descartar(): void {
    const vigente = this.vigente();
    if (vigente) this.aplicar(vigente);
  }

  protected cambiar(posicion: number, campo: 'nombre' | 'puntaje', valor: string): void {
    this.items.update((items) =>
      items.map((item, indice) => (indice === posicion ? { ...item, [campo]: valor } : item)),
    );
  }

  protected agregar(): void {
    this.items.update((items) => [...items, { id: null, nombre: '', puntaje: '' }]);
  }

  protected quitar(posicion: number): void {
    this.items.update((items) => items.filter((_, indice) => indice !== posicion));
  }

  protected mover(posicion: number, paso: -1 | 1): void {
    this.items.update((items) => {
      const destino = posicion + paso;
      if (destino < 0 || destino >= items.length) return items;
      const copia = [...items];
      [copia[posicion], copia[destino]] = [copia[destino], copia[posicion]];
      return copia;
    });
  }

  protected repartir(): void {
    const partes = repartirIgual(this.items().length);
    this.items.update((items) =>
      items.map((item, indice) => ({ ...item, puntaje: partes[indice] })),
    );
  }

  /** Primer intento sin código: el backend responde TOTP_REQUERIDO y se abre el autenticador. */
  protected guardar(): void {
    if (!this.validos() || !this.hayCambios() || this.guardando()) return;
    this.guardando.set(true);
    this.error.set(null);
    this.aviso.set(null);
    this.parametros
      .guardarCampana(this.items(), this.vigente()?.actualizado_en ?? null)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (datos) => this.guardado(datos),
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

  /** La ventana del autenticador reenvía los mismos ítems con el código. */
  protected readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    this.guardando.set(true);
    return this.parametros
      .guardarCampana(this.items(), this.vigente()?.actualizado_en ?? null, codigo)
      .pipe(
        tap((datos) => {
          this.cerrarTotp();
          this.guardado(datos);
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
    this.aviso.set('Verificación cancelada. Los ítems no se modificaron.');
  }

  protected cerrarTotp(): void {
    this.requiereTotp.set(false);
    this.errorTotp.set('');
    const ventana = this.ventanaTotp()?.nativeElement;
    if (ventana?.open) ventana.close();
  }

  private guardado(datos: ConfiguracionCampana): void {
    this.guardando.set(false);
    this.aplicar(datos);
    this.aviso.set(
      'Ítems guardados. Aplican a las plantillas que se descarguen desde ahora; las ya descargadas quedan viejas.',
    );
  }

  private aplicar(datos: ConfiguracionCampana): void {
    this.vigente.set(datos);
    this.items.set(
      datos.items.map((item) => ({
        id: item.id,
        nombre: item.nombre,
        puntaje: String(item.puntaje),
      })),
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
}
