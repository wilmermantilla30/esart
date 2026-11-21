import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  CambioPermisoUsuario,
  FiltrosAuditoria,
  MilitarParaUsuario,
  PaginaAuditoria,
  PermisoDeComponente,
  RespuestaPermisosRol,
  RespuestaPermisosUsuario,
  ResumenRol,
  SolicitudCrearUsuario,
  UsuarioGestion,
  UsuarioMalla,
} from '../modelos/administracion';
import { ClienteApiService } from './cliente-api.service';

/** Acciones sobre un usuario existente (POST /administracion/usuarios/{id}/{accion}). */
export type AccionUsuario = 'activar' | 'desactivar' | 'desbloquear';

/**
 * Administración: malla de permisos, gestión de usuarios y consulta de auditoría. Las reglas de protección
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

  // --- Gestión de usuarios (HU-10) ---

  listarUsuariosGestion(texto: string): Observable<UsuarioGestion[]> {
    return this.clienteApi.obtener<UsuarioGestion[]>('/administracion/usuarios', {}, { texto: texto.trim() });
  }

  /** Busca la cédula en Personal militar: datos del militar y nombre de usuario sugerido. */
  buscarMilitarParaUsuario(cedula: string): Observable<MilitarParaUsuario> {
    return this.clienteApi.obtener<MilitarParaUsuario>(
      `/administracion/usuarios/militar/${encodeURIComponent(cedula.trim())}`,
    );
  }

  crearUsuario(solicitud: SolicitudCrearUsuario): Observable<UsuarioGestion> {
    return this.clienteApi.enviar<UsuarioGestion>('/administracion/usuarios', solicitud);
  }

  aplicarAccionUsuario(usuarioId: number, accion: AccionUsuario): Observable<UsuarioGestion> {
    return this.clienteApi.enviar<UsuarioGestion>(`/administracion/usuarios/${usuarioId}/${accion}`);
  }

  restablecerContrasena(usuarioId: number, contrasenaTemporal: string): Observable<UsuarioGestion> {
    return this.clienteApi.enviar<UsuarioGestion>(`/administracion/usuarios/${usuarioId}/restablecer-contrasena`, {
      contrasena_temporal: contrasenaTemporal,
    });
  }

  restablecerTotp(
    usuarioId: number,
    datos: { contrasena: string; codigo_totp: string; justificacion: string },
  ): Observable<{ restablecido: boolean; estado_totp: string }> {
    return this.clienteApi.enviar<{ restablecido: boolean; estado_totp: string }>(
      `/administracion/usuarios/${usuarioId}/restablecer-totp`,
      datos,
    );
  }

  consultarAuditoria(filtros: FiltrosAuditoria): Observable<PaginaAuditoria> {
    return this.clienteApi.obtener<PaginaAuditoria>('/administracion/auditoria', {}, { ...filtros });
  }
}
