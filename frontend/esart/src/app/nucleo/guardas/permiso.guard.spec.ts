import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree } from '@angular/router';
import { Observable, firstValueFrom, of } from 'rxjs';

import { SesionService } from '../servicios/sesion.service';
import { exigirPermiso } from './permiso.guard';

describe('exigirPermiso (HU-09)', () => {
  const crearArbol = vi.fn((comandos: string[]) => ({ comandos }) as unknown as UrlTree);

  function evaluar(
    haySesion: boolean,
    permisos: string[],
    componente?: string,
    componentes?: string[],
  ) {
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
    const datos = componentes ? { componentes } : componente ? { componente } : {};
    const ruta = { data: datos } as unknown as ActivatedRouteSnapshot;
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

  it('con una lista de componentes basta con tener uno (S2-09)', async () => {
    const lista = ['PARAMETROS_HABILITACION', 'MALLAS_CURRICULARES'];
    expect(await evaluar(true, ['MALLAS_CURRICULARES'], undefined, lista)).toBe(true);
  });

  it('con una lista de componentes y ninguno, lleva al Panel principal (S2-09)', async () => {
    await evaluar(true, ['DASHBOARD'], undefined, [
      'PARAMETROS_HABILITACION',
      'MALLAS_CURRICULARES',
    ]);
    expect(crearArbol).toHaveBeenCalledWith(['/', 'dashboard']);
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
