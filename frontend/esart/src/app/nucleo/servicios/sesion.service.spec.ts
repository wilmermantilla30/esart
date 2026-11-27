import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { SesionService } from './sesion.service';

describe('SesionService', () => {
  let sesion: SesionService;
  let backend: HttpTestingController;

  const usuarioDePrueba = {
    nombre_usuario: 'comandante.esart',
    nombre_completo: 'Comandante',
    rol: 'USUARIO',
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    sesion = TestBed.inject(SesionService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('usa los permisos completos de ADMINISTRADOR resueltos por el backend', () => {
    sesion.renovarSesion().subscribe();
    const codigos = ['USUARIOS', 'PERMISOS', 'AUDITORIA', 'PERSONAL_CARGUE_EXCEL'];
    backend
      .expectOne('/api/auth/yo')
      .flush({
        ...usuarioDePrueba,
        rol: 'ADMINISTRADOR',
        permisos: codigos,
        menu: codigos.map((codigo) => ({
          codigo,
          nombre: codigo,
          ruta: '/modulo/' + codigo,
          operaciones: ['crear', 'leer', 'actualizar', 'eliminar'],
          hijos: [],
        })),
      });
    for (const codigo of codigos) {
      expect(sesion.tienePermiso(codigo)).toBe(true);
      for (const operacion of ['crear', 'leer', 'actualizar', 'eliminar'])
        expect(sesion.puede(codigo, operacion)).toBe(true);
    }
  });

  it('no inventa permisos desde la etiqueta de rol recibida sin la malla del servidor', () => {
    sesion.renovarSesion().subscribe();
    backend
      .expectOne('/api/auth/yo')
      .flush({ ...usuarioDePrueba, rol: 'ADMINISTRADOR', permisos: [], menu: [] });
    expect(sesion.tienePermiso('USUARIOS')).toBe(false);
    expect(sesion.puede('PERSONAL_CARGUE_EXCEL', 'crear')).toBe(false);
  });

  it('cambia la contraseña temporal sin sesión y continúa con el desafío MFA', () => {
    sesion.iniciarSesion('cuenta.local', 'temporal').subscribe();
    backend.expectOne('/api/auth/login').flush({
      totp_requerido: true,
      cambio_contrasena_requerido: true,
      desafio_id: 'cambio',
      expira_en: '2026-11-16T23:00:00Z',
    });
    expect(sesion.haySesion()).toBe(false);
    expect(sesion.requiereCambioContrasena()).toBe(true);
    sesion.cambiarContrasena('temporal', 'nueva-local-2026').subscribe();
    const cambio = backend.expectOne('/api/auth/cambiar-contrasena-inicial');
    expect(cambio.request.body.desafio_id).toBe('cambio');
    cambio.flush({
      totp_requerido: true,
      configuracion_requerida: true,
      desafio_id: 'vinculacion',
      expira_en: '2026-11-16T23:00:00Z',
    });
    expect(sesion.haySesion()).toBe(false);
    expect(sesion.cambioInicialPendiente()).toBeNull();
    expect(sesion.tomarPasoMfaPendiente()?.desafio_id).toBe('vinculacion');
    expect(sesion.tomarPasoMfaPendiente()).toBeNull();
    backend.expectNone('/api/auth/yo');
  });

  it('borra menú y permisos anteriores al recibir un desafío de otro login', () => {
    sesion.renovarSesion().subscribe();
    backend.expectOne('/api/auth/yo').flush({
      ...usuarioDePrueba,
      permisos: ['USUARIOS'],
      menu: [{ codigo: 'USUARIOS', operaciones: ['leer'], hijos: [] }],
    });
    expect(sesion.tienePermiso('USUARIOS')).toBe(true);
    sesion.iniciarSesion('otra.cuenta', 'clave').subscribe();
    backend
      .expectOne('/api/auth/login')
      .flush({ totp_requerido: true, desafio_id: 'mfa', expira_en: '2026-11-16T23:00:00Z' });
    expect(sesion.haySesion()).toBe(false);
    expect(sesion.menu()).toBeNull();
    expect(sesion.tienePermiso('USUARIOS')).toBe(false);
  });

  it('solicita CAPTCHA antes del login con usuario normalizado y sin Authorization', () => {
    sesion.obtenerCaptcha('  cuenta.local  ', 'a'.repeat(43)).subscribe();
    const solicitud = backend.expectOne('/api/auth/captcha');
    expect(solicitud.request.method).toBe('GET');
    expect(solicitud.request.headers.get('X-ESART-Usuario')).toBe('cuenta.local');
    expect(solicitud.request.headers.get('X-ESART-Captcha-Anterior')).toBe('a'.repeat(43));
    expect(solicitud.request.headers.has('Authorization')).toBe(false);
    expect(sesion.haySesion()).toBe(false);
    solicitud.flush({
      captcha_id: 'b'.repeat(43),
      imagen_png_base64: 'iVBORw0KGgo=',
      expira_en: '2026-11-16T12:05:00Z',
      longitud: 6,
    });
  });

  it('no solicita una imagen si falta el usuario del intento', () => {
    const error = vi.fn();
    sesion.obtenerCaptcha('  ').subscribe({ error });
    expect(error).toHaveBeenCalledWith(expect.objectContaining({ status: 422 }));
    backend.expectNone('/api/auth/captcha');
  });

  it('envía el desafío CAPTCHA del servidor sin contadores ni tiempos del cliente', () => {
    sesion
      .iniciarSesion('cuenta.local', 'clave-local', { id: 'reto', respuesta: 'respuesta' })
      .subscribe();
    const solicitud = backend.expectOne('/api/auth/login');
    expect(solicitud.request.body).toEqual({
      nombre_usuario: 'cuenta.local',
      contrasena: 'clave-local',
      captcha_id: 'reto',
      captcha_respuesta: 'respuesta',
    });
    solicitud.flush({ usuario: usuarioDePrueba, expira_por_inactividad_segundos: 1800 });
  });

  it('envía el login al contrato y guarda solo los datos públicos del usuario', () => {
    let usuarioRecibido: unknown;
    sesion
      .iniciarSesion('  comandante.esart ', 'Clave-1')
      .subscribe((usuario) => (usuarioRecibido = usuario));

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
    backend.expectOne('/api/auth/login').flush(
      {
        error: {
          codigo: 'CREDENCIALES_INVALIDAS',
          mensaje: 'Usuario o contraseña incorrectos.',
          detalle: null,
        },
      },
      { status: 401, statusText: 'Unauthorized' },
    );
    expect(sesion.usuario()).toBeNull();
  });

  it('comprobarSesion recupera el usuario desde /api/auth/yo', () => {
    let resultado: boolean | undefined;
    sesion.comprobarSesion().subscribe((valor) => (resultado = valor));
    backend.expectOne('/api/auth/yo').flush({
      ...usuarioDePrueba,
      permisos: ['VERIFICAR_ARTILLERO'],
      expira_por_inactividad_segundos: 1800,
    });

    expect(resultado).toBe(true);
    expect(sesion.usuario()).toEqual({ ...usuarioDePrueba, requiere_cambio_contrasena: false });
  });

  it('con contraseña temporal lo marca y, al cambiarla, la marca se quita', () => {
    sesion.comprobarSesion().subscribe();
    backend.expectOne('/api/auth/yo').flush({
      ...usuarioDePrueba,
      requiere_cambio_contrasena: true,
      permisos: [],
      menu: [],
      expira_por_inactividad_segundos: 1800,
    });
    expect(sesion.requiereCambioContrasena()).toBe(true);

    sesion.cambiarContrasena('Temporal2026x', 'NuevaClave2026').subscribe();
    const peticion = backend.expectOne('/api/auth/cambiar-contrasena');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      contrasena_actual: 'Temporal2026x',
      contrasena_nueva: 'NuevaClave2026',
    });
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    expect(sesion.requiereCambioContrasena()).toBe(false);
  });

  it('puede() lee las operaciones del menú, también en las pestañas', () => {
    sesion.comprobarSesion().subscribe();
    backend.expectOne('/api/auth/yo').flush({
      ...usuarioDePrueba,
      permisos: ['USUARIOS', 'PERSONAL_MILITAR', 'PERSONAL_VERIFICAR'],
      menu: [
        {
          codigo: 'USUARIOS',
          nombre: 'Usuarios',
          ruta: '/administracion/usuarios',
          operaciones: ['leer', 'crear'],
          hijos: [],
        },
        {
          codigo: 'PERSONAL_MILITAR',
          nombre: 'Personal',
          ruta: '/personal',
          operaciones: ['leer'],
          hijos: [
            {
              codigo: 'PERSONAL_VERIFICAR',
              nombre: 'Verificar',
              ruta: '/personal/verificar',
              operaciones: ['leer'],
              hijos: [],
            },
          ],
        },
      ],
      expira_por_inactividad_segundos: 1800,
    });
    expect(sesion.puede('USUARIOS', 'crear')).toBe(true);
    expect(sesion.puede('USUARIOS', 'actualizar')).toBe(false);
    expect(sesion.puede('PERSONAL_VERIFICAR', 'leer')).toBe(true);
    expect(sesion.puede('AUDITORIA', 'leer')).toBe(false);
  });

  it('puede() también conoce las operaciones de los permisos especiales sin menú (S2-09)', () => {
    sesion.comprobarSesion().subscribe();
    backend.expectOne('/api/auth/yo').flush({
      ...usuarioDePrueba,
      permisos: ['MALLAS_CURRICULARES'],
      menu: [],
      operaciones: { MALLAS_CURRICULARES: ['leer', 'actualizar'] },
      expira_por_inactividad_segundos: 1800,
    });
    expect(sesion.puede('MALLAS_CURRICULARES', 'actualizar')).toBe(true);
    expect(sesion.puede('MALLAS_CURRICULARES', 'crear')).toBe(false);
    expect(sesion.puede('USUARIOS', 'leer')).toBe(false);
  });

  it('comprobarSesion responde false (sin lanzar error) si no hay sesión', () => {
    let resultado: boolean | undefined;
    sesion.comprobarSesion().subscribe((valor) => (resultado = valor));
    backend.expectOne('/api/auth/yo').flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(resultado).toBe(false);
  });

  it('cerrarSesion limpia el estado local aunque el servidor falle', () => {
    sesion.iniciarSesion('comandante.esart', 'Clave-1').subscribe();
    backend
      .expectOne('/api/auth/login')
      .flush({ usuario: usuarioDePrueba, expira_por_inactividad_segundos: 1800 });

    let completado = false;
    sesion.cerrarSesion().subscribe({ complete: () => (completado = true) });
    const peticion = backend.expectOne('/api/auth/cerrar-sesion');
    expect(peticion.request.method).toBe('POST');
    peticion.flush(null, { status: 500, statusText: 'Server Error' });

    expect(completado).toBe(true);
    expect(sesion.usuario()).toBeNull();
  });
});
