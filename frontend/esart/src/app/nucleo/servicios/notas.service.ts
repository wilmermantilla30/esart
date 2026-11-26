import { HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  DetalleEntrega,
  EntregaDeMateria,
  EntregaEnBandeja,
  FiltroBandeja,
  MisMaterias,
} from '../modelos/notas';
import { ClienteApiService } from './cliente-api.service';
import { ArchivoDescargado, nombreDesdeCabecera } from './parametros.service';

/**
 * Notas: carga del instructor (S2-12: sus materias, la plantilla y la entrega) y revisión del
 * Inspector de Estudios (S2-13: bandeja, aprobar, devolver y reabrir).
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

  /** Aprueba la entrega revisada (versión = su subido_en). Sin código responde TOTP_REQUERIDO. */
  aprobar(entregaId: number, version: string, codigoTotp = ''): Observable<DetalleEntrega> {
    return this.api.enviar<DetalleEntrega>(`/notas/revision/entregas/${entregaId}/aprobar`, {
      version,
      codigo_totp: codigoTotp,
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
}
