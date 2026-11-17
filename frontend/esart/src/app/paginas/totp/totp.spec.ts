import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { toDataURL } from 'qrcode';
import { Totp } from './totp';
vi.mock('qrcode', () => ({
  toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,iVBORw0KGgo='),
}));

describe('Totp', () => {
  let fixture: ComponentFixture<Totp>;
  let http: HttpTestingController;
  function crear(modo: 'CONFIGURAR' | 'LOGIN' = 'CONFIGURAR', vinculacionInicial = false) {
    TestBed.configureTestingModule({
      imports: [Totp],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(Totp);
    fixture.componentRef.setInput('modo', modo);
    fixture.componentRef.setInput('vinculacionInicial', vinculacionInicial);
    fixture.componentRef.setInput('volverAlInicioAlCerrar', false);
    fixture.componentRef.setInput('desafioId', 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa');
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  }
  function codigo(valor: string) {
    [...fixture.nativeElement.querySelectorAll('.totp-digitos input')].forEach((e, i) => {
      const input = e as HTMLInputElement;
      input.value = valor[i];
      input.dispatchEvent(new Event('input'));
    });
    fixture.detectChanges();
  }
  afterEach(() => http.verify());
  it('vincula durante el primer login sin sesión completa y retira el QR al confirmar', async () => {
    crear('CONFIGURAR', true);
    http.expectNone('/api/auth/totp/estado');
    const configuracion = http.expectOne('/api/auth/totp/login/configurar');
    expect(configuracion.request.body).toEqual({
      desafio_id: 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',
    });
    configuracion.flush({
      uri: 'otpauth://totp/ESART:prueba?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=ESART',
      expira_en: new Date(Date.now() + 120_000).toISOString(),
    });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#totp-contrasena')).toBeNull();
    expect(fixture.nativeElement.querySelector('.totp-qr')).not.toBeNull();
    codigo('012345');
    fixture.componentInstance.verificar();
    const solicitud = http.expectOne('/api/auth/totp/login/vincular');
    expect(solicitud.request.body.codigo).toBe('012345');
    solicitud.flush({
      usuario: { nombre_usuario: 'prueba', rol: 'USUARIO' },
      activo: true,
      codigos_recuperacion: ['0123456789abcdef0123456789abcdef'],
    });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.totp-qr')).toBeNull();
    expect(fixture.componentInstance.codigosRecuperacion()).toHaveLength(1);
  });
  it('cancelar la vinculación inicial no emite completado ni redirige al inicio', () => {
    crear('CONFIGURAR', true);
    http.expectOne('/api/auth/totp/login/configurar').flush(
      {
        error: {
          codigo: 'VERIFICACION_INVALIDA',
          mensaje: 'Desafío vencido. Inicie sesión otra vez.',
        },
      },
      { status: 401, statusText: 'Unauthorized' },
    );
    const recibido = vi.fn();
    const cancelado = vi.fn();
    fixture.componentInstance.completado.subscribe(recibido);
    fixture.componentInstance.cancelar.subscribe(cancelado);
    fixture.componentInstance.cerrar();
    expect(recibido).not.toHaveBeenCalled();
    expect(cancelado).toHaveBeenCalledOnce();
    expect(fixture.componentInstance.qr()).toBe('');
  });
  it('recupera login con código completo y espera la confirmación del servidor', async () => {
    crear('LOGIN');
    const recibido = vi.fn();
    fixture.componentInstance.completado.subscribe(recibido);
    fixture.componentInstance.usarRecuperacion.set(true);
    fixture.componentInstance.codigoRecuperacion.setValue('0123456789abcdef0123456789abcdef');
    fixture.componentInstance.verificar();
    const solicitud = http.expectOne('/api/auth/totp/login/confirmar');
    expect(solicitud.request.body.recuperacion).toBe(true);
    expect(solicitud.request.body.codigo).toBe('0123456789abcdef0123456789abcdef');
    expect(recibido).not.toHaveBeenCalled();
    solicitud.flush({ usuario: { nombre_usuario: 'prueba', rol: 'USUARIO' } });
    await fixture.whenStable();
    expect(recibido).toHaveBeenCalledWith({ modo: 'LOGIN' });
    expect(fixture.componentInstance.codigoRecuperacion.value).toBe('');
  });
  it('retiene los códigos de recuperación hasta confirmar guardado y los limpia al cerrar', async () => {
    crear();
    http.expectOne('/api/auth/totp/estado').flush({ configurado: false, activo: false });
    await fixture.whenStable();
    const componente = fixture.componentInstance;
    const recibido = vi.fn();
    componente.completado.subscribe(recibido);
    componente.pendiente.set(true);
    componente.expiraEn.set(Date.now() + 60_000);
    componente.digitos.setValue(['0', '1', '2', '3', '4', '5']);
    componente.verificar();
    http.expectOne('/api/auth/totp/confirmar').flush({
      activo: true,
      codigos_recuperacion: ['0123456789abcdef0123456789abcdef'],
    });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(recibido).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('0123456789abcdef0123456789abcdef');
    componente.confirmarGuardado();
    expect(recibido).toHaveBeenCalledWith({ modo: 'CONFIGURAR' });
    expect(componente.codigosRecuperacion()).toEqual([]);
    componente.codigosRecuperacion.set(['secreto']);
    componente.cerrar();
    expect(componente.codigosRecuperacion()).toEqual([]);
  });
  it('no borra la contraseña escrita mientras llega el estado inicial', async () => {
    crear();
    const campo = fixture.nativeElement.querySelector('#totp-contrasena') as HTMLInputElement;
    campo.value = 'entrada-solo-prueba';
    campo.dispatchEvent(new Event('input'));
    http.expectOne('/api/auth/totp/estado').flush({ configurado: false, activo: false });
    await fixture.whenStable();
    expect(campo.value).toBe('entrada-solo-prueba');
  });
  it('consulta estado sin obtener secretos', async () => {
    crear();
    http
      .expectOne('/api/auth/totp/estado')
      .flush({ configurado: false, activo: false, fecha_activacion: null });
    await fixture.whenStable();
    expect(fixture.componentInstance).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('CONFIGURAR AUTENTICADOR');
  });
  it('conserva ceros iniciales y solo completa login tras respuesta del servidor', async () => {
    crear('LOGIN');
    const recibido = vi.fn();
    fixture.componentInstance.completado.subscribe(recibido);
    codigo('012345');
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
    const r = http.expectOne('/api/auth/totp/login/confirmar');
    expect(r.request.body.codigo).toBe('012345');
    expect(recibido).not.toHaveBeenCalled();
    r.flush({
      usuario: { nombre_usuario: 'cuenta.local', nombre_completo: 'Cuenta', rol: 'USUARIO' },
      expira_por_inactividad_segundos: 1800,
    });
    await fixture.whenStable();
    expect(recibido).toHaveBeenCalledWith({ modo: 'LOGIN' });
  });
  it('genera QR local y lo retira al activar', async () => {
    crear();
    http.expectOne('/api/auth/totp/estado').flush({ configurado: false, activo: false });
    await fixture.whenStable();
    const campo = fixture.nativeElement.querySelector('#totp-contrasena') as HTMLInputElement;
    campo.value = 'clave-solo-prueba';
    campo.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    [...fixture.nativeElement.querySelectorAll('button')]
      .find((b: any) => b.textContent.toUpperCase().includes('CONFIGURAR AUTENTICADOR'))!
      .click();
    const uri = 'otpauth://totp/ESART:test?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=ESART';
    http
      .expectOne('/api/auth/totp/configurar')
      .flush({ uri, expira_en: new Date(Date.now() + 600_000).toISOString() });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(toDataURL).toHaveBeenCalledWith(uri, expect.anything());
    expect(fixture.nativeElement.querySelector('.totp-qr')).not.toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('GEZDGNBV');
    fixture.componentInstance.mostrarClave.set(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('GEZDGNBV');
    fixture.componentInstance.configurar();
    http.expectNone('/api/auth/totp/configurar');
    codigo('012345');
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
    http.expectOne('/api/auth/totp/confirmar').flush({ configurado: true, activo: true });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.totp-qr')).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('GEZDGNBV');
  });
  it('no genera QR ni permite configurar sin una sesión autorizada', async () => {
    crear();
    http
      .expectOne('/api/auth/totp/estado')
      .flush(
        { error: { codigo: 'NO_AUTENTICADO', mensaje: 'Debe iniciar sesión.' } },
        { status: 401, statusText: 'Unauthorized' },
      );
    await fixture.whenStable();
    fixture.componentInstance.formulario.controls.contrasena.setValue('solo-prueba');
    fixture.componentInstance.configurar();
    http.expectNone('/api/auth/totp/configurar');
    expect(fixture.componentInstance.qr()).toBe('');
  });
  it('retira los secretos al expirar y no confirma códigos expirados', async () => {
    crear();
    http.expectOne('/api/auth/totp/estado').flush({ configurado: false, activo: false });
    await fixture.whenStable();
    const componente = fixture.componentInstance;
    componente.pendiente.set(true);
    componente.claveManual.set('GEZDGNBV');
    componente.qr.set('data:image/png;base64,prueba-unitaria');
    componente.expiraEn.set(Date.now() - 1000);
    codigo('012345');
    componente.verificar();
    http.expectNone('/api/auth/totp/confirmar');
    await new Promise((r) => setTimeout(r, 1100));
    expect(componente.estadoVinculacion()).toBe('EXPIRADA');
    expect(componente.claveManual()).toBe('');
    expect(componente.qr()).toBe('');
  });
});
