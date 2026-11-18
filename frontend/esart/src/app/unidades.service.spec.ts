import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { UnidadesService } from './unidades.service';

describe('UnidadesService', () => {
  it('consulta el endpoint real y conserva identificadores como cadenas', () => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    const servicio = TestBed.inject(UnidadesService);
    const http = TestBed.inject(HttpTestingController);
    let respuesta: unknown;
    servicio.listar().subscribe(x => respuesta = x);
    const solicitud = http.expectOne('/api/catalogos/unidades');
    expect(solicitud.request.method).toBe('GET');
    // Prueba del contrato de transporte; no inserta registros en PostgreSQL.
    solicitud.flush([{ id: '9223372036854775807' }]);
    expect((respuesta as { id: string }[])[0].id).toBe('9223372036854775807');
    http.verify();
  });
});
