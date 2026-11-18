import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { EstadisticasService } from '../../nucleo/servicios/estadisticas.service';
import {
  RAMPA_AZUL,
  alturaBarra,
  colorDeCelda,
  gruposDeGrados,
  porcentaje,
} from './panel-principal';

describe('Panel principal: cálculos de las gráficas', () => {
  it('la celda vacía no lleva color y la más alta toma el tono más oscuro con texto blanco', () => {
    expect(colorDeCelda(0, 10)).toEqual({ fondo: 'transparent', textoClaro: false });
    expect(colorDeCelda(10, 10)).toEqual({
      fondo: RAMPA_AZUL[RAMPA_AZUL.length - 1],
      textoClaro: true,
    });
    expect(colorDeCelda(1, 10).textoClaro).toBe(false);
    // Por encima del máximo de la escala no se sale de la rampa.
    expect(colorDeCelda(0.9, 0.4).fondo).toBe(RAMPA_AZUL[RAMPA_AZUL.length - 1]);
  });

  it('altura de barra y porcentajes', () => {
    expect(alturaBarra(4, 8, 150)).toBe(75);
    expect(alturaBarra(3, 0, 150)).toBe(0);
    expect(porcentaje(1, 3)).toBe(33);
    expect(porcentaje(5, 0)).toBe(0);
  });

  it('agrupa los grados por categoría en el orden recibido', () => {
    const grupos = gruposDeGrados([
      { sigla: 'ST', nombre: 'Subteniente', categoria: 'OFICIAL' },
      { sigla: 'CT', nombre: 'Capitán', categoria: 'OFICIAL' },
      { sigla: 'CS', nombre: 'Cabo Segundo', categoria: 'SUBOFICIAL' },
      { sigla: 'SLP', nombre: 'Soldado Profesional', categoria: 'SOLDADO_PROFESIONAL' },
    ]);
    expect(grupos.map((grupo) => [grupo.categoria, grupo.grados.length])).toEqual([
      ['Oficiales', 2],
      ['Suboficiales', 1],
      ['Soldados', 1],
    ]);
  });
});

describe('EstadisticasService', () => {
  let servicio: EstadisticasService;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(EstadisticasService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('pide el panel con año y semestre solo si se eligieron', () => {
    servicio.panel(2026, 2).subscribe();
    backend.expectOne('/api/estadisticas/panel?anio=2026&semestre=2').flush({});
    servicio.panel(null, null).subscribe();
    backend.expectOne('/api/estadisticas/panel').flush({});
  });
});
