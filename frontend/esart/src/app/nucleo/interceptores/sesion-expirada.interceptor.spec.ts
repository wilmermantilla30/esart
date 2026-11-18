import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { SesionService } from '../servicios/sesion.service';
import { sesionExpiradaInterceptor } from './sesion-expirada.interceptor';

describe('sesionExpiradaInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let navegar: ReturnType<typeof vi.fn>;
  let olvidarSesion: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    navegar = vi.fn().mockResolvedValue(true);
    olvidarSesion = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([sesionExpiradaInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate: navegar } },
        { provide: SesionService, useValue: { olvidarSesion } },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('un 401 en una ruta protegida limpia la sesión y lleva al login con el aviso', () => {
    let errorRecibido = false;
    http.get('/api/catalogos/unidades').subscribe({ error: () => (errorRecibido = true) });
    backend
      .expectOne('/api/catalogos/unidades')
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(errorRecibido).toBe(true);
    expect(olvidarSesion).toHaveBeenCalledTimes(1);
    expect(navegar).toHaveBeenCalledWith(['/', 'inicio-sesion'], {
      queryParams: { motivo: 'sesion-expirada' },
    });
  });

  it.each([
    '/api/auth/login',
    '/api/auth/yo',
    '/api/auth/totp/login/configurar',
    '/api/auth/totp/login/vincular',
    '/api/auth/totp/login/confirmar',
  ])('un 401 de %s no redirige', (ruta) => {
    http.post(ruta, {}).subscribe({ error: () => undefined });
    backend.expectOne(ruta).flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(navegar).not.toHaveBeenCalled();
    expect(olvidarSesion).not.toHaveBeenCalled();
  });

  it('otros errores (por ejemplo 403) no cierran la sesión', () => {
    http.get('/api/catalogos/unidades').subscribe({ error: () => undefined });
    backend
      .expectOne('/api/catalogos/unidades')
      .flush(null, { status: 403, statusText: 'Forbidden' });
    expect(navegar).not.toHaveBeenCalled();
  });
});
