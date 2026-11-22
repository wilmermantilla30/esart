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
