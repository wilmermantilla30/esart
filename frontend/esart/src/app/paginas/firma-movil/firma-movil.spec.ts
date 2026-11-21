import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';

import { FirmaMovil } from './firma-movil';

const TOKEN = 'tokenDeUnSoloUso1234567890abcdefghij';
const RESUMEN = {
  estado: 'ABIERTA',
  tipo: 'CERTIFICACION',
  numero: 'ESART-20261119-ABC123',
  artillero: 'SV Carlos Andrés Colorado Gil',
  firmante: 'CR Juan Pérez Gómez',
  cargo: 'Director de la Escuela de Artillería',
  expira_en: '2026-11-19T10:15:00Z',
  texto_consentimiento: 'Declaro que revisé el documento.',
};

describe('FirmaMovil (página del celular)', () => {
  let fixture: ComponentFixture<FirmaMovil>;
  let http: HttpTestingController;
  const pagina = () => fixture.nativeElement as HTMLElement;
  const botonFirmar = () =>
    [...pagina().querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Firmar documento'),
    )!;

  beforeEach(async () => {
    // jsdom no dibuja en canvas: se simula lo necesario.
    const contexto = {
      scale() {},
      beginPath() {},
      moveTo() {},
      lineTo() {},
      stroke() {},
      clearRect() {},
    };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(contexto as never);
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(
      'data:image/png;base64,AAAA',
    );
    await TestBed.configureTestingModule({
      imports: [FirmaMovil],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ token: TOKEN }) } },
        },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(FirmaMovil);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function abrir(resumen = RESUMEN) {
    http.expectOne(`/api/firma-movil/${TOKEN}`).flush(resumen);
    fixture.detectChanges();
  }

  function dibujar() {
    const lienzo = pagina().querySelector('canvas')!;
    const evento = (tipo: string, x: number) =>
      Object.assign(new MouseEvent(tipo, { clientX: x, clientY: 20, bubbles: true }), {
        pointerId: 1,
      });
    lienzo.dispatchEvent(evento('pointerdown', 10));
    lienzo.dispatchEvent(evento('pointermove', 60));
    lienzo.dispatchEvent(evento('pointerup', 60));
    fixture.detectChanges();
  }

  it('muestra el documento, el firmante y el enlace al borrador', () => {
    abrir();
    expect(pagina().textContent).toContain('SV Carlos Andrés Colorado Gil');
    expect(pagina().textContent).toContain('CR Juan Pérez Gómez');
    expect(pagina().querySelector('a')?.getAttribute('href')).toBe(`/api/firma-movil/${TOKEN}/pdf`);
  });

  it('solo permite firmar con trazo, aceptación y código de 6 dígitos', () => {
    abrir();
    expect(botonFirmar().disabled).toBe(true);
    dibujar();
    const casilla = pagina().querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    casilla.click();
    fixture.detectChanges();
    expect(botonFirmar().disabled).toBe(true);
    const codigo = pagina().querySelector<HTMLInputElement>('input[inputmode="numeric"]')!;
    codigo.value = '12a34-56';
    codigo.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(botonFirmar().disabled).toBe(false);

    botonFirmar().click();
    const peticion = http.expectOne(`/api/firma-movil/${TOKEN}/firmar`);
    expect(peticion.request.body).toEqual({
      rubrica_png: 'data:image/png;base64,AAAA',
      codigo_totp: '123456',
      acepto: true,
    });
    peticion.flush({ estado: 'APROBADA', codigo_verificacion: 'F-1A2B3C4D' });
    fixture.detectChanges();
    expect(pagina().textContent).toContain('Documento firmado');
    expect(pagina().textContent).toContain('F-1A2B3C4D');
  });

  it('un código inválido muestra el error y limpia el campo', () => {
    abrir();
    dibujar();
    pagina().querySelector<HTMLInputElement>('input[type="checkbox"]')!.click();
    const codigo = pagina().querySelector<HTMLInputElement>('input[inputmode="numeric"]')!;
    codigo.value = '000000';
    codigo.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    botonFirmar().click();
    http
      .expectOne(`/api/firma-movil/${TOKEN}/firmar`)
      .flush(
        {
          error: {
            codigo: 'TOTP_INVALIDO',
            mensaje: 'Código del autenticador inválido o ya utilizado.',
            detalle: null,
          },
        },
        { status: 422, statusText: 'Unprocessable' },
      );
    fixture.detectChanges();
    expect(pagina().querySelector('[role="alert"]')?.textContent).toContain('inválido');
    expect(codigo.value).toBe('');
  });

  it('una solicitud vencida no muestra el formulario', () => {
    abrir({ ...RESUMEN, estado: 'EXPIRADA' });
    expect(pagina().textContent).toContain('ya no está disponible');
    expect(pagina().querySelector('canvas')).toBeNull();
  });
});
