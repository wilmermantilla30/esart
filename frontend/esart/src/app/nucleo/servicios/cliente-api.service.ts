import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
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

  /**
   * GET a una ruta de la API, por ejemplo obtener('/auth/yo').
   * Los parámetros de consulta vacíos (null, undefined o '') no se envían.
   */
  obtener<T>(
    ruta: string,
    cabeceras: Record<string, string> = {},
    parametros: Record<string, string | number | null | undefined> = {},
  ): Observable<T> {
    let params = new HttpParams();
    for (const [nombre, valor] of Object.entries(parametros)) {
      if (valor !== null && valor !== undefined && valor !== '') {
        params = params.set(nombre, String(valor));
      }
    }
    return this.http.get<T>(PREFIJO_API + ruta, { headers: cabeceras, params });
  }

  /** PUT con cuerpo JSON (reemplaza un recurso). Angular agrega la cabecera CSRF. */
  reemplazar<T>(ruta: string, cuerpo: unknown): Observable<T> {
    return this.http.put<T>(PREFIJO_API + ruta, cuerpo);
  }

  /**
   * GET de un archivo (respuesta binaria completa, con cabeceras). La usa la descarga de
   * plantillas: el nombre del archivo viene en Content-Disposition.
   */
  descargarArchivo(ruta: string): Observable<HttpResponse<Blob>> {
    return this.http.get(PREFIJO_API + ruta, { observe: 'response', responseType: 'blob' });
  }

  /** DELETE a una ruta de la API. Angular agrega la cabecera CSRF. */
  eliminar<T>(ruta: string): Observable<T> {
    return this.http.delete<T>(PREFIJO_API + ruta);
  }

  /** POST con cuerpo JSON a una ruta de la API. */
  enviar<T>(ruta: string, cuerpo: unknown = null): Observable<T> {
    return this.http.post<T>(PREFIJO_API + ruta, cuerpo);
  }
}
