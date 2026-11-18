import {
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  inject,
  input,
  output,
  signal,
  OnInit,
  AfterViewInit,
} from '@angular/core';
import { Router } from '@angular/router';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable, finalize, interval } from 'rxjs';
import { toDataURL } from 'qrcode';
import { leerErrorApi } from '../../nucleo/modelos/error-api';
import { RUTA_PAGINA_INICIO, RUTA_PAGINA_INICIO_SESION } from '../../nucleo/rutas-paginas';
import { ModoTotp, OperacionTotp, TotpService } from '../../nucleo/servicios/totp.service';

@Component({
  imports: [ReactiveFormsModule],
  selector: 'app-totp',
  styleUrl: './totp.css',
  templateUrl: './totp.html',
})
export class Totp implements OnInit, AfterViewInit {
  readonly modo = input<ModoTotp>('CONFIGURAR');
  readonly desafioId = input('');
  readonly vinculacionInicial = input(false);
  readonly nombreUsuario = input('');
  readonly volverAlInicioAlCerrar = input(true);
  readonly operacion = input<OperacionTotp | null>(null);
  /** CODIGO_OPERACION: el endpoint de la operación valida el código y ejecuta la acción. */
  readonly verificarCodigo = input<((codigo: string) => Observable<unknown>) | null>(null);
  readonly operacionEtiqueta = input('');
  readonly moduloEtiqueta = input('');
  readonly errorInicial = input('');
  readonly cancelar = output<void>();
  readonly completado = output<{ modo: ModoTotp; autorizacion_id?: string }>();
  private readonly servicio = inject(TotpService);
  private readonly destruccion = inject(DestroyRef);
  private readonly elemento = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly enrutador = inject(Router, { optional: true });
  private readonly focoAnterior = document.activeElement as HTMLElement | null;
  private readonly fb = inject(NonNullableFormBuilder);
  readonly formulario = this.fb.group({
    contrasena: ['', [Validators.required, Validators.maxLength(72)]],
    digitos: this.fb.array(
      Array.from({ length: 6 }, () =>
        this.fb.control('', [Validators.required, Validators.pattern('[0-9]')]),
      ),
    ),
  });
  readonly procesando = signal(false);
  readonly usarRecuperacion = signal(false);
  readonly codigoRecuperacion = this.fb.control('', [
    Validators.required,
    Validators.pattern('[0-9a-f]{32}'),
  ]);
  readonly codigosRecuperacion = signal<string[]>([]);
  readonly error = signal('');
  readonly mensaje = signal('');
  readonly qr = signal('');
  readonly estadoVinculacion = signal('INICIAL');
  readonly claveManual = signal('');
  readonly mostrarClave = signal(false);
  readonly copiado = signal(false);
  readonly expiraEn = signal<number | null>(null);
  readonly sesionValida = signal(false);
  readonly activo = signal(false);
  readonly pendiente = signal(false);
  private readonly identificador = signal('');
  get digitos() {
    return this.formulario.controls.digitos;
  }

  constructor() {
    this.destruccion.onDestroy(() => {
      this.codigosRecuperacion.set([]);
      this.codigoRecuperacion.reset();
      this.limpiarSecreto();
      this.focoAnterior?.focus();
    });
    interval(1000)
      .pipe(takeUntilDestroyed(this.destruccion))
      .subscribe(() => {
        if (this.pendiente() && this.expiraEn() !== null && Date.now() >= this.expiraEn()!) {
          this.limpiarSecreto();
          this.estadoVinculacion.set('EXPIRADA');
          this.error.set(
            this.vinculacionInicial()
              ? 'La vinculación expiró. Cancele y vuelva a iniciar sesión para obtener otro QR.'
              : 'La configuración expiró. Confirme su contraseña para iniciar otra vinculación.',
          );
        }
      });
  }
  ngAfterViewInit(): void {
    this.elemento.nativeElement.querySelector<HTMLInputElement>('input')?.focus();
  }
  @HostListener('document:keydown', ['$event'])
  teclado(evento: KeyboardEvent): void {
    if (evento.key === 'Escape') {
      evento.preventDefault();
      this.cerrar();
    }
    if (evento.key !== 'Tab') return;
    const entradas = [
      ...this.elemento.nativeElement.querySelectorAll<HTMLElement>('button,input'),
    ].filter((e) => !e.hasAttribute('disabled'));
    const primero = entradas[0],
      ultimo = entradas[entradas.length - 1];
    if (evento.shiftKey && document.activeElement === primero) {
      evento.preventDefault();
      ultimo?.focus();
    }
    if (!evento.shiftKey && document.activeElement === ultimo) {
      evento.preventDefault();
      primero?.focus();
    }
  }

  ngOnInit(): void {
    this.identificador.set(this.desafioId());
    if (this.errorInicial()) this.error.set(this.errorInicial());
    if (this.modo() === 'CONFIGURAR') {
      if (this.vinculacionInicial()) {
        this.configurar();
        return;
      }
      this.ejecutar(this.servicio.estado(), (r) => {
        this.activo.set(r.activo);
        this.sesionValida.set(true);
      });
    } else if (this.modo() === 'DESBLOQUEO') {
      this.ejecutar(this.servicio.solicitarDesbloqueo(this.nombreUsuario()), (r) =>
        this.identificador.set(r.desafio_id),
      );
    } else if (this.modo() === 'AUTORIZAR_ACCION' && this.operacion()) {
      this.ejecutar(this.servicio.crearDesafio(this.operacion()!), (r) =>
        this.identificador.set(r.desafio_id),
      );
    }
  }
  private ejecutar<T>(solicitud: Observable<T>, correcto: (r: T) => void): void {
    if (this.procesando()) return;
    this.procesando.set(true);
    this.error.set('');
    solicitud
      .pipe(
        takeUntilDestroyed(this.destruccion),
        finalize(() => {
          this.procesando.set(false);
        }),
      )
      .subscribe({
        next: correcto,
        error: (fallo) => {
          const error = leerErrorApi(fallo);
          this.error.set(error.mensaje);
          if (this.modo() === 'CONFIGURAR') {
            this.estadoVinculacion.set(
              error.estadoHttp === 401
                ? 'SESION_REQUERIDA'
                : error.estadoHttp === 0 || error.estadoHttp >= 500
                  ? 'ERROR_CONEXION'
                  : 'CODIGO_INCORRECTO',
            );
            if (error.estadoHttp === 401 && !this.pendiente()) this.sesionValida.set(false);
          }
          this.digitos.reset();
        },
      });
  }
  configurar(): void {
    if (
      (!this.vinculacionInicial() && this.formulario.controls.contrasena.invalid) ||
      this.procesando() ||
      (!this.vinculacionInicial() && !this.sesionValida()) ||
      this.pendiente()
    )
      return;
    this.estadoVinculacion.set('GENERANDO_QR');
    const solicitud = this.vinculacionInicial()
      ? this.servicio.configurarLogin(this.identificador())
      : this.servicio.configurar(this.formulario.controls.contrasena.value);
    this.ejecutar(solicitud, (r) => {
      if (!URL.canParse(r.uri)) {
        this.estadoVinculacion.set('ERROR_CONEXION');
        this.error.set('El servidor no entregó una configuración válida.');
        return;
      }
      const uri = new URL(r.uri);
      const clave = uri.searchParams.get('secret') ?? '';
      const vencimiento = Date.parse(r.expira_en);
      if (
        uri.protocol !== 'otpauth:' ||
        uri.hostname !== 'totp' ||
        !/^[A-Z2-7]+$/.test(clave) ||
        !Number.isFinite(vencimiento) ||
        vencimiento <= Date.now()
      ) {
        this.estadoVinculacion.set('EXPIRADA');
        this.error.set('La configuración recibida no es válida o ha expirado.');
        return;
      }
      this.claveManual.set(clave);
      this.expiraEn.set(vencimiento);
      this.pendiente.set(true);
      toDataURL(r.uri, { width: 240, margin: 2, errorCorrectionLevel: 'M' })
        .then((imagen) => {
          if (!this.destruccion.destroyed && this.pendiente() && Date.now() < this.expiraEn()!) {
            this.qr.set(imagen);
            this.estadoVinculacion.set('QR_DISPONIBLE');
          }
        })
        .catch(() => {
          this.estadoVinculacion.set('ERROR_CONEXION');
          this.error.set(
            'No fue posible generar el QR local. Cierre y vuelva a abrir para recuperar la configuración pendiente.',
          );
        });
    });
    this.formulario.controls.contrasena.reset();
  }
  verificar(): void {
    if (this.modo() === 'LOGIN' && this.usarRecuperacion()) {
      if (this.codigoRecuperacion.invalid || this.procesando()) return;
      this.ejecutar(
        this.servicio.confirmarLogin(this.identificador(), this.codigoRecuperacion.value, true),
        () => {
          this.codigoRecuperacion.reset();
          this.terminar();
        },
      );
      return;
    }
    if (this.digitos.invalid || this.procesando()) {
      this.digitos.markAllAsTouched();
      return;
    }
    const codigo = this.digitos.getRawValue().join('');
    if (this.modo() === 'LOGIN') {
      this.ejecutar(this.servicio.confirmarLogin(this.identificador(), codigo), () =>
        this.terminar(),
      );
    } else if (this.modo() === 'DESBLOQUEO') {
      this.ejecutar(this.servicio.confirmarDesbloqueo(this.identificador(), codigo), () =>
        this.terminar(),
      );
    } else if (this.modo() === 'CODIGO_OPERACION' && this.verificarCodigo()) {
      this.ejecutar(this.verificarCodigo()!(codigo), () => this.terminar());
    } else if (this.modo() === 'AUTORIZAR_ACCION' && this.operacion()) {
      this.ejecutar(
        this.servicio.verificarAccion(this.identificador(), this.operacion()!, codigo),
        (r) => {
          this.digitos.reset();
          this.completado.emit({ modo: this.modo(), autorizacion_id: r.autorizacion_id });
        },
      );
    } else if (this.modo() === 'CONFIGURAR' && this.pendiente()) {
      if (this.expiraEn() === null || Date.now() >= this.expiraEn()!) return;
      this.estadoVinculacion.set('VERIFICANDO');
      const solicitud = this.vinculacionInicial()
        ? this.servicio.confirmarVinculacionLogin(this.identificador(), codigo)
        : this.servicio.confirmar(codigo);
      this.ejecutar<{ codigos_recuperacion?: string[] }>(solicitud, (r) => {
        this.activo.set(true);
        this.limpiarSecreto();
        this.estadoVinculacion.set('EXITOSA');
        this.codigosRecuperacion.set(r.codigos_recuperacion ?? []);
        if (!this.codigosRecuperacion().length) this.completado.emit({ modo: 'CONFIGURAR' });
        this.digitos.reset();
        this.mensaje.set(
          'Autenticador activado. Para la siguiente verificación espere un código nuevo.',
        );
      });
    }
  }
  desactivar(): void {
    if (this.formulario.controls.contrasena.invalid || this.digitos.invalid || this.procesando())
      return;
    this.ejecutar(
      this.servicio.desactivar(
        this.formulario.controls.contrasena.value,
        this.digitos.getRawValue().join(''),
      ),
      () => {
        this.activo.set(false);
        this.digitos.reset();
        this.mensaje.set('Autenticador revocado.');
        this.servicio.olvidarSesion();
        this.sesionValida.set(false);
        void this.enrutador?.navigateByUrl('/' + RUTA_PAGINA_INICIO_SESION);
      },
    );
    this.formulario.controls.contrasena.reset();
  }
  private terminar(): void {
    this.digitos.reset();
    this.completado.emit({ modo: this.modo() });
  }
  confirmarGuardado(): void {
    this.codigosRecuperacion.set([]);
    this.completado.emit({ modo: 'CONFIGURAR' });
  }
  renovarRecuperacion(): void {
    if (this.formulario.controls.contrasena.invalid || this.digitos.invalid) return;
    this.ejecutar(
      this.servicio.renovarRecuperacion(
        this.formulario.controls.contrasena.value,
        this.digitos.getRawValue().join(''),
      ),
      (r) => {
        this.codigosRecuperacion.set(r.codigos_recuperacion);
        this.digitos.reset();
      },
    );
    this.formulario.controls.contrasena.reset();
  }
  revocarConRecuperacion(): void {
    if (this.formulario.controls.contrasena.invalid || this.codigoRecuperacion.invalid) return;
    this.ejecutar(
      this.servicio.revocarConRecuperacion(
        this.formulario.controls.contrasena.value,
        this.codigoRecuperacion.value,
      ),
      () => {
        this.codigoRecuperacion.reset();
        this.activo.set(false);
        this.sesionValida.set(false);
        this.servicio.olvidarSesion();
        this.mensaje.set(
          'Autenticador y sesiones revocados. Inicie sesión para vincular otro dispositivo.',
        );
      },
    );
    this.formulario.controls.contrasena.reset();
  }
  pegar(evento: ClipboardEvent): void {
    const texto = evento.clipboardData?.getData('text').trim() ?? '';
    if (/^[0-9]{6}$/.test(texto)) {
      evento.preventDefault();
      this.digitos.setValue(texto.split(''));
    }
  }
  avanzar(indice: number, evento: Event): void {
    const entrada = evento.target as HTMLInputElement;
    const valor = entrada.value.replace(/[^0-9]/g, '').slice(-1);
    this.digitos.at(indice).setValue(valor);
    if (valor && indice < 5)
      this.elemento.nativeElement.querySelector<HTMLInputElement>(`#totp-${indice + 1}`)?.focus();
  }
  private limpiarSecreto(): void {
    this.qr.set('');
    this.claveManual.set('');
    this.mostrarClave.set(false);
    this.copiado.set(false);
    this.pendiente.set(false);
    this.expiraEn.set(null);
  }
  fechaExpiracion(): string {
    return this.expiraEn() === null ? '' : new Date(this.expiraEn()!).toLocaleTimeString();
  }
  async copiarClave(): Promise<void> {
    if (!this.claveManual() || !this.pendiente()) return;
    try {
      await navigator.clipboard.writeText(this.claveManual());
      if (!this.destruccion.destroyed && this.pendiente()) this.copiado.set(true);
    } catch {
      this.error.set(
        'El navegador no permite copiar. Muestre la clave y transcríbala en su autenticador.',
      );
    }
  }
  cerrar(): void {
    if (!this.procesando()) {
      this.codigosRecuperacion.set([]);
      this.codigoRecuperacion.reset();
      this.digitos.reset();
      this.formulario.controls.contrasena.reset();
      this.limpiarSecreto();
      this.cancelar.emit();
    }
    if (!this.procesando() && this.modo() === 'CONFIGURAR' && this.volverAlInicioAlCerrar())
      void this.enrutador?.navigateByUrl('/' + RUTA_PAGINA_INICIO);
  }
}
