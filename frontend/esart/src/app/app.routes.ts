import { Route, Routes } from '@angular/router';

import { exigirPermiso } from './nucleo/guardas/permiso.guard';
import {
  exigirSesion,
  exigirSesionParaCambiarContrasena,
  soloSinSesion,
} from './nucleo/guardas/sesion.guard';
import {
  RUTA_PAGINA_CAMBIAR_CONTRASENA,
  RUTA_PAGINA_INICIO,
  RUTA_PAGINA_INICIO_SESION,
} from './nucleo/rutas-paginas';

/** Carga diferida de la página provisional de los módulos que aún no tienen pantalla. */
const cargarEnConstruccion = () =>
  import('./compartido/en-construccion/en-construccion').then((m) => m.EnConstruccion);

/**
 * Ruta de un módulo todavía sin pantalla. Exige su permiso de la malla igual que
 * cuando tenga pantalla: así la navegación ya respeta la malla desde hoy.
 */
function rutaEnConstruccion(
  ruta: string,
  componente: string,
  titulo: string,
  descripcion: string,
): Route {
  return {
    path: ruta,
    title: `${titulo} — ESART`,
    canActivate: [exigirPermiso],
    data: { componente, titulo, descripcion },
    loadComponent: cargarEnConstruccion,
  };
}

/**
 * Rutas del front. Las páginas se cargan bajo demanda (loadComponent) para que el
 * login descargue solo lo necesario. Todas las páginas internas viven dentro del marco
 * Plataforma (encabezado + sidebar) y exigen su permiso de la malla (HU-09).
 */
export const routes: Routes = [
  {
    path: 'totp',
    title: 'Seguridad del autenticador — ESART',
    canActivate: [exigirSesion],
    loadComponent: () => import('./paginas/totp/totp').then((m) => m.Totp),
  },
  {
    path: RUTA_PAGINA_INICIO_SESION,
    title: 'Iniciar sesión — ESART',
    canActivate: [soloSinSesion],
    loadComponent: () =>
      import('./paginas/inicio-sesion/inicio-sesion').then((m) => m.InicioSesion),
  },
  {
    // Fuera del marco Plataforma: con contraseña temporal no se muestra el menú.
    path: RUTA_PAGINA_CAMBIAR_CONTRASENA,
    title: 'Cambiar contraseña — ESART',
    canActivate: [exigirSesionParaCambiarContrasena],
    loadComponent: () =>
      import('./paginas/cambiar-contrasena/cambiar-contrasena').then((m) => m.CambiarContrasena),
  },
  {
    path: '',
    canActivate: [exigirSesion],
    loadComponent: () => import('./paginas/plataforma/plataforma').then((m) => m.Plataforma),
    children: [
      { path: '', pathMatch: 'full', redirectTo: RUTA_PAGINA_INICIO },
      {
        path: RUTA_PAGINA_INICIO,
        title: 'Panel principal — ESART',
        canActivate: [exigirPermiso],
        data: { componente: 'DASHBOARD' },
        loadComponent: () =>
          import('./paginas/panel-principal/panel-principal').then((m) => m.PanelPrincipal),
      },
      {
        path: 'personal',
        canActivate: [exigirPermiso],
        data: { componente: 'PERSONAL_MILITAR' },
        loadComponent: () =>
          import('./paginas/personal-militar/personal-militar').then((m) => m.PersonalMilitar),
        children: [
          {
            path: '',
            title: 'Personal militar — ESART',
            loadComponent: () =>
              import('./paginas/personal-militar/panel-personal/panel-personal').then(
                (m) => m.PanelPersonal,
              ),
          },
          {
            path: 'verificar',
            title: 'Verificar artillero — ESART',
            canActivate: [exigirPermiso],
            data: { componente: 'PERSONAL_VERIFICAR' },
            loadComponent: () =>
              import('./paginas/personal-militar/verificar-artillero/verificar-artillero').then(
                (m) => m.VerificarArtillero,
              ),
          },
          {
            path: 'habilitados',
            title: 'Habilitados — ESART',
            canActivate: [exigirPermiso],
            data: { componente: 'PERSONAL_HABILITADOS' },
            loadComponent: () =>
              import('./paginas/personal-militar/habilitados/habilitados').then(
                (m) => m.Habilitados,
              ),
          },
          {
            path: 'cargue-excel',
            title: 'Cargue masivo por Excel — ESART',
            canActivate: [exigirPermiso],
            data: { componente: 'PERSONAL_CARGUE_EXCEL' },
            loadComponent: () =>
              import('./paginas/personal-militar/cargue-excel/cargue-excel').then(
                (m) => m.CargueExcel,
              ),
          },
          {
            path: 'cargue-manual',
            title: 'Registro manual de personal — ESART',
            canActivate: [exigirPermiso],
            data: { componente: 'PERSONAL_CARGUE_MANUAL' },
            loadComponent: () =>
              import('./paginas/personal-militar/cargue-manual/cargue-manual').then(
                (m) => m.CargueManual,
              ),
          },
        ],
      },
      {
        path: 'instructores',
        title: 'Instructores — ESART',
        canActivate: [exigirPermiso],
        data: { componente: 'INSTRUCTORES' },
        loadComponent: () =>
          import('./paginas/instructores/instructores').then((m) => m.Instructores),
      },
      {
        path: 'administracion/usuarios',
        title: 'Gestión de usuarios — ESART',
        canActivate: [exigirPermiso],
        data: { componente: 'USUARIOS' },
        loadComponent: () =>
          import('./paginas/administracion/gestion-usuarios/gestion-usuarios').then(
            (m) => m.GestionUsuarios,
          ),
      },
      {
        path: 'administracion/parametros',
        title: 'Parámetros — ESART',
        canActivate: [exigirPermiso],
        // S2-09: quien solo tiene MALLAS_CURRICULARES entra y ve únicamente esa pestaña.
        data: { componentes: ['PARAMETROS_HABILITACION', 'MALLAS_CURRICULARES'] },
        loadComponent: () =>
          import('./paginas/administracion/parametros/parametros').then((m) => m.Parametros),
      },
      {
        path: 'administracion/permisos',
        title: 'Malla de permisos — ESART',
        canActivate: [exigirPermiso],
        data: { componente: 'PERMISOS' },
        loadComponent: () =>
          import('./paginas/administracion/malla-permisos/malla-permisos').then(
            (m) => m.MallaPermisos,
          ),
      },
      {
        path: 'administracion/auditoria',
        title: 'Auditoría — ESART',
        canActivate: [exigirPermiso],
        data: { componente: 'AUDITORIA' },
        loadComponent: () =>
          import('./paginas/administracion/auditoria/auditoria').then((m) => m.Auditoria),
      },
      {
        path: 'unidades',
        title: 'Unidades — ESART',
        loadComponent: () => import('./unidades').then((m) => m.Unidades),
      },
    ],
  },
  // Cualquier otra ruta va al Panel principal (y de ahí al login si no hay sesión).
  { path: '**', redirectTo: RUTA_PAGINA_INICIO },
];
