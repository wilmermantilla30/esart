import { computed, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of } from 'rxjs';

import { InactividadService } from '../../nucleo/servicios/inactividad.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { AvisoInactividad } from './aviso-inactividad';

describe('AvisoInactividad (HU-08)', () => {
  let fixture: ComponentFixture<AvisoInactividad>;
  let pagina: HTMLElement;
  const segundosRestantes = signal<number | null>(null);
  const continuarSesion = vi.fn();
  const cerrarSesion = vi.fn(() => of(undefined));
  const navegar = vi.fn().mockResolvedValue(true);

  beforeEach(async () => {
    segundosRestantes.set(null);
    vi.clearAllMocks();
    TestBed.configureTestingModule({
      imports: [AvisoInactividad],
      providers: [
        {
          provide: InactividadService,
          useValue: {
            segundosRestantes,
            mostrarAviso: computed(() => {
              const s = segundosRestantes();
              return s !== null && s > 0 && s <= 120;
            }),
            continuarSesion,
          },
        },
        { provide: SesionService, useValue: { cerrarSesion } },
        { provide: Router, useValue: { navigate: navegar } },
      ],
    });
    fixture = TestBed.createComponent(AvisoInactividad);
    pagina = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  });

  it('no muestra nada mientras falte más de 2 minutos', async () => {
    segundosRestantes.set(600);
    await fixture.whenStable();
    expect(pagina.querySelector('[role="alertdialog"]')).toBeNull();
  });

  it('muestra el aviso con la cuenta regresiva en m:ss', async () => {
    segundosRestantes.set(105);
    await fixture.whenStable();
    const aviso = pagina.querySelector('[role="alertdialog"]');
    expect(aviso).not.toBeNull();
    expect(aviso!.textContent).toContain('Su sesión está por cerrarse');
    expect(aviso!.textContent).toContain('1:45');
  });

  it('"Continuar sesión" renueva la sesión', async () => {
    segundosRestantes.set(90);
    await fixture.whenStable();
    const boton = [...pagina.querySelectorAll('button')].find((b) => b.textContent?.includes('Continuar'))!;
    boton.click();
    expect(continuarSesion).toHaveBeenCalledTimes(1);
  });

  it('"Cerrar sesión" cierra y lleva al login', async () => {
    segundosRestantes.set(90);
    await fixture.whenStable();
    const boton = [...pagina.querySelectorAll('button')].find((b) => b.textContent?.includes('Cerrar sesión'))!;
    boton.click();
    expect(cerrarSesion).toHaveBeenCalledTimes(1);
    expect(navegar).toHaveBeenCalledWith(['/', 'inicio-sesion']);
  });
});
