/** Modelos de la carga de notas del instructor (S2-12, contrato de API §5g). */

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
