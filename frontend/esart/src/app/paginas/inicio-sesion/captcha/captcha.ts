import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  OnDestroy,
  OnInit,
  inject,
  input,
  output,
  signal,
  OnChanges,
  SimpleChanges,
} from '@angular/core';
import { catchError, interval, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RespuestaCaptcha } from '../../../nucleo/modelos/sesion';
import { leerErrorApi } from '../../../nucleo/modelos/error-api';
import { SesionService } from '../../../nucleo/servicios/sesion.service';

@Component({
  selector: 'app-captcha',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './captcha.html',
  styleUrl: './captcha.css',
})
export class Captcha implements OnInit, OnChanges, AfterViewInit, OnDestroy {
  readonly nombreUsuario = input.required<string>();
  readonly procesando = input(false);
  readonly enviar = output<RespuestaCaptcha>();
  readonly cancelar = output<void>();
  readonly contrasena = input('');
  readonly contrasenaCambiada = output<string>();
  readonly revision = input(0);
  readonly mensajeServidor = input('');
  private expiraEn = 0;
  private readonly sesion = inject(SesionService);
  private readonly destruccion = inject(DestroyRef);
  private readonly elemento: ElementRef<HTMLElement> = inject(ElementRef);
  private readonly focoAnterior = document.activeElement as HTMLElement | null;
  private readonly identificador = signal('');
  protected readonly imagen = signal('');
  protected readonly codigoIngresado = signal('');
  protected readonly certificado = signal(false);
  protected readonly error = signal('');
  protected readonly cargando = signal(false);

  ngOnInit(): void {
    this.generarCodigo();
    interval(1000)
      .pipe(takeUntilDestroyed(this.destruccion))
      .subscribe(() => {
        if (
          this.expiraEn &&
          Date.now() >= this.expiraEn &&
          !this.procesando() &&
          !this.cargando()
        ) {
          this.generarCodigo();
          this.error.set('El código expiró. Se solicitó uno nuevo.');
        }
      });
  }
  ngOnChanges(cambios: SimpleChanges): void {
    if (cambios['revision'] && !cambios['revision'].firstChange) {
      // Un envío de login consume el ID incluso si la solución fue incorrecta.
      // X-ESART-Captcha-Anterior solo sirve para reemplazar uno AÚN no consumido.
      this.identificador.set('');
      this.generarCodigo();
    }
  }
  ngAfterViewInit(): void {
    this.elemento.nativeElement.querySelector<HTMLButtonElement>('button')?.focus();
  }
  ngOnDestroy(): void {
    this.focoAnterior?.focus();
  }

  protected actualizarCodigo(valor: string): void {
    this.codigoIngresado.set(
      valor
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, '')
        .slice(0, 6),
    );
    this.error.set('');
  }
  protected alternarCertificado(valor: boolean): void {
    this.certificado.set(valor);
  }

  protected generarCodigo(): void {
    if (this.cargando() || this.procesando()) return;
    this.cargando.set(true);
    this.expiraEn = 0;
    this.imagen.set('');
    this.codigoIngresado.set('');
    this.error.set('');
    const anterior = this.identificador() || null;
    this.sesion
      .obtenerCaptcha(this.nombreUsuario(), anterior)
      .pipe(
        catchError((fallo: unknown) => {
          // Puede haberse consumido en otro envío. Solo un reintento, sin reutilizar el ID.
          if (anterior && fallo instanceof HttpErrorResponse && fallo.status === 409) {
            this.identificador.set('');
            return this.sesion.obtenerCaptcha(this.nombreUsuario());
          }
          return throwError(() => fallo);
        }),
        takeUntilDestroyed(this.destruccion),
      )
      .subscribe({
        next: (reto) => {
          if (
            !/^[A-Za-z0-9_-]{43}$/.test(reto.captcha_id) ||
            reto.longitud !== 6 ||
            !Number.isFinite(Date.parse(reto.expira_en)) ||
            reto.imagen_png_base64.length > 90000 ||
            !/^[A-Za-z0-9+/]+={0,2}$/.test(reto.imagen_png_base64)
          ) {
            this.identificador.set('');
            this.imagen.set('');
            this.error.set('No fue posible cargar el código. Solicite uno nuevo.');
          } else {
            this.identificador.set(reto.captcha_id);
            this.imagen.set('data:image/png;base64,' + reto.imagen_png_base64);
            this.expiraEn = Date.parse(reto.expira_en);
          }
          this.cargando.set(false);
        },
        error: (fallo) => {
          this.identificador.set('');
          this.imagen.set('');
          this.error.set(leerErrorApi(fallo).mensaje);
          this.cargando.set(false);
        },
      });
  }

  protected validar(): void {
    if (this.cargando() || this.procesando()) return;
    if (!this.contrasena()) {
      this.error.set('Ingrese su contraseña para este intento.');
      return;
    }
    if (this.expiraEn && Date.now() >= this.expiraEn) {
      this.generarCodigo();
      this.error.set('El código expiró. Resuelva el nuevo desafío.');
      return;
    }
    if (!this.certificado()) {
      this.error.set('Debe aceptar la certificación.');
      return;
    }
    if (!this.identificador() || this.codigoIngresado().length !== 6) {
      this.error.set('Ingrese los seis caracteres del código recibido.');
      return;
    }
    // Solo se envía la respuesta del operador. No existe comparación ni aprobación local.
    this.enviar.emit({ id: this.identificador(), respuesta: this.codigoIngresado() });
    this.codigoIngresado.set('');
  }

  protected cerrar(): void {
    if (!this.procesando()) this.cancelar.emit();
  }

  @HostListener('document:keydown', ['$event'])
  protected teclado(evento: KeyboardEvent): void {
    if (evento.key === 'Escape') {
      evento.preventDefault();
      this.cerrar();
    }
    if (evento.key !== 'Tab') return;
    const controles = [
      ...this.elemento.nativeElement.querySelectorAll<HTMLElement>('button,input,[tabindex]'),
    ].filter((e) => !e.hasAttribute('disabled') && e.tabIndex >= 0);
    const primero = controles[0],
      ultimo = controles[controles.length - 1];
    if (evento.shiftKey && document.activeElement === primero) {
      evento.preventDefault();
      ultimo?.focus();
    } else if (!evento.shiftKey && document.activeElement === ultimo) {
      evento.preventDefault();
      primero?.focus();
    }
  }
}
