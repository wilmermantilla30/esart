import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';

import { InicioSesion } from './inicio-sesion';

describe('InicioSesion', () => {
  let fixture: ComponentFixture<InicioSesion>;
  let pagina: HTMLElement;
  let backend: HttpTestingController;
  let navegarPorUrl: ReturnType<typeof vi.fn>;

  async function crearPagina(
    parametros: Record<string, string> = {},
    estado: Record<string, unknown> = { bloqueado: false },
  ) {
    navegarPorUrl = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [InicioSesion],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigateByUrl: navegarPorUrl } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(parametros) } },
        },
      ],
    });
    fixture = TestBed.createComponent(InicioSesion);
    backend = TestBed.inject(HttpTestingController);
    pagina = fixture.nativeElement as HTMLElement;
    backend.expectOne('/api/auth/bloqueo').flush(estado);
    await fixture.whenStable();
  }

  function escribir(selector: string, valor: string) {
    const campo = pagina.querySelector<HTMLInputElement>(selector)!;
    campo.value = valor;
    campo.dispatchEvent(new Event('input'));
  }

  async function enviar() {
    pagina.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  afterEach(() => backend.verify());

  it('presenta solo el envío actual público y mantiene restringido el histórico', async () => {
    await crearPagina(
      {},
      {
        bloqueado: true,
        usuario_intentado: 'cuenta.local',
        bloqueado_hasta: '2026-11-16T15:00:00Z',
        ahora_servidor: '2026-11-16T12:00:00Z',
        detalles_autorizados: false,
        intentos_fallidos_consecutivos: null,
        direccion_ip: null,
        intento_actual: {
          alcance: 'ENVIO_ACTUAL',
          envios_registrados: 1,
          fecha: '2026-11-16T12:00:00Z',
          direccion_ip_observada: '127.0.0.1',
          observacion_ip: 'Peer local del backend, no una terminal remota verificada.',
        },
      },
    );
    const ventana = pagina.querySelector('app-ventana-bloqueo')!;
    expect(ventana.textContent).toContain('1 registrado (este envío)');
    expect(ventana.textContent).toContain('Histórico restringido');
    expect(ventana.textContent).toContain('127.0.0.1');
    expect(ventana.textContent).not.toContain('7 registrados');
    backend.expectNone('/api/auth/administracion/bloqueos');
    backend.expectNone('/api/auth/login');
  });

  it('presenta los campos recibidos cuando el contrato del servidor autoriza sus detalles', async () => {
    await crearPagina(
      {},
      {
        bloqueado: true,
        usuario_intentado: 'cuenta.local',
        bloqueado_hasta: '2026-11-16T15:00:00Z',
        ahora_servidor: '2026-11-16T12:00:00Z',
        detalles_autorizados: true,
        intentos_fallidos_consecutivos: 7,
        direccion_ip: '192.0.2.4',
      },
    );
    const ventana = pagina.querySelector('app-ventana-bloqueo')!;
    expect(ventana.textContent).toContain('7 registrados');
    expect(ventana.textContent).toContain('192.0.2.4');
    expect(ventana.textContent).toContain('03:00');
  });

  it('no muestra datos recibidos si el servidor no autoriza su exposición', async () => {
    await crearPagina(
      {},
      {
        bloqueado: true,
        usuario_intentado: 'cuenta.local',
        bloqueado_hasta: '2026-11-16T15:00:00Z',
        ahora_servidor: '2026-11-16T12:00:00Z',
        detalles_autorizados: false,
        intentos_fallidos_consecutivos: 7,
        direccion_ip: '192.0.2.4',
      },
    );
    const ventana = pagina.querySelector('app-ventana-bloqueo')!;
    expect(ventana.textContent).not.toContain('7 registrados');
    expect(ventana.textContent).not.toContain('192.0.2.4');
  });

  it('recupera el bloqueo del servidor al recargar sin iniciar autenticación', async () => {
    await crearPagina(
      {},
      {
        bloqueado: true,
        usuario_intentado: 'cuenta.local',
        bloqueado_hasta: '2026-11-16T15:00:00Z',
        ahora_servidor: '2026-11-16T12:00:00Z',
      },
    );
    expect(pagina.querySelector('app-ventana-bloqueo')).not.toBeNull();
    expect(pagina.textContent).toContain('03:00:00');
    expect(pagina.textContent).toContain('Este comprobante no incluye datos del envío');
    expect(pagina.textContent).not.toContain('0 registrados');
    expect(pagina.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
    backend.expectNone('/api/auth/login');
    backend.expectNone('/api/auth/captcha');
  });

  it('reconoce CAPTCHA y restricción desde el servidor sin contar intentos', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'cuenta.local');
    escribir('#contrasena', 'clave-local');
    await enviar();
    backend.expectOne('/api/auth/login').flush(
      {
        error: {
          codigo: 'CREDENCIALES_INVALIDAS',
          mensaje: 'No fue posible iniciar sesión.',
          detalle: { captcha_requerido: true, acceso_temporalmente_restringido: true },
        },
      },
      { status: 401, statusText: 'Unauthorized' },
    );
    await fixture.whenStable();
    expect(pagina.textContent).not.toContain('verificación CAPTCHA del servidor');
    expect(pagina.textContent).toContain('acceso está temporalmente restringido');
    expect(pagina.querySelector<HTMLInputElement>('#contrasena')?.value).toBe('');
  });

  it('env?a el desaf?o del modal junto con las credenciales al login real', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'cuenta.local');
    escribir('#contrasena', 'clave-local');
    await enviar();
    backend.expectOne('/api/auth/login').flush(
      {
        error: {
          codigo: 'CREDENCIALES_INVALIDAS',
          mensaje: 'No fue posible iniciar sesi?n.',
          detalle: { captcha_requerido: true },
        },
      },
      { status: 401, statusText: 'Unauthorized' },
    );
    await fixture.whenStable();
    escribir('#contrasena', 'clave-local');
    pagina.querySelector('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    backend.expectOne('/api/auth/captcha').flush({
      captcha_id: 'a'.repeat(43),
      imagen_png_base64: 'iVBORw0KGgo=',
      longitud: 6,
      expira_en: '2026-11-16T12:05:00Z',
    });
    await fixture.whenStable();
    escribir('#codigo-captcha', 'ACD346');
    pagina.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click();
    await fixture.whenStable();
    [...pagina.querySelectorAll<HTMLButtonElement>('button')]
      .find((b) => b.textContent?.includes('Validar e Ingresar'))!
      .click();
    const solicitud = backend.expectOne('/api/auth/login');
    expect(solicitud.request.body).toEqual({
      nombre_usuario: 'cuenta.local',
      contrasena: 'clave-local',
      captcha_id: 'a'.repeat(43),
      captcha_respuesta: 'ACD346',
    });
    solicitud.flush({
      usuario: { nombre_usuario: 'cuenta.local', nombre_completo: 'Cuenta', rol: 'USUARIO' },
      expira_por_inactividad_segundos: 1800,
    });
    await fixture.whenStable();
    expect(navegarPorUrl).toHaveBeenCalledWith('/dashboard');
    expect(pagina.querySelector('[role="dialog"]')).toBeNull();
  });

  it('cierra el modal y no pide otro desafío cuando el login informa bloqueo', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'cuenta.local');
    escribir('#contrasena', 'clave-local');
    await enviar();
    backend.expectOne('/api/auth/login').flush(
      {
        error: {
          codigo: 'CREDENCIALES_INVALIDAS',
          mensaje: 'No fue posible iniciar sesión.',
          detalle: { captcha_requerido: true },
        },
      },
      { status: 401, statusText: 'Unauthorized' },
    );
    await fixture.whenStable();
    escribir('#contrasena', 'clave-local');
    pagina.querySelector('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    backend.expectOne('/api/auth/captcha').flush({
      captcha_id: 'a'.repeat(43),
      imagen_png_base64: 'iVBORw0KGgo=',
      longitud: 6,
      expira_en: '2026-11-16T12:05:00Z',
    });
    await fixture.whenStable();
    escribir('#codigo-captcha', 'ACD346');
    pagina.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click();
    await fixture.whenStable();
    [...pagina.querySelectorAll<HTMLButtonElement>('button')]
      .find((b) => b.textContent?.includes('Validar e Ingresar'))!
      .click();
    backend.expectOne('/api/auth/login').flush(
      {
        error: {
          codigo: 'CUENTA_BLOQUEADA',
          mensaje: 'Acceso bloqueado temporalmente.',
          detalle: {
            bloqueado_hasta: '2026-11-16T15:00:00Z',
            ahora_servidor: '2026-11-16T12:00:00Z',
            segundos_restantes: 10800,
          },
        },
      },
      { status: 423, statusText: 'Locked' },
    );
    await fixture.whenStable();
    expect(pagina.querySelector('app-captcha')).toBeNull();
    expect(pagina.querySelector('[role="alert"]')?.textContent).toContain(
      'Acceso bloqueado temporalmente.',
    );
    expect(pagina.textContent).toContain('03:00:00');
    expect(pagina.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
    await enviar();
    backend.expectNone('/api/auth/login');
    backend.expectNone('/api/auth/captcha');
  });

  it('muestra el formulario con etiquetas accesibles y sin los extras quitados', async () => {
    await crearPagina();
    expect(pagina.querySelector('label[for="nombre-usuario"]')?.textContent).toContain('Usuario');
    expect(pagina.querySelector('label[for="contrasena"]')?.textContent).toContain('Contraseña');
    expect(pagina.textContent).not.toContain('Olvidó su contraseña');
    expect(pagina.textContent).not.toContain('Recordar equipo');
  });

  it('no envía nada si faltan datos y muestra los errores de los campos', async () => {
    await crearPagina();
    await enviar();
    backend.expectNone('/api/auth/login');
    expect(pagina.textContent).toContain('Escriba su usuario');
    expect(pagina.textContent).toContain('Escriba su contraseña');
  });

  it('inicia sesión y va al inicio', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'comandante.esart');
    escribir('#contrasena', 'Clave-1');
    await enviar();

    backend.expectOne('/api/auth/login').flush({
      usuario: {
        nombre_usuario: 'comandante.esart',
        nombre_completo: 'Comandante',
        rol: 'USUARIO',
      },
      expira_por_inactividad_segundos: 1800,
    });
    expect(navegarPorUrl).toHaveBeenCalledWith('/dashboard');
  });

  it('vuelve a la página pedida si es interna, pero nunca a otro sitio', async () => {
    await crearPagina({ volver: '//sitio-malicioso.com' });
    escribir('#nombre-usuario', 'comandante.esart');
    escribir('#contrasena', 'Clave-1');
    await enviar();
    backend.expectOne('/api/auth/login').flush({
      usuario: {
        nombre_usuario: 'comandante.esart',
        nombre_completo: 'Comandante',
        rol: 'USUARIO',
      },
      expira_por_inactividad_segundos: 1800,
    });
    expect(navegarPorUrl).toHaveBeenCalledWith('/dashboard');
  });

  it('muestra el mensaje genérico del servidor y vacía la contraseña', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'comandante.esart');
    escribir('#contrasena', 'mala');
    await enviar();

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
    await fixture.whenStable();

    expect(pagina.querySelector('[role="alert"]')?.textContent).toContain(
      'Usuario o contraseña incorrectos.',
    );
    expect(pagina.querySelector<HTMLInputElement>('#contrasena')!.value).toBe('');
    expect(navegarPorUrl).not.toHaveBeenCalled();
  });

  it('muestra la hora de desbloqueo cuando la cuenta está bloqueada', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'comandante.esart');
    escribir('#contrasena', 'mala');
    await enviar();

    backend.expectOne('/api/auth/login').flush(
      {
        error: {
          codigo: 'CUENTA_BLOQUEADA',
          mensaje: 'La cuenta está bloqueada temporalmente.',
          detalle: {
            bloqueado_hasta: '2026-11-18T17:30:00Z',
            ahora_servidor: '2026-11-18T14:30:00Z',
            segundos_restantes: 10800,
          },
        },
      },
      { status: 423, statusText: 'Locked' },
    );
    await fixture.whenStable();

    expect(pagina.textContent).toContain('La cuenta está bloqueada temporalmente.');
    expect(pagina.textContent).toContain('Desbloqueo estimado');
    expect(pagina.textContent).toContain('03:00:00');
    expect(pagina.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
    await enviar();
    backend.expectNone('/api/auth/login');
    backend.expectNone('/api/auth/captcha');
  });

  it('actualiza el plazo del servidor sin peticiones y permite acceso al terminar', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'cuenta.local');
    escribir('#contrasena', 'clave-local');
    await enviar();
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'performance'] });
    try {
      backend.expectOne('/api/auth/login').flush(
        {
          error: {
            codigo: 'CUENTA_BLOQUEADA',
            mensaje: 'Acceso bloqueado temporalmente.',
            detalle: {
              bloqueado_hasta: '2026-11-16T13:00:00Z',
              ahora_servidor: '2026-11-16T12:59:57Z',
              segundos_restantes: 3,
              captcha_requerido: true,
            },
          },
        },
        { status: 423, statusText: 'Locked' },
      );
      fixture.detectChanges();
      expect(pagina.textContent).toContain('00:00:03');
      vi.advanceTimersByTime(1000);
      fixture.detectChanges();
      expect(pagina.textContent).toContain('00:00:02');
      expect(pagina.querySelector('app-captcha')).toBeNull();
      backend.expectNone('/api/auth/login');
      backend.expectNone('/api/auth/captcha');
      vi.advanceTimersByTime(2000);
      fixture.detectChanges();
      expect(pagina.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(
        false,
      );
      expect(pagina.textContent).not.toContain('Acceso bloqueado temporalmente.');
      escribir('#contrasena', 'clave-local');
      pagina.querySelector('form')!.dispatchEvent(new Event('submit'));
      backend.expectOne('/api/auth/login').flush(
        {
          error: {
            codigo: 'CREDENCIALES_INVALIDAS',
            mensaje: 'No fue posible iniciar sesión.',
            detalle: { captcha_requerido: true },
          },
        },
        { status: 401, statusText: 'Unauthorized' },
      );
      fixture.detectChanges();
      expect(pagina.textContent).toContain('verificación CAPTCHA del servidor');
    } finally {
      fixture.destroy();
      vi.useRealTimers();
    }
  });

  it('avisa si el servidor no responde', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'comandante.esart');
    escribir('#contrasena', 'Clave-1');
    await enviar();
    backend.expectOne('/api/auth/login').error(new ProgressEvent('error'), { status: 0 });
    await fixture.whenStable();
    expect(pagina.textContent).toContain('No fue posible conectar con el servidor');
  });

  it('muestra el aviso de sesión expirada', async () => {
    await crearPagina({ motivo: 'sesion-expirada' });
    expect(pagina.textContent).toContain('Su sesión expiró por inactividad');
  });

  it('el botón del ojo muestra y oculta la contraseña', async () => {
    await crearPagina();
    const boton = pagina.querySelector<HTMLButtonElement>(
      'button[aria-label="Mostrar contraseña"]',
    )!;
    boton.click();
    await fixture.whenStable();
    expect(pagina.querySelector<HTMLInputElement>('#contrasena')!.type).toBe('text');
  });
});
