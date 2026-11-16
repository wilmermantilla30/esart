import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { RespuestaVerificacion } from '../../../nucleo/modelos/verificacion';
import { VerificarArtillero } from './verificar-artillero';

const APTO_POR_VENCER: RespuestaVerificacion = {
  artillero: {
    numero_documento: '9900000004',
    nombre_completo: 'Diana Carolina Ruiz Pardo',
    grado: 'SS',
    categoria: 'SUBOFICIAL',
    unidad_militar: { sigla: 'SIM-ESART', nombre: 'Escuela de Artillería (simulado)' },
    estado_servicio: 'ACTIVO',
  },
  resultado: 'APTO',
  fecha_verificacion: '2026-11-16T17:00:00Z',
  criterios: [
    { descripcion: 'Estado de servicio activo', tipo: 'OBLIGATORIO', cumple: true, detalle: null, motivo: null },
    { descripcion: 'Curso habilitante aprobado (SACLI o SACME)', tipo: 'ALTERNATIVO', cumple: false, detalle: null, motivo: 'No tiene curso SACLI o SACME aprobado.' },
    { descripcion: 'Reentrenamiento vigente', tipo: 'ALTERNATIVO', cumple: true, detalle: 'Vigente hasta el 16-dic-2026 (faltan 30 días).', motivo: null },
  ],
  motivos: [],
  alerta: 'El reentrenamiento vence el 16-dic-2026 (faltan 30 días). Planee el próximo reentrenamiento.',
  cursos: [],
  reentrenamientos: [
    { numero_certificado: 'SIM-CERT-9900000004', tipo: 'OBUS', calibre: '105MM', fecha_expedicion: '2025-12-16', fecha_vencimiento: '2026-12-16', estado: 'POR_VENCER' },
  ],
};

describe('VerificarArtillero', () => {
  let fixture: ComponentFixture<VerificarArtillero>;
  let pagina: HTMLElement;
  let backend: HttpTestingController;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      imports: [VerificarArtillero],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(VerificarArtillero);
    pagina = fixture.nativeElement as HTMLElement;
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  async function verificar(cedula: string) {
    const campo = pagina.querySelector<HTMLInputElement>('#cedula')!;
    campo.value = cedula;
    campo.dispatchEvent(new Event('input'));
    pagina.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  it('no consulta con una cédula inválida', async () => {
    await verificar('abc');
    backend.expectNone(() => true);
    expect(pagina.textContent).toContain('Escriba solo números');
  });

  it('muestra APTO, la alerta de vencimiento y los criterios', async () => {
    await verificar('9.900.000.004');
    backend.expectOne('/api/verificar/artillero/9.900.000.004').flush(APTO_POR_VENCER);
    await fixture.whenStable();

    expect(pagina.textContent).toContain('Diana Carolina Ruiz Pardo');
    expect(pagina.textContent).toContain('APTO');
    expect(pagina.querySelector('[role="status"]')?.textContent).toContain('Planee el próximo reentrenamiento');
    expect(pagina.textContent).toContain('Basta con uno');
    expect(pagina.textContent).toContain('No tiene curso SACLI o SACME aprobado.');
    expect(pagina.textContent).toContain('SIM-CERT-9900000004');
  });

  it('muestra el mensaje del servidor si no existe el militar', async () => {
    await verificar('1111111111');
    backend
      .expectOne('/api/verificar/artillero/1111111111')
      .flush(
        { error: { codigo: 'ARTILLERO_NO_ENCONTRADO', mensaje: 'No se encontró un militar con esa cédula.', detalle: null } },
        { status: 404, statusText: 'Not Found' },
      );
    await fixture.whenStable();
    expect(pagina.querySelector('[role="alert"]')?.textContent).toContain('No se encontró un militar con esa cédula.');
  });
});
