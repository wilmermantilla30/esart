import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { CursosService } from './cursos.service';

describe('CursosService (S2-02)', () => {
  let servicio: CursosService;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(CursosService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('lista con los filtros que tienen valor', () => {
    servicio.listar({ estado: 'EN_CURSO', tipo: '', texto: '  SIM ' }).subscribe();
    backend.expectOne('/api/cursos?estado=EN_CURSO&texto=SIM').flush([]);
  });

  it('asigna o quita el instructor de una materia con PUT', () => {
    servicio.asignarInstructor(5, 42, 9).subscribe();
    const asignar = backend.expectOne('/api/cursos/5/materias/42/instructor');
    expect(asignar.request.method).toBe('PUT');
    expect(asignar.request.body).toEqual({ instructor_id: 9 });
    asignar.flush({});

    servicio.asignarInstructor(5, 42, null).subscribe();
    const quitar = backend.expectOne('/api/cursos/5/materias/42/instructor');
    expect(quitar.request.body).toEqual({ instructor_id: null });
    quitar.flush({});
  });

  it('asigna la malla vigente con POST', () => {
    servicio.asignarMallaVigente(5).subscribe();
    const peticion = backend.expectOne('/api/cursos/5/malla');
    expect(peticion.request.method).toBe('POST');
    peticion.flush({});
  });
});
