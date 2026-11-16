import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ElementoMenu } from '../../nucleo/modelos/sesion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { Plataforma } from './plataforma';

const MENU_USUARIO: ElementoMenu[] = [
  { codigo: 'DASHBOARD', nombre: 'Panel principal', ruta: '/dashboard', operaciones: ['leer'], hijos: [] },
  {
    codigo: 'PERSONAL_MILITAR',
    nombre: 'Personal militar',
    ruta: '/personal',
    operaciones: ['leer'],
    hijos: [
      { codigo: 'PERSONAL_VERIFICAR', nombre: 'Verificar artillero', ruta: '/personal/verificar', operaciones: ['leer'], hijos: [] },
    ],
  },
];

describe('Plataforma (sidebar por permisos, HU-09)', () => {
  async function crearConMenu(menu: ElementoMenu[], permisos: string[]) {
    TestBed.configureTestingModule({
      imports: [Plataforma],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const sesion = TestBed.inject(SesionService);
    sesion.renovarSesion().subscribe();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/yo')
      .flush({
        nombre_usuario: 'usuario1.esart',
        nombre_completo: 'MY Juan Pérez',
        rol: 'USUARIO',
        permisos,
        menu,
        expira_por_inactividad_segundos: 1800,
      });
    const fixture = TestBed.createComponent(Plataforma);
    await fixture.whenStable();
    return { pagina: fixture.nativeElement as HTMLElement, sesion };
  }

  it('dibuja en el sidebar solo los módulos del menú del usuario', async () => {
    const { pagina } = await crearConMenu(MENU_USUARIO, ['DASHBOARD', 'PERSONAL_MILITAR', 'PERSONAL_VERIFICAR']);
    // El segundo <span> de cada enlace es el nombre (el primero es el ícono).
    const enlaces = [...pagina.querySelectorAll('#sidebar-modulos a span:last-child')].map((s) => s.textContent?.trim());
    expect(enlaces).toEqual(['Panel principal', 'Personal militar']);
    expect(pagina.textContent).not.toContain('Gestión de usuarios');
  });

  it('muestra el usuario con sus iniciales y el nombre del rol', async () => {
    const { pagina } = await crearConMenu(MENU_USUARIO, []);
    expect(pagina.textContent).toContain('MY Juan Pérez');
    expect(pagina.textContent).toContain('Usuario');
    expect(pagina.textContent).toContain('MJ');
  });

  it('avisa si el rol no tiene módulos asignados', async () => {
    const { pagina } = await crearConMenu([], []);
    expect(pagina.textContent).toContain('Su rol no tiene módulos asignados.');
  });

  it('tienePermiso refleja la malla recibida', async () => {
    const { sesion } = await crearConMenu(MENU_USUARIO, ['PERSONAL_VERIFICAR', 'VER_DOCUMENTO_COMPLETO']);
    expect(sesion.tienePermiso('VER_DOCUMENTO_COMPLETO')).toBe(true);
    expect(sesion.tienePermiso('USUARIOS')).toBe(false);
  });
});
