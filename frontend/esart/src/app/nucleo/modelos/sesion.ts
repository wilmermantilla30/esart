/**
 * Tipos de /api/auth según docs/contrato_api.md (§2).
 * Los nombres de los campos son los del contrato (snake_case), sin traducir.
 */

/** Cuerpo de POST /api/auth/login. */
export interface SolicitudInicioSesion {
  nombre_usuario: string;
  contrasena: string;
  /** El captcha se exige a partir del 3.er fallo (HU-07); mientras tanto va en null. */
  captcha_id: string | null;
  captcha_respuesta: string | null;
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
