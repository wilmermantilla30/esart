import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  FiltrosHabilitacion,
  PaginaHabilitacion,
  RespuestaVerificacion,
  ResumenHabilitacion,
} from '../modelos/verificacion';
import { ClienteApiService } from './cliente-api.service';

/**
 * Consultas de verificación de habilitación (contrato de API §3). Solo transporta datos:
 * la regla APTO / NO APTO y los permisos los aplica el backend.
 */
@Injectable({ providedIn: 'root' })
export class VerificacionService {
  private readonly clienteApi = inject(ClienteApiService);

  /** Verifica un artillero por cédula (el backend acepta puntos y espacios). */
  verificarArtillero(numeroDocumento: string): Observable<RespuestaVerificacion> {
    return this.clienteApi.obtener<RespuestaVerificacion>(
      `/verificar/artillero/${encodeURIComponent(numeroDocumento.trim())}`,
    );
  }

  /** Listado paginado con el estado de cada militar. */
  listarHabilitacion(filtros: FiltrosHabilitacion): Observable<PaginaHabilitacion> {
    return this.clienteApi.obtener<PaginaHabilitacion>('/verificar/habilitacion', {}, {
      estado: filtros.estado,
      texto: filtros.texto.trim(),
      pagina: filtros.pagina,
      tamano_pagina: filtros.tamano_pagina,
    });
  }

  /** Indicadores del panel de Personal militar. */
  obtenerResumen(): Observable<ResumenHabilitacion> {
    return this.clienteApi.obtener<ResumenHabilitacion>('/verificar/resumen');
  }
}
