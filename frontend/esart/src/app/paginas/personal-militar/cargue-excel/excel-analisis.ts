import { utils, WorkSheet } from 'xlsx';
import { AnalisisExcel, CAMPOS, Incidencia, normalizar } from './excel-modelos';
import {
  indiceUnidades,
  normalizarGenero,
  normalizarDocumento,
  resolverUnidad,
  UnidadExcel,
} from './excel-normalizacion';

export function analizarHoja(
  hoja: WorkSheet,
  validar = false,
  unidades: UnidadExcel[] | null = null,
): AnalisisExcel {
  const rango = utils.decode_range(hoja['!ref'] || 'A1');
  if (rango.e.r >= 100000 || rango.e.c >= 200)
    throw new Error('La hoja supera el límite de 100.000 filas o 200 columnas. Divida el archivo.');
  const matriz = utils.sheet_to_json<unknown[]>(hoja, {
    header: 1,
    range: { s: { r: 0, c: 0 }, e: rango.e },
    defval: '',
    raw: false,
    blankrows: true,
  });
  const texto = (v: unknown) => String(v ?? '').trim();
  if (!matriz.some((fila) => fila.some((v) => texto(v))))
    throw new Error('La hoja seleccionada está vacía.');
  // La fila 1 siempre es el encabezado, igual que en el backend.
  const cabecera = 0;
  const ancho = matriz.reduce((max, fila) => Math.max(max, fila.length), 0);
  const encabezados = Array.from({ length: ancho }, (_, i) => texto(matriz[cabecera][i]));
  const filas = matriz
    .slice(cabecera + 1)
    .map((fila, i) => ({
      numero: cabecera + i + 2,
      valores: Array.from({ length: ancho }, (_, j) => texto(fila[j])),
    }))
    .filter((f) => f.valores.some(Boolean));
  const incidencias: Incidencia[] = [];
  const columnas = encabezados.map((nombre, indice) => {
    const campo = CAMPOS.find((c) => [c.nombre, ...c.alias].includes(normalizar(nombre)));
    const llenos = filas.filter((f) => f.valores[indice] !== '').length;
    return {
      nombre: nombre || `Columna ${utils.encode_col(indice)} sin encabezado`,
      campo: campo?.nombre ?? null,
      tipo: campo?.tipo ?? 'Sin mapeo',
      llenos,
      vacios: filas.length - llenos,
      porcentaje: filas.length ? Math.round((llenos / filas.length) * 100) : 0,
      errores: 0,
      advertencias: 0,
    };
  });
  const agregar = (
    fila: number,
    indice: number,
    valor: string,
    motivo: string,
    nivel: 'Error' | 'Advertencia' = 'Error',
    columna?: string,
  ) => {
    incidencias.push({
      fila,
      indice,
      columna: columna ?? columnas[indice]?.nombre ?? 'Hoja',
      valor,
      motivo,
      nivel,
    });
    if (columnas[indice]) columnas[indice][nivel === 'Error' ? 'errores' : 'advertencias']++;
  };
  if (validar) {
    if (!filas.length) agregar(cabecera + 1, -1, '', 'La hoja no contiene registros.');
    for (const campo of CAMPOS.filter((c) => c.requerido)) {
      if (!columnas.some((c) => c.campo === campo.nombre))
        agregar(cabecera + 1, -1, '', 'Falta una columna obligatoria.', 'Error', campo.nombre);
    }
    const documentos = new Map<string, number>();
    const duplicados = new Set<number>();
    const indiceCatalogo = indiceUnidades(unidades ?? []);
    columnas.forEach((col, indice) => {
      if (!col.campo)
        agregar(
          cabecera + 1,
          indice,
          encabezados[indice],
          'Columna no reconocida: no se enviará al servidor.',
          'Advertencia',
        );
      if (col.campo && columnas.findIndex((c) => c.campo === col.campo) !== indice)
        agregar(
          cabecera + 1,
          indice,
          col.nombre,
          'Más de una columna corresponde al mismo atributo.',
        );
      const campo = CAMPOS.find((c) => c.nombre === col.campo);
      if (!campo) return;
      for (const fila of filas) {
        let valor = fila.valores[indice];
        if (!valor) {
          if (campo.requerido)
            agregar(fila.numero, indice, valor, 'Dato obligatorio sin diligenciar.');
          continue;
        }
        if (campo.nombre === 'documento_identidad') {
          try {
            valor = normalizarDocumento(valor);
          } catch (error) {
            agregar(fila.numero, indice, valor, (error as Error).message);
            continue;
          }
        }
        if (campo.nombre === 'genero') {
          try {
            valor = normalizarGenero(valor);
          } catch (error) {
            agregar(fila.numero, indice, valor, (error as Error).message);
            continue;
          }
        }
        if (campo.max && valor.length > campo.max)
          agregar(fila.numero, indice, valor, `Máximo ${campo.max} caracteres.`);
        if (campo.nombre === 'documento_identidad') {
          if (documentos.has(valor)) {
            agregar(
              fila.numero,
              indice,
              valor,
              `Documento duplicado con la fila ${documentos.get(valor)}.`,
            );
            const primera = documentos.get(valor)!;
            if (!duplicados.has(primera)) {
              agregar(primera, indice, valor, `Documento duplicado con la fila ${fila.numero}.`);
              duplicados.add(primera);
            }
          } else documentos.set(valor, fila.numero);
        }
        if (
          campo.nombre === 'activo' &&
          !['true', 'false', '1', '0', 'si', 'no', 'verdadero', 'falso'].includes(normalizar(valor))
        )
          agregar(fila.numero, indice, valor, 'Utilice sí/no, true/false o 1/0.');
        if (campo.nombre === 'unidad_actual_id') {
          try {
            resolverUnidad(
              valor,
              indiceCatalogo,
              unidades,
              normalizar(encabezados[indice]) === 'unidad_actual_id' ||
                normalizar(encabezados[indice]) === 'unidad_id',
            );
          } catch (error) {
            agregar(fila.numero, indice, valor, (error as Error).message);
          }
        }
      }
    });
    // Una fórmula sin resultado almacenado no debe convertirse en un dato vacío válido.
    for (const fila of filas)
      columnas.forEach((_, indice) => {
        const celda = hoja[utils.encode_cell({ r: fila.numero - 1, c: indice })];
        if (celda?.t === 'e')
          agregar(
            fila.numero,
            indice,
            fila.valores[indice],
            'La celda contiene un error de Excel.',
          );
        if (celda?.f)
          agregar(
            fila.numero,
            indice,
            fila.valores[indice],
            'Reemplace la fórmula por su valor antes de importar.',
          );
      });
  }
  return { columnas, filas, incidencias, validado: validar };
}
