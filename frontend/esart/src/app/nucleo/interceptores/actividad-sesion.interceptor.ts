import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { tap } from 'rxjs';

import { PREFIJO_API } from '../servicios/cliente-api.service';
import { InactividadService } from '../servicios/inactividad.service';
import { RUTA_INICIAR_SESION } from '../servicios/sesion.service';

/** Cabecera con los segundos que le quedan a la sesión (contrato de API §1.4). */
export const CABECERA_SESION_EXPIRA_EN = 'X-Sesion-Expira-En';

/**
 * Mantiene al día la cuenta regresiva de inactividad (HU-08) con lo que informa el backend:
 * - toda respuesta autenticada trae la cabecera X-Sesion-Expira-En;
 * - el login trae expira_por_inactividad_segundos en el cuerpo (aún no hay sesión al pedirlo).
 */
export const actividadSesionInterceptor: HttpInterceptorFn = (peticion, siguiente) => {
  const inactividad = inject(InactividadService);

  return siguiente(peticion).pipe(
    tap((evento) => {
      if (!(evento instanceof HttpResponse)) {
        return;
      }
      const cabecera = evento.headers.get(CABECERA_SESION_EXPIRA_EN);
      if (cabecera !== null) {
        inactividad.reiniciar(Number(cabecera));
        return;
      }
      if (peticion.url.startsWith(PREFIJO_API + RUTA_INICIAR_SESION)) {
        const cuerpo = evento.body as { expira_por_inactividad_segundos?: unknown } | null;
        if (typeof cuerpo?.expira_por_inactividad_segundos === 'number') {
          inactividad.reiniciar(cuerpo.expira_por_inactividad_segundos);
        }
      }
    }),
  );
};
