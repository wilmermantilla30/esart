import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, finalize, map, of, tap, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import {
  CaptchaLocal,
  EstadoBloqueoPublico,
  RespuestaInicioSesion,
  RespuestaUsuarioActual,
  SolicitudInicioSesion,
  UsuarioEnSesion,
} from '../modelos/sesion';
import { ClienteApiService } from './cliente-api.service';

/** Rutas de autenticación del backend (contrato de API, §2). */
export const RUTA_INICIAR_SESION = '/auth/login';
export const RUTA_USUARIO_ACTUAL = '/auth/yo';
export const RUTA_CERRAR_SESION = '/auth/cerrar-sesion';
export const RUTA_CAPTCHA = '/auth/captcha';

/**
 * Estado de la sesión en el navegador.
 *
 * Solo guarda los datos PÚBLICOS del usuario en memoria (signal). No usa localStorage
 * ni sessionStorage: la sesión real es la cookie httpOnly y la valida el backend. Si la
 * página se recarga, el estado se recupera preguntando a /api/auth/yo.
 */
@Injectable({ providedIn: 'root' })
export class SesionService {
  private readonly clienteApi = inject(ClienteApiService);

  private readonly usuarioActual = signal<UsuarioEnSesion | null>(null);

  /** Usuario en sesión, o null si no hay sesión confirmada. */
  readonly usuario = this.usuarioActual.asReadonly();
  readonly haySesion = computed(() => this.usuarioActual() !== null);

  consultarBloqueo(): Observable<EstadoBloqueoPublico> {
    return this.clienteApi.obtener<EstadoBloqueoPublico>('/auth/bloqueo');
  }

  obtenerCaptcha(nombreUsuario: string, anterior: string | null = null): Observable<CaptchaLocal> {
    const nombre = nombreUsuario.trim();
    if (nombre.length < 3 || nombre.length > 80 || /[\x00-\x1f\x7f]/.test(nombre)) {
      return throwError(() => new HttpErrorResponse({ status: 422, error: { error: {
        codigo: 'DATOS_INVALIDOS', mensaje: 'Escriba un usuario válido antes de solicitar el código.',
        detalle: null,
      } } }));
    }
    // Contexto del desafío, nunca identidad autenticada. No requiere token JWT.
    const cabeceras: Record<string, string> = { 'X-ESART-Usuario': nombre };
    if (anterior) cabeceras['X-ESART-Captcha-Anterior'] = anterior;
    return this.clienteApi.obtener<CaptchaLocal>(RUTA_CAPTCHA, cabeceras);
  }

  /** Envía las credenciales. Si son correctas, el backend deja las cookies y aquí se guarda el usuario. */
  iniciarSesion(nombreUsuario: string, contrasena: string,
    captcha: { id: string; respuesta: string } | null = null): Observable<UsuarioEnSesion> {
    const solicitud: SolicitudInicioSesion = {
      nombre_usuario: nombreUsuario.trim(),
      contrasena,
      captcha_id: captcha?.id ?? null,
      captcha_respuesta: captcha?.respuesta ?? null,
    };
    return this.clienteApi.enviar<RespuestaInicioSesion>(RUTA_INICIAR_SESION, solicitud).pipe(
      map((respuesta) => respuesta.usuario),
      tap((usuario) => this.usuarioActual.set(usuario)),
    );
  }

  /**
   * Confirma con el backend si la cookie de sesión sigue siendo válida.
   * Devuelve true/false y nunca lanza error (lo usan las guardas de ruta).
   */
  comprobarSesion(): Observable<boolean> {
    if (this.usuarioActual()) {
      return of(true);
    }
    return this.clienteApi.obtener<RespuestaUsuarioActual>(RUTA_USUARIO_ACTUAL).pipe(
      tap((respuesta) =>
        this.usuarioActual.set({
          nombre_usuario: respuesta.nombre_usuario,
          nombre_completo: respuesta.nombre_completo,
          rol: respuesta.rol,
        }),
      ),
      map(() => true),
      catchError(() => {
        this.usuarioActual.set(null);
        return of(false);
      }),
    );
  }

  /**
   * Pide al backend revocar la sesión y borrar las cookies.
   * El estado local se limpia SIEMPRE, aunque la petición falle (por ejemplo, sin red).
   */
  cerrarSesion(): Observable<void> {
    return this.clienteApi.enviar<void>(RUTA_CERRAR_SESION).pipe(
      catchError(() => of(undefined)),
      map(() => undefined),
      finalize(() => this.olvidarSesion()),
    );
  }

  /** Borra el estado local (lo usa el interceptor cuando el backend responde 401). */
  olvidarSesion(): void {
    this.usuarioActual.set(null);
  }
}
