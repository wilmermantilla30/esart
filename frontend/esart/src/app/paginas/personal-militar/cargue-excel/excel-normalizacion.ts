export interface UnidadExcel {
  id: string;
  codigo: string | null;
  nombre: string | null;
}

/** Misma regla que habilitacion.normalizar_cedula: 5 a 15 dígitos. */
export function normalizarDocumento(valor: string): string {
  const documento = valor.replace(/[.\s-]/g, '');
  if (!/^[0-9]{5,15}$/.test(documento))
    throw new Error('La cédula debe tener solo números (entre 5 y 15 dígitos).');
  return documento;
}

// Coincidencia exacta: solo se normalizan mayúsculas y espacios, nunca se aproxima.
export function claveUnidad(valor: string): string {
  return valor.trim().replace(/\s+/g, ' ').toLowerCase();
}
export function indiceUnidades(unidades: UnidadExcel[]): Map<string, Set<string>> {
  const indice = new Map<string, Set<string>>();
  for (const unidad of unidades)
    for (const texto of [unidad.nombre, unidad.codigo]) {
      if (!texto) continue;
      const clave = claveUnidad(texto);
      if (!indice.has(clave)) indice.set(clave, new Set());
      indice.get(clave)!.add(String(unidad.id));
    }
  return indice;
}
export function resolverUnidad(
  valor: string,
  indice: Map<string, Set<string>>,
  unidades: UnidadExcel[] | null,
  permitirId = false,
): string {
  if (!unidades)
    throw new Error(
      'No se pudo consultar el catálogo institucional de unidades. Intente validar de nuevo.',
    );
  if (permitirId && /^\d+$/.test(valor) && unidades.some((u) => String(u.id) === valor))
    return valor;
  const ids = indice.get(claveUnidad(valor));
  if (!ids?.size) throw new Error('Unidad no encontrada en el catálogo institucional');
  if (ids.size !== 1)
    throw new Error(
      'Varias unidades coinciden con ese nombre. Indique la sigla oficial única de la unidad en el Excel.',
    );
  return [...ids][0];
}
export function normalizarGenero(valor: string): string {
  const genero = valor.trim().toUpperCase();
  if (genero === 'MASCULINO' || genero === 'M') return 'M';
  if (genero === 'FEMENINO' || genero === 'F') return 'F';
  throw new Error('Género inválido. Utilice MASCULINO, FEMENINO, M o F.');
}
