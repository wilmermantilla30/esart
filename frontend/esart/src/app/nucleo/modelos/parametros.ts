/** Modelos del panel de Parámetros (docs/contrato_api.md §6). */

/** Los cuatro valores de la regla APTO / NO APTO. */
export interface ValoresRegla {
  cursos_habilitantes: string[];
  meses_vigencia_reentrenamiento: number;
  dias_alerta_vencimiento: number;
  exige_apto_para_disparar: boolean;
}

export interface CursoDisponible {
  codigo: string;
  nombre: string;
}

export interface ResumenRegla {
  total: number;
  aptos: number;
  no_aptos: number;
  reentrenamiento_por_vencer: number;
}

export interface ReglaHabilitacion {
  valores: ValoresRegla;
  /** Versión de la regla: se devuelve al guardar para no pisar el cambio de otro administrador. */
  actualizado_en: string | null;
  actualizado_por: string | null;
  cursos_disponibles: CursoDisponible[];
  resumen: ResumenRegla;
}

export interface SimulacionRegla {
  actual: ResumenRegla;
  propuesto: ResumenRegla;
  pasan_a_no_apto: number;
  pasan_a_apto: number;
}

/** Nota mínima de aprobación (S2-10). Cada curso guarda la vigente al crearse. */
export interface NotaMinima {
  /** Escala 0 a 5 con 2 decimales. */
  valor: number;
  /** Versión: se devuelve al guardar para no pisar el cambio de otro administrador. */
  actualizado_en: string;
  actualizado_por: string | null;
  /** Cursos en curso que ya tienen su nota guardada (no cambian al guardar otra). */
  cursos_en_curso: number;
}

// --- Mallas curriculares (S2-09) ---

export type TipoDeCurso = 'EDUCACION_MILITAR' | 'ESPECIALIZACION' | 'EDUCACION_SUPERIOR';
export type ModalidadCurso = 'PRESENCIAL' | 'VIRTUAL' | 'MIXTA';

/** Tipo de curso en el listado, con su versión vigente (null si todavía no tiene malla). */
export interface TipoCursoMalla {
  codigo: string;
  nombre: string;
  tipo: string | null;
  modalidad: string;
  duracion_semanas: number;
  activo: boolean;
  version: number | null;
  anio: number | null;
  materias: number;
  evaluables: number;
}

export interface VersionMallaResumen {
  numero: number;
  anio: number;
  estado: 'VIGENTE' | 'HISTORICA';
  observacion: string | null;
  creado_en: string;
  creado_por: string | null;
  materias: number;
  /** Cursos creados con esta versión: la conservan aunque haya versiones nuevas. */
  cursos: number;
}

export interface FilaMalla {
  orden: number;
  codigo_materia: string;
  materia: string;
  area: string | null;
  modulo: string | null;
  evaluable: boolean;
}

export interface DetalleMalla {
  tipo_curso: {
    codigo: string;
    nombre: string;
    tipo: string | null;
    modalidad: string;
    duracion_semanas: number;
    activo: boolean;
  };
  version: VersionMallaResumen | null;
  filas: FilaMalla[];
  versiones: VersionMallaResumen[];
}

export interface MateriaCatalogo {
  codigo: string;
  nombre: string;
}

/** Fila que se envía al guardar (el orden lo da la posición en la tabla). */
export interface FilaMallaEditada {
  orden: number;
  materia: string;
  evaluable: boolean;
  area: string | null;
  modulo: string | null;
}

export interface MallaEditada {
  anio: number;
  filas: FilaMallaEditada[];
  observacion: string | null;
  /** Número de la versión vigente que se editó (null si el tipo no tenía malla). */
  version: number | null;
}

export interface NuevoTipoCurso {
  codigo: string;
  nombre: string;
  tipo: TipoDeCurso;
  modalidad: ModalidadCurso;
  duracion_semanas: number;
}

export type FormatoPlantilla = 'XLSX' | 'XLS' | 'PDF' | 'DOCX';

export interface Plantilla {
  id: number;
  nombre_oficial: string;
  nombre_archivo: string;
  formato: FormatoPlantilla;
  version: string;
  descripcion: string;
  tamano_bytes: number;
  sha256: string;
  subido_en: string;
  subido_por: string | null;
}

export interface NuevaPlantilla {
  archivo: File;
  nombre_oficial: string;
  version: string;
  descripcion: string;
}

export interface PoliticaSeguridad {
  codigo: string;
  nombre: string;
  modulo: string;
  requiere_totp: boolean;
  activa: boolean;
}

export interface ParametrosSeguridad {
  totp_habilitado: boolean;
  usuarios_activos: number;
  usuarios_con_autenticador: number;
  minutos_inactividad_sesion: number;
  intento_captcha: number;
  intento_bloqueo: number;
  horas_bloqueo: number;
  politicas: PoliticaSeguridad[];
}

// --- Fase de campaña del CAPINTE: ítems y puntajes (S2-16) ---------------------------------

export interface ItemCampana {
  id: number;
  orden: number;
  nombre: string;
  puntaje: number;
}

export interface ConfiguracionCampana {
  codigo_materia: string;
  materia: string;
  items: ItemCampana[];
  /** Suma de los puntajes (debe dar 5,00 al redondear). */
  total: number;
  /** Versión para la concurrencia (null si no hay ítems). */
  actualizado_en: string | null;
  actualizado_por: string | null;
}

/** Ítem en el formulario (id null = nuevo); el puntaje como texto para no perder decimales. */
export interface ItemCampanaPropuesto {
  id: number | null;
  nombre: string;
  puntaje: string;
}
