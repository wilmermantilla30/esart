import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { errorDeFoto } from '../../paginas/instructores/instructores';
import {
  InstructoresService,
  inicialesInstructor,
  urlFotoInstructor,
} from './instructores.service';

describe('InstructoresService', () => {
  let servicio: InstructoresService;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(InstructoresService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('lista con filtros y no envía los vacíos', () => {
    servicio.listar('', 'OA', 'ACTIVOS').subscribe();
    backend.expectOne('/api/instructores?especialidad=OA&estado=ACTIVOS').flush([]);
  });

  it('sube la foto como multipart con PUT y la quita con DELETE', () => {
    const foto = new File(['x'], 'foto.png', { type: 'image/png' });
    servicio.cambiarFoto(3, foto).subscribe();
    const subida = backend.expectOne('/api/instructores/3/foto');
    expect(subida.request.method).toBe('PUT');
    expect((subida.request.body as FormData).get('archivo')).toBe(foto);
    subida.flush({});

    servicio.quitarFoto(3).subscribe();
    expect(backend.expectOne('/api/instructores/3/foto').request.method).toBe('DELETE');
  });

  it('activa y desactiva por su ruta', () => {
    servicio.cambiarEstado(5, false).subscribe();
    backend.expectOne('/api/instructores/5/desactivar').flush({});
    servicio.cambiarEstado(5, true).subscribe();
    backend.expectOne('/api/instructores/5/activar').flush({});
  });

  it('consulta los cursos del instructor', () => {
    servicio.cursos(4).subscribe();
    const peticion = backend.expectOne('/api/instructores/4/cursos');
    expect(peticion.request.method).toBe('GET');
    peticion.flush({ comandante: [], participa: [] });
  });

  it('la URL de la foto cambia con la versión del instructor', () => {
    expect(urlFotoInstructor({ id: 2, version: '2026-11-17T22:00:00Z' })).toBe(
      '/api/instructores/2/foto?v=2026-11-17T22%3A00%3A00Z',
    );
  });

  it('las iniciales salen del primer nombre y el primer apellido', () => {
    expect(inicialesInstructor({ nombres: 'maría fernanda', apellidos: 'López Ruiz' })).toBe('ML');
    expect(inicialesInstructor({ nombres: null, apellidos: null })).toBe('?');
  });

  it('valida tipo y tamaño de la foto antes de subirla', () => {
    expect(errorDeFoto(new File(['x'], 'a.jpg', { type: 'image/jpeg' }))).toBeNull();
    expect(errorDeFoto(new File(['x'], 'a.gif', { type: 'image/gif' }))).toContain('JPG');
    const grande = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'a.png', { type: 'image/png' });
    expect(errorDeFoto(grande)).toContain('5 MB');
  });
});
