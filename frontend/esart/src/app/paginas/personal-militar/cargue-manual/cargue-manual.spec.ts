import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { OpcionesRegistroPersonal, PersonalRegistrado } from '../../../nucleo/modelos/personal';
import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { CargueManual } from './cargue-manual';

const OPCIONES: OpcionesRegistroPersonal = {
  categorias: [
    { codigo: 'OFICIAL', nombre: 'Oficial', grados: [{ codigo: 'MY', nombre: 'Mayor' }] },
    {
      codigo: 'SUBOFICIAL',
      nombre: 'Suboficial',
      grados: [{ codigo: 'SS', nombre: 'Sargento Segundo' }],
    },
  ],
  unidades: [
    { id: 4, codigo: 'BAART3', nombre: 'Batallón de Artillería 3' },
    { id: 7, codigo: 'ESART', nombre: 'Escuela de Artillería' },
  ],
};

const REGISTRADO: PersonalRegistrado = {
  id: 51,
  documento_identidad: '1024589632',
  nombres: 'Carlos Andrés',
  apellidos: 'Colorado Gil',
  nombre_completo: 'MY Carlos Andrés Colorado Gil',
  grado: 'MY',
  genero: 'M',
  categoria: 'OFICIAL',
  unidad_actual_id: 7,
  unidad_nombre: 'Escuela de Artillería',
  especialidad_actual: null,
  activo: true,
};

describe('CargueManual', () => {
  let fixture: ComponentFixture<CargueManual>;
  let http: HttpTestingController;
  let permisos: Set<string>;

  async function crear(conPermisos: string[]) {
    permisos = new Set(conPermisos);
    await TestBed.configureTestingModule({
      imports: [CargueManual],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        // Solo interesa la operación "crear" de cada componente de la malla.
        { provide: SesionService, useValue: { puede: (codigo: string) => permisos.has(codigo) } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(CargueManual);
    fixture.detectChanges();
    http.expectOne('/api/personal/opciones-registro').flush(OPCIONES);
    fixture.detectChanges();
  }

  const elemento = () => fixture.nativeElement as HTMLElement;
  const formulario = () =>
    (fixture.componentInstance as unknown as { formulario: CargueManual['formulario'] }).formulario;

  function diligenciar() {
    formulario().patchValue({
      documento_identidad: '1024589632',
      nombres: '  Carlos   Andrés ',
      apellidos: 'Colorado Gil',
      grado: 'MY',
      genero: 'M',
      categoria: 'OFICIAL',
      especialidad_actual: '',
    });
  }

  function enviar() {
    elemento().querySelector('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
  }

  afterEach(() => http.verify());

  it('preselecciona la Escuela de Artillería y agrupa los grados por categoría', async () => {
    await crear([]);
    expect(formulario().controls.unidad_actual_id.value).toBe('7');
    const grupos = elemento().querySelectorAll('optgroup');
    expect([...grupos].map((g) => g.label)).toEqual(['Oficial', 'Suboficial']);
  });

  it('al elegir grado fija la categoría y al cambiar categoría borra un grado ajeno', async () => {
    await crear([]);
    const selectGrado = elemento().querySelector<HTMLSelectElement>(
      'select[formcontrolname="grado"]',
    )!;
    selectGrado.value = 'SS';
    selectGrado.dispatchEvent(new Event('change'));
    expect(formulario().controls.categoria.value).toBe('SUBOFICIAL');

    const selectCategoria = elemento().querySelector<HTMLSelectElement>(
      'select[formcontrolname="categoria"]',
    )!;
    selectCategoria.value = 'OFICIAL';
    selectCategoria.dispatchEvent(new Event('change'));
    expect(formulario().controls.grado.value).toBe('');
  });

  it('no envía si faltan obligatorios o la cédula tiene letras', async () => {
    await crear([]);
    diligenciar();
    formulario().controls.documento_identidad.setValue('10AB');
    enviar();
    http.expectNone('/api/personal');
    expect(elemento().querySelector('[aria-invalid="true"]')).not.toBeNull();
  });

  it('envía el cuerpo limpio y muestra los accesos según los permisos', async () => {
    await crear(['INSTRUCTORES']);
    diligenciar();
    enviar();
    const peticion = http.expectOne('/api/personal');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      documento_identidad: '1024589632',
      nombres: 'Carlos Andrés',
      apellidos: 'Colorado Gil',
      grado: 'MY',
      genero: 'M',
      categoria: 'OFICIAL',
      unidad_actual_id: 7,
      especialidad_actual: null,
      activo: true,
    });
    peticion.flush(REGISTRADO, { status: 201, statusText: 'Created' });
    fixture.detectChanges();

    expect(elemento().textContent).toContain('MY Carlos Andrés Colorado Gil');
    const enlaces = [...elemento().querySelectorAll<HTMLAnchorElement>('a.registro-acceso')];
    // Tiene permiso de crear instructores, pero no usuarios.
    expect(enlaces.map((a) => a.getAttribute('href'))).toEqual(['/instructores?cedula=1024589632']);
  });

  it('con ambos permisos ofrece instructor y usuario; sin permisos, ninguno', async () => {
    await crear(['INSTRUCTORES', 'USUARIOS']);
    diligenciar();
    enviar();
    http.expectOne('/api/personal').flush(REGISTRADO, { status: 201, statusText: 'Created' });
    fixture.detectChanges();
    expect(elemento().querySelectorAll('a.registro-acceso').length).toBe(2);

    http.verify();
    TestBed.resetTestingModule();
    await crear([]);
    diligenciar();
    enviar();
    http.expectOne('/api/personal').flush(REGISTRADO, { status: 201, statusText: 'Created' });
    fixture.detectChanges();
    expect(elemento().querySelectorAll('a.registro-acceso').length).toBe(0);
  });

  it('muestra el error del backend (cédula repetida) y conserva el formulario', async () => {
    await crear([]);
    diligenciar();
    enviar();
    http
      .expectOne('/api/personal')
      .flush(
        {
          error: {
            codigo: 'DOCUMENTO_EXISTENTE',
            mensaje: 'Ya existe un militar registrado con ese documento de identidad.',
            detalle: null,
          },
        },
        { status: 409, statusText: 'Conflict' },
      );
    fixture.detectChanges();
    expect(elemento().querySelector('[role="alert"]')!.textContent).toContain(
      'Ya existe un militar',
    );
    expect(formulario().controls.nombres.value).toBe('  Carlos   Andrés ');
  });
});
