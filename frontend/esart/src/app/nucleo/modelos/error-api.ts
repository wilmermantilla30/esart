import { HttpErrorResponse } from '@angular/common/http';

/**
 * Formato único de error del backend (docs/contrato_api.md §1.2):
 * { "error": { "codigo", "mensaje", "detalle" } }
 */
export interface ErrorApi {
  codigo: string;
  mensaje: string;
  detalle: Record<string, unknown> | null;
  /** Código HTTP de la respuesta (0 si no hubo respuesta del servidor). */
  estadoHttp: number;
}

/** Código propio del front para cuando el servidor no respondió (caído, sin red, proxy apagado). */
export const CODIGO_SIN_CONEXION = 'SIN_CONEXION';

/** Bad Gateway, Service Unavailable y Gateway Timeout: el servidor de la API no respondió. */
const ESTADOS_SERVIDOR_NO_DISPONIBLE = new Set([502, 503, 504]);

const MENSAJE_SIN_CONEXION = 'No fue posible conectar con el servidor. Intente de nuevo en unos minutos.';
const MENSAJE_ERROR_INESPERADO = 'Ocurrió un error inesperado. Intente de nuevo.';

/**
 * Convierte cualquier error HTTP en un ErrorApi.
 *
 * Es la ÚNICA función que interpreta errores del backend: las pantallas solo leen
 * 'codigo' y 'mensaje'. Nunca muestra detalles técnicos (pila, SQL, texto crudo).
 */
export function leerErrorApi(error: unknown): ErrorApi {
  if (!(error instanceof HttpErrorResponse)) {
    return { codigo: 'ERROR_INTERNO', mensaje: MENSAJE_ERROR_INESPERADO, detalle: null, estadoHttp: 0 };
  }
  if (error.status === 0) {
    return { codigo: CODIGO_SIN_CONEXION, mensaje: MENSAJE_SIN_CONEXION, detalle: null, estadoHttp: 0 };
  }

  const cuerpo = error.error as { error?: Partial<ErrorApi> } | null;
  const errorDelContrato = cuerpo && typeof cuerpo === 'object' ? cuerpo.error : undefined;
  if (errorDelContrato && typeof errorDelContrato.codigo === 'string') {
    return {
      codigo: errorDelContrato.codigo,
      mensaje:
        typeof errorDelContrato.mensaje === 'string' && errorDelContrato.mensaje
          ? errorDelContrato.mensaje
          : MENSAJE_ERROR_INESPERADO,
      detalle: (errorDelContrato.detalle as Record<string, unknown> | null) ?? null,
      estadoHttp: error.status,
    };
  }

  // 502/503/504 sin el formato del contrato: el backend no está disponible (caído o
  // detrás de un proxy que no lo alcanza). Para el usuario es lo mismo que sin conexión.
  if (ESTADOS_SERVIDOR_NO_DISPONIBLE.has(error.status)) {
    return { codigo: CODIGO_SIN_CONEXION, mensaje: MENSAJE_SIN_CONEXION, detalle: null, estadoHttp: error.status };
  }

  // Cualquier otra respuesta que no sigue el contrato: mensaje genérico.
  return { codigo: 'ERROR_INTERNO', mensaje: MENSAJE_ERROR_INESPERADO, detalle: null, estadoHttp: error.status };
}
