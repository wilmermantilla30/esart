/**
 * Modelos de la carga de notas (S2-12, §5g), su revisión por el Inspector (S2-13, §5h) y la
 * habilitación y el Consejo Académico (S2-14, §5i).
 */

export type EstadoEntrega = 'EN_REVISION' | 'APROBADA' | 'DEVUELTA';
/** Planilla ordinaria (S2-12) o notas de habilitación (S2-14). */
export type TipoEntrega = 'ORDINARIA' | 'HABILITACION';

export interface MateriaDelInstructor {
  curso_id: number;
  codigo_curso: string;
  nombre_curso: string;
  tipo_curso: string;
  estado_curso: string;
  fecha_inicio: string;
  fecha_fin: string;
  malla_id: number;
  orden: number;
  codigo_materia: string;
  materia: string;
  nota_minima: number | null;
  alumnos: number;
  /** null = todavía no ha subido notas. */
  estado_entrega: EstadoEntrega | null;
  subido_en: string | null;
  revisado_en: string | null;
  observacion_revision: string | null;
  notas_entregadas: number;
  /** La materia ya tiene notas aprobadas (siguen vigentes mientras se corrige). */
  tiene_notas_oficiales: boolean;
  /** S2-14: alumnos con nota ordinaria oficial bajo la mínima (deben habilitar). */
  alumnos_a_habilitar: number;
  /** Estado de la entrega de habilitación (null = todavía no se registra). */
  estado_habilitacion: EstadoEntrega | null;
  observacion_habilitacion: string | null;
  /** S2-16: fase de campaña por ítems (la registra el comandante del curso). */
  por_items: boolean;
  /** Falso si el curso está cancelado o el Inspector ya aprobó la entrega. */
  puede_subir: boolean;
}

export interface MisMaterias {
  /** Falso si el usuario no corresponde a un instructor activo. */
  es_instructor: boolean;
  materias: MateriaDelInstructor[];
}

export interface NotaAlumno {
  cedula: string;
  grado: string | null;
  apellidos: string;
  nombres: string;
  nota: number;
}

export interface EntregaDeMateria {
  curso_id: number;
  codigo_curso: string;
  materia: string;
  nota_minima: number | null;
  entrega: {
    estado: EstadoEntrega;
    nombre_archivo: string;
    subido_en: string;
    subido_por: string | null;
    revisado_en: string | null;
    observacion_revision: string | null;
    notas: NotaAlumno[];
  } | null;
}

/** Error de una fila de la planilla (fila null = falta un alumno). */
export interface ErrorPlanilla {
  fila: number | null;
  mensaje: string;
}

// --- Revisión por el Inspector de Estudios (S2-13) ---------------------------------------

/** Filtro de la bandeja: un estado o todas. */
export type FiltroBandeja = EstadoEntrega | 'TODAS';

/** Una entrega en la bandeja del Inspector, con el resumen de sus notas. */
export interface EntregaEnBandeja {
  id: number;
  tipo: TipoEntrega;
  estado: EstadoEntrega;
  nombre_archivo: string;
  /** Versión de la entrega: aprobar y devolver la envían (el instructor pudo subir otra). */
  subido_en: string;
  subido_por: string | null;
  revisado_en: string | null;
  revisado_por: string | null;
  observacion_revision: string | null;
  curso_id: number;
  codigo_curso: string;
  nombre_curso: string;
  estado_curso: string;
  tipo_curso: string;
  malla_id: number;
  orden: number;
  codigo_materia: string;
  materia: string;
  nota_minima: number | null;
  instructor: string;
  alumnos: number;
  promedio: number | null;
  por_debajo_de_la_minima: number;
  tiene_notas_oficiales: boolean;
}

export interface NotaEnRevision extends NotaAlumno {
  /** Nota aprobada antes del mismo tipo: la ordinaria oficial o la habilitación anterior. */
  nota_oficial: number | null;
  /** Nota ordinaria oficial (en una habilitación, la que perdió la materia). */
  nota_ordinaria: number | null;
}

export interface DetalleEntrega extends EntregaEnBandeja {
  notas: NotaEnRevision[];
}

// --- Habilitación (S2-14) ------------------------------------------------------------------

export interface AlumnoAHabilitar {
  cedula: string;
  grado: string | null;
  apellidos: string;
  nombres: string;
  /** Nota ordinaria oficial con la que perdió la materia. */
  nota_ordinaria: number;
  /** Nota de habilitación ya registrada (null si todavía no). */
  nota_habilitacion: number | null;
}

export interface FormularioHabilitacion {
  curso_id: number;
  codigo_curso: string;
  materia: string;
  nota_minima: number | null;
  alumnos: AlumnoAHabilitar[];
  estado: EstadoEntrega | null;
  subido_en: string | null;
  revisado_en: string | null;
  observacion_revision: string | null;
}

// --- Consejo Académico (S2-14) -------------------------------------------------------------

export type DecisionConsejo = 'APRUEBA_MATERIA' | 'REPITE_CURSO' | 'PIERDE_CURSO' | 'OTRA';
export type FiltroConsejo = 'PENDIENTES' | 'DECIDIDOS' | 'TODOS';

/** Alumno que perdió la habilitación de una materia y, si ya la hay, la decisión del Consejo. */
export interface CasoConsejo {
  id: number;
  curso_id: number;
  codigo_curso: string;
  nombre_curso: string;
  estado_curso: string;
  tipo_curso: string;
  malla_id: number;
  codigo_materia: string;
  materia: string;
  nota_minima: number | null;
  cedula: string;
  grado: string | null;
  apellidos: string;
  nombres: string;
  nota_ordinaria: number;
  nota_habilitacion: number;
  habilitacion_aprobada_en: string;
  decision: DecisionConsejo | null;
  numero_acta: string | null;
  fecha_acta: string | null;
  observacion: string | null;
  registrado_en: string | null;
  registrado_por: string | null;
}

export interface SolicitudDecisionConsejo {
  decision: DecisionConsejo;
  numero_acta: string;
  fecha_acta: string;
  observacion: string | null;
}
