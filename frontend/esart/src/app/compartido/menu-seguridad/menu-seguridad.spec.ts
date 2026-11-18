import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { MenuSeguridad } from './menu-seguridad';

describe('Menú de seguridad de la llave', () => {
  function crear() {
    TestBed.configureTestingModule({
      imports: [MenuSeguridad],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const fixture = TestBed.createComponent(MenuSeguridad);
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const pagina = fixture.nativeElement as HTMLElement;
    const llave = pagina.querySelector<HTMLButtonElement>('.seguridad-llave')!;
    function abrir(estado = { configurado: false, activo: false, estado: 'NO_CONFIGURADO' }) {
      llave.click();
      http.expectOne('/api/auth/totp/estado').flush(estado);
      fixture.detectChanges();
    }
    return { fixture, http, pagina, llave, abrir };
  }

  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('consulta solo el estado al abrir; conserva cambio de contraseña sin crear secretos', () => {
    const { abrir, pagina, http, llave } = crear();
    http.expectNone('/api/auth/totp/estado');
    abrir();
    expect(llave.getAttribute('aria-expanded')).toBe('true');
    expect(pagina.textContent).toContain('No configurado');
    expect(pagina.textContent).toContain('Configurar autenticador');
    expect(pagina.querySelector('a')?.getAttribute('href')).toBe('/cambiar-contrasena');
    http.expectNone('/api/auth/totp/configurar');
  });

  it('identifica pendiente y abre el mismo diálogo sin navegar ni generar QR sin contraseña', () => {
    const { abrir, pagina, fixture, http } = crear();
    const navegar = vi.spyOn(TestBed.inject(Router), 'navigateByUrl');
    abrir({ configurado: true, activo: false, estado: 'PENDIENTE' });
    expect(pagina.textContent).toContain('Completar configuración');
    pagina.querySelector<HTMLButtonElement>('.seguridad-opcion[type="button"]')!.click();
    fixture.detectChanges();
    http
      .expectOne('/api/auth/totp/estado')
      .flush({ configurado: true, activo: false, estado: 'PENDIENTE' });
    fixture.detectChanges();
    expect(pagina.querySelector('app-totp [role="dialog"]')).toBeTruthy();
    http.expectNone('/api/auth/totp/configurar');
    pagina.querySelector<HTMLButtonElement>('.totp-cerrar')!.click();
    fixture.detectChanges();
    http
      .expectOne('/api/auth/totp/estado')
      .flush({ configurado: true, activo: false, estado: 'PENDIENTE' });
    expect(navegar).not.toHaveBeenCalled();
    expect(pagina.querySelector('app-totp')).toBeNull();
  });

  it('muestra administración para un factor activo sin solicitar el secreto', () => {
    const { abrir, pagina, http } = crear();
    abrir({ configurado: true, activo: true, estado: 'ACTIVO' });
    expect(pagina.textContent).toContain('Autenticador activo');
    expect(pagina.textContent).toContain('Administrar autenticador');
    expect(pagina.textContent).not.toContain('Configurar autenticador');
    http.expectNone('/api/auth/totp/configurar');
  });

  it('no confunde un factor revocado con uno pendiente', () => {
    const { abrir, pagina } = crear();
    abrir({ configurado: true, activo: false, estado: 'REVOCADO' });
    expect(pagina.textContent).toContain('Autenticador revocado');
    expect(pagina.textContent).toContain('Configurar autenticador');
    expect(pagina.textContent).not.toContain('Completar configuración');
  });

  it('no inventa acciones de recuperación para un estado bloqueado', () => {
    const { abrir, pagina } = crear();
    abrir({ configurado: true, activo: false, estado: 'BLOQUEADO' });
    expect(pagina.textContent).toContain('Autenticador bloqueado');
    expect(pagina.querySelector('#seguridad-opciones button')).toBeNull();
  });

  it('ante un error permite reconsultar sin revelar el detalle interno ni abrir configuración', () => {
    const { llave, http, fixture, pagina } = crear();
    llave.click();
    http
      .expectOne('/api/auth/totp/estado')
      .flush({ mensaje: 'detalle interno privado' }, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(pagina.textContent).toContain('Estado no disponible');
    expect(pagina.textContent).not.toContain('detalle interno privado');
    pagina.querySelector<HTMLButtonElement>('#seguridad-opciones button')!.click();
    http.expectOne('/api/auth/totp/estado').flush({ configurado: false, activo: false });
    fixture.detectChanges();
    expect(pagina.textContent).toContain('Configurar autenticador');
    expect(pagina.querySelector('app-totp')).toBeNull();
  });

  it('cierra con Escape o clic exterior', () => {
    const { abrir, llave, fixture, pagina } = crear();
    abrir();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();
    expect(llave.getAttribute('aria-expanded')).toBe('false');
    abrir();
    document.body.click();
    fixture.detectChanges();
    expect(pagina.querySelector('#seguridad-opciones')).toBeNull();
  });
});
