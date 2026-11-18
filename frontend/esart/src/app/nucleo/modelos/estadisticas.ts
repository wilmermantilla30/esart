/** Estadísticas del panel principal (docs/contrato_api.md §3b). */

export type Semestre = 1 | 2;

export interface IndicadoresPanel {
  cursos_periodo: number;
  alumnos_periodo: number;
  /** Alumnos de cursos CULMINADOS del período. */
  egresados: number;
  cursos_culminados: number;
  /** Estado de HOY (no depende del filtro). */
  cursos_en_curso: number;
  alumnos_en_curso: number;
}

export interface HabilitacionPanel {
  total: number;
  aptos: number;
  no_aptos: number;
  reentrenamiento_por_vencer: number;
}

export interface CursosDelAnio {
  anio: number;
  semestre_1: number;
  semestre_2: number;
}

export interface GradoCatalogo {
  sigla: string;
  nombre: string;
  categoria: 'OFICIAL' | 'SUBOFICIAL' | 'SOLDADO_PROFESIONAL' | 'OTRO' | string;
}

export interface CursoEstadistica {
  id: number;
  codigo: string;
  nombre: string;
  tipo_curso: string;
  estado: 'EN_CURSO' | 'CULMINADO' | 'CANCELADO' | 'APLAZADO' | string;
  fecha_inicio: string;
  fecha_fin: string;
  comandante: string;
  alumnos: number;
  /** Alumnos por grado (sigla) al entrar al curso. */
  grados: Record<string, number>;
  genero: { M: number; F: number };
}

export interface CursoEnSeguimiento extends CursoEstadistica {
  dias_totales: number;
  dias_transcurridos: number;
  porcentaje: number;
  dias_restantes: number;
  /** Ya pasó la fecha de fin y sigue "en curso". */
  vencido: boolean;
}

export interface PanelEstadisticas {
  periodo: { anio: number | null; semestre: Semestre | null };
  hoy: string;
  anios_disponibles: number[];
  indicadores: IndicadoresPanel;
  habilitacion: HabilitacionPanel;
  cursos_por_anio: CursosDelAnio[];
  grados: GradoCatalogo[];
  cursos: CursoEstadistica[];
  en_curso: CursoEnSeguimiento[];
}
