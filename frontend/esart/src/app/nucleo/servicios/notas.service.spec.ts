import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { NotasService } from './notas.service';

describe('NotasService (S2-12)', () => {
  let servicio: NotasService;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(NotasService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('sube la planilla como multipart al curso y la materia', () => {
    const archivo = new File(['x'], 'notas.xlsx');
    servicio.subir(18, 42, archivo).subscribe();
    const peticion = backend.expectOne('/api/notas/entregas/18/42');
    expect(peticion.request.method).toBe('POST');
    expect((peticion.request.body as FormData).get('archivo')).toBe(archivo);
    peticion.flush({});
  });

  it('descarga la plantilla con el nombre que envía el backend', () => {
    let nombre = '';
    servicio.descargarPlantilla(18, 42).subscribe((archivo) => (nombre = archivo.nombre));
    backend.expectOne('/api/notas/plantilla/18/42').flush(new Blob(['x']), {
      headers: { 'Content-Disposition': "attachment; filename*=UTF-8''Notas_SIM_MAT-001.xlsx" },
    });
    expect(nombre).toBe('Notas_SIM_MAT-001.xlsx');
  });
});
