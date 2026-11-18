import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ImportacionExcelService } from './importacion-excel.service';

describe('ImportacionExcelService', () => {
  it('usa el endpoint documentado y el campo multipart archivo sin fijar Content-Type', () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const servicio = TestBed.inject(ImportacionExcelService);
    const http = TestBed.inject(HttpTestingController);
    const archivo = new File(['Excel original'], 'seleccion.xlsx');
    servicio
      .importar(archivo, 'CARGUE_PERSONAL', {
        tipo_curso_id: 3,
        nombre_curso: 'Curso básico',
        comandante_id: 8,
        fecha_inicio: '2026-02-01',
        fecha_fin: '2026-03-01',
        estado_curso: 'CULMINADO',
        observacion_curso: 'Sin novedad',
      })
      .subscribe();
    const peticion = http.expectOne('/api/importaciones/excel');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body.get('archivo').name).toBe('seleccion.xlsx');
    expect(peticion.request.body.get('archivo')).toBe(archivo);
    expect(peticion.request.body.get('hoja')).toBe('CARGUE_PERSONAL');
    expect(peticion.request.body.get('comandante_id')).toBe('8');
    expect(peticion.request.body.get('fecha_fin')).toBe('2026-03-01');
    expect(peticion.request.body.get('observacion_curso')).toBe('Sin novedad');
    expect(peticion.request.body.has('codigo_totp')).toBe(false);
    expect(peticion.request.headers.has('Content-Type')).toBe(false);
    peticion.flush({
      estado: 'APLICADA',
      importacion_id: 'real',
      filas_totales: 1,
      filas_validas: 1,
      filas_rechazadas: 0,
    });
    http.verify();
  });
});
