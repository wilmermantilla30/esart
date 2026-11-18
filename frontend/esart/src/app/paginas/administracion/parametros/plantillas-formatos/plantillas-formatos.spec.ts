import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SesionService } from '../../../../nucleo/servicios/sesion.service';
import { PlantillasFormatosPestana } from './plantillas-formatos';

/** jsdom no tiene DragEvent ni DataTransfer: se arma un evento con los campos que se leen. */
function arrastre(tipo: string, archivos: File[] = [], tipos = archivos.length ? ['Files'] : []) {
  const evento = new Event(tipo, { bubbles: true, cancelable: true });
  Object.defineProperty(evento, 'dataTransfer', {
    value: { types: tipos, files: archivos, dropEffect: 'none' },
  });
  return evento;
}

describe('Plantillas y formatos: arrastrar y soltar', () => {
  let fixture: ComponentFixture<PlantillasFormatosPestana>;
  let http: HttpTestingController;
  const excel = new File(['contenido'], 'Plantilla_Cargue_Masivo_Personal_ESART.xlsx');

  async function crear(puedePublicar: boolean) {
    await TestBed.configureTestingModule({
      imports: [PlantillasFormatosPestana],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SesionService, useValue: { puede: () => puedePublicar } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PlantillasFormatosPestana);
    fixture.detectChanges();
    http.expectOne((peticion) => peticion.url === '/api/parametros/plantillas').flush([]);
    fixture.detectChanges();
  }

  const host = () => fixture.nativeElement as HTMLElement;
  const ventana = () => host().querySelector('[aria-labelledby="titulo-subir-plantilla"]');
  const texto = () => host().textContent ?? '';

  afterEach(() => http.verify());

  it('con la ventana abierta, un archivo soltado en el fondo (fuera del cuadro) se carga', async () => {
    await crear(true);
    fixture.componentInstance.abrirSubida();
    fixture.detectChanges();
    const fondo = ventana() as HTMLElement;

    fondo.dispatchEvent(arrastre('dragenter', [excel]));
    fixture.detectChanges();
    expect(texto()).toContain('Suelte el archivo en cualquier parte');

    const sobre = arrastre('dragover', [excel]);
    fondo.dispatchEvent(sobre);
    expect(sobre.defaultPrevented).toBe(true);

    const soltar = arrastre('drop', [excel]);
    fondo.dispatchEvent(soltar);
    fixture.detectChanges();
    expect(soltar.defaultPrevented).toBe(true);
    expect(texto()).toContain('Plantilla_Cargue_Masivo_Personal_ESART.xlsx');
    expect(texto()).not.toContain('Suelte el archivo en cualquier parte');
  });

  it('con la ventana cerrada, soltar sobre la pestaña la abre con el archivo', async () => {
    await crear(true);
    expect(ventana()).toBeNull();
    host().dispatchEvent(arrastre('dragenter', [excel]));
    host().dispatchEvent(arrastre('drop', [excel]));
    fixture.detectChanges();
    expect(ventana()).not.toBeNull();
    expect(texto()).toContain('Plantilla_Cargue_Masivo_Personal_ESART.xlsx');
  });

  it('sin permiso de publicar, soltar un archivo no abre la ventana', async () => {
    await crear(false);
    const soltar = arrastre('drop', [excel]);
    host().dispatchEvent(soltar);
    fixture.detectChanges();
    expect(soltar.defaultPrevented).toBe(false);
    expect(ventana()).toBeNull();
  });

  it('ignora arrastres que no traen archivos (texto o enlaces)', async () => {
    await crear(true);
    host().dispatchEvent(arrastre('dragenter', [], ['text/plain']));
    fixture.detectChanges();
    expect(texto()).not.toContain('Suelte el archivo en cualquier parte');
  });

  it('el aviso no parpadea al pasar entre elementos hijos y se quita al salir', async () => {
    await crear(true);
    fixture.componentInstance.abrirSubida();
    fixture.detectChanges();
    const fondo = ventana() as HTMLElement;
    const hijo = fondo.querySelector('form') as HTMLElement;
    fondo.dispatchEvent(arrastre('dragenter', [excel]));
    hijo.dispatchEvent(arrastre('dragenter', [excel]));
    fondo.dispatchEvent(arrastre('dragleave', [excel]));
    fixture.detectChanges();
    expect(texto()).toContain('Suelte el archivo en cualquier parte');
    hijo.dispatchEvent(arrastre('dragleave', [excel]));
    fixture.detectChanges();
    expect(texto()).not.toContain('Suelte el archivo en cualquier parte');
  });
});
