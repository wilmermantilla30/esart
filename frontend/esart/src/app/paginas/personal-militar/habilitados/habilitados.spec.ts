import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { PaginaHabilitacion } from '../../../nucleo/modelos/verificacion';
import { Habilitados } from './habilitados';

const PAGINA: PaginaHabilitacion = {
  elementos: [
    {
      numero_documento: '9900000005',
      nombre_completo: 'Jorge Iván Díaz Moreno',
      grado: 'CP',
      unidad_militar_sigla: 'SIM-GRUAR1',
      activo: true,
      resultado: 'NO_APTO',
      motivos: ['Reentrenamiento vencido el 17-sep-2026.'],
      curso_habilitante: null,
      reentrenamiento_vence: '2026-09-17',
      estado_reentrenamiento: 'VENCIDO',
    },
  ],
  pagina: 1,
  tamano_pagina: 25,
  total_elementos: 1,
  total_paginas: 1,
};

describe('Habilitados', () => {
  it('carga el listado y muestra estado y motivos de cada artillero', async () => {
    TestBed.configureTestingModule({
      imports: [Habilitados],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const fixture = TestBed.createComponent(Habilitados);
    const backend = TestBed.inject(HttpTestingController);

    const peticion = backend.expectOne((p) => p.url === '/api/verificar/habilitacion');
    expect(peticion.request.params.get('pagina')).toBe('1');
    expect(peticion.request.params.has('estado')).toBe(false); // "Todos" no envía filtro.
    peticion.flush(PAGINA);
    await fixture.whenStable();

    const pagina = fixture.nativeElement as HTMLElement;
    expect(pagina.textContent).toContain('Jorge Iván Díaz Moreno');
    expect(pagina.textContent).toContain('NO APTO');
    expect(pagina.textContent).toContain('Reentrenamiento vencido el 17-sep-2026.');
    expect(pagina.textContent).toContain('1 resultado(s)');
    backend.verify();
  });
});
