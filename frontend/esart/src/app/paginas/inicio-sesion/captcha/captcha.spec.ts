import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Captcha } from './captcha';

describe('CAPTCHA local', () => {
  let fixture: ComponentFixture<Captcha>;
  let http: HttpTestingController;
  const reto = { captcha_id: 'a'.repeat(43), imagen_png_base64: 'iVBORw0KGgo=', longitud: 6,
    expira_en: '2026-11-16T12:05:00Z' };

  beforeEach(async () => {
    TestBed.configureTestingModule({ imports: [Captcha],
      providers: [provideHttpClient(), provideHttpClientTesting()] });
    fixture = TestBed.createComponent(Captcha);
    fixture.componentRef.setInput('nombreUsuario', 'cuenta.local');
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const solicitud = http.expectOne('/api/auth/captcha');
    expect(solicitud.request.headers.get('X-ESART-Usuario')).toBe('cuenta.local');
    solicitud.flush(reto);
    await fixture.whenStable();
  });
  afterEach(() => http.verify());

  it('muestra PNG del servidor sin texto correcto ni generador local', () => {
    const pagina = fixture.nativeElement as HTMLElement;
    const imagen = pagina.querySelector<HTMLImageElement>('img[width="312"]')!;
    expect(imagen.src).toBe('data:image/png;base64,' + reto.imagen_png_base64);
    expect(pagina.textContent).not.toContain('7BA9K4');
    expect(pagina.querySelector('[role="dialog"]')?.getAttribute('aria-modal')).toBe('true');
  });

  it('envía ID y respuesta sin compararla ni emitir un booleano de validación', async () => {
    const recibir = vi.fn();
    fixture.componentInstance.enviar.subscribe(recibir);
    const pagina = fixture.nativeElement as HTMLElement;
    const campo = pagina.querySelector<HTMLInputElement>('#codigo-captcha')!;
    campo.value = 'ACD346'; campo.dispatchEvent(new Event('input'));
    const casilla = pagina.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    casilla.click();
    await fixture.whenStable();
    const boton = [...pagina.querySelectorAll<HTMLButtonElement>('button')]
      .find(b => b.textContent?.includes('Validar e Ingresar'))!;
    boton.click();
    expect(recibir).toHaveBeenCalledWith({ id: reto.captcha_id, respuesta: 'ACD346' });
    http.expectNone('/api/auth/validar-captcha');
  });

  it('regenerar remite el ID anterior para invalidarlo en el servidor', async () => {
    const pagina = fixture.nativeElement as HTMLElement;
    pagina.querySelector<HTMLButtonElement>('button[aria-label="Generar otro código"]')!.click();
    const solicitud = http.expectOne('/api/auth/captcha');
    expect(solicitud.request.headers.get('X-ESART-Captcha-Anterior')).toBe(reto.captcha_id);
    solicitud.flush({ ...reto, captcha_id: 'b'.repeat(43) });
    await fixture.whenStable();
  });
});
