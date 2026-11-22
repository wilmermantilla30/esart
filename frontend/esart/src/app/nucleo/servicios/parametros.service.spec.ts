import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Plantilla, ValoresRegla } from '../modelos/parametros';
import { ParametrosService, nombreDesdeCabecera } from './parametros.service';

describe('ParametrosService', () => {
  let servicio: ParametrosService;
  let backend: HttpTestingController;

  const valores: ValoresRegla = {
    cursos_habilitantes: ['SACLI'],
    meses_vigencia_reentrenamiento: 12,
    dias_alerta_vencimiento: 60,
    exige_apto_para_disparar: true,
  };
  const plantilla: Plantilla = {
    id: 7,
    nombre_oficial: 'Plantilla de cargue',
    nombre_archivo: 'Plantilla_Cargue.xlsx',
    formato: 'XLSX',
    version: 'v1.0',
    descripcion: '',
    tamano_bytes: 10,
    sha256: 'a'.repeat(64),
    subido_en: '2026-11-17T20:00:00Z',
    subido_por: 'admin.esart',
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(ParametrosService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('guarda la regla con la versión editada y el código del autenticador', () => {
    servicio.guardarRegla(valores, '2026-11-17T20:00:00Z', '123456').subscribe();
    const peticion = backend.expectOne('/api/parametros/habilitacion');
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual({
      ...valores,
      version: '2026-11-17T20:00:00Z',
      codigo_totp: '123456',
    });
    peticion.flush({});
  });

  it('guarda la nota mínima con la versión editada y el código del autenticador (S2-10)', () => {
    servicio.guardarNotaMinima(3.5, '2026-11-21T20:00:00Z', '654321').subscribe();
    const peticion = backend.expectOne('/api/parametros/nota-minima');
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual({
      valor: 3.5,
      version: '2026-11-21T20:00:00Z',
      codigo_totp: '654321',
    });
    peticion.flush({});
  });

  it('simula sin guardar (POST a /simular)', () => {
    servicio.simularRegla(valores).subscribe();
    const peticion = backend.expectOne('/api/parametros/habilitacion/simular');
    expect(peticion.request.method).toBe('POST');
    peticion.flush({});
  });

  it('filtra plantillas por formato solo si se indica', () => {
    servicio.listarPlantillas('PDF').subscribe();
    backend.expectOne('/api/parametros/plantillas?formato=PDF').flush([]);
    servicio.listarPlantillas().subscribe();
    backend.expectOne('/api/parametros/plantillas').flush([]);
  });

  it('publica la plantilla como multipart con sus datos', () => {
    const archivo = new File(['x'], 'acta.docx');
    servicio
      .publicarPlantilla({ archivo, nombre_oficial: 'Acta', version: 'v2', descripcion: 'Uso' })
      .subscribe();
    const peticion = backend.expectOne('/api/parametros/plantillas');
    const datos = peticion.request.body as FormData;
    expect(datos.get('archivo')).toBe(archivo);
    expect(datos.get('nombre_oficial')).toBe('Acta');
    expect(datos.get('version')).toBe('v2');
    peticion.flush(plantilla);
  });

  it('descarga el archivo con el nombre que envía el servidor', () => {
    let nombre = '';
    servicio.descargarPlantilla(plantilla).subscribe((archivo) => (nombre = archivo.nombre));
    backend.expectOne('/api/parametros/plantillas/7/descarga').flush(new Blob(['x']), {
      headers: {
        'Content-Disposition': "attachment; filename*=UTF-8''Plantilla%20C%C3%A9dula.xlsx",
      },
    });
    expect(nombre).toBe('Plantilla Cédula.xlsx');
  });

  it('usa el nombre guardado si la cabecera no trae uno legible', () => {
    expect(nombreDesdeCabecera(null, 'respaldo.pdf')).toBe('respaldo.pdf');
    expect(nombreDesdeCabecera("attachment; filename*=UTF-8''%E0%A4%A", 'respaldo.pdf')).toBe(
      'respaldo.pdf',
    );
  });
});
