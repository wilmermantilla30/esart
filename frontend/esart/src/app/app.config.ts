import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { provideHttpClient, withXsrfConfiguration } from '@angular/common/http';

export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(withXsrfConfiguration({ cookieName: 'esart_csrf', headerName: 'X-CSRF-Token' })),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes)
  ]
};
