import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import {
  MOTIVO_SESION_EXPIRADA,
  PARAMETRO_MOTIVO,
  RUTA_PAGINA_CAMBIAR_CONTRASENA,
  RUTA_PAGINA_INICIO_SESION,
} from '../rutas-paginas';
import { PREFIJO_API } from '../servicios/cliente-api.service';
import {
  RUTA_INICIAR_SESION,
  RUTA_USUARIO_ACTUAL,
  SesionService,
} from '../servicios/sesion.service';

/**
 * Peticiones cuyo 401 NO significa "la sesión expiró":
 * - el login (un 401 ahí es "credenciales inválidas" y lo muestra la propia pantalla);
 * - /auth/yo (lo usan las guardas justamente para averiguar si hay sesión).
 */
const RUTAS_SIN_REDIRECCION = [
  PREFIJO_API + RUTA_INICIAR_SESION,
  PREFIJO_API + RUTA_USUARIO_ACTUAL,
  PREFIJO_API + '/auth/totp/login/configurar',
  PREFIJO_API + '/auth/totp/login/vincular',
  PREFIJO_API + '/auth/totp/login/confirmar',
  PREFIJO_API + '/auth/cambiar-contrasena-inicial',
];

/** Código del 403 que da el backend mientras la contraseña sea temporal. */
export const CODIGO_CAMBIO_CONTRASENA_REQUERIDO = 'CAMBIO_CONTRASENA_REQUERIDO';

/**
 * Si el backend responde 401 a cualquier otra petición, la sesión ya no es válida
 * (30 minutos sin actividad, revocada o cookie borrada): se limpia el estado y se
 * lleva al login con el aviso "Su sesión expiró por inactividad" (contrato §1.2).
 * El error se sigue propagando para que la pantalla deje de mostrar "cargando".
 */
export const sesionExpiradaInterceptor: HttpInterceptorFn = (peticion, siguiente) => {
  const sesion = inject(SesionService);
  const enrutador = inject(Router);

  return siguiente(peticion).pipe(
    catchError((error: unknown) => {
      const esRutaExcluida = RUTAS_SIN_REDIRECCION.some((ruta) => peticion.url.startsWith(ruta));
      if (error instanceof HttpErrorResponse && error.status === 401 && !esRutaExcluida) {
        sesion.olvidarSesion();
        void enrutador.navigate(['/', RUTA_PAGINA_INICIO_SESION], {
          queryParams: { [PARAMETRO_MOTIVO]: MOTIVO_SESION_EXPIRADA },
        });
      }
      // Contraseña temporal: el backend no responde nada más hasta que se cambie.
      if (
        error instanceof HttpErrorResponse &&
        error.status === 403 &&
        error.error?.error?.codigo === CODIGO_CAMBIO_CONTRASENA_REQUERIDO
      ) {
        void enrutador.navigate(['/', RUTA_PAGINA_CAMBIAR_CONTRASENA]);
      }
      return throwError(() => error);
    }),
  );
};
