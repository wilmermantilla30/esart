/**
 * Tipos de /api/auth según docs/contrato_api.md (§2).
 * Los nombres de los campos son los del contrato (snake_case), sin traducir.
 */

/** Cuerpo de POST /api/auth/login. */
export interface SolicitudInicioSesion {
  nombre_usuario: string;
  contrasena: string;
  /** Obligatorio desde el cuarto intento; desafío emitido y validado por el servidor en la siguiente HU. */
  captcha_id: string | null;
  captcha_respuesta: string | null;
}

/** Desafío opaco: nunca contiene su respuesta correcta. */
export interface CaptchaLocal {
  captcha_id: string;
  imagen_png_base64: string;
  expira_en: string;
  longitud: number;
}

export interface RespuestaCaptcha {
  id: string;
  respuesta: string;
}

/** Datos de bloqueo. Solo el servidor decide qué detalles autoriza. */
export interface DetalleBloqueo {
  intento_actual?: {
    alcance: 'ENVIO_ACTUAL';
    envios_registrados: 1;
    fecha: string;
    direccion_ip_observada: string | null;
    observacion_ip: string;
  } | null;
  bloqueado_hasta?: string | null;
  ahora_servidor?: string;
  segundos_restantes?: number;
  detalles_autorizados?: boolean;
  intentos_fallidos_consecutivos?: number | null;
  direccion_ip?: string | null;
  ip_observacion?: string | null;
  ip_es_loopback?: boolean | null;
  ip_terminal_verificada?: boolean;
}

export interface EstadoBloqueoPublico extends DetalleBloqueo {
  bloqueado: boolean;
  usuario_intentado?: string;
}

/** Datos públicos del usuario en sesión. Nunca incluye el token: ese viaja en la cookie httpOnly. */
export interface UsuarioEnSesion {
  nombre_usuario: string;
  nombre_completo: string;
  /** Código del rol: 'ADMINISTRADOR' o 'USUARIO'. */
  rol: string;
}

/** Respuesta 200 de POST /api/auth/login. */
export interface RespuestaInicioSesion {
  usuario: UsuarioEnSesion;
  expira_por_inactividad_segundos: number;
}

/** Respuesta de GET /api/auth/yo. */
export interface RespuestaUsuarioActual extends UsuarioEnSesion {
  permisos: string[];
  expira_por_inactividad_segundos: number;
}
