/** Tipos de /api/verificar (contrato de API §3). Campos en snake_case, como el backend. */

export type ResultadoHabilitacion = 'APTO' | 'NO_APTO';
export type EstadoReentrenamiento = 'VIGENTE' | 'POR_VENCER' | 'VENCIDO' | 'SIN_REGISTRO' | 'ANULADO';
export type FiltroEstado = '' | 'APTO' | 'NO_APTO' | 'POR_VENCER';

export interface CriterioVerificacion {
  descripcion: string;
  /** OBLIGATORIO: debe cumplirse. ALTERNATIVO: basta con que se cumpla uno de ellos. */
  tipo: 'OBLIGATORIO' | 'ALTERNATIVO';
  cumple: boolean;
  detalle: string | null;
  motivo: string | null;
}

export interface CursoVerificacion {
  nombre: string;
  codigo: string | null;
  institucion: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  estado: 'APROBADO' | 'EN_CURSO';
  habilitante: boolean;
}

export interface ReentrenamientoVerificacion {
  numero_certificado: string;
  tipo: string;
  calibre: string;
  fecha_expedicion: string;
  fecha_vencimiento: string;
  estado: EstadoReentrenamiento;
}

/** S2-17: materia evaluable de un curso con la nota que cuenta. */
export interface MateriaAcademica {
  orden: number;
  materia: string;
  /** null si todavía no tiene nota aprobada (curso en curso). */
  nota: number | null;
  /** Cómo terminó si pasó por habilitación (null si no la necesitó). */
  estado: 'HABILITADA' | 'APROBADA_POR_CONSEJO' | 'HABILITACION_PERDIDA' | null;
  instructor: string | null;
}

/** S2-17: curso con notas en la plataforma (cerrado o en curso, parcial). */
export interface CursoAcademico {
  codigo: string;
  nombre: string;
  tipo_curso: string;
  fecha_inicio: string;
  fecha_fin: string;
  estado_curso: string;
  cerrado: boolean;
  nota_minima: number | null;
  nota_final: number | null;
  resultado: 'APROBADO' | 'REPROBADO' | null;
  motivo: string | null;
  puesto: number | null;
  aprobados_del_curso: number | null;
  materias_con_nota: number;
  materias: MateriaAcademica[];
}

export interface RespuestaVerificacion {
  artillero: {
    numero_documento: string;
    nombre_completo: string;
    grado: string;
    categoria: string;
    unidad_militar: { sigla: string | null; nombre: string | null } | null;
    estado_servicio: 'ACTIVO' | 'INACTIVO';
  };
  resultado: ResultadoHabilitacion;
  fecha_verificacion: string;
  criterios: CriterioVerificacion[];
  motivos: string[];
  alerta: string | null;
  cursos: CursoVerificacion[];
  /** S2-17: notas por materia, nota final y puesto de los cursos con notas en la plataforma. */
  historial_academico: CursoAcademico[];
  reentrenamientos: ReentrenamientoVerificacion[];
}

export interface ElementoHabilitacion {
  numero_documento: string;
  nombre_completo: string;
  grado: string;
  unidad_militar_sigla: string | null;
  activo: boolean;
  resultado: ResultadoHabilitacion;
  motivos: string[];
  curso_habilitante: string | null;
  reentrenamiento_vence: string | null;
  estado_reentrenamiento: EstadoReentrenamiento;
}

/** Formato único de paginación (contrato §1.3). */
export interface PaginaHabilitacion {
  elementos: ElementoHabilitacion[];
  pagina: number;
  tamano_pagina: number;
  total_elementos: number;
  total_paginas: number;
}

export interface ResumenHabilitacion {
  total: number;
  aptos: number;
  no_aptos: number;
  reentrenamiento_por_vencer: number;
  activos: number;
  unidades: number;
  dias_alerta_vencimiento: number;
}

export interface FiltrosHabilitacion {
  estado: FiltroEstado;
  texto: string;
  pagina: number;
  tamano_pagina: number;
}

/** Documentos PDF que se generan desde la verificación (script maestro del backend). */
export type TipoDocumentoArtillero = 'DIPLOMA' | 'OFICIO_REMISORIO' | 'CERTIFICACION';

export interface OpcionDocumentoArtillero {
  codigo: TipoDocumentoArtillero;
  nombre: string;
}

/** Opciones del selector; deben coincidir con REPORTES de aplicacion/reportes/maestro.py. */
export const DOCUMENTOS_ARTILLERO: readonly OpcionDocumentoArtillero[] = [
  { codigo: 'DIPLOMA', nombre: 'Diploma' },
  { codigo: 'OFICIO_REMISORIO', nombre: 'Oficio remisorio' },
  { codigo: 'CERTIFICACION', nombre: 'Certificación' },
];
