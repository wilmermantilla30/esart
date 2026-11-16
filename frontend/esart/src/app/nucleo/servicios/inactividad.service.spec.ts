import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { actividadSesionInterceptor } from '../interceptores/actividad-sesion.interceptor';
import { InactividadService } from './inactividad.service';
import { SesionService } from './sesion.service';

describe('InactividadService (HU-08)', () => {
  let inactividad: InactividadService;
  let sesion: SesionService;
  let backend: HttpTestingController;
  let navegar: ReturnType<typeof vi.fn>;

  const usuario = { nombre_usuario: 'usuario1.esart', nombre_completo: 'Usuario 1', rol: 'USUARIO' };
  const respuestaYo = { ...usuario, permisos: [], expira_por_inactividad_segundos: 1800 };

  /** Inicia sesión simulada: el login informa 1800 s de inactividad permitidos. */
  function iniciarSesion(segundos = 1800) {
    sesion.iniciarSesion('usuario1.esart', 'clave').subscribe();
    backend.expectOne('/api/auth/login').flush({ usuario, expira_por_inactividad_segundos: segundos });
    TestBed.tick();
  }

  beforeEach(() => {
    vi.useFakeTimers();
    navegar = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([actividadSesionInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate: navegar } },
      ],
    });
    inactividad = TestBed.inject(InactividadService);
    sesion = TestBed.inject(SesionService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
    inactividad.detener();
    vi.useRealTimers();
  });

  it('el login inicia la cuenta regresiva con el tiempo que informa el backend', () => {
    iniciarSesion();
    expect(inactividad.segundosRestantes()).toBe(1800);
    expect(inactividad.mostrarAviso()).toBe(false);
  });

  it('muestra el aviso solo en los últimos 2 minutos', () => {
    iniciarSesion(300);
    vi.advanceTimersByTime(179_000);
    expect(inactividad.mostrarAviso()).toBe(false);
    vi.advanceTimersByTime(2_000);
    expect(inactividad.segundosRestantes()).toBe(119);
    expect(inactividad.mostrarAviso()).toBe(true);
  });

  it('cada respuesta con X-Sesion-Expira-En reinicia la cuenta y oculta el aviso', () => {
    iniciarSesion(130);
    vi.advanceTimersByTime(20_000);
    expect(inactividad.mostrarAviso()).toBe(true);

    inactividad.continuarSesion();
    backend.expectOne('/api/auth/yo').flush(respuestaYo, { headers: { 'X-Sesion-Expira-En': '1800' } });

    expect(inactividad.segundosRestantes()).toBe(1800);
    expect(inactividad.mostrarAviso()).toBe(false);
    expect(navegar).not.toHaveBeenCalled();
  });

  it('al vencer pregunta al backend y, si la sesión ya no vale, va al login con el aviso', () => {
    iniciarSesion(60);
    vi.advanceTimersByTime(61_000);

    backend
      .expectOne('/api/auth/yo')
      .flush({ error: { codigo: 'SESION_EXPIRADA', mensaje: 'x', detalle: null } }, { status: 401, statusText: 'x' });
    TestBed.tick();

    expect(navegar).toHaveBeenCalledWith(['/', 'inicio-sesion'], { queryParams: { motivo: 'sesion-expirada' } });
    expect(sesion.haySesion()).toBe(false);
    expect(inactividad.segundosRestantes()).toBeNull();
  });

  it('al vencer, si hubo actividad en otra pestaña, la sesión sigue y la cuenta se reinicia', () => {
    iniciarSesion(60);
    vi.advanceTimersByTime(61_000);

    backend.expectOne('/api/auth/yo').flush(respuestaYo, { headers: { 'X-Sesion-Expira-En': '1500' } });

    expect(navegar).not.toHaveBeenCalled();
    expect(inactividad.segundosRestantes()).toBe(1500);
  });

  it('al cerrar sesión se detiene la cuenta regresiva', () => {
    iniciarSesion();
    sesion.cerrarSesion().subscribe();
    backend.expectOne('/api/auth/cerrar-sesion').flush(null, { status: 204, statusText: 'No Content' });
    TestBed.tick();
    expect(inactividad.segundosRestantes()).toBeNull();
  });

  it('ignora valores inválidos de la cabecera', () => {
    inactividad.reiniciar(Number('abc'));
    inactividad.reiniciar(-5);
    expect(inactividad.segundosRestantes()).toBeNull();
  });
});
