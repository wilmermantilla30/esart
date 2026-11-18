import { Component, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';

import { RUTA_PAGINA_INICIO_SESION } from '../../nucleo/rutas-paginas';
import { InactividadService } from '../../nucleo/servicios/inactividad.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/**
 * Aviso de cierre por inactividad (HU-08): aparece 2 minutos antes de que la sesión venza,
 * con la cuenta regresiva y dos opciones. Se coloca una sola vez en el componente raíz.
 */
@Component({
  selector: 'esart-aviso-inactividad',
  template: `
    @if (inactividad.mostrarAviso()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-azul-pizarra/60 p-4">
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="titulo-aviso-inactividad"
          aria-describedby="texto-aviso-inactividad"
          class="w-full max-w-md bg-white rounded-xl border border-gris-bordes shadow-xl p-6"
        >
          <div class="flex items-start gap-3">
            <span class="material-symbols-outlined text-warning text-[28px] shrink-0" aria-hidden="true">schedule</span>
            <div>
              <h2 id="titulo-aviso-inactividad" class="font-headline text-headline-sm text-negro-institucional">
                Su sesión está por cerrarse
              </h2>
              <p id="texto-aviso-inactividad" class="mt-1 text-body-md text-azul-pizarra/80">
                Por seguridad, la sesión se cerrará por inactividad en
                <span class="font-code text-code-md font-semibold text-azul-pizarra" aria-live="polite">{{
                  tiempoRestante()
                }}</span
                >.
              </p>
            </div>
          </div>
          <div class="mt-6 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <button
              type="button"
              (click)="cerrarSesion()"
              [disabled]="procesando()"
              class="inline-flex items-center justify-center gap-2 py-2.5 px-4 border border-gris-bordes rounded-sm text-label-lg font-headline text-azul-pizarra bg-white hover:border-azul-institucional hover:text-azul-institucional focus:outline-none focus:ring-2 focus:ring-azul-institucional/40 disabled:opacity-70"
            >
              <span class="material-symbols-outlined text-[18px]" aria-hidden="true">logout</span>
              Cerrar sesión
            </button>
            <button
              #botonContinuar
              type="button"
              (click)="continuar()"
              [disabled]="procesando()"
              class="inline-flex items-center justify-center gap-2 py-2.5 px-4 bg-azul-institucional hover:bg-[#1A8FB3] text-white rounded-sm text-label-lg font-headline focus:outline-none focus:ring-2 focus:ring-azul-institucional/40 disabled:opacity-70"
            >
              <span class="material-symbols-outlined text-[18px]" aria-hidden="true">refresh</span>
              Continuar sesión
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class AvisoInactividad {
  protected readonly inactividad = inject(InactividadService);
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);

  protected readonly procesando = signal(false);
  private readonly botonContinuar = viewChild<ElementRef<HTMLButtonElement>>('botonContinuar');

  /** Cuenta regresiva en formato m:ss (por ejemplo 1:45). */
  protected readonly tiempoRestante = computed(() => {
    const segundos = this.inactividad.segundosRestantes() ?? 0;
    return `${Math.floor(segundos / 60)}:${String(segundos % 60).padStart(2, '0')}`;
  });

  constructor() {
    // Al abrirse, el foco va a "Continuar sesión" (accesible con teclado y lector de pantalla).
    effect(() => {
      this.botonContinuar()?.nativeElement.focus();
    });
    // Cuando el aviso se cierra (se renovó o se salió), se habilitan de nuevo los botones.
    effect(() => {
      if (!this.inactividad.mostrarAviso()) {
        this.procesando.set(false);
      }
    });
  }

  protected continuar(): void {
    this.procesando.set(true);
    this.inactividad.continuarSesion();
  }

  protected cerrarSesion(): void {
    this.procesando.set(true);
    this.sesion.cerrarSesion().subscribe({
      complete: () => void this.enrutador.navigate(['/', RUTA_PAGINA_INICIO_SESION]),
    });
  }
}
