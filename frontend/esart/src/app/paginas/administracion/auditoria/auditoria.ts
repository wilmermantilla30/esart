import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { EventoAuditoria, PaginaAuditoria } from '../../../nucleo/modelos/administracion';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import { AdministracionService } from '../../../nucleo/servicios/administracion.service';

/** Nombre legible de cada acción auditada (las mismas del CHECK de la base, p0007). */
export const NOMBRES_ACCION: Readonly<Record<string, string>> = {
  LOGIN_EXITOSO: 'Inicio de sesión',
  LOGIN_FALLIDO: 'Inicio de sesión fallido',
  USUARIO_BLOQUEADO: 'Cuenta bloqueada',
  USUARIO_DESBLOQUEADO: 'Cuenta desbloqueada',
  CIERRE_SESION: 'Cierre de sesión',
  CONSULTA_ARTILLERO: 'Verificación de artillero',
  CONSULTA_HABILITADOS: 'Consulta de habilitados',
  CONSULTA_NO_HABILITADOS: 'Consulta de no habilitados',
  CONSULTA_RESUMEN: 'Consulta del panel',
  ACCESO_DENEGADO: 'Acceso denegado',
  PERMISOS_ROL_MODIFICADOS: 'Permisos de rol modificados',
  PERMISOS_USUARIO_MODIFICADOS: 'Permisos de usuario modificados',
  USUARIO_CREADO: 'Usuario creado',
  IMPORTACION_EXCEL: 'Importación de Excel',
};

const TAMANO_PAGINA = 50;

/**
 * Auditoría (componente AUDITORIA): registro inmutable de quién hizo qué, cuándo y desde dónde.
 * Solo consulta: la tabla no admite cambios ni borrados.
 */
@Component({
  selector: 'esart-auditoria',
  imports: [FormsModule],
  templateUrl: './auditoria.html',
})
export class Auditoria {
  private readonly administracion = inject(AdministracionService);

  protected readonly acciones = Object.entries(NOMBRES_ACCION).map(([valor, texto]) => ({ valor, texto }));

  protected accion = '';
  protected usuario = '';
  protected documento = '';
  protected desde = '';
  protected hasta = '';
  protected readonly pagina = signal(1);

  protected readonly cargando = signal(false);
  protected readonly datos = signal<PaginaAuditoria | null>(null);
  protected readonly error = signal<ErrorApi | null>(null);

  constructor() {
    this.cargar();
  }

  protected buscar(): void {
    this.pagina.set(1);
    this.cargar();
  }

  protected limpiar(): void {
    this.accion = this.usuario = this.documento = this.desde = this.hasta = '';
    this.buscar();
  }

  protected irAPagina(pagina: number): void {
    this.pagina.set(pagina);
    this.cargar();
  }

  protected nombreAccion(accion: string): string {
    return NOMBRES_ACCION[accion] ?? accion;
  }

  protected fechaHora(valor: string): string {
    return new Date(valor).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'medium' });
  }

  /** Detalle compacto para la tabla (el backend ya garantiza que no lleva credenciales). */
  protected detalle(evento: EventoAuditoria): string {
    return evento.detalle ? JSON.stringify(evento.detalle) : '';
  }

  private cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.administracion
      .consultarAuditoria({
        accion: this.accion,
        usuario: this.usuario,
        documento: this.documento,
        desde: this.desde,
        hasta: this.hasta,
        pagina: this.pagina(),
        tamano_pagina: TAMANO_PAGINA,
      })
      .subscribe({
        next: (respuesta) => {
          this.datos.set(respuesta);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }
}
