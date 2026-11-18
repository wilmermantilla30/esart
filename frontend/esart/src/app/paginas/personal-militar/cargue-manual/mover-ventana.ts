/** Posición (esquina superior izquierda) de una ventana flotante, en píxeles del viewport. */
export interface PosicionVentana {
  x: number;
  y: number;
}

/** Margen mínimo entre la ventana y el borde del navegador. */
export const MARGEN_VENTANA = 8;
/** Paso al mover la ventana con las flechas del teclado. */
export const PASO_TECLADO = 24;

const limitar = (valor: number, minimo: number, maximo: number) =>
  Math.min(Math.max(valor, minimo), Math.max(minimo, maximo));

/**
 * Mantiene la ventana completa dentro del navegador (con MARGEN_VENTANA a cada lado).
 * Si la ventana es más grande que el navegador, queda pegada al margen superior/izquierdo.
 */
export function limitarPosicion(
  posicion: PosicionVentana,
  tamano: { ancho: number; alto: number },
  viewport: { ancho: number; alto: number },
): PosicionVentana {
  return {
    x: Math.round(
      limitar(posicion.x, MARGEN_VENTANA, viewport.ancho - tamano.ancho - MARGEN_VENTANA),
    ),
    y: Math.round(
      limitar(posicion.y, MARGEN_VENTANA, viewport.alto - tamano.alto - MARGEN_VENTANA),
    ),
  };
}

/** Desplazamiento que corresponde a una flecha del teclado (null si es otra tecla). */
export function pasoDeTecla(tecla: string): PosicionVentana | null {
  switch (tecla) {
    case 'ArrowLeft':
      return { x: -PASO_TECLADO, y: 0 };
    case 'ArrowRight':
      return { x: PASO_TECLADO, y: 0 };
    case 'ArrowUp':
      return { x: 0, y: -PASO_TECLADO };
    case 'ArrowDown':
      return { x: 0, y: PASO_TECLADO };
    default:
      return null;
  }
}
