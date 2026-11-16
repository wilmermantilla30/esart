import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { SesionService } from './sesion.service';

describe('SesionService', () => {
  let sesion: SesionService;
  let backend: HttpTestingController;

  const usuarioDePrueba = { nombre_usuario: 'comandante.esart', nombre_completo: 'Comandante', rol: 'USUARIO' };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    sesion = TestBed.inject(SesionService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('envía el login al contrato y guarda solo los datos públicos del usuario', () => {
    let usuarioRecibido: unknown;
    sesion.iniciarSesion('  comandante.esart ', 'Clave-1').subscribe((usuario) => (usuarioRecibido = usuario));

    const peticion = backend.expectOne('/api/auth/login');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      nombre_usuario: 'comandante.esart',
      contrasena: 'Clave-1',
      captcha_id: null,
      captcha_respuesta: null,
    });
    peticion.flush({ usuario: usuarioDePrueba, expira_por_inactividad_segundos: 1800 });

    expect(usuarioRecibido).toEqual(usuarioDePrueba);
    expect(sesion.usuario()).toEqual(usuarioDePrueba);
    expect(sesion.haySesion()).toBe(true);
  });

  it('no guarda nada si el login falla', () => {
    sesion.iniciarSesion('comandante.esart', 'mala').subscribe({ error: () => undefined });
    backend
      .expectOne('/api/auth/login')
      .flush(
        { error: { codigo: 'CREDENCIALES_INVALIDAS', mensaje: 'Usuario o contraseña incorrectos.', detalle: null } },
        { status: 401, statusText: 'Unauthorized' },
      );
    expect(sesion.usuario()).toBeNull();
  });

  it('comprobarSesion recupera el usuario desde /api/auth/yo', () => {
    let resultado: boolean | undefined;
    sesion.comprobarSesion().subscribe((valor) => (resultado = valor));
    backend
      .expectOne('/api/auth/yo')
      .flush({ ...usuarioDePrueba, permisos: ['VERIFICAR_ARTILLERO'], expira_por_inactividad_segundos: 1800 });

    expect(resultado).toBe(true);
    expect(sesion.usuario()).toEqual(usuarioDePrueba);
  });

  it('comprobarSesion responde false (sin lanzar error) si no hay sesión', () => {
    let resultado: boolean | undefined;
    sesion.comprobarSesion().subscribe((valor) => (resultado = valor));
    backend.expectOne('/api/auth/yo').flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(resultado).toBe(false);
  });

  it('cerrarSesion limpia el estado local aunque el servidor falle', () => {
    sesion.iniciarSesion('comandante.esart', 'Clave-1').subscribe();
    backend.expectOne('/api/auth/login').flush({ usuario: usuarioDePrueba, expira_por_inactividad_segundos: 1800 });

    let completado = false;
    sesion.cerrarSesion().subscribe({ complete: () => (completado = true) });
    const peticion = backend.expectOne('/api/auth/cerrar-sesion');
    expect(peticion.request.method).toBe('POST');
    peticion.flush(null, { status: 500, statusText: 'Server Error' });

    expect(completado).toBe(true);
    expect(sesion.usuario()).toBeNull();
  });
});
