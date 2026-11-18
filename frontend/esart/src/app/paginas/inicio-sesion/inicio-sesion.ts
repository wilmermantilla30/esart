import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { EncabezadoInstitucional } from '../../compartido/encabezado-institucional/encabezado-institucional';
import { PieInstitucional } from '../../compartido/pie-institucional/pie-institucional';
import { ErrorApi, leerErrorApi } from '../../nucleo/modelos/error-api';
import {
  MOTIVO_SESION_EXPIRADA,
  PARAMETRO_MOTIVO,
  PARAMETRO_VOLVER_A,
  RUTA_PAGINA_INICIO,
  RUTA_PAGINA_CAMBIAR_CONTRASENA,
  esRutaInternaSegura,
} from '../../nucleo/rutas-paginas';
import {
  DesafioSegundoFactor,
  DetalleBloqueo,
  RespuestaCaptcha,
} from '../../nucleo/modelos/sesion';
import { Totp } from '../totp/totp';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { Captcha } from '../inicio-sesion/captcha/captcha'; //importación del captcha
import { VentanaBloqueo } from '../inicio-sesion/ventana-bloqueo/ventana-bloqueo'; //importacion de la ventan de bloqueo

/** Límites del backend (esquemas/autenticacion.py). Se validan también aquí para avisar antes de enviar. */
export const LONGITUD_MINIMA_USUARIO = 3;
export const LONGITUD_MAXIMA_USUARIO = 80;
export const LONGITUD_MAXIMA_CONTRASENA = 72;

/**
 * Página de inicio de sesión (diseño institucional de Stitch).
 *
 * Solo envía usuario y contraseña al backend y muestra el resultado. Nunca guarda la
 * contraseña: el campo se vacía después de cada intento fallido.
 */
@Component({
  selector: 'esart-inicio-sesion',
  imports: [
    ReactiveFormsModule,
    EncabezadoInstitucional,
    PieInstitucional,
    Captcha,
    VentanaBloqueo,
    Totp,
  ],
  templateUrl: './inicio-sesion.html',
})
export class InicioSesion {
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);
  private readonly rutaActual = inject(ActivatedRoute);
  private readonly destruccion = inject(DestroyRef);
  private relojBloqueo: ReturnType<typeof setInterval> | null = null;
  private usuarioBloqueado = '';

  protected readonly formulario = inject(NonNullableFormBuilder).group({
    nombreUsuario: [
      '',
      [
        Validators.required,
        Validators.minLength(LONGITUD_MINIMA_USUARIO),
        Validators.maxLength(LONGITUD_MAXIMA_USUARIO),
      ],
    ],
    contrasena: ['', [Validators.required, Validators.maxLength(LONGITUD_MAXIMA_CONTRASENA)]],
  });

  protected readonly enviando = signal(false);
  protected readonly contrasenaVisible = signal(false);
  protected readonly errorServidor = signal<ErrorApi | null>(null);

  /** Aviso cuando se llega aquí porque la sesión anterior expiró (lo pone el interceptor). */
  protected readonly sesionExpirada =
    this.rutaActual.snapshot.queryParamMap.get(PARAMETRO_MOTIVO) === MOTIVO_SESION_EXPIRADA;

  protected readonly longitudMinimaUsuario = LONGITUD_MINIMA_USUARIO;
  protected readonly longitudMaximaUsuario = LONGITUD_MAXIMA_USUARIO;
  protected readonly longitudMaximaContrasena = LONGITUD_MAXIMA_CONTRASENA;

  // Estados del CAPTCHA
  readonly captchaRequerido = signal<boolean>(false);
  readonly mostrarCaptcha = signal(false);
  readonly revisionCaptcha = signal(0);
  readonly pasoTotp = signal<DesafioSegundoFactor | null>(null);
  readonly desbloqueoTotp = signal(false);
  readonly accesoRestringido = signal<boolean>(false);
  readonly segundosRestantes = signal<number | null>(null);
  readonly tiempoRestante = computed(() => {
    const segundos = this.segundosRestantes();
    if (segundos === null) return null;
    const horas = Math.floor(segundos / 3600);
    const minutos = Math.floor((segundos % 3600) / 60);
    return `${horas.toString().padStart(2, '0')}:${minutos.toString().padStart(2, '0')}:${(segundos % 60).toString().padStart(2, '0')}`;
  });

  protected readonly mostrarVentanaBloqueo = signal(false);
  protected readonly datosBloqueo = signal<{
    usuario: string;
    intentos: number | null;
    desbloqueo: string | null;
    codigo: string;
    ip: string;
    ipObservacion: string | null;
    detallesAutorizados: boolean;
    enviosActuales: number | null;
    fechaEnvio: string | null;
  } | null>(null);

  constructor() {
    this.pasoTotp.set(this.sesion.tomarPasoMfaPendiente());
    this.destruccion.onDestroy(() => this.detenerReloj());
    this.sesion
      .consultarBloqueo()
      .pipe(takeUntilDestroyed())
      .subscribe({
        next: (estado) => {
          if (!estado.bloqueado) return;
          const nombre = estado.usuario_intentado ?? '';
          this.formulario.controls.nombreUsuario.setValue(nombre);
          const respuesta: ErrorApi = {
            codigo: 'CUENTA_BLOQUEADA',
            estadoHttp: 423,
            mensaje: 'El acceso esta bloqueado temporalmente.',
            detalle: {
              bloqueado_hasta: estado.bloqueado_hasta,
              ahora_servidor: estado.ahora_servidor,
            },
          };
          this.errorServidor.set(respuesta);
          this.mostrarBloqueo(respuesta, nombre);
          if (!this.accesoRestringido()) return;
          this.prepararRegistro(estado, nombre, respuesta.codigo);
          this.mostrarVentanaBloqueo.set(true);
        },
        error: () => {
          /* No inventar un estado ante un fallo de lectura; el login sigue validandolo. */
        },
      });
    this.formulario.controls.nombreUsuario.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe((nombre) => {
        if (this.usuarioBloqueado && nombre.trim().toLowerCase() !== this.usuarioBloqueado) {
          this.liberarInterfaz();
        }
      });
  }

  private detenerReloj(): void {
    if (this.relojBloqueo !== null) clearInterval(this.relojBloqueo);
    this.relojBloqueo = null;
  }

  private prepararRegistro(
    detalle: DetalleBloqueo | Record<string, unknown>,
    nombre: string,
    codigo: string,
  ): void {
    const autorizados = detalle.detalles_autorizados === true;
    const contador = detalle.intentos_fallidos_consecutivos;
    const candidato = detalle.intento_actual;
    const actual =
      candidato && typeof candidato === 'object' ? (candidato as Record<string, unknown>) : null;
    const envioValido =
      actual?.['alcance'] === 'ENVIO_ACTUAL' &&
      actual?.['envios_registrados'] === 1 &&
      typeof actual?.['fecha'] === 'string' &&
      Number.isFinite(Date.parse(actual['fecha']));
    const ipActual =
      envioValido && typeof actual?.['direccion_ip_observada'] === 'string'
        ? actual['direccion_ip_observada']
        : '';
    this.datosBloqueo.set({
      usuario: nombre,
      intentos:
        autorizados && typeof contador === 'number' && Number.isInteger(contador) && contador >= 0
          ? contador
          : null,
      ip: envioValido
        ? ipActual
        : autorizados && typeof detalle.direccion_ip === 'string'
          ? detalle.direccion_ip
          : '',
      ipObservacion:
        envioValido && typeof actual?.['observacion_ip'] === 'string'
          ? actual['observacion_ip']
          : autorizados && typeof detalle.ip_observacion === 'string'
            ? detalle.ip_observacion
            : null,
      desbloqueo: typeof detalle.bloqueado_hasta === 'string' ? detalle.bloqueado_hasta : null,
      codigo,
      detallesAutorizados: autorizados,
      enviosActuales: envioValido ? 1 : null,
      fechaEnvio: envioValido ? (actual['fecha'] as string) : null,
    });
  }

  private liberarInterfaz(): void {
    this.detenerReloj();

    this.accesoRestringido.set(false);
    this.segundosRestantes.set(null);
    this.usuarioBloqueado = '';

    this.captchaRequerido.set(false);
    this.mostrarCaptcha.set(false);

    this.mostrarVentanaBloqueo.set(false);
    this.datosBloqueo.set(null);

    this.errorServidor.set(null);
  }

  private mostrarBloqueo(respuesta: ErrorApi, nombre: string): void {
    this.detenerReloj();
    this.usuarioBloqueado = nombre.trim().toLowerCase();
    this.accesoRestringido.set(true);
    this.captchaRequerido.set(false);
    const fecha = respuesta.detalle?.['bloqueado_hasta'];
    const observado = respuesta.detalle?.['ahora_servidor'];
    const finFecha = typeof fecha === 'string' ? Date.parse(fecha) : NaN;
    const ahoraFecha = typeof observado === 'string' ? Date.parse(observado) : Date.now();
    this.segundosRestantes.set(null);
    if (!Number.isFinite(finFecha) || !Number.isFinite(ahoraFecha)) return;
    // El plazo procede del servidor; este reloj solo informa y limita la interfaz.
    const inicio = performance.now();
    const fin = finFecha;
    const actualizar = () => {
      const restante = Math.max(
        0,
        Math.ceil((fin - (ahoraFecha + performance.now() - inicio)) / 1000),
      );
      this.segundosRestantes.set(restante);
      if (restante === 0) this.liberarInterfaz();
    };
    actualizar();
    if (this.accesoRestringido()) this.relojBloqueo = setInterval(actualizar, 1000);
  }

  protected alternarVisibilidadContrasena(): void {
    this.contrasenaVisible.update((visible) => !visible);
  }

  /** Indica si un campo debe mostrar su error (solo después de que el usuario lo tocó o intentó enviar). */
  protected campoConError(nombreCampo: 'nombreUsuario' | 'contrasena'): boolean {
    const campo = this.formulario.controls[nombreCampo];
    return campo.invalid && (campo.touched || campo.dirty);
  }

  protected iniciarSesion(): void {
    if (this.enviando() || this.accesoRestringido()) return;
    if (this.formulario.invalid) {
      this.formulario.markAllAsTouched();
      return;
    }
    if (this.captchaRequerido()) {
      this.mostrarCaptcha.set(true);
      return;
    }
    this.enviarLogin();
  }

  protected enviarLogin(captcha: RespuestaCaptcha | null = null): void {
    // Evitar solicitudes simultáneas o bloqueadas.
    if (this.enviando() || this.accesoRestringido() || this.formulario.invalid) {
      return;
    }

    // Si el backend exige CAPTCHA, debe enviarse su respuesta.
    if (this.captchaRequerido() && !captcha) {
      this.mostrarCaptcha.set(true);
      return;
    }

    this.enviando.set(true);
    this.errorServidor.set(null);

    const { nombreUsuario, contrasena } = this.formulario.getRawValue();

    this.sesion
      .iniciarSesion(nombreUsuario, contrasena, captcha)
      .pipe(takeUntilDestroyed(this.destruccion))
      .subscribe({
        next: (resultado) => {
          if ('totp_requerido' in resultado) {
            if (resultado.cambio_contrasena_requerido) {
              void this.enrutador.navigateByUrl('/' + RUTA_PAGINA_CAMBIAR_CONTRASENA);
            } else this.pasoTotp.set(resultado);
            this.mostrarCaptcha.set(false);
            this.formulario.controls.contrasena.reset();
            this.enviando.set(false);
            return;
          }
          this.detenerReloj();

          // Restablecer estados.
          this.mostrarCaptcha.set(false);
          this.captchaRequerido.set(false);
          this.accesoRestringido.set(false);
          this.mostrarVentanaBloqueo.set(false);
          this.datosBloqueo.set(null);
          this.segundosRestantes.set(null);
          this.usuarioBloqueado = '';

          // Limpiar contraseña.
          this.formulario.controls.contrasena.reset();

          this.enviando.set(false);

          const volverA = this.rutaActual.snapshot.queryParamMap.get(PARAMETRO_VOLVER_A);

          void this.enrutador.navigateByUrl(
            esRutaInternaSegura(volverA) ? volverA : '/' + RUTA_PAGINA_INICIO,
          );
        },

        error: (error: unknown) => {
          const respuesta = leerErrorApi(error);

          // 1. VERIFICAR BLOQUEO DEL BACKEND.
          if (respuesta.estadoHttp === 423 && respuesta.codigo === 'CUENTA_BLOQUEADA') {
            this.mostrarCaptcha.set(false);
            this.errorServidor.set(respuesta);

            // Activar bloqueo y contador.
            this.mostrarBloqueo(respuesta, nombreUsuario);
            if (!this.accesoRestringido()) {
              this.formulario.controls.contrasena.reset();
              this.enviando.set(false);
              return;
            }

            this.prepararRegistro(respuesta.detalle ?? {}, nombreUsuario, respuesta.codigo);

            // Mostrar ventana institucional.
            this.mostrarVentanaBloqueo.set(true);

            // Limpiar contraseña.
            this.formulario.controls.contrasena.reset();

            this.enviando.set(false);

            return;
          }

          // 2. ERRORES DE CAPTCHA O CREDENCIALES.
          if (captcha && respuesta.estadoHttp === 401 && respuesta.codigo !== 'CAPTCHA_INVALIDO') {
            respuesta.mensaje =
              'No se pudo validar el código o las credenciales. ' +
              'Ingrese nuevamente la contraseña y solicite un código nuevo.';
          }

          this.errorServidor.set(respuesta);

          // 3. RESPETAR ESTADO CAPTCHA DEL BACKEND.
          const captchaObligatorio = respuesta.detalle?.['captcha_requerido'];

          if (typeof captchaObligatorio === 'boolean') {
            this.captchaRequerido.set(captchaObligatorio);
          }

          // 4. RESTRICCIÓN TEMPORAL.
          this.accesoRestringido.set(
            respuesta.detalle?.['acceso_temporalmente_restringido'] === true,
          );

          this.formulario.controls.contrasena.reset();
          this.enviando.set(false);
          if (this.captchaRequerido() && !this.accesoRestringido()) {
            // Cada envío consume el desafío: conservar la ventana y pedir otro.
            if (captcha) this.revisionCaptcha.update((valor) => valor + 1);
            this.mostrarCaptcha.set(true);
          }
        },
      });
  }

  protected cancelarCaptcha(): void {
    this.mostrarCaptcha.set(false);
    this.formulario.controls.contrasena.reset();
  }

  protected cerrarTotp(): void {
    this.pasoTotp.set(null);
    this.desbloqueoTotp.set(false);
    this.formulario.controls.contrasena.reset();
  }

  protected completarTotp(): void {
    const desbloqueo = this.desbloqueoTotp();
    this.cerrarTotp();
    this.liberarInterfaz();
    if (!desbloqueo) {
      const volver = this.rutaActual.snapshot.queryParamMap.get(PARAMETRO_VOLVER_A);
      void this.enrutador.navigateByUrl(
        esRutaInternaSegura(volver) ? volver : '/' + RUTA_PAGINA_INICIO,
      );
    }
  }

  /** Hora local de desbloqueo cuando la cuenta está bloqueada (USUARIO_BLOQUEADO, contrato §1.2). */
  protected horaDesbloqueo(error: ErrorApi): string | null {
    const valor = error.detalle?.['bloqueado_hasta'] ?? error.detalle?.['desbloqueo_estimado'];
    if (typeof valor !== 'string') {
      return null;
    }
    const fecha = new Date(valor);
    return Number.isNaN(fecha.getTime())
      ? null
      : fecha.toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' });
  }
}
