import { registerLocaleData } from '@angular/common';
import localeEsCo from '@angular/common/locales/es-CO';
import { ApplicationConfig, LOCALE_ID, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { actividadSesionInterceptor } from './nucleo/interceptores/actividad-sesion.interceptor';
import { sesionExpiradaInterceptor } from './nucleo/interceptores/sesion-expirada.interceptor';

// Fechas y números en español de Colombia en toda la aplicación ("18 nov 2026", "1.234").
registerLocaleData(localeEsCo);

export const appConfig: ApplicationConfig = {
  providers: [
    { provide: LOCALE_ID, useValue: 'es-CO' },
    provideHttpClient(
      // CSRF por doble cookie (contrato §1.1): Angular copia la cookie esart_csrf en la
      // cabecera X-CSRF-Token en cada POST/PUT/DELETE a rutas relativas.
      withXsrfConfiguration({ cookieName: 'esart_csrf', headerName: 'X-CSRF-Token' }),
      // actividadSesion: reinicia la cuenta regresiva de inactividad con cada respuesta (HU-08).
      withInterceptors([sesionExpiradaInterceptor, actividadSesionInterceptor]),
    ),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
  ],
};
