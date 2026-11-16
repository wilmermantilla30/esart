import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { sesionExpiradaInterceptor } from './nucleo/interceptores/sesion-expirada.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(
      // CSRF por doble cookie (contrato §1.1): Angular copia la cookie esart_csrf en la
      // cabecera X-CSRF-Token en cada POST/PUT/DELETE a rutas relativas.
      withXsrfConfiguration({ cookieName: 'esart_csrf', headerName: 'X-CSRF-Token' }),
      withInterceptors([sesionExpiradaInterceptor]),
    ),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
  ],
};
