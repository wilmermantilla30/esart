import { Component } from '@angular/core';

/**
 * Encabezado institucional (escudo + Ejército Nacional) de todas las páginas.
 * El lado derecho se rellena desde la página que lo usa (<ng-content>): en el login
 * va el sello de servidor seguro; dentro del sistema, el usuario y "Cerrar sesión".
 */
@Component({
  selector: 'esart-encabezado-institucional',
  template: `
    <header
      class="py-4 px-6 md:px-12 flex items-center justify-between gap-4 border-b border-gris-bordes/60 bg-white/80 backdrop-blur-sm"
    >
      <div class="flex items-center gap-3 min-w-0">
        <img src="imagenes/escudo-esart.png" alt="Escudo de la Escuela de Artillería" class="h-10 w-auto object-contain" />
        <div class="border-l border-gris-bordes pl-3 min-w-0">
          <div class="font-headline font-bold text-sm tracking-tight text-negro-institucional">
            EJÉRCITO NACIONAL DE COLOMBIA
          </div>
          <div class="text-xs text-azul-pizarra/70 font-medium">Jefatura de Educación y Doctrina • CEMIL</div>
        </div>
      </div>
      <ng-content />
    </header>
  `,
})
export class EncabezadoInstitucional {}
