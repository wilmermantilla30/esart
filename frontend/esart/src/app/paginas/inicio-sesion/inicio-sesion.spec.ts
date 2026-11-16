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

  async function crearPagina(parametros: Record<string, string> = {}) {
    navegarPorUrl = vi.fn().mockResolvedValue(true);
    TestBed.configureTestingModule({
      imports: [InicioSesion],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigateByUrl: navegarPorUrl } },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap(parametros) } } },
      ],
    });
    fixture = TestBed.createComponent(InicioSesion);
    backend = TestBed.inject(HttpTestingController);
    pagina = fixture.nativeElement as HTMLElement;
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
      usuario: { nombre_usuario: 'comandante.esart', nombre_completo: 'Comandante', rol: 'USUARIO' },
      expira_por_inactividad_segundos: 1800,
    });
    expect(navegarPorUrl).toHaveBeenCalledWith('/inicio');
  });

  it('vuelve a la página pedida si es interna, pero nunca a otro sitio', async () => {
    await crearPagina({ volver: '//sitio-malicioso.com' });
    escribir('#nombre-usuario', 'comandante.esart');
    escribir('#contrasena', 'Clave-1');
    await enviar();
    backend.expectOne('/api/auth/login').flush({
      usuario: { nombre_usuario: 'comandante.esart', nombre_completo: 'Comandante', rol: 'USUARIO' },
      expira_por_inactividad_segundos: 1800,
    });
    expect(navegarPorUrl).toHaveBeenCalledWith('/inicio');
  });

  it('muestra el mensaje genérico del servidor y vacía la contraseña', async () => {
    await crearPagina();
    escribir('#nombre-usuario', 'comandante.esart');
    escribir('#contrasena', 'mala');
    await enviar();

    backend
      .expectOne('/api/auth/login')
      .flush(
        { error: { codigo: 'CREDENCIALES_INVALIDAS', mensaje: 'Usuario o contraseña incorrectos.', detalle: null } },
        { status: 401, statusText: 'Unauthorized' },
      );
    await fixture.whenStable();

    expect(pagina.querySelector('[role="alert"]')?.textContent).toContain('Usuario o contraseña incorrectos.');
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
          codigo: 'USUARIO_BLOQUEADO',
          mensaje: 'La cuenta está bloqueada temporalmente.',
          detalle: { desbloqueo_estimado: '2026-11-18T17:30:00Z' },
        },
      },
      { status: 423, statusText: 'Locked' },
    );
    await fixture.whenStable();

    expect(pagina.textContent).toContain('La cuenta está bloqueada temporalmente.');
    expect(pagina.textContent).toContain('Desbloqueo estimado');
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
    const boton = pagina.querySelector<HTMLButtonElement>('button[aria-label="Mostrar contraseña"]')!;
    boton.click();
    await fixture.whenStable();
    expect(pagina.querySelector<HTMLInputElement>('#contrasena')!.type).toBe('text');
  });
});
