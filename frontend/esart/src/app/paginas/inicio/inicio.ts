import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { EncabezadoInstitucional } from '../../compartido/encabezado-institucional/encabezado-institucional';
import { PieInstitucional } from '../../compartido/pie-institucional/pie-institucional';
import { RUTA_PAGINA_INICIO_SESION } from '../../nucleo/rutas-paginas';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/** Nombre visible de cada código de rol (la base solo admite ADMINISTRADOR y USUARIO). */
const NOMBRES_DE_ROL: Record<string, string> = {
  ADMINISTRADOR: 'Administrador',
  USUARIO: 'Usuario',
};

/**
 * Página de inicio PROVISIONAL tras el login: confirma la sesión y permite cerrarla.
 * Se reemplazará por el panel de verificación cuando lleguen los diseños.
 */
@Component({
  selector: 'esart-inicio',
  imports: [EncabezadoInstitucional, PieInstitucional],
  templateUrl: './inicio.html',
})
export class Inicio {
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);

  protected readonly usuario = this.sesion.usuario;
  protected readonly cerrandoSesion = signal(false);

  protected nombreDeRol(codigoRol: string): string {
    return NOMBRES_DE_ROL[codigoRol] ?? codigoRol;
  }

  protected cerrarSesion(): void {
    if (this.cerrandoSesion()) {
      return;
    }
    this.cerrandoSesion.set(true);
    // cerrarSesion nunca falla: aunque no haya red, el estado local se limpia y se sale.
    this.sesion.cerrarSesion().subscribe({
      complete: () => void this.enrutador.navigate(['/', RUTA_PAGINA_INICIO_SESION]),
    });
  }
}
