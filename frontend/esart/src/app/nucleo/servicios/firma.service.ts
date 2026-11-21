import { HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  CandidatoFirmante,
  EstadoSolicitud,
  FirmaRealizada,
  FirmanteAutorizado,
  ResumenFirmaMovil,
  SolicitudFirmaCreada,
  TipoFirmable,
} from '../modelos/firma';
import { ClienteApiService, PREFIJO_API } from './cliente-api.service';
import { ArchivoDescargado, nombreDesdeCabecera } from './parametros.service';

/** Ruta pública de la página de firma en el celular (la que abre el QR). */
export const RUTA_FIRMA_MOVIL = 'firma';

/**
 * Firma desde el celular. Las rutas /firma usan la sesión del PC (permisos en el backend);
 * las /firma-movil solo el token del QR y el TOTP del firmante.
 */
@Injectable({ providedIn: 'root' })
export class FirmaService {
  private readonly api = inject(ClienteApiService);

  firmantes(tipo: TipoFirmable): Observable<FirmanteAutorizado[]> {
    return this.api.obtener<FirmanteAutorizado[]>('/firma/firmantes', {}, { tipo });
  }

  /** Usuarios que se pueden autorizar (requiere FIRMA_DOCUMENTOS crear). */
  candidatos(): Observable<CandidatoFirmante[]> {
    return this.api.obtener<CandidatoFirmante[]>('/firma/candidatos');
  }

  /** Autoriza a un usuario como firmante de un tipo de documento, con su cargo. */
  autorizar(usuarioId: number, tipo: TipoFirmable, cargo: string): Observable<unknown> {
    return this.api.enviar('/firma/autorizaciones', {
      usuario_id: usuarioId,
      tipo,
      cargo: cargo.trim(),
    });
  }

  solicitar(
    cedula: string,
    tipo: TipoFirmable,
    autorizacionId: string,
  ): Observable<SolicitudFirmaCreada> {
    return this.api.enviar<SolicitudFirmaCreada>('/firma/solicitudes', {
      cedula: cedula.trim(),
      tipo,
      autorizacion_id: autorizacionId,
    });
  }

  estado(solicitudId: string): Observable<EstadoSolicitud> {
    return this.api.obtener<EstadoSolicitud>(
      `/firma/solicitudes/${encodeURIComponent(solicitudId)}`,
    );
  }

  /** PDF firmado (versión actual del documento guardado). */
  descargarFirmado(documentoId: string): Observable<ArchivoDescargado> {
    return this.api
      .descargarArchivo(`/verificar/documentos/${encodeURIComponent(documentoId)}/archivo`)
      .pipe(
        map((respuesta: HttpResponse<Blob>) => ({
          nombre: nombreDesdeCabecera(
            respuesta.headers.get('Content-Disposition'),
            'documento_firmado.pdf',
          ),
          contenido: respuesta.body ?? new Blob(),
        })),
      );
  }

  // --- Celular (sin sesión) ---

  abrir(token: string): Observable<ResumenFirmaMovil> {
    return this.api.obtener<ResumenFirmaMovil>(`/firma-movil/${encodeURIComponent(token)}`);
  }

  /** Dirección del borrador para abrirlo en el visor de PDF del celular. */
  urlBorrador(token: string): string {
    return `${PREFIJO_API}/firma-movil/${encodeURIComponent(token)}/pdf`;
  }

  firmar(
    token: string,
    rubricaPng: string,
    codigoTotp: string,
    acepto: boolean,
  ): Observable<FirmaRealizada> {
    return this.api.enviar<FirmaRealizada>(`/firma-movil/${encodeURIComponent(token)}/firmar`, {
      rubrica_png: rubricaPng,
      codigo_totp: codigoTotp,
      acepto,
    });
  }
}
