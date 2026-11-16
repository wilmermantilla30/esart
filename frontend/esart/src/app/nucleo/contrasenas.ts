/**
 * Reglas de contraseña del lado del navegador. Son las mismas que aplica el backend
 * (validar_contrasena_nueva): aquí solo sirven para avisar antes de enviar.
 */

export const LONGITUD_MINIMA_CONTRASENA = 10;
const LONGITUD_MAXIMA_BYTES = 72;
const LONGITUD_CONTRASENA_GENERADA = 12;

/** Sin caracteres que se confunden al dictarlos o copiarlos a mano (0/O, 1/l/I). */
const LETRAS = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ';
const DIGITOS = '23456789';

export interface ReglaContrasena {
  texto: string;
  cumple: boolean;
}

/** Estado de cada regla para una contraseña (para la lista de chequeo del formulario). */
export function revisarContrasena(contrasena: string): ReglaContrasena[] {
  return [
    { texto: `Al menos ${LONGITUD_MINIMA_CONTRASENA} caracteres`, cumple: contrasena.length >= LONGITUD_MINIMA_CONTRASENA },
    { texto: 'Letras y números', cumple: /[A-Za-z]/.test(contrasena) && /\d/.test(contrasena) },
    {
      texto: 'Máximo 72 bytes',
      cumple: new TextEncoder().encode(contrasena).length <= LONGITUD_MAXIMA_BYTES,
    },
  ];
}

export function contrasenaValida(contrasena: string): boolean {
  return revisarContrasena(contrasena).every((regla) => regla.cumple);
}

/**
 * Contraseña temporal aleatoria (generador criptográfico del navegador) que siempre cumple
 * las reglas: 12 caracteres con letras y números. No se guarda en ningún lado.
 */
export function generarContrasenaTemporal(): string {
  const alfabeto = LETRAS + DIGITOS;
  for (;;) {
    const aleatorios = crypto.getRandomValues(new Uint32Array(LONGITUD_CONTRASENA_GENERADA));
    const contrasena = Array.from(aleatorios, (valor) => alfabeto[valor % alfabeto.length]).join('');
    if (contrasenaValida(contrasena)) {
      return contrasena;
    }
  }
}
