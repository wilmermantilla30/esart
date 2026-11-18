import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { DatosCurso } from './datos-curso';
import { DatosCursoImportacion } from './excel-modelos';

describe('DatosCurso', () => {
  let fixture: ComponentFixture<DatosCurso>;
  let component: DatosCurso;
  let http: HttpTestingController;
  let emitido: DatosCursoImportacion | null;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DatosCurso],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(DatosCurso);
    component = fixture.componentInstance;
    component.cambio.subscribe((valor) => (emitido = valor));
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne('/api/importaciones/datos-curso').flush({
      tipos_curso: [
        { id: 3, codigo: 'CAP-SL', nombre: 'Curso de capacitación SL' },
        { id: 4, codigo: 'ESP-AR', nombre: 'Especialización artillería' },
      ],
      instructores: [{ id: 8, nombre: 'MY Juan Pérez' }],
      siguiente_codigo: '15',
    });
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('lista tipos con sigla y nombre, y muestra el número siguiente en solo lectura', () => {
    const opciones = [...fixture.nativeElement.querySelectorAll('select')[0].options].map(
      (o: HTMLOptionElement) => o.textContent?.trim(),
    );
    expect(opciones).toContain('CAP-SL — Curso de capacitación SL');
    const numero: HTMLInputElement = fixture.nativeElement.querySelector('input[readonly]');
    expect(numero.value).toBe('15');
  });

  it('precarga el nombre del tipo elegido y permite editarlo', () => {
    component.elegirTipo('4');
    expect(component.formulario.controls.nombre_curso.value).toBe('Especialización artillería');
    component.formulario.controls.nombre_curso.setValue('Especialización artillería cohorte 2');
    expect(component.formulario.controls.tipo_curso_id.value).toBe('4');
    expect(component.formulario.controls.nombre_curso.value).toContain('cohorte 2');
  });

  it('solo emite el curso cuando está completo y la fecha final no es anterior', () => {
    component.elegirTipo('3');
    component.formulario.patchValue({
      comandante_id: '8',
      fecha_inicio: '2026-03-01',
      fecha_fin: '2026-02-01',
    });
    expect(emitido).toBeNull();
    expect(component.fechasInvalidas()).toBe(true);
    component.formulario.patchValue({ fecha_fin: '2026-04-01', estado_curso: 'APLAZADO' });
    expect(emitido).toEqual({
      tipo_curso_id: 3,
      nombre_curso: 'Curso de capacitación SL',
      comandante_id: 8,
      fecha_inicio: '2026-03-01',
      fecha_fin: '2026-04-01',
      estado_curso: 'APLAZADO',
      observacion_curso: '',
    });
  });

  it('muestra el error del servidor si la estructura de cursos no está disponible', () => {
    component.recargar();
    http
      .expectOne('/api/importaciones/datos-curso')
      .flush(
        { error: { codigo: 'IMPORTACION_NO_DISPONIBLE', mensaje: 'Migración p0011 pendiente' } },
        { status: 503, statusText: 'Unavailable' },
      );
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Migración p0011 pendiente');
  });
});
