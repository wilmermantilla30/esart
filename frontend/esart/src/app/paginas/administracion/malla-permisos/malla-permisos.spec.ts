import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Operaciones, RespuestaPermisosRol } from '../../../nucleo/modelos/administracion';
import { MallaPermisos, aplicarCambio, resumirOperaciones } from './malla-permisos';

const NADA: Operaciones = { acceder: false, crear: false, leer: false, actualizar: false, eliminar: false };

describe('Regla de casillas de la malla', () => {
  it('marcar una operación marca también Acceder', () => {
    expect(aplicarCambio(NADA, 'leer', true)).toEqual({ ...NADA, acceder: true, leer: true });
  });

  it('quitar Acceder quita todas las operaciones', () => {
    const todo = { acceder: true, crear: true, leer: true, actualizar: true, eliminar: true };
    expect(aplicarCambio(todo, 'acceder', false)).toEqual(NADA);
  });

  it('resume las operaciones en texto', () => {
    expect(resumirOperaciones({ ...NADA, acceder: true, leer: true })).toBe('Acceder · Leer');
    expect(resumirOperaciones(NADA)).toBe('Sin acceso');
  });
});

describe('MallaPermisos', () => {
  const ROL_USUARIO: RespuestaPermisosRol = {
    rol: 'USUARIO',
    nombre: 'Usuario',
    editable: true,
    filas: [
      { codigo: 'DASHBOARD', nombre: 'Panel principal', ruta: '/dashboard', codigo_padre: null, especial: false, permisos: { ...NADA, acceder: true, leer: true } },
      { codigo: 'AUDITORIA', nombre: 'Auditoría', ruta: '/administracion/auditoria', codigo_padre: null, especial: false, permisos: NADA },
    ],
  };

  it('carga el rol editable y guarda solo los módulos cambiados', async () => {
    TestBed.configureTestingModule({ imports: [MallaPermisos], providers: [provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(MallaPermisos);
    const backend = TestBed.inject(HttpTestingController);

    backend.expectOne('/api/administracion/permisos/roles').flush([
      { codigo: 'ADMINISTRADOR', nombre: 'Administrador', editable: false },
      { codigo: 'USUARIO', nombre: 'Usuario', editable: true },
    ]);
    backend.expectOne('/api/administracion/permisos/roles/USUARIO').flush(ROL_USUARIO);
    await fixture.whenStable();

    const pagina = fixture.nativeElement as HTMLElement;
    const casillaLeerAuditoria = pagina.querySelector<HTMLInputElement>('input[aria-label="Leer en Auditoría"]')!;
    casillaLeerAuditoria.checked = true;
    casillaLeerAuditoria.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(pagina.textContent).toContain('1 módulo(s) con cambios');

    [...pagina.querySelectorAll('button')].find((b) => b.textContent?.includes('Guardar cambios'))!.click();
    const guardado = backend.expectOne('/api/administracion/permisos/roles/USUARIO');
    expect(guardado.request.method).toBe('PUT');
    expect(guardado.request.body).toEqual({
      permisos: [{ componente: 'AUDITORIA', acceder: true, crear: false, leer: true, actualizar: false, eliminar: false }],
    });
    backend.verify();
  });
});
