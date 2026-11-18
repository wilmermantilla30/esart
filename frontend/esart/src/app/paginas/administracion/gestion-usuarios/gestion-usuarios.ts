import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { contrasenaValida, generarContrasenaTemporal, revisarContrasena } from '../../../nucleo/contrasenas';
import { MilitarParaUsuario, UsuarioGestion } from '../../../nucleo/modelos/administracion';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import { AccionUsuario, AdministracionService } from '../../../nucleo/servicios/administracion.service';
import { SesionService } from '../../../nucleo/servicios/sesion.service';

const COMPONENTE = 'USUARIOS';
const PATRON_CEDULA = /^\d{5,15}$/;

/** Lo que se muestra UNA vez tras crear o restablecer, para entregárselo al usuario. */
export interface CredencialEntregable {
  titulo: string;
  usuario: string;
  nombre: string | null;
  contrasenaTemporal: string;
}

/** Texto del estado de un usuario para la tabla (activo, bloqueado, contraseña temporal). */
export function estadoDeUsuario(usuario: UsuarioGestion): { texto: string; clases: string; icono: string } {
  if (!usuario.activo) {
    return { texto: 'Inactivo', clases: 'bg-gris-claro text-azul-pizarra/70 border-gris-bordes', icono: 'block' };
  }
  if (usuario.bloqueado) {
    return { texto: 'Bloqueado', clases: 'bg-error/10 text-error border-error/30', icono: 'lock' };
  }
  if (usuario.requiere_cambio_contrasena) {
    return { texto: 'Contraseña temporal', clases: 'bg-warning/10 text-warning border-warning/40', icono: 'lock_reset' };
  }
  return { texto: 'Activo', clases: 'bg-success/10 text-success border-success/30', icono: 'check_circle' };
}

/**
 * Gestión de usuarios (componente USUARIOS, HU-10).
 *
 * Todo usuario corresponde a un militar de Personal militar: se busca su cédula, se sugiere
 * el nombre de usuario (editable), se elige el rol y se da una contraseña temporal que el
 * usuario debe cambiar al entrar. Las reglas (no desactivarse a sí mismo, siempre un
 * administrador de permisos, auditoría) las aplica el backend.
 */
@Component({
  selector: 'esart-gestion-usuarios',
  imports: [FormsModule],
  templateUrl: './gestion-usuarios.html',
})
export class GestionUsuarios {
  private readonly administracion = inject(AdministracionService);
  private readonly sesion = inject(SesionService);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly puedeCrear = computed(() => this.sesion.puede(COMPONENTE, 'crear'));
  protected readonly puedeActualizar = computed(() => this.sesion.puede(COMPONENTE, 'actualizar'));
  protected readonly miUsuario = computed(() => this.sesion.usuario()?.nombre_usuario ?? '');
  protected readonly estadoDeUsuario = estadoDeUsuario;

  // --- Lista ---
  protected texto = '';
  protected readonly usuarios = signal<UsuarioGestion[]>([]);
  protected readonly cargando = signal(false);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);
  /** Id del usuario con una acción en curso (deshabilita sus botones). */
  protected readonly ocupado = signal<number | null>(null);

  // --- Nuevo usuario ---
  protected readonly creando = signal(false);
  protected readonly cedula = signal('');
  protected readonly buscandoMilitar = signal(false);
  protected readonly militar = signal<MilitarParaUsuario | null>(null);
  protected readonly errorAlta = signal<ErrorApi | null>(null);
  protected readonly nombreUsuario = signal('');
  protected readonly rol = signal<'USUARIO' | 'ADMINISTRADOR'>('USUARIO');
  protected readonly contrasenaTemporal = signal('');
  protected readonly guardando = signal(false);
  protected readonly reglasAlta = computed(() => revisarContrasena(this.contrasenaTemporal()));
  protected readonly puedeGuardarAlta = computed(() => {
    const militar = this.militar();
    return (
      !!militar &&
      militar.activo &&
      !militar.usuario_existente &&
      /^\S{3,80}$/.test(this.nombreUsuario().trim()) &&
      contrasenaValida(this.contrasenaTemporal())
    );
  });

  // --- Restablecer contraseña ---
  protected readonly restableciendo = signal<UsuarioGestion | null>(null);
  protected readonly contrasenaRestablecida = signal('');
  protected readonly errorRestablecer = signal<ErrorApi | null>(null);

  /** Credencial para entregar al usuario: se muestra una vez y se borra al cerrar el aviso. */
  protected readonly credencial = signal<CredencialEntregable | null>(null);

  constructor() {
    this.cargar();
    this.abrirDesdeRegistro();
  }

  /**
   * Llegada desde "Registro manual de personal" (/administracion/usuarios?cedula=...): abre el
   * alta con la cédula ya buscada. Solo si el usuario puede crear usuarios.
   */
  private abrirDesdeRegistro(): void {
    const cedula = this.ruta.snapshot.queryParamMap.get('cedula') ?? '';
    if (!PATRON_CEDULA.test(cedula) || !this.puedeCrear()) return;
    this.abrirAlta();
    this.cedula.set(cedula);
    this.buscarMilitar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.administracion.listarUsuariosGestion(this.texto).subscribe({
      next: (usuarios) => {
        this.usuarios.set(usuarios);
        this.cargando.set(false);
      },
      error: (error: unknown) => {
        this.error.set(leerErrorApi(error));
        this.cargando.set(false);
      },
    });
  }

  protected fecha(valor: string | null): string {
    return valor ? new Date(valor).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' }) : 'Nunca';
  }

  // --- Nuevo usuario ---

  protected abrirAlta(): void {
    this.creando.set(true);
    this.cedula.set('');
    this.militar.set(null);
    this.errorAlta.set(null);
    this.nombreUsuario.set('');
    this.rol.set('USUARIO');
    this.contrasenaTemporal.set(generarContrasenaTemporal());
  }

  protected cerrarAlta(): void {
    this.creando.set(false);
    this.contrasenaTemporal.set('');
    this.militar.set(null);
  }

  protected buscarMilitar(): void {
    const cedula = this.cedula().trim();
    this.militar.set(null);
    if (!PATRON_CEDULA.test(cedula)) {
      this.errorAlta.set({
        codigo: 'DATOS_INVALIDOS',
        mensaje: 'Escriba la cédula solo con números (5 a 15 dígitos).',
        detalle: null,
        estadoHttp: 0,
      });
      return;
    }
    this.buscandoMilitar.set(true);
    this.errorAlta.set(null);
    this.administracion.buscarMilitarParaUsuario(cedula).subscribe({
      next: (militar) => {
        this.militar.set(militar);
        this.nombreUsuario.set(militar.nombre_usuario_sugerido);
        this.buscandoMilitar.set(false);
      },
      error: (error: unknown) => {
        this.errorAlta.set(leerErrorApi(error));
        this.buscandoMilitar.set(false);
      },
    });
  }

  protected generarParaAlta(): void {
    this.contrasenaTemporal.set(generarContrasenaTemporal());
  }

  protected crear(): void {
    const militar = this.militar();
    if (!militar || !this.puedeGuardarAlta() || this.guardando()) {
      return;
    }
    if (
      this.rol() === 'ADMINISTRADOR' &&
      !confirm(`¿Crear a ${this.nombreUsuario().trim()} como ADMINISTRADOR? Tendrá todos los permisos.`)
    ) {
      return;
    }
    this.guardando.set(true);
    this.errorAlta.set(null);
    const contrasena = this.contrasenaTemporal();
    this.administracion
      .crearUsuario({
        documento_identidad: militar.documento_identidad,
        nombre_usuario: this.nombreUsuario().trim(),
        rol: this.rol(),
        contrasena_temporal: contrasena,
      })
      .subscribe({
        next: (creado) => {
          this.guardando.set(false);
          this.cerrarAlta();
          this.credencial.set({
            titulo: 'Usuario creado',
            usuario: creado.usuario,
            nombre: creado.nombre_completo,
            contrasenaTemporal: contrasena,
          });
          this.cargar();
        },
        error: (error: unknown) => {
          this.errorAlta.set(leerErrorApi(error));
          this.guardando.set(false);
        },
      });
  }

  // --- Acciones sobre un usuario ---

  protected aplicar(usuario: UsuarioGestion, accion: AccionUsuario): void {
    if (accion === 'desactivar' && !confirm(`¿Desactivar a ${usuario.usuario}? Se cerrarán sus sesiones abiertas.`)) {
      return;
    }
    this.ocupado.set(usuario.id);
    this.error.set(null);
    this.aviso.set(null);
    this.administracion.aplicarAccionUsuario(usuario.id, accion).subscribe({
      next: (actualizado) => {
        this.reemplazarFila(actualizado);
        const textos: Record<AccionUsuario, string> = {
          activar: 'activado',
          desactivar: 'desactivado',
          desbloquear: 'desbloqueado',
        };
        this.aviso.set(`Usuario ${actualizado.usuario} ${textos[accion]}.`);
        this.ocupado.set(null);
      },
      error: (error: unknown) => {
        this.error.set(leerErrorApi(error));
        this.ocupado.set(null);
      },
    });
  }

  protected abrirRestablecer(usuario: UsuarioGestion): void {
    this.restableciendo.set(usuario);
    this.contrasenaRestablecida.set(generarContrasenaTemporal());
    this.errorRestablecer.set(null);
  }

  protected cerrarRestablecer(): void {
    this.restableciendo.set(null);
    this.contrasenaRestablecida.set('');
  }

  protected generarParaRestablecer(): void {
    this.contrasenaRestablecida.set(generarContrasenaTemporal());
  }

  protected confirmarRestablecer(): void {
    const usuario = this.restableciendo();
    const contrasena = this.contrasenaRestablecida();
    if (!usuario || !contrasenaValida(contrasena)) {
      return;
    }
    this.ocupado.set(usuario.id);
    this.errorRestablecer.set(null);
    this.administracion.restablecerContrasena(usuario.id, contrasena).subscribe({
      next: (actualizado) => {
        this.reemplazarFila(actualizado);
        this.cerrarRestablecer();
        this.credencial.set({
          titulo: 'Contraseña restablecida',
          usuario: actualizado.usuario,
          nombre: actualizado.nombre_completo,
          contrasenaTemporal: contrasena,
        });
        this.ocupado.set(null);
      },
      error: (error: unknown) => {
        this.errorRestablecer.set(leerErrorApi(error));
        this.ocupado.set(null);
      },
    });
  }

  protected copiar(texto: string): void {
    void navigator.clipboard?.writeText(texto);
  }

  protected cerrarCredencial(): void {
    this.credencial.set(null);
  }

  private reemplazarFila(actualizado: UsuarioGestion): void {
    this.usuarios.update((lista) => lista.map((u) => (u.id === actualizado.id ? actualizado : u)));
  }
}
