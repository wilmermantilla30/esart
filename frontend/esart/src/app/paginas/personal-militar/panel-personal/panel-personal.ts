import { NgTemplateOutlet } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import { ResumenHabilitacion } from '../../../nucleo/modelos/verificacion';
import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { VerificacionService } from '../../../nucleo/servicios/verificacion.service';

interface Indicador {
  titulo: string;
  valor: number;
  ayuda: string;
  icono: string;
  clasesIcono: string;
  /** Filtro del listado al que lleva el indicador (null: no es enlace). */
  filtro: string | null;
}

/**
 * Panel del módulo Personal militar: indicadores de habilitación calculados por el
 * backend con la misma regla de la verificación.
 */
@Component({
  selector: 'esart-panel-personal',
  imports: [RouterLink, NgTemplateOutlet],
  template: `
    @if (error(); as fallo) {
      <div class="p-4 bg-error/10 border border-error/40 rounded-lg flex items-start gap-3 text-body-md" role="alert">
        <span class="material-symbols-outlined text-error" aria-hidden="true">error</span>
        <span>{{ fallo.mensaje }}</span>
      </div>
    }

    <section class="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3" aria-label="Indicadores de habilitación">
      @for (indicador of indicadores(); track indicador.titulo) {
        @if (indicador.filtro !== null && puedeListar) {
          <a
            routerLink="/personal/habilitados"
            [queryParams]="indicador.filtro ? { estado: indicador.filtro } : {}"
            class="block bg-white rounded-xl border border-gris-bordes p-4 hover:border-azul-institucional transition-colors focus:outline-none focus:ring-2 focus:ring-azul-institucional/40"
          >
            <ng-container *ngTemplateOutlet="tarjeta; context: { $implicit: indicador }" />
          </a>
        } @else {
          <article class="bg-white rounded-xl border border-gris-bordes p-4">
            <ng-container *ngTemplateOutlet="tarjeta; context: { $implicit: indicador }" />
          </article>
        }
      } @empty {
        @if (cargando()) {
          <p class="col-span-full text-body-md text-azul-pizarra/60">Consultando indicadores…</p>
        }
      }
    </section>

    <ng-template #tarjeta let-indicador>
      <div class="flex items-center justify-between">
        <span class="text-label-md font-headline uppercase tracking-wider text-azul-pizarra/60">{{ indicador.titulo }}</span>
        <span class="material-symbols-outlined text-[20px]" [class]="indicador.clasesIcono" aria-hidden="true">{{
          indicador.icono
        }}</span>
      </div>
      <div class="mt-2 font-headline font-bold text-display-md text-negro-institucional">{{ indicador.valor }}</div>
      <span class="text-xs text-azul-pizarra/60">{{ indicador.ayuda }}</span>
    </ng-template>
  `,
  host: { class: 'block space-y-4' },
})
export class PanelPersonal {
  private readonly verificacion = inject(VerificacionService);
  /** Los indicadores llevan al listado solo si el usuario puede verlo. */
  protected readonly puedeListar = inject(SesionService).tienePermiso('PERSONAL_HABILITADOS');

  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly indicadores = signal<Indicador[]>([]);

  constructor() {
    this.verificacion.obtenerResumen().subscribe({
      next: (resumen) => {
        this.indicadores.set(this.construirIndicadores(resumen));
        this.cargando.set(false);
      },
      error: (error: unknown) => {
        this.error.set(leerErrorApi(error));
        this.cargando.set(false);
      },
    });
  }

  private construirIndicadores(resumen: ResumenHabilitacion): Indicador[] {
    return [
      { titulo: 'Total', valor: resumen.total, ayuda: 'Artilleros registrados', icono: 'groups', clasesIcono: 'material-symbols-outlined text-azul-institucional', filtro: '' },
      { titulo: 'APTO', valor: resumen.aptos, ayuda: 'Habilitados hoy', icono: 'check_circle', clasesIcono: 'material-symbols-outlined text-success', filtro: 'APTO' },
      { titulo: 'NO APTO', valor: resumen.no_aptos, ayuda: 'Sin habilitación', icono: 'cancel', clasesIcono: 'material-symbols-outlined text-error', filtro: 'NO_APTO' },
      {
        titulo: 'Por vencer',
        valor: resumen.reentrenamiento_por_vencer,
        ayuda: `Reentrenamiento en ${resumen.dias_alerta_vencimiento} días o menos`,
        icono: 'schedule',
        clasesIcono: 'material-symbols-outlined text-warning',
        filtro: 'POR_VENCER',
      },
      { titulo: 'Activos', valor: resumen.activos, ayuda: 'En servicio activo', icono: 'verified', clasesIcono: 'material-symbols-outlined text-azul-institucional', filtro: null },
      { titulo: 'Unidades', valor: resumen.unidades, ayuda: 'Con personal registrado', icono: 'domain', clasesIcono: 'material-symbols-outlined text-azul-institucional', filtro: null },
    ];
  }
}
