/**
 * Firma electrónica desde el celular (rúbrica + TOTP de ESART).
 * Contrato: /api/firma (PC, con sesión) y /api/firma-movil/{token} (celular, sin sesión).
 * Flujo y reglas: docs/ESART_FIRMA_MOVIL.md.
 */

export type TipoFirmable = 'CERTIFICACION' | 'OFICIO_REMISORIO';
export type EstadoSolicitudFirma =
  'PENDIENTE' | 'ABIERTA' | 'APROBADA' | 'RECHAZADA' | 'EXPIRADA' | 'CANCELADA';

export interface FirmanteAutorizado {
  autorizacion_id: string;
  usuario_id: number;
  nombre: string;
  cargo: string;
  tipo: TipoFirmable;
}

/** Usuario que FIRMA_DOCUMENTOS (crear) puede autorizar como firmante. */
export interface CandidatoFirmante {
  usuario_id: number;
  usuario: string | null;
  nombre: string;
  totp_activo: boolean;
}

export interface SolicitudFirmaCreada {
  solicitud_id: string;
  documento_id: string;
  /** Dirección que codifica el QR (absoluta si el backend la tiene configurada). */
  url_firma: string;
  url_publica_configurada: boolean;
  expira_en: string;
  firmante: string;
  cargo: string;
}

export interface EstadoSolicitud {
  solicitud_id: string;
  documento_id: string;
  estado: EstadoSolicitudFirma;
  estado_documento: string;
  expira_en: string;
  firmante: string;
  cargo: string;
}

/** Lo que ve el celular al abrir el QR. */
export interface ResumenFirmaMovil {
  estado: EstadoSolicitudFirma;
  tipo: TipoFirmable;
  numero: string;
  artillero: string;
  firmante: string;
  cargo: string;
  expira_en: string;
  texto_consentimiento: string;
}

export interface FirmaRealizada {
  estado: EstadoSolicitudFirma;
  codigo_verificacion: string;
}
