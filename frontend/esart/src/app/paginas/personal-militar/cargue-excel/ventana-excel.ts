/** Geometría de la ventana, independiente del procesamiento de archivos. */
export interface RectVentana {
  x: number;
  y: number;
  ancho: number;
  alto: number;
}
export interface ViewportVentana {
  ancho: number;
  alto: number;
}
export type BordeVentana = 'n' | 's' | 'e' | 'o' | 'ne' | 'no' | 'se' | 'so';
export const BORDES_VENTANA: BordeVentana[] = ['n', 's', 'e', 'o', 'ne', 'no', 'se', 'so'];
const MARGEN = 8;
const limitar = (valor: number, minimo: number, maximo: number) =>
  Math.min(Math.max(valor, minimo), maximo);

export function limitesViewport(viewport: ViewportVentana) {
  const margen = Math.min(MARGEN, viewport.ancho / 4, viewport.alto / 4);
  return {
    margen,
    ancho: Math.max(1, viewport.ancho - margen * 2),
    alto: Math.max(1, viewport.alto - margen * 2),
  };
}
export function ajustarRectangulo(rect: RectVentana, viewport: ViewportVentana): RectVentana {
  const { margen, ancho: maxAncho, alto: maxAlto } = limitesViewport(viewport);
  const ancho = limitar(rect.ancho, Math.min(640, maxAncho), maxAncho);
  const alto = limitar(rect.alto, Math.min(420, maxAlto), maxAlto);
  return {
    x: limitar(rect.x, margen, viewport.ancho - margen - ancho),
    y: limitar(rect.y, margen, viewport.alto - margen - alto),
    ancho,
    alto,
  };
}
export function rectanguloMaximo(viewport: ViewportVentana): RectVentana {
  const { margen, ancho, alto } = limitesViewport(viewport);
  return { x: margen, y: margen, ancho, alto };
}
export function redimensionarRectangulo(
  rect: RectVentana,
  borde: BordeVentana,
  dx: number,
  dy: number,
  viewport: ViewportVentana,
): RectVentana {
  const { margen, ancho, alto } = limitesViewport(viewport);
  const minAncho = Math.min(640, ancho);
  const minAlto = Math.min(420, alto);
  let izquierda = rect.x,
    derecha = rect.x + rect.ancho,
    arriba = rect.y,
    abajo = rect.y + rect.alto;
  if (borde.includes('e'))
    derecha = limitar(derecha + dx, izquierda + minAncho, viewport.ancho - margen);
  if (borde.includes('o')) izquierda = limitar(izquierda + dx, margen, derecha - minAncho);
  if (borde.includes('s')) abajo = limitar(abajo + dy, arriba + minAlto, viewport.alto - margen);
  if (borde.includes('n')) arriba = limitar(arriba + dy, margen, abajo - minAlto);
  return { x: izquierda, y: arriba, ancho: derecha - izquierda, alto: abajo - arriba };
}
