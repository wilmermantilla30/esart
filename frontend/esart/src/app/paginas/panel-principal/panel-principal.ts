import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { iconoDeComponente } from '../../nucleo/iconos-menu';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/**
 * Panel principal (componente DASHBOARD): bienvenida y accesos directos a los módulos
 * que el usuario tiene permitidos. Los indicadores llegarán con la verificación.
 */
@Component({
  selector: 'esart-panel-principal',
  imports: [RouterLink],
  template: `
    <section class="bg-white rounded-xl border border-gris-bordes shadow-sm p-6 md:p-8">
      <span
        class="px-2.5 py-1 rounded-full bg-azul-hielo text-azul-institucional font-headline text-label-sm uppercase tracking-wider"
        >Panel principal</span
      >
      @if (usuario(); as usuarioEnSesion) {
        <h1 class="font-headline font-bold text-headline-md text-negro-institucional mt-3">
          Bienvenido, {{ usuarioEnSesion.nombre_completo || usuarioEnSesion.nombre_usuario }}
        </h1>
      }
      <p class="text-body-md text-azul-pizarra/70 mt-1">Seleccione un módulo para comenzar.</p>

      <ul class="mt-6 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        @for (modulo of accesos(); track modulo.codigo) {
          <li>
            <a
              [routerLink]="modulo.ruta"
              class="flex items-start gap-3 p-4 rounded-lg border border-gris-bordes hover:border-azul-institucional hover:bg-azul-hielo/50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-azul-institucional/40"
            >
              <span
                class="material-symbols-outlined text-azul-institucional text-[24px]"
                aria-hidden="true"
                >{{ iconoDeComponente(modulo.codigo) }}</span
              >
              <span>
                <span class="block font-headline text-title-md text-negro-institucional">{{
                  modulo.nombre
                }}</span>
                @if (modulo.hijos.length) {
                  <span class="block text-xs text-azul-pizarra/60 mt-0.5">{{
                    nombresHijos(modulo.hijos)
                  }}</span>
                }
              </span>
            </a>
          </li>
        }
      </ul>
    </section>
  `,
})
export class PanelPrincipal {
  private readonly sesion = inject(SesionService);
  protected readonly usuario = this.sesion.usuario;
  protected readonly iconoDeComponente = iconoDeComponente;

  /** Accesos directos: todos los módulos del menú menos el propio panel. */
  protected readonly accesos = computed(() =>
    (this.sesion.menu() ?? []).filter((m) => m.codigo !== 'DASHBOARD'),
  );

  protected nombresHijos(hijos: { nombre: string }[]): string {
    return hijos.map((hijo) => hijo.nombre).join(' · ');
  }
}
