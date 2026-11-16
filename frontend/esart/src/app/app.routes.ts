import { Routes } from '@angular/router';

import { exigirSesion, soloSinSesion } from './nucleo/guardas/sesion.guard';
import { RUTA_PAGINA_INICIO, RUTA_PAGINA_INICIO_SESION } from './nucleo/rutas-paginas';

/**
 * Rutas del front. Las páginas se cargan bajo demanda (loadComponent) para que el
 * login descargue solo lo necesario.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: RUTA_PAGINA_INICIO },
  {
    path: RUTA_PAGINA_INICIO_SESION,
    title: 'Iniciar sesión — ESART',
    canActivate: [soloSinSesion],
    loadComponent: () => import('./paginas/inicio-sesion/inicio-sesion').then((m) => m.InicioSesion),
  },
  {
    path: RUTA_PAGINA_INICIO,
    title: 'Inicio — ESART',
    canActivate: [exigirSesion],
    loadComponent: () => import('./paginas/inicio/inicio').then((m) => m.Inicio),
  },
  {
    path: 'unidades',
    title: 'Unidades — ESART',
    canActivate: [exigirSesion],
    loadComponent: () => import('./unidades').then((m) => m.Unidades),
  },
  // Cualquier otra ruta va al inicio (y de ahí al login si no hay sesión).
  { path: '**', redirectTo: RUTA_PAGINA_INICIO },
];
