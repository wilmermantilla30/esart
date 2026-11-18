import { Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

/**
 * Página provisional para módulos que ya están en la malla de permisos pero todavía no
 * tienen pantalla. El título y la descripción vienen en `data` de la ruta.
 */
@Component({
  selector: 'esart-en-construccion',
  template: `
    <section class="bg-white rounded-xl border border-gris-bordes p-8 flex flex-col items-center text-center gap-3">
      <span class="material-symbols-outlined text-azul-institucional text-[40px]" aria-hidden="true">construction</span>
      <h2 class="font-headline text-headline-sm text-negro-institucional">{{ titulo }}</h2>
      <p class="max-w-lg text-body-md text-azul-pizarra/70">{{ descripcion }}</p>
    </section>
  `,
})
export class EnConstruccion {
  private readonly datos = inject(ActivatedRoute).snapshot.data;
  protected readonly titulo = (this.datos['titulo'] as string | undefined) ?? 'En construcción';
  protected readonly descripcion =
    (this.datos['descripcion'] as string | undefined) ?? 'Esta sección estará disponible próximamente.';
}
