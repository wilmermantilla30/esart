import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, finalize, map, of, tap } from 'rxjs';

import {
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

  /** Envía las credenciales. Si son correctas, el backend deja las cookies y aquí se guarda el usuario. */
  iniciarSesion(nombreUsuario: string, contrasena: string): Observable<UsuarioEnSesion> {
    const solicitud: SolicitudInicioSesion = {
      nombre_usuario: nombreUsuario.trim(),
      contrasena,
      captcha_id: null,
      captcha_respuesta: null,
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
