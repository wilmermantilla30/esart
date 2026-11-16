/**
 * Rutas de las páginas del front y parámetros que viajan entre ellas.
 * Se definen una sola vez para no repetir textos sueltos en guardas, interceptor y páginas.
 */
export const RUTA_PAGINA_INICIO_SESION = 'inicio-sesion';
/** Página de entrada tras el login: el Panel principal (componente DASHBOARD). */
export const RUTA_PAGINA_INICIO = 'dashboard';

/** Parámetro con la página a la que se vuelve después de iniciar sesión. */
export const PARAMETRO_VOLVER_A = 'volver';

/** Parámetro con el motivo por el que se llegó al login (por ejemplo, sesión expirada). */
export const PARAMETRO_MOTIVO = 'motivo';
export const MOTIVO_SESION_EXPIRADA = 'sesion-expirada';

/**
 * Indica si un destino de "volver" es seguro: debe ser una ruta interna.
 * Rechaza '//sitio.com' y 'https://...' para que nadie pueda armar un enlace de login
 * que, tras autenticar, lleve al usuario a otro sitio (redirección abierta).
 */
export function esRutaInternaSegura(ruta: string | null | undefined): ruta is string {
  return !!ruta && ruta.startsWith('/') && !ruta.startsWith('//') && !ruta.startsWith('/\\');
}
