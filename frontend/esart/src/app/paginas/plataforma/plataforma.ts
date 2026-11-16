import { Component, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { PieInstitucional } from '../../compartido/pie-institucional/pie-institucional';
import { iconoDeComponente } from '../../nucleo/iconos-menu';
import { RUTA_PAGINA_CAMBIAR_CONTRASENA, RUTA_PAGINA_INICIO_SESION } from '../../nucleo/rutas-paginas';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/** Nombre visible de cada código de rol (la base solo admite ADMINISTRADOR y USUARIO). */
const NOMBRES_DE_ROL: Readonly<Record<string, string>> = {
  ADMINISTRADOR: 'Administrador',
  USUARIO: 'Usuario',
};

/**
 * Marco de todas las páginas internas: encabezado con el usuario, sidebar con los módulos
 * que su rol le permite (menú de /api/auth/yo) y el contenido de la página activa.
 */
@Component({
  selector: 'esart-plataforma',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, PieInstitucional],
  templateUrl: './plataforma.html',
})
export class Plataforma {
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);

  protected readonly usuario = this.sesion.usuario;
  protected readonly menu = computed(() => this.sesion.menu() ?? []);
  protected readonly iconoDeComponente = iconoDeComponente;
  protected readonly rutaCambiarContrasena = '/' + RUTA_PAGINA_CAMBIAR_CONTRASENA;

  /** En celular el sidebar se abre y cierra con el botón de menú. */
  protected readonly sidebarAbierto = signal(false);
  protected readonly cerrandoSesion = signal(false);

  /** Iniciales para el avatar: primeras letras de las dos primeras palabras del nombre. */
  protected readonly iniciales = computed(() => {
    const nombre = this.usuario()?.nombre_completo || this.usuario()?.nombre_usuario || '';
    return nombre
      .split(/[\s.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((parte) => parte[0]!.toUpperCase())
      .join('');
  });

  protected readonly nombreRol = computed(() => {
    const rol = this.usuario()?.rol ?? '';
    return NOMBRES_DE_ROL[rol] ?? rol;
  });

  constructor() {
    // Al navegar en celular, el sidebar se cierra solo.
    this.enrutador.events
      .pipe(
        filter((evento) => evento instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.sidebarAbierto.set(false));
  }

  protected alternarSidebar(): void {
    this.sidebarAbierto.update((abierto) => !abierto);
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
