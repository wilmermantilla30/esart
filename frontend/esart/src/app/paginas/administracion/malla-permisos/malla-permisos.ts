import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  CambioPermisoUsuario,
  ComponenteMalla,
  ModoPermisoUsuario,
  Operaciones,
  RespuestaPermisosRol,
  RespuestaPermisosUsuario,
  ResumenRol,
  UsuarioMalla,
} from '../../../nucleo/modelos/administracion';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import { AdministracionService } from '../../../nucleo/servicios/administracion.service';

type NombreOperacion = keyof Operaciones;

/** Columnas de la malla, en el orden en que se muestran. */
export const COLUMNAS: ReadonlyArray<{ clave: NombreOperacion; titulo: string }> = [
  { clave: 'acceder', titulo: 'Acceder' },
  { clave: 'crear', titulo: 'Crear' },
  { clave: 'leer', titulo: 'Leer' },
  { clave: 'actualizar', titulo: 'Editar' },
  { clave: 'eliminar', titulo: 'Eliminar' },
];

const MODOS: ReadonlyArray<{ valor: ModoPermisoUsuario; texto: string }> = [
  { valor: 'HEREDAR', texto: 'Según su rol' },
  { valor: 'CONCEDER', texto: 'Conceder' },
  { valor: 'QUITAR', texto: 'Quitar' },
];

const SIN_PERMISOS: Operaciones = { acceder: false, crear: false, leer: false, actualizar: false, eliminar: false };

interface EdicionUsuario {
  modo: ModoPermisoUsuario;
  operaciones: Operaciones;
}

/** Resumen legible de unas operaciones: "Acceder · Leer" o "Sin acceso". */
export function resumirOperaciones(operaciones: Operaciones | null | undefined): string {
  if (!operaciones?.acceder) {
    return 'Sin acceso';
  }
  return COLUMNAS.filter((c) => operaciones[c.clave]).map((c) => c.titulo).join(' · ');
}

/** Regla de la malla: sin "Acceder" no vale nada; marcar otra operación marca "Acceder". */
export function aplicarCambio(actual: Operaciones, clave: NombreOperacion, valor: boolean): Operaciones {
  if (clave === 'acceder' && !valor) {
    return { ...SIN_PERMISOS };
  }
  return { ...actual, [clave]: valor, acceder: clave === 'acceder' ? valor : actual.acceder || valor };
}

function iguales(a: Operaciones, b: Operaciones): boolean {
  return COLUMNAS.every((c) => a[c.clave] === b[c.clave]);
}

/**
 * Malla de permisos (componente PERMISOS): qué puede hacer cada rol y excepciones por usuario.
 * El rol ADMINISTRADOR y los usuarios administradores se muestran completos y no se editan.
 */
@Component({
  selector: 'esart-malla-permisos',
  imports: [FormsModule],
  templateUrl: './malla-permisos.html',
})
export class MallaPermisos {
  private readonly administracion = inject(AdministracionService);

  protected readonly columnas = COLUMNAS;
  protected readonly modos = MODOS;
  protected readonly resumir = resumirOperaciones;

  protected readonly pestana = signal<'ROL' | 'USUARIO'>('ROL');
  protected readonly guardando = signal(false);
  protected readonly mensaje = signal<string | null>(null);
  protected readonly error = signal<ErrorApi | null>(null);

  // --- Por rol ---
  protected readonly roles = signal<ResumenRol[]>([]);
  protected readonly datosRol = signal<RespuestaPermisosRol | null>(null);
  protected readonly edicionRol = signal<Record<string, Operaciones>>({});

  // --- Por usuario ---
  protected textoUsuario = '';
  protected readonly usuarios = signal<UsuarioMalla[]>([]);
  protected readonly datosUsuario = signal<RespuestaPermisosUsuario | null>(null);
  protected readonly edicionUsuario = signal<Record<string, EdicionUsuario>>({});

  protected readonly cambiosRol = computed(() => {
    const datos = this.datosRol();
    const edicion = this.edicionRol();
    return (datos?.filas ?? []).filter((f) => !iguales(f.permisos, edicion[f.codigo] ?? f.permisos));
  });

  protected readonly cambiosUsuario = computed(() => {
    const datos = this.datosUsuario();
    const edicion = this.edicionUsuario();
    return (datos?.filas ?? []).filter((f) => {
      const editado = edicion[f.codigo];
      if (!editado) {
        return false;
      }
      if (editado.modo !== f.modo) {
        return true;
      }
      // Mismo modo: solo cambia algo si es "Conceder" con otras operaciones.
      return f.modo === 'CONCEDER' && !iguales(editado.operaciones, f.excepcion ?? SIN_PERMISOS);
    });
  });

  constructor() {
    this.administracion.listarRoles().subscribe({
      next: (roles) => {
        this.roles.set(roles);
        // Se abre el primer rol editable (USUARIO); el administrador es fijo.
        const inicial = roles.find((r) => r.editable) ?? roles[0];
        if (inicial) {
          this.seleccionarRol(inicial.codigo);
        }
      },
      error: (error: unknown) => this.error.set(leerErrorApi(error)),
    });
  }

  protected cambiarPestana(pestana: 'ROL' | 'USUARIO'): void {
    this.pestana.set(pestana);
    this.mensaje.set(null);
    this.error.set(null);
    if (pestana === 'USUARIO' && this.usuarios().length === 0) {
      this.buscarUsuarios();
    }
  }

  protected sangria(fila: ComponenteMalla): boolean {
    return fila.codigo_padre !== null;
  }

  // --- Por rol ---------------------------------------------------------------------------

  protected seleccionarRol(codigo: string): void {
    this.mensaje.set(null);
    this.error.set(null);
    this.administracion.permisosDeRol(codigo).subscribe({
      next: (datos) => this.cargarRol(datos),
      error: (error: unknown) => this.error.set(leerErrorApi(error)),
    });
  }

  private cargarRol(datos: RespuestaPermisosRol): void {
    this.datosRol.set(datos);
    this.edicionRol.set(Object.fromEntries(datos.filas.map((f) => [f.codigo, { ...f.permisos }])));
  }

  protected operacionRol(codigo: string, clave: NombreOperacion): boolean {
    return this.edicionRol()[codigo]?.[clave] ?? false;
  }

  protected cambiarOperacionRol(codigo: string, clave: NombreOperacion, valor: boolean): void {
    this.edicionRol.update((edicion) => ({ ...edicion, [codigo]: aplicarCambio(edicion[codigo] ?? SIN_PERMISOS, clave, valor) }));
  }

  protected descartarRol(): void {
    const datos = this.datosRol();
    if (datos) {
      this.cargarRol(datos);
    }
  }

  protected guardarRol(): void {
    const datos = this.datosRol();
    const cambios = this.cambiosRol();
    if (!datos || cambios.length === 0) {
      return;
    }
    const edicion = this.edicionRol();
    this.guardando.set(true);
    this.error.set(null);
    this.administracion
      .guardarPermisosDeRol(
        datos.rol,
        cambios.map((f) => ({ componente: f.codigo, ...edicion[f.codigo]! })),
      )
      .subscribe({
        next: (respuesta) => {
          this.cargarRol(respuesta);
          this.mensaje.set(`Permisos del rol ${respuesta.nombre} guardados (${cambios.length} módulo(s)).`);
          this.guardando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.guardando.set(false);
        },
      });
  }

  // --- Por usuario -----------------------------------------------------------------------

  protected buscarUsuarios(): void {
    this.administracion.listarUsuarios(this.textoUsuario).subscribe({
      next: (usuarios) => this.usuarios.set(usuarios),
      error: (error: unknown) => this.error.set(leerErrorApi(error)),
    });
  }

  protected seleccionarUsuario(usuario: UsuarioMalla): void {
    this.mensaje.set(null);
    this.error.set(null);
    this.administracion.permisosDeUsuario(usuario.id).subscribe({
      next: (datos) => this.cargarUsuario(datos),
      error: (error: unknown) => this.error.set(leerErrorApi(error)),
    });
  }

  private cargarUsuario(datos: RespuestaPermisosUsuario): void {
    this.datosUsuario.set(datos);
    this.edicionUsuario.set(
      Object.fromEntries(
        datos.filas.map((f) => [f.codigo, { modo: f.modo, operaciones: { ...(f.excepcion ?? SIN_PERMISOS) } }]),
      ),
    );
  }

  protected edicionDe(codigo: string): EdicionUsuario {
    return this.edicionUsuario()[codigo] ?? { modo: 'HEREDAR', operaciones: { ...SIN_PERMISOS } };
  }

  protected cambiarModo(codigo: string, modo: ModoPermisoUsuario): void {
    this.edicionUsuario.update((edicion) => {
      const actual = edicion[codigo] ?? { modo: 'HEREDAR', operaciones: { ...SIN_PERMISOS } };
      // Al conceder se propone "Acceder + Leer" para no guardar un permiso vacío.
      const operaciones =
        modo === 'CONCEDER' && !actual.operaciones.acceder
          ? { ...SIN_PERMISOS, acceder: true, leer: true }
          : actual.operaciones;
      return { ...edicion, [codigo]: { modo, operaciones } };
    });
  }

  protected cambiarOperacionUsuario(codigo: string, clave: NombreOperacion, valor: boolean): void {
    this.edicionUsuario.update((edicion) => {
      const actual = edicion[codigo]!;
      return { ...edicion, [codigo]: { ...actual, operaciones: aplicarCambio(actual.operaciones, clave, valor) } };
    });
  }

  protected descartarUsuario(): void {
    const datos = this.datosUsuario();
    if (datos) {
      this.cargarUsuario(datos);
    }
  }

  protected guardarUsuario(): void {
    const datos = this.datosUsuario();
    const cambios = this.cambiosUsuario();
    if (!datos || cambios.length === 0) {
      return;
    }
    const edicion = this.edicionUsuario();
    const solicitud: CambioPermisoUsuario[] = cambios.map((f) => {
      const editado = edicion[f.codigo]!;
      return {
        componente: f.codigo,
        modo: editado.modo,
        crear: editado.operaciones.crear,
        leer: editado.operaciones.leer,
        actualizar: editado.operaciones.actualizar,
        eliminar: editado.operaciones.eliminar,
      };
    });
    this.guardando.set(true);
    this.error.set(null);
    this.administracion.guardarPermisosDeUsuario(datos.usuario.id, solicitud).subscribe({
      next: (respuesta) => {
        this.cargarUsuario(respuesta);
        this.mensaje.set(
          `Permisos de ${respuesta.usuario.usuario} guardados (${cambios.length} módulo(s)). ` +
            'El usuario verá su menú actualizado al recargar la página.',
        );
        this.guardando.set(false);
      },
      error: (error: unknown) => {
        this.error.set(leerErrorApi(error));
        this.guardando.set(false);
      },
    });
  }
}
