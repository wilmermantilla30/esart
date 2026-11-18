/**
 * Registro manual de personal militar (componente PERSONAL_CARGUE_MANUAL).
 * Contrato: GET /api/personal/opciones-registro y POST /api/personal.
 */

export interface OpcionGrado {
  /** Sigla que se guarda en personal_militar.grado (ej. "MY"). */
  codigo: string;
  nombre: string;
}

export interface OpcionCategoria {
  /** OFICIAL | SUBOFICIAL | SOLDADO_PROFESIONAL */
  codigo: string;
  nombre: string;
  grados: OpcionGrado[];
}

export interface OpcionUnidad {
  id: number;
  codigo: string;
  nombre: string;
}

export interface OpcionesRegistroPersonal {
  categorias: OpcionCategoria[];
  unidades: OpcionUnidad[];
}

export type Genero = 'M' | 'F';

export interface NuevoPersonal {
  documento_identidad: string;
  nombres: string;
  apellidos: string;
  grado: string;
  genero: Genero;
  categoria: string;
  unidad_actual_id: number | null;
  especialidad_actual: string | null;
  activo: boolean;
}

export interface PersonalRegistrado extends NuevoPersonal {
  id: number;
  nombre_completo: string;
  unidad_nombre: string | null;
}
