import { Injectable, inject } from '@angular/core';
import { ClienteApiService } from './cliente-api.service';
import { SesionService } from './sesion.service';

export type ModoTotp = 'CONFIGURAR' | 'LOGIN' | 'DESBLOQUEO' | 'AUTORIZAR_ACCION';
export interface EstadoTotp {
  estado?: 'NO_CONFIGURADO' | 'PENDIENTE' | 'ACTIVO' | 'REVOCADO' | 'BLOQUEADO';
  configurado: boolean;
  activo: boolean;
  fecha_activacion: string | null;
}
export interface OperacionTotp {
  codigo_politica: string;
  recurso_id: string;
  datos: Record<string, unknown>;
}
export interface DesafioTotp {
  desafio_id: string;
  expira_en: string;
}

@Injectable({ providedIn: 'root' })
export class TotpService {
  private readonly api = inject(ClienteApiService);
  private readonly sesion = inject(SesionService);
  estado() {
    return this.api.obtener<EstadoTotp>('/auth/totp/estado');
  }
  configurar(contrasena: string) {
    return this.api.enviar<{ uri: string; expira_en: string }>('/auth/totp/configurar', {
      contrasena,
    });
  }
  confirmar(codigo: string) {
    return this.api.enviar<EstadoTotp & { codigos_recuperacion?: string[] }>(
      '/auth/totp/confirmar',
      { codigo },
    );
  }
  configurarLogin(desafioId: string) {
    return this.api.enviar<{ uri: string; expira_en: string }>('/auth/totp/login/configurar', {
      desafio_id: desafioId,
    });
  }
  confirmarVinculacionLogin(desafioId: string, codigo: string) {
    return this.sesion.confirmarVinculacionLogin(desafioId, codigo);
  }
  desactivar(contrasena: string, codigo: string) {
    return this.api.enviar<EstadoTotp>('/auth/totp/desactivar', { contrasena, codigo });
  }
  confirmarLogin(desafioId: string, codigo: string, recuperacion = false) {
    return this.sesion.confirmarLoginTotp(desafioId, codigo, recuperacion);
  }
  renovarRecuperacion(contrasena: string, codigo: string) {
    return this.api.enviar<{ codigos_recuperacion: string[] }>('/auth/totp/recuperacion/renovar', {
      contrasena,
      codigo,
    });
  }
  revocarConRecuperacion(contrasena: string, codigo: string) {
    return this.api.enviar<EstadoTotp>('/auth/totp/recuperacion/revocar', { contrasena, codigo });
  }
  olvidarSesion() {
    this.sesion.olvidarSesion();
  }
  solicitarDesbloqueo(nombreUsuario: string) {
    return this.api.enviar<DesafioTotp>('/auth/desbloqueo/solicitar', {
      nombre_usuario: nombreUsuario,
    });
  }
  confirmarDesbloqueo(desafioId: string, codigo: string) {
    return this.api.enviar<{ procesado: boolean }>('/auth/desbloqueo/confirmar', {
      desafio_id: desafioId,
      codigo,
    });
  }
  crearDesafio(operacion: OperacionTotp) {
    return this.api.enviar<DesafioTotp>('/seguridad/desafios', operacion);
  }
  verificarAccion(desafioId: string, operacion: OperacionTotp, codigo: string) {
    return this.api.enviar<{ autorizacion_id: string; expira_en: string }>(
      `/seguridad/desafios/${encodeURIComponent(desafioId)}/verificar`,
      { ...operacion, codigo },
    );
  }
  ejecutarAutorizada(autorizacionId: string, operacion: OperacionTotp) {
    return this.api.enviar<unknown>(
      `/seguridad/autorizaciones/${encodeURIComponent(autorizacionId)}/ejecutar`,
      operacion,
    );
  }
}
