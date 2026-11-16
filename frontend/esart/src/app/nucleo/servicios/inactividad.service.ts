import { DestroyRef, Injectable, computed, effect, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { MOTIVO_SESION_EXPIRADA, PARAMETRO_MOTIVO, RUTA_PAGINA_INICIO_SESION } from '../rutas-paginas';
import { SesionService } from './sesion.service';

/** Segundos antes del cierre en que se muestra el aviso (contrato de API §1.4: 2 minutos). */
export const SEGUNDOS_AVISO_ANTES_DE_EXPIRAR = 120;

/** Cada cuánto se recalcula la cuenta regresiva en pantalla. */
const MILISEGUNDOS_ENTRE_REVISIONES = 1000;

/**
 * Cuenta regresiva del cierre de sesión por inactividad (HU-08).
 *
 * - La hora de vencimiento la fija el BACKEND: cada respuesta autenticada trae
 *   X-Sesion-Expira-En y el login trae expira_por_inactividad_segundos.
 * - Se guarda como hora absoluta (no como contador), así no se desfasa si el navegador
 *   pausa la pestaña.
 * - Al llegar a cero no cierra a ciegas: pregunta al backend, porque el usuario pudo
 *   seguir trabajando en otra pestaña. Solo si la sesión ya no es válida va al login.
 */
@Injectable({ providedIn: 'root' })
export class InactividadService {
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);

  /** Momento (milisegundos desde 1970) en que la sesión vence, o null si no hay sesión. */
  private vencimiento: number | null = null;
  private temporizador: ReturnType<typeof setInterval> | null = null;
  private comprobandoAlVencer = false;

  private readonly segundosRestantesActuales = signal<number | null>(null);

  /** Segundos que le quedan a la sesión, o null si no hay cuenta regresiva activa. */
  readonly segundosRestantes = this.segundosRestantesActuales.asReadonly();

  /** true durante los últimos 2 minutos: es cuando se muestra el aviso. */
  readonly mostrarAviso = computed(() => {
    const restantes = this.segundosRestantesActuales();
    return restantes !== null && restantes > 0 && restantes <= SEGUNDOS_AVISO_ANTES_DE_EXPIRAR;
  });

  constructor() {
    // Si la sesión termina por cualquier camino (cerrar sesión, 401), se detiene la cuenta.
    effect(() => {
      if (!this.sesion.haySesion()) {
        this.detener();
      }
    });
    inject(DestroyRef).onDestroy(() => this.detener());
  }

  /** Reinicia la cuenta con los segundos informados por el backend. */
  reiniciar(segundos: number): void {
    if (!Number.isFinite(segundos) || segundos <= 0) {
      return;
    }
    this.vencimiento = Date.now() + segundos * 1000;
    this.actualizar();
    if (this.temporizador === null) {
      this.temporizador = setInterval(() => this.actualizar(), MILISEGUNDOS_ENTRE_REVISIONES);
    }
  }

  /** Botón "Continuar sesión": cualquier petición autenticada renueva la actividad. */
  continuarSesion(): void {
    this.sesion.renovarSesion().subscribe((vigente) => {
      if (!vigente) {
        this.irAlLoginPorExpiracion();
      }
    });
  }

  /** Detiene la cuenta regresiva (sin sesión no hay nada que contar). */
  detener(): void {
    if (this.temporizador !== null) {
      clearInterval(this.temporizador);
      this.temporizador = null;
    }
    this.vencimiento = null;
    this.segundosRestantesActuales.set(null);
  }

  private actualizar(): void {
    if (this.vencimiento === null) {
      return;
    }
    const restantes = Math.max(0, Math.ceil((this.vencimiento - Date.now()) / 1000));
    this.segundosRestantesActuales.set(restantes);
    if (restantes === 0 && !this.comprobandoAlVencer) {
      this.comprobarAlVencer();
    }
  }

  /** Al vencer, confirma con el backend antes de cerrar (puede haber actividad en otra pestaña). */
  private comprobarAlVencer(): void {
    this.comprobandoAlVencer = true;
    this.sesion.renovarSesion().subscribe((vigente) => {
      this.comprobandoAlVencer = false;
      if (!vigente) {
        this.irAlLoginPorExpiracion();
      }
      // Si sigue vigente, la respuesta trajo X-Sesion-Expira-En y la cuenta ya se reinició.
    });
  }

  private irAlLoginPorExpiracion(): void {
    this.detener();
    this.sesion.olvidarSesion();
    void this.enrutador.navigate(['/', RUTA_PAGINA_INICIO_SESION], {
      queryParams: { [PARAMETRO_MOTIVO]: MOTIVO_SESION_EXPIRADA },
    });
  }
}
