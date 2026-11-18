import { Component, computed, inject } from '@angular/core';
import {
  IsActiveMatchOptions,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import type { CargueExcel } from './cargue-excel/cargue-excel';

import { iconoDeComponente } from '../../nucleo/iconos-menu';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/** Código del módulo en la malla de permisos. */
const CODIGO_MODULO = 'PERSONAL_MILITAR';

/**
 * Módulo Personal militar: pestañas horizontales (Panel + componentes hijos que el rol
 * permite: Verificar artillero, Habilitados, Cargue por Excel, Registro manual) y el
 * contenido de la pestaña activa.
 */
@Component({
  selector: 'esart-personal-militar',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="space-y-4">
      <div>
        <h1 class="font-headline font-bold text-headline-md text-negro-institucional">
          Personal militar
        </h1>
        <p class="text-body-md text-azul-pizarra/70">
          Verificación de habilitación y registro del personal artillero.
        </p>
      </div>

      <!-- Pestañas del módulo -->
      <nav
        class="bg-white rounded-xl border border-gris-bordes p-1.5 flex gap-1 overflow-x-auto"
        aria-label="Secciones de Personal militar"
      >
        @for (pestana of pestanas(); track pestana.ruta) {
          @if (pestana.codigo === 'PERSONAL_CARGUE_EXCEL') {
            <button
              type="button"
              aria-haspopup="dialog"
              aria-controls="excel-importacion"
              (click)="abrirCargue(pestana.ruta)"
              class="shrink-0 inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-label-lg font-headline bg-azul-hielo text-azul-pizarra border border-azul-claro/40 hover:bg-green-100 transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-azul-institucional/40"
            >
              <span class="material-symbols-outlined text-[18px]" aria-hidden="true"
                >upload_file</span
              >
              Cargue masivo por Excel
            </button>
          } @else {
            <a
              [routerLink]="pestana.ruta"
              routerLinkActive="bg-azul-institucional text-white shadow-sm"
              [routerLinkActiveOptions]="opcionesPestanaActiva"
              class="shrink-0 inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-label-lg font-headline text-azul-pizarra hover:bg-azul-hielo transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-azul-institucional/40"
            >
              <span class="material-symbols-outlined text-[18px]" aria-hidden="true">{{
                pestana.icono
              }}</span>
              <span>{{ pestana.nombre }}</span>
            </a>
          }
        }
      </nav>

      <router-outlet
        #contenido="outlet"
        (activate)="activarPagina($event, contenido)"
        (deactivate)="cargueActivo = null"
      />
    </div>
  `,
})
export class PersonalMilitar {
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);
  protected cargueActivo: CargueExcel | null = null;

  protected abrirCargue(ruta: string) {
    if (this.cargueActivo) this.cargueActivo.abrir();
    else void this.enrutador.navigateByUrl(ruta);
  }

  protected activarPagina(pagina: unknown, salida: RouterOutlet) {
    if (salida.activatedRoute.snapshot.routeConfig?.path !== 'cargue-excel') return;
    const cargue = pagina as CargueExcel;
    this.cargueActivo = cargue;
    // La vista hija debe estar montada antes de invocar showModal().
    queueMicrotask(() => {
      if (this.cargueActivo === cargue) cargue.abrir();
    });
  }

  /**
   * Una pestaña está activa si la ruta coincide exactamente (así "Panel" no queda activo en las
   * demás), ignorando los parámetros: /personal/verificar?cedula=... sigue resaltando su pestaña.
   */
  protected readonly opcionesPestanaActiva: IsActiveMatchOptions = {
    paths: 'exact',
    queryParams: 'ignored',
    matrixParams: 'ignored',
    fragment: 'ignored',
  };

  /** Primera pestaña: el panel del módulo; después, los hijos que el rol permite. */
  protected readonly pestanas = computed(() => {
    const modulo = (this.sesion.menu() ?? []).find((m) => m.codigo === CODIGO_MODULO);
    if (!modulo) {
      return [];
    }
    return [
      { nombre: 'Panel', ruta: modulo.ruta, icono: 'analytics', codigo: 'PANEL_PERSONAL' },
      ...modulo.hijos.map((hijo) => ({
        nombre: hijo.nombre,
        ruta: hijo.ruta,
        icono: iconoDeComponente(hijo.codigo),
        codigo: hijo.codigo,
      })),
    ];
  });
}
