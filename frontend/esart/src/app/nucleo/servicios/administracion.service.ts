import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  CambioPermisoUsuario,
  FiltrosAuditoria,
  PaginaAuditoria,
  PermisoDeComponente,
  RespuestaPermisosRol,
  RespuestaPermisosUsuario,
  ResumenRol,
  UsuarioMalla,
} from '../modelos/administracion';
import { ClienteApiService } from './cliente-api.service';

/**
 * Administración: malla de permisos y consulta de auditoría. Las reglas de protección
 * (rol ADMINISTRADOR fijo, no quitarse la malla, siempre un administrador) las aplica el backend.
 */
@Injectable({ providedIn: 'root' })
export class AdministracionService {
  private readonly clienteApi = inject(ClienteApiService);

  listarRoles(): Observable<ResumenRol[]> {
    return this.clienteApi.obtener<ResumenRol[]>('/administracion/permisos/roles');
  }

  permisosDeRol(codigoRol: string): Observable<RespuestaPermisosRol> {
    return this.clienteApi.obtener<RespuestaPermisosRol>(
      `/administracion/permisos/roles/${encodeURIComponent(codigoRol)}`,
    );
  }

  guardarPermisosDeRol(codigoRol: string, permisos: PermisoDeComponente[]): Observable<RespuestaPermisosRol> {
    return this.clienteApi.reemplazar<RespuestaPermisosRol>(
      `/administracion/permisos/roles/${encodeURIComponent(codigoRol)}`,
      { permisos },
    );
  }

  listarUsuarios(texto: string): Observable<UsuarioMalla[]> {
    return this.clienteApi.obtener<UsuarioMalla[]>('/administracion/permisos/usuarios', {}, { texto: texto.trim() });
  }

  permisosDeUsuario(usuarioId: number): Observable<RespuestaPermisosUsuario> {
    return this.clienteApi.obtener<RespuestaPermisosUsuario>(`/administracion/permisos/usuarios/${usuarioId}`);
  }

  guardarPermisosDeUsuario(usuarioId: number, cambios: CambioPermisoUsuario[]): Observable<RespuestaPermisosUsuario> {
    return this.clienteApi.reemplazar<RespuestaPermisosUsuario>(`/administracion/permisos/usuarios/${usuarioId}`, {
      cambios,
    });
  }

  consultarAuditoria(filtros: FiltrosAuditoria): Observable<PaginaAuditoria> {
    return this.clienteApi.obtener<PaginaAuditoria>('/administracion/auditoria', {}, { ...filtros });
  }
}
