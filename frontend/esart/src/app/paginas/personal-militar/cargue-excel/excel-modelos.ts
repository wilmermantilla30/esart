export interface CampoExcel {
  nombre: string;
  alias: string[];
  tipo: string;
  max?: number;
  requerido: boolean;
}
// Fuente: PersonalMilitar, backend/aplicacion/modelos/persistencia.py.
// Las claves y fechas generadas por PostgreSQL no son campos de entrada.
export const CAMPOS: CampoExcel[] = [
  {
    nombre: 'documento_identidad',
    alias: ['documento', 'numero_documento', 'cedula'],
    tipo: 'Texto',
    max: 50,
    requerido: true,
  },
  { nombre: 'nombres', alias: ['nombre'], tipo: 'Texto', max: 150, requerido: true },
  { nombre: 'apellidos', alias: ['apellido'], tipo: 'Texto', max: 150, requerido: true },
  { nombre: 'grado', alias: [], tipo: 'Texto', max: 20, requerido: true },
  { nombre: 'genero', alias: ['sexo'], tipo: 'Texto', max: 1, requerido: true },
  { nombre: 'categoria', alias: [], tipo: 'Texto', max: 30, requerido: true },
  {
    nombre: 'unidad_actual_id',
    alias: ['unidad', 'unidad_id', 'unidad_actual', 'nombre_unidad', 'sigla_unidad'],
    tipo: 'Nombre o sigla oficial',
    requerido: false,
  },
  {
    nombre: 'especialidad_actual',
    alias: ['especialidad'],
    tipo: 'Texto',
    max: 100,
    requerido: false,
  },
  { nombre: 'activo', alias: [], tipo: 'Booleano', requerido: false },
];
export interface Incidencia {
  fila: number;
  columna: string;
  indice: number;
  valor: string;
  motivo: string;
  nivel: 'Error' | 'Advertencia';
}
export interface ColumnaExcel {
  nombre: string;
  campo: string | null;
  tipo: string;
  llenos: number;
  vacios: number;
  porcentaje: number;
  errores: number;
  advertencias: number;
}
export interface FilaExcel {
  numero: number;
  valores: string[];
}
export interface AnalisisExcel {
  columnas: ColumnaExcel[];
  filas: FilaExcel[];
  incidencias: Incidencia[];
  validado: boolean;
}
export interface HojaExcel {
  nombre: string;
  filas: number;
  columnas: number;
}
export interface ResultadoImportacion {
  importacion_id: string;
  estado: string;
  filas_totales: number;
  filas_validas: number;
  filas_rechazadas: number;
  curso_id?: number;
  curso_codigo?: string;
  registros_nuevos?: number;
  grados_actualizados?: number;
}
export const ESTADOS_CURSO = [
  { valor: 'EN_CURSO', texto: 'En curso' },
  { valor: 'CULMINADO', texto: 'Culminado' },
  { valor: 'CANCELADO', texto: 'Cancelado' },
  { valor: 'APLAZADO', texto: 'Aplazado' },
] as const;
export type EstadoCurso = (typeof ESTADOS_CURSO)[number]['valor'];
export interface OpcionCatalogo {
  id: number;
  nombre: string;
  codigo?: string | null;
}
export interface DatosFormularioCurso {
  tipos_curso: OpcionCatalogo[];
  instructores: OpcionCatalogo[];
  siguiente_codigo: string;
}
/** Curso que se crea con la importación; se envía junto al archivo (multipart). */
export interface DatosCursoImportacion {
  tipo_curso_id: number;
  nombre_curso: string;
  comandante_id: number;
  fecha_inicio: string;
  fecha_fin: string;
  estado_curso: EstadoCurso;
  observacion_curso: string;
}
export function normalizar(valor: string): string {
  return valor
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s+/g, '_');
}
