import { provideHttpClient } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { PersonalMilitar } from './personal-militar';
import { CargueExcel } from './cargue-excel/cargue-excel';

@Component({ template: '<p>Panel de personal</p>' })
class PanelPrueba {}

describe('Acceso único al cargue de personal', () => {
  it('el botón superior navega, abre el modal y permite reabrirlo sin sección duplicada', async () => {
    const menu = signal([
      {
        codigo: 'PERSONAL_MILITAR',
        nombre: 'Personal',
        ruta: '/personal',
        operaciones: ['leer'],
        hijos: [
          {
            codigo: 'PERSONAL_CARGUE_EXCEL',
            nombre: 'Cargue masivo por Excel',
            ruta: '/personal/cargue-excel',
            operaciones: ['crear'],
            hijos: [],
          },
        ],
      },
    ]);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        { provide: SesionService, useValue: { menu } },
        provideRouter([
          {
            path: 'personal',
            component: PersonalMilitar,
            children: [
              { path: '', component: PanelPrueba },
              { path: 'cargue-excel', component: CargueExcel },
            ],
          },
        ]),
      ],
    });
    const abrir = vi.spyOn(CargueExcel.prototype, 'abrir').mockImplementation(function (
      this: CargueExcel,
    ) {
      expect(this.dialogo()?.nativeElement.tagName).toBe('DIALOG');
      this.visible.set(true);
    });
    const harness = await RouterTestingHarness.create('/personal');
    const boton = harness.routeNativeElement!.querySelector('nav button') as HTMLButtonElement;
    expect(boton.textContent).toContain('Cargue masivo por Excel');
    boton.click();
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(abrir).toHaveBeenCalledTimes(1);
    expect(harness.routeNativeElement!.querySelector('app-cargue-excel dialog')).not.toBeNull();
    expect(harness.routeNativeElement!.querySelector('app-cargue-excel section')).not.toBeNull(); // contenido funcional dentro del dialog
    expect(harness.routeNativeElement!.querySelector('app-cargue-excel > section')).toBeNull();
    expect(harness.routeNativeElement!.textContent).not.toContain(
      'Personal militar / Importaciones',
    );
    (harness.routeNativeElement!.querySelector('nav button') as HTMLButtonElement).click();
    expect(abrir).toHaveBeenCalledTimes(2);
    expect(
      [...harness.routeNativeElement!.querySelectorAll('button')].filter((b) =>
        b.textContent?.includes('Cargue masivo por Excel'),
      ),
    ).toHaveLength(1);
    abrir.mockRestore();
  });
});
