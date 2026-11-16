import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import {
  PARAMETRO_VOLVER_A,
  RUTA_PAGINA_INICIO,
  RUTA_PAGINA_INICIO_SESION,
} from '../rutas-paginas';
import { SesionService } from '../servicios/sesion.service';

/**
 * Protege las páginas internas: si no hay sesión válida, lleva al login y recuerda
 * a qué página quería entrar el usuario.
 *
 * Es solo comodidad de navegación: la seguridad real la aplica el backend en cada
 * petición (cookie + permisos). Ocultar una página no protege datos.
 */
export const exigirSesion: CanActivateFn = (_ruta, estado) => {
  const sesion = inject(SesionService);
  const enrutador = inject(Router);
  return sesion
    .comprobarSesion()
    .pipe(
      map((haySesion) =>
        haySesion
          ? true
          : enrutador.createUrlTree(['/', RUTA_PAGINA_INICIO_SESION], {
              queryParams: { [PARAMETRO_VOLVER_A]: estado.url },
            }),
      ),
    );
};

/** La página de login solo es para quien NO tiene sesión; si ya la tiene, va al inicio. */
export const soloSinSesion: CanActivateFn = () => {
  const sesion = inject(SesionService);
  const enrutador = inject(Router);
  return sesion
    .comprobarSesion()
    .pipe(map((haySesion) => (haySesion ? enrutador.createUrlTree(['/', RUTA_PAGINA_INICIO]) : true)));
};
