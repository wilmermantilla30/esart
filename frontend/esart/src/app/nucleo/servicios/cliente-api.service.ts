import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

/** Prefijo de todas las rutas del backend (mismo origen; en desarrollo lo atiende el proxy). */
export const PREFIJO_API = '/api';

/**
 * Único punto por el que el front llama al backend.
 *
 * - Usa siempre rutas relativas (/api/...): mismo origen, sin CORS y con las cookies de sesión.
 * - Nunca maneja el token: viaja solo en la cookie httpOnly 'esart_sesion'.
 * - La cabecera X-CSRF-Token la agrega Angular (withXsrfConfiguration en app.config.ts).
 */
@Injectable({ providedIn: 'root' })
export class ClienteApiService {
  private readonly http = inject(HttpClient);

  /** GET a una ruta de la API, por ejemplo obtener('/auth/yo'). */
  obtener<T>(ruta: string): Observable<T> {
    return this.http.get<T>(PREFIJO_API + ruta);
  }

  /** POST con cuerpo JSON a una ruta de la API. */
  enviar<T>(ruta: string, cuerpo: unknown = null): Observable<T> {
    return this.http.post<T>(PREFIJO_API + ruta, cuerpo);
  }
}
