import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { EncabezadoInstitucional } from '../../compartido/encabezado-institucional/encabezado-institucional';
import { PieInstitucional } from '../../compartido/pie-institucional/pie-institucional';
import { contrasenaValida, revisarContrasena } from '../../nucleo/contrasenas';
import { ErrorApi, leerErrorApi } from '../../nucleo/modelos/error-api';
import { RUTA_PAGINA_INICIO, RUTA_PAGINA_INICIO_SESION } from '../../nucleo/rutas-paginas';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/**
 * Cambiar contraseña. Es obligatoria cuando la contraseña es temporal (la puso un
 * administrador al crear el usuario o al restablecerla): hasta cambiarla no se puede
 * entrar a ninguna otra página. También se llega desde el encabezado, de forma voluntaria.
 */
@Component({
  selector: 'esart-cambiar-contrasena',
  imports: [FormsModule, EncabezadoInstitucional, PieInstitucional],
  templateUrl: './cambiar-contrasena.html',
})
export class CambiarContrasena {
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);

  protected readonly usuario = this.sesion.usuario;
  /** Se toma al abrir la página: después de cambiarla, el aviso de "obligatorio" ya no aplica. */
  protected readonly obligatorio = this.sesion.requiereCambioContrasena();

  protected readonly actual = signal('');
  protected readonly nueva = signal('');
  protected readonly confirmacion = signal('');
  protected readonly mostrar = signal(false);

  protected readonly enviando = signal(false);
  protected readonly error = signal<ErrorApi | null>(null);

  protected readonly reglas = computed(() => [
    ...revisarContrasena(this.nueva()),
    { texto: 'Distinta de la actual', cumple: !!this.nueva() && this.nueva() !== this.actual() },
    {
      texto: 'La confirmación coincide',
      cumple: !!this.nueva() && this.nueva() === this.confirmacion(),
    },
  ]);
  protected readonly puedeEnviar = computed(
    () =>
      !!this.actual() &&
      contrasenaValida(this.nueva()) &&
      this.reglas().every((regla) => regla.cumple),
  );

  protected guardar(): void {
    if (!this.puedeEnviar() || this.enviando()) {
      return;
    }
    this.enviando.set(true);
    this.error.set(null);
    this.sesion.cambiarContrasena(this.actual(), this.nueva()).subscribe({
      next: () => {
        // No se guardan en memoria más tiempo del necesario.
        this.actual.set('');
        this.nueva.set('');
        this.confirmacion.set('');
        this.enviando.set(false);
        void this.enrutador.navigate([
          '/',
          this.sesion.mfaPendiente() ? RUTA_PAGINA_INICIO_SESION : RUTA_PAGINA_INICIO,
        ]);
      },
      error: (error: unknown) => {
        this.error.set(leerErrorApi(error));
        this.enviando.set(false);
      },
    });
  }

  protected volver(): void {
    void this.enrutador.navigate(['/', RUTA_PAGINA_INICIO]);
  }

  protected salir(): void {
    this.sesion.cerrarSesion().subscribe({
      complete: () => void this.enrutador.navigate(['/', RUTA_PAGINA_INICIO_SESION]),
    });
  }
}
