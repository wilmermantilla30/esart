/** Modelos del módulo Cursos (S2-02, contrato de API §5f). */

export type EstadoCurso = 'EN_CURSO' | 'APLAZADO' | 'CULMINADO' | 'CANCELADO';

export interface CursoListado {
  id: number;
  codigo: string;
  nombre: string;
  tipo_curso: string;
  fecha_inicio: string;
  fecha_fin: string;
  estado: EstadoCurso;
  alumnos: number;
  comandante: string | null;
  /** Versión de malla con que se creó (null = curso anterior a la malla). */
  version_malla: number | null;
  materias_con_nota: number;
  /** Materias con nota que ya tienen instructor titular. */
  asignadas: number;
}

export interface MateriaDelCurso {
  malla_id: number;
  orden: number;
  codigo_materia: string;
  materia: string;
  area: string | null;
  modulo: string | null;
  evaluable: boolean;
  /** S2-16: fase de campaña por ítems; la registra el comandante (sin instructor). */
  por_items: boolean;
  instructor_id: number | null;
  instructor: string | null;
  tipo_instructor: 'MILITAR' | 'CIVIL' | null;
  asignado_en: string | null;
  asignado_por: string | null;
}

export interface DetalleCurso {
  id: number;
  codigo: string;
  nombre: string;
  tipo_curso: string;
  nombre_tipo_curso: string;
  fecha_inicio: string;
  fecha_fin: string;
  estado: EstadoCurso;
  alumnos: number;
  comandante: string | null;
  nota_minima_aprobacion: number | null;
  version_malla: number | null;
  anio_malla: number | null;
  estado_malla: 'VIGENTE' | 'HISTORICA' | null;
  /** Solo EN_CURSO y APLAZADO admiten cambios. */
  editable: boolean;
  /** Versión vigente que se puede asignar a un curso sin malla (null si no aplica). */
  version_vigente_disponible: number | null;
  materias: MateriaDelCurso[];
}

export interface InstructorDisponible {
  id: number;
  tipo: 'MILITAR' | 'CIVIL';
  nombre: string;
}

export interface FiltrosCursos {
  estado: EstadoCurso | '';
  tipo: string;
  texto: string;
}

// --- Nota final, puesto y cierre (S2-15, §5j) -----------------------------------------------

export type ResultadoFinal = 'APROBADO' | 'REPROBADO';

export interface ResultadoAlumno {
  cedula: string;
  grado: string | null;
  apellidos: string;
  nombres: string;
  /** Promedio de las materias evaluables con nota (provisional si faltan). */
  nota_final: number | null;
  materias_evaluadas: number;
  materias_habilitadas: number;
  /** Lo que falta para el resultado definitivo (vacío si está completo). */
  pendientes: string[];
  /** null mientras esté incompleto. */
  resultado: ResultadoFinal | null;
  motivo: string | null;
  /** Solo los aprobados; los empates comparten el puesto. */
  puesto: number | null;
}

export interface ResultadosCurso {
  curso_id: number;
  codigo_curso: string;
  estado_curso: string;
  nota_minima: number | null;
  /** El curso ya se cerró: los resultados están guardados y no cambian. */
  cerrado: boolean;
  cerrado_en: string | null;
  cerrado_por: string | null;
  materias_evaluables: number;
  completo: boolean;
  puede_cerrar: boolean;
  /** Pendientes del curso (entregas de notas sin aprobar). */
  pendientes: string[];
  alumnos: ResultadoAlumno[];
}
