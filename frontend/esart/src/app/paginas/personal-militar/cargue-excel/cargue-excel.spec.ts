import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { CargueExcel } from './cargue-excel';
import { ImportacionExcelService } from './importacion-excel.service';
import { BORDES_VENTANA } from './ventana-excel';
import { of } from 'rxjs';
import { VerificacionService } from '../../../nucleo/servicios/verificacion.service';

const CURSO = {
  tipo_curso_id: 3,
  nombre_curso: 'Curso básico',
  comandante_id: 8,
  fecha_inicio: '2026-02-01',
  fecha_fin: '2026-03-01',
  estado_curso: 'EN_CURSO' as const,
  observacion_curso: '',
};

describe('CargueExcel', () => {
  let component: CargueExcel;
  let fixture: ComponentFixture<CargueExcel>;

  beforeEach(async () => {
    // jsdom no implementa la capa modal de <dialog>.
    HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
      this.open = true;
    };
    HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
      this.open = false;
    };
    await TestBed.configureTestingModule({
      imports: [CargueExcel],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(CargueExcel);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  function prepararConfirmacion() {
    const archivo = new File(['contenido original sin reconstruir'], 'personal-original.xlsx');
    component.archivo.set(archivo);
    component.curso.set(CURSO);
    component.hoja.set('CARGUE_PERSONAL');
    component.analisis.set({
      columnas: [
        {
          nombre: 'Documento',
          campo: 'documento_identidad',
          tipo: 'Texto',
          llenos: 2,
          vacios: 0,
          porcentaje: 100,
          errores: 0,
          advertencias: 0,
        },
      ],
      filas: [
        { numero: 2, valores: ['9900000001'] },
        { numero: 4, valores: ['9900000002'] },
      ],
      incidencias: [],
      validado: true,
    });
    component.confirmar.set(true);
    return archivo;
  }

  it('confirma con archivo original y hoja, impide el doble clic y notifica el refresco del listado', () => {
    const archivo = prepararConfirmacion();
    const refrescar = vi.spyOn(TestBed.inject(VerificacionService), 'notificarPersonalActualizado');
    const http = TestBed.inject(HttpTestingController);
    component.importar();
    component.importar();
    expect(component.enviando()).toBe(true);
    const peticion = http.expectOne('/api/importaciones/excel');
    expect(peticion.request.body.get('archivo')).toBe(archivo);
    expect(peticion.request.body.get('hoja')).toBe('CARGUE_PERSONAL');
    expect(peticion.request.body.get('tipo_curso_id')).toBe('3');
    expect(peticion.request.body.get('estado_curso')).toBe('EN_CURSO');
    peticion.flush({
      importacion_id: 'id-real-del-servidor',
      estado: 'APLICADA',
      filas_totales: 2,
      filas_validas: 2,
      filas_rechazadas: 0,
    });
    expect(component.resultado()?.filas_validas).toBe(2);
    expect(component.enviando()).toBe(false);
    expect(refrescar).toHaveBeenCalledOnce();
    component.confirmar.set(true);
    component.importar();
    http.expectNone('/api/importaciones/excel');
    http.verify();
  });

  it('pide el código TOTP en la ventana emergente y reenvía el mismo archivo y hoja', () => {
    const archivo = prepararConfirmacion();
    const http = TestBed.inject(HttpTestingController);
    component.importar();
    http
      .expectOne('/api/importaciones/excel')
      .flush(
        { error: { codigo: 'TOTP_REQUERIDO', mensaje: 'Ingrese el código' } },
        { status: 409, statusText: 'Conflict' },
      );
    expect(component.requiereTotp()).toBe(true);
    expect(component.error()).toBe('');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.excel-totp app-totp')).not.toBeNull();

    let rechazo: unknown;
    component.verificarCodigoTotp('111111').subscribe({ error: (e) => (rechazo = e) });
    http
      .expectOne('/api/importaciones/excel')
      .flush(
        { error: { codigo: 'TOTP_INVALIDO', mensaje: 'Código inválido' } },
        { status: 422, statusText: 'Unprocessable' },
      );
    expect(rechazo).toBeTruthy();
    expect(component.requiereTotp()).toBe(true);

    component.verificarCodigoTotp('222222').subscribe();
    const peticion = http.expectOne('/api/importaciones/excel');
    expect(peticion.request.body.get('archivo')).toBe(archivo);
    expect(peticion.request.body.get('hoja')).toBe('CARGUE_PERSONAL');
    expect(peticion.request.body.get('codigo_totp')).toBe('222222');
    peticion.flush({
      importacion_id: 'id',
      estado: 'APLICADA',
      filas_totales: 2,
      filas_validas: 2,
      filas_rechazadas: 0,
    });
    expect(component.resultado()?.filas_validas).toBe(2);
    component.cerrarTotp();
    expect(component.requiereTotp()).toBe(false);
    http.verify();
  });

  it('cierra la ventana TOTP y muestra en el cargue los errores que no son del código', () => {
    prepararConfirmacion();
    const http = TestBed.inject(HttpTestingController);
    component.importar();
    http
      .expectOne('/api/importaciones/excel')
      .flush(
        { error: { codigo: 'TOTP_REQUERIDO', mensaje: 'Ingrese el código' } },
        { status: 409, statusText: 'Conflict' },
      );
    component.verificarCodigoTotp('123456').subscribe();
    http
      .expectOne('/api/importaciones/excel')
      .flush(
        { error: { codigo: 'IMPORTACION_NO_DISPONIBLE', mensaje: 'Sin guardado' } },
        { status: 503, statusText: 'Unavailable' },
      );
    expect(component.requiereTotp()).toBe(false);
    expect(component.error()).toBe('Sin guardado');
    http.verify();
  });

  it('mantiene la ventana y la numeración original de incidencias devueltas por el backend', () => {
    prepararConfirmacion();
    const cerrar = vi.spyOn(component, 'cerrar');
    const http = TestBed.inject(HttpTestingController);
    component.importar();
    http.expectOne('/api/importaciones/excel').flush(
      {
        error: {
          codigo: 'IMPORTACION_RECHAZADA',
          mensaje: 'Datos inválidos',
          detalle: {
            errores: [
              {
                fila: 4,
                columna: 'documento_identidad',
                valor: '9900000002',
                motivo: 'Documento existente',
              },
            ],
          },
        },
      },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    expect(component.errores()[0]).toMatchObject({ fila: 4, valor: '9900000002', indice: 0 });
    expect(component.analisis()?.columnas[0].errores).toBe(1);
    expect(component.enviando()).toBe(false);
    expect(component.resultado()).toBeNull();
    expect(cerrar).not.toHaveBeenCalled();
    http.verify();
  });

  it('bloquea la importación sin validación, con errores y durante el envío', () => {
    expect(component.puedeImportar()).toBe(false);
    component.archivo.set(new File(['original'], 'original.xlsx'));
    component.hoja.set('CARGUE_PERSONAL');
    component.analisis.set({
      columnas: [],
      filas: [{ numero: 2, valores: ['123'] }],
      incidencias: [],
      validado: true,
    });
    component.curso.set(null);
    expect(component.puedeImportar()).toBe(false);
    component.curso.set(CURSO);
    expect(component.puedeImportar()).toBe(true);
    component.enviando.set(true);
    expect(component.puedeImportar()).toBe(false);
    component.enviando.set(false);
    component.analisis.update((a) => ({
      ...a!,
      incidencias: [
        {
          fila: 1,
          indice: -1,
          columna: 'nombres',
          valor: '',
          motivo: 'Columna ausente',
          nivel: 'Error',
        },
      ],
    }));
    expect(component.puedeImportar()).toBe(false);
    expect(component.completos()).toBe(0);
    component.filtrar('correctos');
    expect(component.filasFiltradas()).toEqual([]);
  });

  it('rechaza archivos de otra extensión sin sustituir el archivo actual', async () => {
    const original = new File(['original'], 'original.xlsx');
    component.archivo.set(original);
    await component.cargar(new File(['texto'], 'datos.csv'));
    expect(component.archivo()).toBe(original);
    expect(component.error()).toContain('.xlsx y .xls');
  });

  function arrastre(tipo: string, archivos: File[] = [], types = ['Files']) {
    const evento = new Event(tipo, { bubbles: true, cancelable: true });
    Object.defineProperty(evento, 'dataTransfer', {
      value: { files: archivos, types, dropEffect: 'none' },
    });
    return evento as DragEvent;
  }

  it.each([
    '.excel-encabezado',
    '.excel-resumen article',
    '#diagnostico table',
    '.excel-preview table',
    'aside',
    '.excel-cuerpo',
    '.excel-pie',
  ])('recibe el archivo en %s con una única carga y conserva la geometría', (selector) => {
    const cargar = vi.spyOn(component, 'cargar').mockResolvedValue();
    const importar = vi.spyOn(TestBed.inject(ImportacionExcelService), 'importar');
    const rect = { x: 20, y: 30, ancho: 800, alto: 500 };
    component.geometria.set(rect);
    fixture.detectChanges();
    const destino = fixture.nativeElement.querySelector(selector) as HTMLElement;
    destino.dispatchEvent(arrastre('dragenter'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.excel-overlay')?.textContent).toContain(
      'Suelte aquí su archivo Excel',
    );
    const archivo = new File(['excel'], 'personal.xlsx');
    const drop = arrastre('drop', [archivo]);
    destino.dispatchEvent(drop);
    fixture.detectChanges();
    expect(drop.defaultPrevented).toBe(true);
    expect(cargar).toHaveBeenCalledExactlyOnceWith(archivo);
    expect(fixture.nativeElement.querySelector('.excel-overlay')).toBeNull();
    expect(component.geometria()).toEqual(rect);
    expect(importar).not.toHaveBeenCalled();
  });

  function puntero(tipo: string, x: number, y: number, id = 7) {
    const evento = new Event(tipo, { bubbles: true, cancelable: true });
    Object.assign(evento, { clientX: x, clientY: y, pointerId: id, isPrimary: true, button: 0 });
    return evento as PointerEvent;
  }

  it.each(BORDES_VENTANA)(
    'captura y finaliza el redimensionamiento del borde %s sin cargar archivos',
    (borde) => {
      const cargar = vi.spyOn(component, 'cargar').mockResolvedValue();
      component.geometria.set({ x: 20, y: 20, ancho: 700, alto: 450 });
      fixture.detectChanges();
      const dialogo = component.dialogo()!.nativeElement;
      dialogo.setPointerCapture = vi.fn();
      dialogo.hasPointerCapture = vi.fn(() => true);
      dialogo.releasePointerCapture = vi.fn();
      const control = fixture.nativeElement.querySelector('.excel-borde-' + borde) as HTMLElement;
      control.dispatchEvent(puntero('pointerdown', 100, 100));
      expect(component.redimensionando()).toBe(true);
      expect(dialogo.setPointerCapture).toHaveBeenCalledWith(7);
      dialogo.dispatchEvent(puntero('pointermove', 110, 110));
      expect(component.geometria()).not.toEqual({ x: 20, y: 20, ancho: 700, alto: 450 });
      dialogo.dispatchEvent(puntero('pointerup', 110, 110));
      expect(component.redimensionando()).toBe(false);
      expect(dialogo.releasePointerCapture).toHaveBeenCalledWith(7);
      expect(cargar).not.toHaveBeenCalled();
    },
  );

  it('maximiza y restaura exactamente la posición y tamaño anteriores', () => {
    const anterior = { x: 50, y: 40, ancho: 700, alto: 450 };
    component.geometria.set(anterior);
    component.alternarMaximizada();
    expect(component.maximizada()).toBe(true);
    expect(component.geometria()).toEqual({
      x: 8,
      y: 8,
      ancho: window.innerWidth - 16,
      alto: window.innerHeight - 16,
    });
    component.alternarMaximizada();
    expect(component.maximizada()).toBe(false);
    expect(component.geometria()).toEqual(anterior);
  });

  it('sale del estado maximizado al redimensionar y cancela el gesto sin interferir con drag and drop', () => {
    component.geometria.set({ x: 50, y: 40, ancho: 700, alto: 450 });
    const dialogo = component.dialogo()!.nativeElement;
    dialogo.setPointerCapture = vi.fn();
    dialogo.hasPointerCapture = vi.fn(() => false);
    component.alternarMaximizada();
    component.iniciarTamano(puntero('pointerdown', 100, 100), 'se');
    component.moverTamano(puntero('pointermove', 70, 70));
    expect(component.maximizada()).toBe(false);
    component.entrarZona(arrastre('dragenter'));
    expect(component.arrastrando()).toBe(false);
    component.terminarTamano(puntero('pointercancel', 70, 70));
    component.entrarZona(arrastre('dragenter'));
    component.iniciarTamano(puntero('pointerdown', 100, 100), 'se');
    expect(component.redimensionando()).toBe(false);
  });

  it('mantiene el resaltado al entrar en hijos y lo limpia al abandonar el recuadro', () => {
    const zona = fixture.nativeElement.querySelector('.excel-zona') as HTMLElement;
    const hijo = zona.querySelector('span')!;
    const entrada = arrastre('dragenter');
    zona.dispatchEvent(entrada);
    fixture.detectChanges();
    expect(entrada.defaultPrevented).toBe(true);
    expect(zona.classList.contains('excel-arrastre')).toBe(true);
    hijo.dispatchEvent(arrastre('dragenter'));
    hijo.dispatchEvent(arrastre('dragleave'));
    expect(component.arrastrando()).toBe(true);
    const sobre = arrastre('dragover');
    hijo.dispatchEvent(sobre);
    expect(sobre.defaultPrevented).toBe(true);
    expect(sobre.dataTransfer!.dropEffect).toBe('copy');
    zona.dispatchEvent(arrastre('dragleave'));
    fixture.detectChanges();
    expect(zona.classList.contains('excel-arrastre')).toBe(false);
  });

  it('el botón y drop ejecutan exactamente el mismo método para el archivo, incluso al reemplazarlo', () => {
    const cargar = vi.spyOn(component, 'cargar').mockResolvedValue();
    const primero = new File(['excel'], 'primero.xlsx');
    const segundo = new File(['excel'], 'segundo.xls');
    component.archivo.set(primero);
    const zona = fixture.nativeElement.querySelector('.excel-zona') as HTMLElement;
    const drop = arrastre('drop', [segundo]);
    zona.dispatchEvent(arrastre('dragenter'));
    zona.dispatchEvent(drop);
    expect(drop.defaultPrevented).toBe(true);
    expect(component.arrastrando()).toBe(false);
    expect(cargar).toHaveBeenCalledExactlyOnceWith(segundo);
    const entrada = fixture.nativeElement.querySelector('input[type=file]') as HTMLInputElement;
    Object.defineProperty(entrada, 'files', { value: [primero] });
    entrada.dispatchEvent(new Event('change'));
    expect(cargar).toHaveBeenLastCalledWith(primero);
    expect(cargar).toHaveBeenCalledTimes(2);
  });

  it('rechaza múltiples archivos, otros formatos y archivos mayores de 20 MB', async () => {
    const zona = fixture.nativeElement.querySelector('.excel-zona') as HTMLElement;
    const archivo = new File(['texto'], 'datos.csv');
    zona.dispatchEvent(arrastre('drop', [archivo, archivo]));
    expect(component.error()).toContain('único archivo');
    zona.dispatchEvent(arrastre('drop', [archivo]));
    expect(component.error()).toContain('.xlsx y .xls');
    const grande = new File(['excel'], 'grande.xlsx');
    Object.defineProperty(grande, 'size', { value: 20 * 1024 * 1024 + 1 });
    zona.dispatchEvent(arrastre('drop', [grande]));
    expect(component.error()).toContain('20 MB');
    expect(component.ocupado()).toBe(false);
  });

  it('ignora texto arrastrado y no acepta nuevas cargas durante el procesamiento o envío', () => {
    const cargar = vi.spyOn(component, 'cargar').mockResolvedValue();
    component.entrarZona(arrastre('dragenter', [], ['text/plain']));
    expect(component.arrastrando()).toBe(false);
    for (const estado of [component.ocupado, component.enviando]) {
      estado.set(true);
      component.entrarZona(arrastre('dragenter'));
      expect(component.arrastrando()).toBe(false);
      const evento = arrastre('drop', [new File(['excel'], 'personal.xlsx')]);
      component.soltar(evento);
      expect(evento.defaultPrevented).toBe(true);
      estado.set(false);
    }
    expect(cargar).not.toHaveBeenCalled();
  });

  it('detecta hojas después del drop y analiza solo la seleccionada sin enviar al backend', async () => {
    const worker = {
      onmessage: null as ((event: { data: unknown }) => void) | null,
      onerror: null,
      postMessage: vi.fn(),
      terminate: vi.fn(),
    };
    vi.stubGlobal(
      'Worker',
      class {
        constructor() {
          return worker;
        }
      },
    );
    try {
      const importar = vi.spyOn(TestBed.inject(ImportacionExcelService), 'importar');
      vi.spyOn(TestBed.inject(ImportacionExcelService), 'unidades').mockReturnValue(of([]));
      component.geometria.set({ x: 20, y: 20, ancho: 700, alto: 450 });
      const dialogo = component.dialogo()!.nativeElement;
      dialogo.setPointerCapture = vi.fn();
      dialogo.hasPointerCapture = vi.fn(() => false);
      component.iniciarTamano(puntero('pointerdown', 100, 100), 'se');
      component.moverTamano(puntero('pointermove', 120, 120));
      component.terminarTamano(puntero('pointerup', 120, 120));
      const geometria = { ...component.geometria()! };
      const archivo = new File(['excel'], 'personal.xlsx');
      Object.defineProperty(archivo, 'arrayBuffer', {
        value: async () => new TextEncoder().encode('excel').buffer,
      });
      component.soltar(arrastre('drop', [archivo]));
      await Promise.resolve();
      expect(component.archivo()).not.toBe(archivo);
      expect(component.archivo()?.name).toBe(archivo.name);
      const archivoConservado = component.archivo();
      expect(component.ocupado()).toBe(true);
      worker.onmessage!({
        data: {
          tipo: 'hojas',
          hojas: [
            { nombre: 'ACTIVOS', filas: 1, columnas: 2 },
            { nombre: 'RESERVA', filas: 3, columnas: 2 },
          ],
        },
      });
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelectorAll('#excel-hoja option')).toHaveLength(3);
      expect(component.archivo()).toBe(archivoConservado);
      expect(component.hoja()).toBe('');
      const selector = fixture.nativeElement.querySelector('#excel-hoja') as HTMLSelectElement;
      selector.value = 'RESERVA';
      selector.dispatchEvent(new Event('change'));
      expect(worker.postMessage).toHaveBeenLastCalledWith({
        tipo: 'analizar',
        hoja: 'RESERVA',
        validar: false,
      });
      worker.onmessage!({
        data: {
          tipo: 'analisis',
          analisis: {
            columnas: [],
            filas: [{ numero: 2, valores: ['123'] }],
            incidencias: [],
            validado: false,
          },
        },
      });
      expect(component.analisis()!.filas).toHaveLength(1);
      expect(component.puedeImportar()).toBe(false);
      await component.validar();
      expect(worker.postMessage).toHaveBeenLastCalledWith({
        tipo: 'analizar',
        hoja: 'RESERVA',
        validar: true,
        unidades: [],
      });
      worker.onmessage!({
        data: {
          tipo: 'analisis',
          analisis: {
            columnas: [],
            filas: [{ numero: 2, valores: ['123'] }],
            incidencias: [],
            validado: true,
          },
        },
      });
      component.cambiarHoja('ACTIVOS');
      expect(component.analisis()).toBeNull();
      expect(worker.postMessage).toHaveBeenLastCalledWith({
        tipo: 'analizar',
        hoja: 'ACTIVOS',
        validar: false,
      });
      expect(component.geometria()).toEqual(geometria);
      expect(importar).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('exige seleccionar de nuevo si Windows deja de permitir leer el archivo', async () => {
    const worker = { onmessage: null, onerror: null, terminate: vi.fn(), postMessage: vi.fn() };
    vi.stubGlobal(
      'Worker',
      class {
        constructor() {
          return worker;
        }
      },
    );
    try {
      const archivo = new File(['excel'], 'original.xlsx');
      Object.defineProperty(archivo, 'arrayBuffer', {
        value: async () => {
          throw new DOMException('Archivo modificado', 'NotReadableError');
        },
      });
      await component.cargar(archivo);
      expect(component.error()).toContain('Vuelva a seleccionarlo');
      expect(component.archivo()).toBeNull();
      expect(component.puedeImportar()).toBe(false);
      expect(worker.postMessage).not.toHaveBeenCalled();
      TestBed.inject(HttpTestingController).expectNone('/api/importaciones/excel');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('no limpia el selector antes de terminar de leer el archivo', async () => {
    let terminar!: () => void;
    vi.spyOn(component, 'cargar').mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          terminar = resolve;
        }),
    );
    const entrada = { files: [new File(['excel'], 'original.xlsx')], value: 'seleccionado' };
    const seleccion = component.seleccionar({ target: entrada } as unknown as Event);
    expect(entrada.value).toBe('seleccionado');
    terminar();
    await seleccion;
    expect(entrada.value).toBe('');
  });

  it('no reintenta ni conserva una carga confirmable si el navegador informa ERR_UPLOAD_FILE_CHANGED', () => {
    prepararConfirmacion();
    component.importar();
    const http = TestBed.inject(HttpTestingController);
    http
      .expectOne('/api/importaciones/excel')
      .error(new ErrorEvent('error', { message: 'net::ERR_UPLOAD_FILE_CHANGED' }));
    expect(component.error()).toContain('Vuelva a seleccionarlo');
    expect(component.archivo()).toBeNull();
    expect(component.puedeImportar()).toBe(false);
    expect(component.enviando()).toBe(false);
    component.importar();
    http.expectNone('/api/importaciones/excel');
    http.verify();
  });
});
