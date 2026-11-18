import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ErrorApi, leerErrorApi } from '../../../../nucleo/modelos/error-api';
import { ParametrosSeguridad } from '../../../../nucleo/modelos/parametros';
import { ParametrosService } from '../../../../nucleo/servicios/parametros.service';

/**
 * Pestaña "Parámetros de Seguridad": SOLO CONSULTA.
 * Muestra la doble autenticación, las reglas del inicio de sesión y qué acciones exigen
 * el código del autenticador. Las políticas se cambian por migración, no desde la web.
 */
@Component({
  selector: 'esart-parametros-seguridad',
  templateUrl: './parametros-seguridad.html',
})
export class ParametrosSeguridadPestana {
  private readonly parametros = inject(ParametrosService);
  private readonly destruir = inject(DestroyRef);

  protected readonly datos = signal<ParametrosSeguridad | null>(null);
  protected readonly error = signal<ErrorApi | null>(null);

  constructor() {
    this.parametros
      .obtenerSeguridad()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (datos) => this.datos.set(datos),
        error: (error: unknown) => this.error.set(leerErrorApi(error)),
      });
  }
}
