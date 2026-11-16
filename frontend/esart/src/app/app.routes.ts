import { Route, Routes } from '@angular/router';

import { exigirPermiso } from './nucleo/guardas/permiso.guard';
import { exigirSesion, soloSinSesion } from './nucleo/guardas/sesion.guard';
import { RUTA_PAGINA_INICIO, RUTA_PAGINA_INICIO_SESION } from './nucleo/rutas-paginas';

/** Carga diferida de la página provisional de los módulos que aún no tienen pantalla. */
const cargarEnConstruccion = () =>
  import('./compartido/en-construccion/en-construccion').then((m) => m.EnConstruccion);

/**
 * Ruta de un módulo todavía sin pantalla. Exige su permiso de la malla igual que
 * cuando tenga pantalla: así la navegación ya respeta la malla desde hoy.
 */
function rutaEnConstruccion(ruta: string, componente: string, titulo: string, descripcion: string): Route {
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
    path: RUTA_PAGINA_INICIO_SESION,
    title: 'Iniciar sesión — ESART',
    canActivate: [soloSinSesion],
    loadComponent: () => import('./paginas/inicio-sesion/inicio-sesion').then((m) => m.InicioSesion),
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
        loadComponent: () => import('./paginas/panel-principal/panel-principal').then((m) => m.PanelPrincipal),
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
              import('./paginas/personal-militar/panel-personal/panel-personal').then((m) => m.PanelPersonal),
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
              import('./paginas/personal-militar/habilitados/habilitados').then((m) => m.Habilitados),
          },
          rutaEnConstruccion(
            'cargue-excel',
            'PERSONAL_CARGUE_EXCEL',
            'Cargue masivo por Excel',
            'Importación del personal desde la plantilla oficial.',
          ),
          rutaEnConstruccion(
            'cargue-manual',
            'PERSONAL_CARGUE_MANUAL',
            'Registro manual de personal',
            'Formulario para registrar un artillero.',
          ),
        ],
      },
      rutaEnConstruccion(
        'administracion/usuarios',
        'USUARIOS',
        'Gestión de usuarios',
        'Crear, editar y desactivar usuarios del sistema.',
      ),
      rutaEnConstruccion(
        'administracion/parametros',
        'PARAMETROS_HABILITACION',
        'Parámetros de habilitación',
        'Reglas que definen cuándo un artillero está APTO: cursos válidos y vigencia del reentrenamiento.',
      ),
      rutaEnConstruccion(
        'administracion/permisos',
        'PERMISOS',
        'Malla de permisos',
        'Qué puede hacer cada rol en cada módulo.',
      ),
      rutaEnConstruccion(
        'administracion/auditoria',
        'AUDITORIA',
        'Auditoría',
        'Registro inmutable de accesos y consultas.',
      ),
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
