import { Component, computed, input } from '@angular/core';

/** Texto, color e ícono de cada estado que muestra la verificación. */
const ESTADOS: Readonly<Record<string, { texto: string; clases: string; icono: string }>> = {
  APTO: { texto: 'APTO', clases: 'bg-success/10 text-success border-success/30', icono: 'check_circle' },
  NO_APTO: { texto: 'NO APTO', clases: 'bg-error/10 text-error border-error/30', icono: 'cancel' },
  VIGENTE: { texto: 'Vigente', clases: 'bg-success/10 text-success border-success/30', icono: 'verified' },
  POR_VENCER: { texto: 'Por vencer', clases: 'bg-warning/10 text-warning border-warning/40', icono: 'schedule' },
  VENCIDO: { texto: 'Vencido', clases: 'bg-error/10 text-error border-error/30', icono: 'event_busy' },
  ANULADO: { texto: 'Anulado', clases: 'bg-gris-claro text-azul-pizarra/70 border-gris-bordes', icono: 'block' },
  SIN_REGISTRO: { texto: 'Sin registro', clases: 'bg-gris-claro text-azul-pizarra/70 border-gris-bordes', icono: 'remove' },
  APROBADO: { texto: 'Aprobado', clases: 'bg-success/10 text-success border-success/30', icono: 'check' },
  EN_CURSO: { texto: 'En curso', clases: 'bg-info/10 text-info border-info/30', icono: 'pending' },
};

/**
 * Insignia de estado (APTO, NO APTO, Por vencer, Vencido…). Además del color lleva ícono y
 * texto: el estado nunca depende solo del color (accesibilidad).
 */
@Component({
  selector: 'esart-insignia-estado',
  template: `
    <span [class]="clasesInsignia()">
      <span class="material-symbols-outlined" [class]="clasesIcono()" aria-hidden="true">{{ definicion().icono }}</span>
      {{ definicion().texto }}
    </span>
  `,
})
export class InsigniaEstado {
  readonly estado = input.required<string>();
  readonly grande = input(false);

  protected readonly clasesInsignia = computed(
    () =>
      'inline-flex items-center gap-1 rounded-full border font-headline whitespace-nowrap ' +
      this.definicion().clases +
      (this.grande() ? ' px-3 py-1 text-title-lg' : ' px-2 py-0.5 text-label-md'),
  );
  protected readonly clasesIcono = computed(() =>
    this.grande() ? 'material-symbols-outlined text-[20px]' : 'material-symbols-outlined text-[14px]',
  );

  protected readonly definicion = computed(
    () => ESTADOS[this.estado()] ?? { texto: this.estado(), clases: 'bg-gris-claro text-azul-pizarra border-gris-bordes', icono: 'info' },
  );
}
