/** Estados del curso (los del cargue por Excel) en palabras y con su color. */
export const ESTADOS_CURSO: Record<string, { texto: string; estilo: string }> = {
  EN_CURSO: {
    texto: 'En curso',
    estilo: 'bg-azul-hielo text-azul-institucional border-azul-claro',
  },
  CULMINADO: { texto: 'Culminado', estilo: 'bg-success/10 text-success border-success/30' },
  CANCELADO: { texto: 'Cancelado', estilo: 'bg-error/10 text-error border-error/30' },
  APLAZADO: { texto: 'Aplazado', estilo: 'bg-warning/10 text-warning border-warning/40' },
};

export function textoEstadoCurso(estado: string): string {
  return ESTADOS_CURSO[estado]?.texto ?? estado;
}

export function estiloEstadoCurso(estado: string): string {
  return ESTADOS_CURSO[estado]?.estilo ?? 'bg-gris-claro text-azul-pizarra border-gris-bordes';
}
