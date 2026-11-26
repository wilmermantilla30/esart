/** Modelos de la carga de notas (S2-12, §5g) y de su revisión por el Inspector (S2-13, §5h). */

export type EstadoEntrega = 'EN_REVISION' | 'APROBADA' | 'DEVUELTA';

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
  /** Nota oficial vigente (null si la materia aún no tiene notas aprobadas). */
  nota_oficial: number | null;
}

export interface DetalleEntrega extends EntregaEnBandeja {
  notas: NotaEnRevision[];
}
