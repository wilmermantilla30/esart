import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { RUTA_PAGINA_INICIO, RUTA_PAGINA_INICIO_SESION } from '../rutas-paginas';
import { SesionService } from '../servicios/sesion.service';

/**
 * Guarda de ruta por permiso de la malla (HU-09): exige el componente indicado en
 * `data.componente` de la ruta. Sin sesión va al login; sin permiso, al Panel principal.
 * Con `data.componentes` (lista) basta con tener uno: Parámetros abre con
 * PARAMETROS_HABILITACION o con el permiso especial MALLAS_CURRICULARES (S2-09).
 *
 * Es solo navegación: el backend verifica el mismo permiso en cada endpoint.
 */
export const exigirPermiso: CanActivateFn = (ruta) => {
  const sesion = inject(SesionService);
  const enrutador = inject(Router);
  const componente = ruta.data['componente'] as string | undefined;
  const componentes =
    (ruta.data['componentes'] as string[] | undefined) ?? (componente ? [componente] : []);

  return sesion.comprobarSesion().pipe(
    map((haySesion) => {
      if (!haySesion) {
        return enrutador.createUrlTree(['/', RUTA_PAGINA_INICIO_SESION]);
      }
      if (!componentes.length || componentes.some((codigo) => sesion.tienePermiso(codigo))) {
        return true;
      }
      return enrutador.createUrlTree(['/', RUTA_PAGINA_INICIO]);
    }),
  );
};
