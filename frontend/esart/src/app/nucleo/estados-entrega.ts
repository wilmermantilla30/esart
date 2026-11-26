import { EstadoEntrega } from './modelos/notas';

/**
 * Estado de una entrega de notas en palabras y con su color. Lo usan la carga del instructor
 * (S2-12) y la revisión del Inspector de Estudios (S2-13).
 */
export const ESTADOS_ENTREGA: Record<
  EstadoEntrega | 'SIN_ENTREGA',
  { texto: string; estilo: string }
> = {
  SIN_ENTREGA: { texto: 'Sin notas', estilo: 'bg-gris-claro text-azul-pizarra border-gris-bordes' },
  EN_REVISION: { texto: 'En revisión', estilo: 'bg-warning/10 text-warning border-warning/40' },
  APROBADA: { texto: 'Aprobada', estilo: 'bg-success/10 text-success border-success/30' },
  DEVUELTA: { texto: 'Devuelta', estilo: 'bg-error/10 text-error border-error/30' },
};
