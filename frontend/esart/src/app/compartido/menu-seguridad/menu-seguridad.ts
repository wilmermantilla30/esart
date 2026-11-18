import {
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { RUTA_PAGINA_CAMBIAR_CONTRASENA } from '../../nucleo/rutas-paginas';
import { EstadoTotp, TotpService } from '../../nucleo/servicios/totp.service';
import { Totp } from '../../paginas/totp/totp';

/** Punto de acceso a la seguridad de la cuenta; las operaciones siguen en Totp. */
@Component({
  selector: 'esart-menu-seguridad',
  imports: [RouterLink, Totp],
  templateUrl: './menu-seguridad.html',
  styleUrl: './menu-seguridad.css',
})
export class MenuSeguridad {
  private readonly servicio = inject(TotpService);
  private readonly destruccion = inject(DestroyRef);
  private readonly elemento = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly boton = viewChild<ElementRef<HTMLButtonElement>>('llave');
  protected readonly rutaContrasena = '/' + RUTA_PAGINA_CAMBIAR_CONTRASENA;
  protected readonly abierto = signal(false);
  protected readonly dialogo = signal(false);
  protected readonly cargando = signal(false);
  protected readonly error = signal(false);
  protected readonly estado = signal<EstadoTotp | null>(null);
  protected readonly etiqueta = computed(() => {
    if (this.cargando()) return 'Consultando estado…';
    if (this.error()) return 'Estado no disponible';
    const estado = this.estado();
    if (estado?.activo) return 'Autenticador activo';
    switch (estado?.estado) {
      case 'PENDIENTE':
        return 'Pendiente de validación';
      case 'BLOQUEADO':
        return 'Autenticador bloqueado';
      case 'REVOCADO':
        return 'Autenticador revocado';
      default:
        return estado?.configurado ? 'Vinculación por revisar' : 'No configurado';
    }
  });
  protected readonly accion = computed(() =>
    this.estado()?.activo
      ? 'Administrar autenticador'
      : this.estado()?.estado === 'PENDIENTE'
        ? 'Completar configuración'
        : 'Configurar autenticador',
  );

  protected alternar(): void {
    if (this.abierto()) {
      this.cerrarMenu();
      return;
    }
    this.abierto.set(true);
    this.consultar();
  }

  protected consultar(): void {
    if (this.cargando()) return;
    this.cargando.set(true);
    this.error.set(false);
    this.estado.set(null);
    this.servicio
      .estado()
      .pipe(takeUntilDestroyed(this.destruccion))
      .subscribe({
        next: (estado) => {
          this.estado.set(estado);
          this.cargando.set(false);
        },
        error: () => {
          this.error.set(true);
          this.cargando.set(false);
        },
      });
  }

  protected abrirAutenticador(): void {
    if (this.cargando() || this.error() || !this.estado() || this.estado()?.estado === 'BLOQUEADO')
      return;
    this.abierto.set(false);
    this.boton()?.nativeElement.focus();
    this.dialogo.set(true);
  }

  protected cerrarDialogo(): void {
    this.dialogo.set(false);
    this.consultar();
    this.boton()?.nativeElement.focus();
  }

  protected cerrarMenu(): void {
    this.abierto.set(false);
  }

  @HostListener('document:click', ['$event'])
  fuera(evento: MouseEvent): void {
    if (!this.elemento.nativeElement.contains(evento.target as Node)) this.cerrarMenu();
  }

  @HostListener('document:keydown', ['$event'])
  teclado(evento: KeyboardEvent): void {
    if (this.dialogo()) return; // El diálogo existente gestiona Escape y la trampa de foco.
    if (evento.key === 'Escape' && this.abierto()) {
      this.cerrarMenu();
      this.boton()?.nativeElement.focus();
      evento.preventDefault();
    }
    if (!this.abierto() || !this.elemento.nativeElement.contains(evento.target as Node)) return;
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(evento.key)) return;
    const opciones = [
      ...this.elemento.nativeElement.querySelectorAll<HTMLElement>(
        '#seguridad-opciones a, #seguridad-opciones button:not(:disabled)',
      ),
    ];
    if (!opciones.length) return;
    const actual = opciones.indexOf(document.activeElement as HTMLElement);
    const siguiente =
      evento.key === 'Home'
        ? 0
        : evento.key === 'End'
          ? opciones.length - 1
          : evento.key === 'ArrowDown'
            ? (actual + 1) % opciones.length
            : (actual <= 0 ? opciones.length : actual) - 1;
    opciones[siguiente].focus();
    evento.preventDefault();
  }

  @HostListener('focusout', ['$event'])
  focoFuera(evento: FocusEvent): void {
    if (evento.relatedTarget && !this.elemento.nativeElement.contains(evento.relatedTarget as Node))
      this.cerrarMenu();
  }
}
