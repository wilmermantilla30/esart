import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { EncabezadoInstitucional } from '../../compartido/encabezado-institucional/encabezado-institucional';
import { PieInstitucional } from '../../compartido/pie-institucional/pie-institucional';
import { ErrorApi, leerErrorApi } from '../../nucleo/modelos/error-api';
import {
  MOTIVO_SESION_EXPIRADA,
  PARAMETRO_MOTIVO,
  PARAMETRO_VOLVER_A,
  RUTA_PAGINA_INICIO,
  esRutaInternaSegura,
} from '../../nucleo/rutas-paginas';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/** Límites del backend (esquemas/autenticacion.py). Se validan también aquí para avisar antes de enviar. */
export const LONGITUD_MINIMA_USUARIO = 3;
export const LONGITUD_MAXIMA_USUARIO = 80;
export const LONGITUD_MAXIMA_CONTRASENA = 72;

/**
 * Página de inicio de sesión (diseño institucional de Stitch).
 *
 * Solo envía usuario y contraseña al backend y muestra el resultado. Nunca guarda la
 * contraseña: el campo se vacía después de cada intento fallido.
 */
@Component({
  selector: 'esart-inicio-sesion',
  imports: [ReactiveFormsModule, EncabezadoInstitucional, PieInstitucional],
  templateUrl: './inicio-sesion.html',
})
export class InicioSesion {
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);
  private readonly rutaActual = inject(ActivatedRoute);

  protected readonly formulario = inject(NonNullableFormBuilder).group({
    nombreUsuario: [
      '',
      [
        Validators.required,
        Validators.minLength(LONGITUD_MINIMA_USUARIO),
        Validators.maxLength(LONGITUD_MAXIMA_USUARIO),
      ],
    ],
    contrasena: ['', [Validators.required, Validators.maxLength(LONGITUD_MAXIMA_CONTRASENA)]],
  });

  protected readonly enviando = signal(false);
  protected readonly contrasenaVisible = signal(false);
  protected readonly errorServidor = signal<ErrorApi | null>(null);

  /** Aviso cuando se llega aquí porque la sesión anterior expiró (lo pone el interceptor). */
  protected readonly sesionExpirada =
    this.rutaActual.snapshot.queryParamMap.get(PARAMETRO_MOTIVO) === MOTIVO_SESION_EXPIRADA;

  protected readonly longitudMinimaUsuario = LONGITUD_MINIMA_USUARIO;
  protected readonly longitudMaximaUsuario = LONGITUD_MAXIMA_USUARIO;
  protected readonly longitudMaximaContrasena = LONGITUD_MAXIMA_CONTRASENA;

  protected alternarVisibilidadContrasena(): void {
    this.contrasenaVisible.update((visible) => !visible);
  }

  /** Indica si un campo debe mostrar su error (solo después de que el usuario lo tocó o intentó enviar). */
  protected campoConError(nombreCampo: 'nombreUsuario' | 'contrasena'): boolean {
    const campo = this.formulario.controls[nombreCampo];
    return campo.invalid && (campo.touched || campo.dirty);
  }

  protected iniciarSesion(): void {
    if (this.enviando()) {
      return;
    }
    if (this.formulario.invalid) {
      // Marca los campos para que se vean sus errores en lugar de enviar algo que el backend rechazará.
      this.formulario.markAllAsTouched();
      return;
    }

    this.enviando.set(true);
    this.errorServidor.set(null);
    const { nombreUsuario, contrasena } = this.formulario.getRawValue();

    this.sesion.iniciarSesion(nombreUsuario, contrasena).subscribe({
      next: () => {
        // Se limpia la contraseña de la memoria del formulario aunque se salga de la página.
        this.formulario.controls.contrasena.reset();
        const volverA = this.rutaActual.snapshot.queryParamMap.get(PARAMETRO_VOLVER_A);
        void this.enrutador.navigateByUrl(esRutaInternaSegura(volverA) ? volverA : '/' + RUTA_PAGINA_INICIO);
      },
      error: (error: unknown) => {
        this.errorServidor.set(leerErrorApi(error));
        this.formulario.controls.contrasena.reset();
        this.enviando.set(false);
      },
    });
  }

  /** Hora local de desbloqueo cuando la cuenta está bloqueada (USUARIO_BLOQUEADO, contrato §1.2). */
  protected horaDesbloqueo(error: ErrorApi): string | null {
    const valor = error.detalle?.['desbloqueo_estimado'];
    if (typeof valor !== 'string') {
      return null;
    }
    const fecha = new Date(valor);
    return Number.isNaN(fecha.getTime())
      ? null
      : fecha.toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' });
  }
}
