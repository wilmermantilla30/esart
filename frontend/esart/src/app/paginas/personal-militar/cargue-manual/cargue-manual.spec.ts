import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { OpcionesRegistroPersonal, PersonalRegistrado } from '../../../nucleo/modelos/personal';
import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { CargueManual } from './cargue-manual';
import { limitarPosicion, MARGEN_VENTANA, pasoDeTecla } from './mover-ventana';

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
    // jsdom no implementa la capa modal de <dialog>.
    HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
      this.open = true;
    };
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
    http.expectOne('/api/personal').flush(
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

  /** jsdom no tiene PointerEvent: se arma desde MouseEvent con los campos que se leen. */
  function puntero(tipo: string, x: number, y: number) {
    const evento = new MouseEvent(tipo, { bubbles: true, clientX: x, clientY: y, button: 0 });
    Object.defineProperties(evento, { pointerId: { value: 1 }, isPrimary: { value: true } });
    return evento;
  }

  it('se abre como ventana modal y se arrastra por la cabecera sin salirse del navegador', async () => {
    await crear([]);
    const dialogo = elemento().querySelector<HTMLDialogElement>('dialog')!;
    expect(dialogo.open).toBe(true);
    expect(dialogo.classList).not.toContain('registro-posicionada');

    const cabecera = elemento().querySelector<HTMLElement>('.registro-cabecera')!;
    cabecera.dispatchEvent(puntero('pointerdown', 100, 50));
    cabecera.dispatchEvent(puntero('pointermove', 400, 300));
    fixture.detectChanges();
    expect(dialogo.classList).toContain('registro-posicionada');
    expect([dialogo.style.left, dialogo.style.top]).toEqual(['300px', '250px']);

    // Arrastrar más allá del borde la deja pegada al margen.
    cabecera.dispatchEvent(puntero('pointermove', -500, -500));
    fixture.detectChanges();
    expect([dialogo.style.left, dialogo.style.top]).toEqual([
      `${MARGEN_VENTANA}px`,
      `${MARGEN_VENTANA}px`,
    ]);
    cabecera.dispatchEvent(puntero('pointerup', 0, 0));

    // Doble clic la vuelve a centrar.
    cabecera.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    fixture.detectChanges();
    expect(dialogo.classList).not.toContain('registro-posicionada');
  });

  it('el botón cerrar no inicia arrastre y Esc equivale a cancelar', async () => {
    await crear([]);
    const cerrar = elemento().querySelector<HTMLButtonElement>('button[aria-label^="Cerrar"]')!;
    cerrar.dispatchEvent(puntero('pointerdown', 10, 10));
    elemento()
      .querySelector('.registro-cabecera')!
      .dispatchEvent(puntero('pointermove', 300, 300));
    fixture.detectChanges();
    expect(elemento().querySelector('dialog')!.classList).not.toContain('registro-posicionada');

    const cancelar = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    elemento()
      .querySelector('dialog')!
      .dispatchEvent(new Event('cancel', { cancelable: true }));
    expect(cancelar).toHaveBeenCalledWith('/personal');
  });

  it('las flechas sobre "Mover ventana" desplazan la ventana', async () => {
    await crear([]);
    const mover = elemento().querySelector<HTMLButtonElement>('.registro-mover')!;
    mover.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    mover.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    fixture.detectChanges();
    // jsdom informa el rectángulo en 0,0: un paso a la derecha desde ahí y luego uno abajo.
    const dialogo = elemento().querySelector<HTMLDialogElement>('dialog')!;
    expect(dialogo.style.top).toBe('24px');
  });
});

describe('mover-ventana', () => {
  const viewport = { ancho: 1000, alto: 700 };
  const tamano = { ancho: 760, alto: 600 };

  it('mantiene la ventana completa dentro del navegador', () => {
    expect(limitarPosicion({ x: 50, y: 40 }, tamano, viewport)).toEqual({ x: 50, y: 40 });
    expect(limitarPosicion({ x: 900, y: 900 }, tamano, viewport)).toEqual({ x: 232, y: 92 });
    expect(limitarPosicion({ x: -90, y: -90 }, tamano, viewport)).toEqual({ x: 8, y: 8 });
  });

  it('si la ventana es más grande que el navegador queda en el margen', () => {
    expect(limitarPosicion({ x: 300, y: 300 }, { ancho: 2000, alto: 900 }, viewport)).toEqual({
      x: 8,
      y: 8,
    });
  });

  it('solo las flechas mueven la ventana', () => {
    expect(pasoDeTecla('ArrowUp')).toEqual({ x: 0, y: -24 });
    expect(pasoDeTecla('Enter')).toBeNull();
  });
});
