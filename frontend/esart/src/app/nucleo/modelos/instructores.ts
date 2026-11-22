/** Modelos del panel de instructores (docs/contrato_api.md §5d). */

export type TipoInstructor = 'MILITAR' | 'CIVIL';
export type EstadoInstructores = 'ACTIVOS' | 'INACTIVOS' | 'TODOS';

export interface Especialidad {
  codigo: string;
  nombre: string;
}

export interface Instructor {
  id: number;
  tipo: TipoInstructor;
  /** Cédula o documento (enmascarado sin el permiso VER_DOCUMENTO_COMPLETO). */
  documento: string;
  grado: string | null;
  nombres: string | null;
  apellidos: string | null;
  nombre_completo: string;
  unidad: string | null;
  profesion: string | null;
  fecha_ingreso_escuela: string;
  activo: boolean;
  tiene_foto: boolean;
  /** Cambia con cada edición: se agrega a la URL de la foto para no mostrar una vieja. */
  version: string;
  nombre_usuario: string | null;
  especialidades: Especialidad[];
}

export interface MilitarParaInstructor {
  documento: string;
  nombre_completo: string;
  unidad: string | null;
  activo: boolean;
  ya_es_instructor: boolean;
}

/** Lo que se puede editar (los nombres solo aplican a civiles). */
export interface DatosInstructor {
  fecha_ingreso_escuela: string;
  especialidades: string[];
  profesion: string | null;
  nombres: string | null;
  apellidos: string | null;
}

export interface NuevoInstructor extends DatosInstructor {
  tipo: TipoInstructor;
  documento: string;
}

/** Curso del instructor (estados del cargue por Excel). */
export interface CursoDelInstructor {
  id: number;
  codigo: string;
  nombre: string;
  tipo_curso: string;
  fecha_inicio: string;
  fecha_fin: string;
  estado: 'EN_CURSO' | 'CULMINADO' | 'CANCELADO' | 'APLAZADO' | string;
  alumnos: number;
}

export interface CursosDelInstructor {
  /** Cursos donde es comandante (lo asigna el cargue por Excel). */
  comandante: CursoDelInstructor[];
  /** Cursos donde participa con otro rol. */
  participa: (CursoDelInstructor & { rol_en_curso: string })[];
  /** S2-02: materias que dicta como titular en cada curso. */
  materias?: MateriaDelInstructor[];
}

export interface MateriaDelInstructor {
  curso_id: number;
  curso: string;
  nombre_curso: string;
  estado: string;
  tipo_curso: string;
  materia: string;
  fecha_inicio: string;
}
