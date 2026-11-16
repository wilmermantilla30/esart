/** Tipos de /api/administracion (malla de permisos y auditoría). Campos como el backend. */

export interface Operaciones {
  acceder: boolean;
  crear: boolean;
  leer: boolean;
  actualizar: boolean;
  eliminar: boolean;
}

export type ModoPermisoUsuario = 'HEREDAR' | 'CONCEDER' | 'QUITAR';

export interface ComponenteMalla {
  codigo: string;
  nombre: string;
  ruta: string | null;
  codigo_padre: string | null;
  /** Permiso sin menú (por ejemplo, ver la cédula completa). */
  especial: boolean;
}

export interface FilaPermisoRol extends ComponenteMalla {
  permisos: Operaciones;
}

export interface RespuestaPermisosRol {
  rol: string;
  nombre: string;
  editable: boolean;
  filas: FilaPermisoRol[];
}

export interface ResumenRol {
  codigo: string;
  nombre: string;
  editable: boolean;
}

export interface UsuarioMalla {
  id: number;
  usuario: string;
  nombre_completo: string;
  rol: string | null;
  activo: boolean;
}

export interface FilaPermisoUsuario extends ComponenteMalla {
  rol: Operaciones;
  modo: ModoPermisoUsuario;
  excepcion: Operaciones | null;
  efectivo: Operaciones;
}

export interface RespuestaPermisosUsuario {
  usuario: UsuarioMalla;
  editable: boolean;
  filas: FilaPermisoUsuario[];
}

export interface PermisoDeComponente extends Operaciones {
  componente: string;
}

export interface CambioPermisoUsuario {
  componente: string;
  modo: ModoPermisoUsuario;
  crear: boolean;
  leer: boolean;
  actualizar: boolean;
  eliminar: boolean;
}

export interface EventoAuditoria {
  id: number;
  fecha: string;
  usuario_id: number | null;
  nombre_usuario: string | null;
  accion: string;
  numero_documento_consultado: string | null;
  resultado: string | null;
  direccion_ip: string | null;
  detalle: Record<string, unknown> | null;
}

export interface PaginaAuditoria {
  elementos: EventoAuditoria[];
  pagina: number;
  tamano_pagina: number;
  total_elementos: number;
  total_paginas: number;
}

export interface FiltrosAuditoria {
  accion: string;
  usuario: string;
  documento: string;
  desde: string;
  hasta: string;
  pagina: number;
  tamano_pagina: number;
}
