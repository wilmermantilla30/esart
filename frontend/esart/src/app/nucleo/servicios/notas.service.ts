import { HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  CasoConsejo,
  DetalleEntrega,
  EntregaDeMateria,
  EntregaEnBandeja,
  FiltroBandeja,
  FiltroConsejo,
  FormularioHabilitacion,
  MisMaterias,
  SolicitudDecisionConsejo,
} from '../modelos/notas';
import { ClienteApiService } from './cliente-api.service';
import { ArchivoDescargado, nombreDesdeCabecera } from './parametros.service';

/**
 * Notas: carga del instructor (S2-12: sus materias, la plantilla y la entrega) y revisión del
 * Inspector de Estudios (S2-13: bandeja, aprobar, devolver y reabrir), habilitación y Consejo
 * Académico (S2-14).
 */
@Injectable({ providedIn: 'root' })
export class NotasService {
  private readonly api = inject(ClienteApiService);

  misMaterias(): Observable<MisMaterias> {
    return this.api.obtener<MisMaterias>('/notas/mis-materias');
  }

  descargarPlantilla(cursoId: number, mallaId: number): Observable<ArchivoDescargado> {
    return this.api.descargarArchivo(`/notas/plantilla/${cursoId}/${mallaId}`).pipe(
      map((respuesta: HttpResponse<Blob>) => ({
        nombre: nombreDesdeCabecera(respuesta.headers.get('Content-Disposition'), 'Notas.xlsx'),
        contenido: respuesta.body ?? new Blob(),
      })),
    );
  }

  entrega(cursoId: number, mallaId: number): Observable<EntregaDeMateria> {
    return this.api.obtener<EntregaDeMateria>(`/notas/entregas/${cursoId}/${mallaId}`);
  }

  /** Sube la planilla llena. Queda EN_REVISION hasta que el Inspector la apruebe. */
  subir(cursoId: number, mallaId: number, archivo: File): Observable<EntregaDeMateria> {
    const datos = new FormData();
    datos.append('archivo', archivo);
    // Multipart: sin fijar Content-Type para que el navegador ponga el boundary.
    return this.api.enviar<EntregaDeMateria>(`/notas/entregas/${cursoId}/${mallaId}`, datos);
  }

  // --- Revisión (S2-13) ---------------------------------------------------------------------

  bandeja(estado: FiltroBandeja): Observable<EntregaEnBandeja[]> {
    return this.api.obtener<EntregaEnBandeja[]>('/notas/revision/entregas', {}, { estado });
  }

  detalleEntrega(entregaId: number): Observable<DetalleEntrega> {
    return this.api.obtener<DetalleEntrega>(`/notas/revision/entregas/${entregaId}`);
  }

  /** Aprueba la entrega revisada (versión = su subido_en). No pide código del autenticador. */
  aprobar(entregaId: number, version: string): Observable<DetalleEntrega> {
    return this.api.enviar<DetalleEntrega>(`/notas/revision/entregas/${entregaId}/aprobar`, {
      version,
    });
  }

  devolver(entregaId: number, version: string, observacion: string): Observable<DetalleEntrega> {
    return this.api.enviar<DetalleEntrega>(`/notas/revision/entregas/${entregaId}/devolver`, {
      version,
      observacion,
    });
  }

  /** Reabre una entrega aprobada para corregirla. Sin código responde TOTP_REQUERIDO. */
  reabrir(entregaId: number, observacion: string, codigoTotp = ''): Observable<DetalleEntrega> {
    return this.api.enviar<DetalleEntrega>(`/notas/revision/entregas/${entregaId}/reabrir`, {
      observacion,
      codigo_totp: codigoTotp,
    });
  }

  // --- Habilitación y Consejo (S2-14) ---------------------------------------------------------

  habilitacion(cursoId: number, mallaId: number): Observable<FormularioHabilitacion> {
    return this.api.obtener<FormularioHabilitacion>(`/notas/habilitaciones/${cursoId}/${mallaId}`);
  }

  /** Registra las notas de habilitación: quedan EN_REVISION para el Inspector. */
  registrarHabilitacion(
    cursoId: number,
    mallaId: number,
    notas: { cedula: string; nota: string }[],
  ): Observable<FormularioHabilitacion> {
    return this.api.enviar<FormularioHabilitacion>(`/notas/habilitaciones/${cursoId}/${mallaId}`, {
      notas,
    });
  }

  casosConsejo(filtro: FiltroConsejo): Observable<CasoConsejo[]> {
    return this.api.obtener<CasoConsejo[]>('/notas/consejo/casos', {}, { filtro });
  }

  /** Registra la decisión del Consejo. Sin código responde TOTP_REQUERIDO. */
  registrarDecision(
    habilitacionId: number,
    datos: SolicitudDecisionConsejo,
    codigoTotp = '',
  ): Observable<CasoConsejo> {
    return this.api.enviar<CasoConsejo>(`/notas/consejo/casos/${habilitacionId}/decision`, {
      ...datos,
      codigo_totp: codigoTotp,
    });
  }
}
