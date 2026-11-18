import { HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, Subject, catchError, from, map, switchMap, throwError } from 'rxjs';

import {
  FiltrosHabilitacion,
  PaginaHabilitacion,
  RespuestaVerificacion,
  ResumenHabilitacion,
  TipoDocumentoArtillero,
} from '../modelos/verificacion';
import { ClienteApiService } from './cliente-api.service';
import { ArchivoDescargado, nombreDesdeCabecera } from './parametros.service';

/**
 * En una descarga (responseType blob) el error JSON del backend también llega como Blob:
 * se convierte a objeto para que leerErrorApi muestre el mensaje real (ej. 409 del diploma).
 */
function errorDeDescarga(error: unknown): Observable<never> {
  if (!(error instanceof HttpErrorResponse) || !(error.error instanceof Blob)) {
    return throwError(() => error);
  }
  return from(error.error.text()).pipe(
    switchMap((texto) => {
      let cuerpo: unknown = null;
      try {
        cuerpo = JSON.parse(texto);
      } catch {
        cuerpo = null;
      }
      return throwError(
        () =>
          new HttpErrorResponse({
            error: cuerpo,
            headers: error.headers,
            status: error.status,
            statusText: error.statusText,
            url: error.url ?? undefined,
          }),
      );
    }),
  );
}

/**
 * Consultas de verificación de habilitación (contrato de API §3). Solo transporta datos:
 * la regla APTO / NO APTO y los permisos los aplica el backend.
 */
@Injectable({ providedIn: 'root' })
export class VerificacionService {
  private readonly clienteApi = inject(ClienteApiService);
  private readonly cambiosPersonal = new Subject<void>();
  readonly personalActualizado$ = this.cambiosPersonal.asObservable();

  /** Invalida listados activos únicamente tras una importación confirmada por la API. */
  notificarPersonalActualizado(): void {
    this.cambiosPersonal.next();
  }

  /** Verifica un artillero por cédula (el backend acepta puntos y espacios). */
  verificarArtillero(numeroDocumento: string): Observable<RespuestaVerificacion> {
    return this.clienteApi.obtener<RespuestaVerificacion>(
      `/verificar/artillero/${encodeURIComponent(numeroDocumento.trim())}`,
    );
  }

  /** Listado paginado con el estado de cada militar. */
  listarHabilitacion(filtros: FiltrosHabilitacion): Observable<PaginaHabilitacion> {
    return this.clienteApi.obtener<PaginaHabilitacion>(
      '/verificar/habilitacion',
      {},
      {
        estado: filtros.estado,
        texto: filtros.texto.trim(),
        pagina: filtros.pagina,
        tamano_pagina: filtros.tamano_pagina,
      },
    );
  }

  /**
   * PDF del documento elegido (diploma, oficio remisorio o certificación) para la cédula.
   * El backend aplica el permiso de verificar, enmascara la cédula si corresponde y lo audita.
   */
  generarDocumento(
    numeroDocumento: string,
    tipo: TipoDocumentoArtillero,
  ): Observable<ArchivoDescargado> {
    const cedula = encodeURIComponent(numeroDocumento.trim());
    return this.clienteApi
      .descargarArchivo(`/verificar/artillero/${cedula}/documento?tipo=${encodeURIComponent(tipo)}`)
      .pipe(
        map((respuesta: HttpResponse<Blob>) => ({
          nombre: nombreDesdeCabecera(
            respuesta.headers.get('Content-Disposition'),
            `${tipo.toLowerCase()}.pdf`,
          ),
          contenido: respuesta.body ?? new Blob(),
        })),
        catchError(errorDeDescarga),
      );
  }

  /** Indicadores del panel de Personal militar. */
  obtenerResumen(): Observable<ResumenHabilitacion> {
    return this.clienteApi.obtener<ResumenHabilitacion>('/verificar/resumen');
  }
}
