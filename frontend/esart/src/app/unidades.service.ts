import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface Unidad {
  id: string;
  codigo: string;
  nombre: string;
  tipo_unidad_id: string | null;
  tipo_codigo: string | null;
  tipo_nombre: string | null;
  unidad_padre_id: string | null;
  padre_codigo: string | null;
  activo: boolean;
  clasificacion_pendiente: boolean;
}

@Injectable({ providedIn: 'root' })
export class UnidadesService {
  private readonly http = inject(HttpClient);
  listar() {
    return this.http.get<Unidad[]>('/api/catalogos/unidades');
  }
}
