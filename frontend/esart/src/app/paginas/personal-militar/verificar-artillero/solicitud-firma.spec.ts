import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SolicitudFirma, esDireccionLocal, urlParaCelular } from './solicitud-firma';

const FIRMANTE = {
  autorizacion_id: 'a1',
  usuario_id: 7,
  nombre: 'CR Juan Pérez Gómez',
  cargo: 'Director de la Escuela de Artillería',
  tipo: 'CERTIFICACION',
};
const SOLICITUD = {
  solicitud_id: 's1',
  documento_id: 'd1',
  url_firma: 'http://192.168.1.50:4200/firma/tokenDeUnSoloUso1234567890',
  url_publica_configurada: true,
  expira_en: '2026-11-19T10:15:00Z',
  firmante: FIRMANTE.nombre,
  cargo: FIRMANTE.cargo,
};

describe('Dirección del QR', () => {
  it('usa la dirección configurada o arma la del navegador', () => {
    expect(urlParaCelular(SOLICITUD, 'http://localhost:4200')).toBe(SOLICITUD.url_firma);
    expect(
      urlParaCelular(
        { url_firma: '/firma/abc', url_publica_configurada: false },
        'http://10.0.0.5:4200',
      ),
    ).toBe('http://10.0.0.5:4200/firma/abc');
  });

  it('detecta direcciones que el celular no puede abrir', () => {
    expect(esDireccionLocal('http://localhost:4200/firma/x')).toBe(true);
    expect(esDireccionLocal('http://127.0.0.1:4200/firma/x')).toBe(true);
    expect(esDireccionLocal('http://192.168.1.50:4200/firma/x')).toBe(false);
  });
});

describe('SolicitudFirma', () => {
  let fixture: ComponentFixture<SolicitudFirma>;
  let http: HttpTestingController;
  const pagina = () => fixture.nativeElement as HTMLElement;
  const boton = (texto: string) =>
    [...pagina().querySelectorAll('button')].find((b) => b.textContent?.includes(texto))!;

  beforeEach(async () => {
    vi.useFakeTimers();
    await TestBed.configureTestingModule({
      imports: [SolicitudFirma],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(SolicitudFirma);
    fixture.componentRef.setInput('cedula', '1024589632');
    fixture.componentRef.setInput('tipo', 'CERTIFICACION');
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  it('sin firmantes autorizados explica qué falta', () => {
    http.expectOne('/api/firma/firmantes?tipo=CERTIFICACION').flush([]);
    fixture.detectChanges();
    expect(pagina().textContent).toContain('No hay firmantes autorizados');
  });

  it('genera el QR, consulta el estado y ofrece el PDF firmado', async () => {
    http.expectOne('/api/firma/firmantes?tipo=CERTIFICACION').flush([FIRMANTE]);
    fixture.detectChanges();
    boton('Generar PDF y código QR').click();
    const peticion = http.expectOne('/api/firma/solicitudes');
    expect(peticion.request.body).toEqual({
      cedula: '1024589632',
      tipo: 'CERTIFICACION',
      autorizacion_id: 'a1',
    });
    peticion.flush(SOLICITUD);
    http
      .expectOne('/api/firma/solicitudes/s1')
      .flush({ ...SOLICITUD, estado: 'PENDIENTE', estado_documento: 'PENDIENTE_FIRMA' });
    fixture.detectChanges();
    expect(pagina().textContent).toContain('Esperando que se escanee');
    expect(pagina().textContent).not.toContain('localhost');

    vi.advanceTimersByTime(3000);
    http
      .expectOne('/api/firma/solicitudes/s1')
      .flush({ ...SOLICITUD, estado: 'APROBADA', estado_documento: 'FIRMADO' });
    fixture.detectChanges();
    expect(pagina().textContent).toContain('Documento firmado por CR Juan Pérez Gómez');
    // Al quedar aprobada deja de consultar.
    vi.advanceTimersByTime(9000);
    http.expectNone('/api/firma/solicitudes/s1');
    expect(boton('Descargar PDF firmado')).toBeTruthy();
  });

  it('sin p0018/p0019 muestra solo el mensaje del backend', () => {
    http.expectOne('/api/firma/firmantes?tipo=CERTIFICACION').flush(
      {
        error: {
          codigo: 'FIRMA_NO_DISPONIBLE',
          mensaje:
            'La firma desde el celular aún no está habilitada en la base de datos (faltan las migraciones p0018 y p0019).',
          detalle: null,
        },
      },
      { status: 503, statusText: 'Unavailable' },
    );
    fixture.detectChanges();
    expect(pagina().querySelector('[role="alert"]')?.textContent).toContain('p0018 y p0019');
    expect(pagina().textContent).not.toContain('No hay firmantes autorizados');
  });

  it('muestra el error del backend (firmante sin autenticador)', () => {
    http.expectOne('/api/firma/firmantes?tipo=CERTIFICACION').flush([FIRMANTE]);
    fixture.detectChanges();
    boton('Generar PDF y código QR').click();
    http.expectOne('/api/firma/solicitudes').flush(
      {
        error: {
          codigo: 'FIRMANTE_SIN_AUTENTICADOR',
          mensaje: 'El firmante debe tener activo el autenticador de ESART para firmar.',
          detalle: null,
        },
      },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();
    expect(pagina().querySelector('[role="alert"]')?.textContent).toContain('autenticador');
  });
});
