import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { SolicitudFirma } from './solicitud-firma';

const CANDIDATOS = [
  { usuario_id: 7, usuario: 'director', nombre: 'CR Juan Pérez Gómez', totp_activo: true },
  { usuario_id: 9, usuario: 'sin.totp', nombre: 'TC Ana Ruiz', totp_activo: false },
];
const FIRMANTE = {
  autorizacion_id: 'a1',
  usuario_id: 7,
  nombre: 'CR Juan Pérez Gómez',
  cargo: 'Director de la Escuela de Artillería',
  tipo: 'CERTIFICACION',
};

describe('SolicitudFirma: autorizar firmante desde la ventana', () => {
  let fixture: ComponentFixture<SolicitudFirma>;
  let http: HttpTestingController;
  const pagina = () => fixture.nativeElement as HTMLElement;

  async function crear(puedeCrearFirma: boolean) {
    await TestBed.configureTestingModule({
      imports: [SolicitudFirma],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: SesionService,
          useValue: {
            puede: (codigo: string, operacion: string) =>
              puedeCrearFirma && codigo === 'FIRMA_DOCUMENTOS' && operacion === 'crear',
          },
        },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(SolicitudFirma);
    fixture.componentRef.setInput('cedula', '9950000148');
    fixture.componentRef.setInput('tipo', 'CERTIFICACION');
    fixture.detectChanges();
  }

  afterEach(() => http.verify());

  it('con "Firma documental" (crear) y sin firmantes abre el formulario y autoriza para ambos tipos', async () => {
    await crear(true);
    http.expectOne('/api/firma/firmantes?tipo=CERTIFICACION').flush([]);
    http.expectOne('/api/firma/candidatos').flush(CANDIDATOS);
    fixture.detectChanges();

    const opciones = [
      ...pagina().querySelectorAll<HTMLOptionElement>('#candidato-firmante option'),
    ];
    expect(opciones.find((o) => o.value === '9')?.disabled).toBe(true); // sin autenticador
    expect(opciones.find((o) => o.value === '9')?.textContent).toContain('sin autenticador');

    const selector = pagina().querySelector<HTMLSelectElement>('#candidato-firmante')!;
    selector.value = '7';
    selector.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    [...pagina().querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Autorizar firmante'))!
      .click();

    // En serie: la segunda autorización sale solo cuando termina la primera.
    const primera = http.expectOne('/api/firma/autorizaciones');
    expect(primera.request.body).toEqual({
      usuario_id: 7,
      tipo: 'CERTIFICACION',
      cargo: 'Director de la Escuela de Artillería',
    });
    primera.flush({}, { status: 201, statusText: 'Created' });
    const segunda = http.expectOne('/api/firma/autorizaciones');
    expect(segunda.request.body).toEqual({
      usuario_id: 7,
      tipo: 'OFICIO_REMISORIO',
      cargo: 'Director de la Escuela de Artillería',
    });
    segunda.flush({}, { status: 201, statusText: 'Created' });
    http.expectOne('/api/firma/firmantes?tipo=CERTIFICACION').flush([FIRMANTE]);
    fixture.detectChanges();
    expect(pagina().textContent).toContain('Generar PDF y código QR');
    expect(pagina().textContent).toContain('CR Juan Pérez Gómez — Director');
  });

  it('sin el permiso solo explica que un administrador debe autorizar', async () => {
    await crear(false);
    http.expectOne('/api/firma/firmantes?tipo=CERTIFICACION').flush([]);
    fixture.detectChanges();
    http.expectNone('/api/firma/candidatos');
    expect(pagina().textContent).toContain('No hay firmantes autorizados');
    expect(pagina().querySelector('#candidato-firmante')).toBeNull();
  });
});
