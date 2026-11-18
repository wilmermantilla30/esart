import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree } from '@angular/router';
import { Observable, firstValueFrom, of } from 'rxjs';

import { SesionService } from '../servicios/sesion.service';
import { exigirPermiso } from './permiso.guard';

describe('exigirPermiso (HU-09)', () => {
  const crearArbol = vi.fn((comandos: string[]) => ({ comandos }) as unknown as UrlTree);

  function evaluar(haySesion: boolean, permisos: string[], componente?: string) {
    TestBed.configureTestingModule({
      providers: [
        { provide: Router, useValue: { createUrlTree: crearArbol } },
        {
          provide: SesionService,
          useValue: {
            comprobarSesion: () => of(haySesion),
            tienePermiso: (codigo: string) => permisos.includes(codigo),
          },
        },
      ],
    });
    const ruta = { data: componente ? { componente } : {} } as unknown as ActivatedRouteSnapshot;
    return TestBed.runInInjectionContext(() =>
      firstValueFrom(
        exigirPermiso(ruta, {} as RouterStateSnapshot) as Observable<boolean | UrlTree>,
      ),
    );
  }

  beforeEach(() => crearArbol.mockClear());

  it('deja pasar si el usuario tiene el permiso del componente', async () => {
    expect(await evaluar(true, ['PERSONAL_VERIFICAR'], 'PERSONAL_VERIFICAR')).toBe(true);
  });

  it('sin el permiso, lleva al Panel principal', async () => {
    await evaluar(true, ['DASHBOARD'], 'USUARIOS');
    expect(crearArbol).toHaveBeenCalledWith(['/', 'dashboard']);
  });

  it('sin sesión, lleva al login', async () => {
    await evaluar(false, [], 'DASHBOARD');
    expect(crearArbol).toHaveBeenCalledWith(['/', 'inicio-sesion']);
  });

  it.each(['USUARIOS', 'PERMISOS', 'AUDITORIA', 'PERSONAL_CARGUE_EXCEL'])(
    'permite el módulo administrativo %s autorizado por el servidor',
    async (codigo) => {
      expect(
        await evaluar(true, ['USUARIOS', 'PERMISOS', 'AUDITORIA', 'PERSONAL_CARGUE_EXCEL'], codigo),
      ).toBe(true);
    },
  );
});
