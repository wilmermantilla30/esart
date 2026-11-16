import { Component } from '@angular/core';

/** Pie de página institucional, igual en todas las páginas. */
@Component({
  selector: 'esart-pie-institucional',
  template: `
    <footer class="py-4 px-6 text-center text-xs text-azul-pizarra/60 border-t border-gris-bordes bg-white">
      <p>
        © {{ anioActual }} Escuela de Artillería “General Carlos Julio Gil Colorado” • Ejército Nacional de
        Colombia • Todos los derechos reservados.
      </p>
    </footer>
  `,
})
export class PieInstitucional {
  /** Año del copyright: se calcula para no tener que editarlo cada año. */
  protected readonly anioActual = new Date().getFullYear();
}
