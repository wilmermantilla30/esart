import {
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { toDataURL } from 'qrcode';
import { Subscription, concatMap, from, interval, startWith, switchMap, toArray } from 'rxjs';

import { leerErrorApi } from '../../../nucleo/modelos/error-api';
import {
  CandidatoFirmante,
  EstadoSolicitud,
  FirmanteAutorizado,
  SolicitudFirmaCreada,
  TipoFirmable,
} from '../../../nucleo/modelos/firma';
import { FirmaService } from '../../../nucleo/servicios/firma.service';
import { SesionService } from '../../../nucleo/servicios/sesion.service';

/** Cada cuánto el PC pregunta si ya se firmó desde el celular. */
const INTERVALO_CONSULTA_MS = 3000;
const ESTADOS_FINALES = new Set(['APROBADA', 'RECHAZADA', 'EXPIRADA', 'CANCELADA']);

/** Dirección que abrirá el celular. Si el backend no la tiene configurada se usa la del navegador. */
export function urlParaCelular(
  solicitud: Pick<SolicitudFirmaCreada, 'url_firma' | 'url_publica_configurada'>,
  origen: string,
): string {
  return solicitud.url_publica_configurada
    ? solicitud.url_firma
    : `${origen}${solicitud.url_firma}`;
}

/** localhost / 127.0.0.1 solo existen en el PC: el celular no podría abrir ese QR. */
export function esDireccionLocal(url: string): boolean {
  try {
    return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(new URL(url).hostname);
  } catch {
    return true;
  }
}

/**
 * Ventana "Firmar desde el celular" de la ficha del artillero (certificación u oficio remisorio).
 * Pasos: 1) elegir firmante autorizado → 2) QR de un solo uso (15 min) mientras el firmante dibuja su
 * rúbrica y confirma con su TOTP en el celular → 3) descargar el PDF firmado.
 * La rúbrica se ubica sola en la línea de firma del documento; el backend valida todo.
 */
@Component({
  selector: 'esart-solicitud-firma',
  template: `
    <div
      class="fixed inset-0 z-50 bg-negro-institucional/40 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="titulo-firma-celular"
    >
      <div
        class="w-full max-w-md bg-white rounded-2xl border border-gris-bordes shadow-xl overflow-hidden"
      >
        <header
          class="px-5 py-4 border-b border-gris-bordes flex items-start justify-between gap-3"
        >
          <div class="flex items-center gap-3">
            <span
              class="w-10 h-10 rounded-xl bg-azul-hielo text-azul-institucional flex items-center justify-center"
            >
              <span class="material-symbols-outlined" aria-hidden="true">phone_iphone</span>
            </span>
            <div>
              <h2
                id="titulo-firma-celular"
                class="font-headline font-bold text-negro-institucional"
              >
                Firmar desde el celular
              </h2>
              <p class="text-xs text-azul-pizarra/60">{{ nombreTipo() }} — {{ cedula() }}</p>
            </div>
          </div>
          <button
            type="button"
            (click)="cerrar.emit()"
            aria-label="Cerrar"
            class="text-azul-pizarra/60 hover:text-azul-pizarra"
          >
            <span class="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </header>

        <!-- Pasos: Generar PDF → Escanear QR → Dibujar firma → Ubicar y validar -->
        <ol
          class="px-5 pt-4 grid grid-cols-4 gap-1 text-[10px] text-center text-azul-pizarra/70"
          aria-label="Pasos"
        >
          @for (paso of pasos; track paso.texto; let i = $index) {
            <li
              class="flex flex-col items-center gap-1"
              [class.text-azul-institucional]="pasoActual() >= i"
            >
              <span class="material-symbols-outlined text-[20px]" aria-hidden="true">{{
                paso.icono
              }}</span>
              {{ paso.texto }}
            </li>
          }
        </ol>

        <div class="px-5 py-4 space-y-4">
          @if (error(); as mensaje) {
            <p class="p-3 bg-error/10 border border-error/40 rounded-lg text-sm" role="alert">
              {{ mensaje }}
            </p>
          }

          @if (!solicitud()) {
            @if (cargandoFirmantes()) {
              <p class="text-sm text-azul-pizarra/70" role="status">
                Cargando firmantes autorizados…
              </p>
            } @else if (error()) {
              <!-- El mensaje del backend (arriba) ya explica el problema. -->
            } @else if (autorizando()) {
              <!-- Autorizar firmante: solo con "Firma documental" > crear en la malla de permisos. -->
              <div class="space-y-3" aria-label="Autorizar firmante">
                <p class="text-sm text-azul-pizarra">
                  Autorice a quien firmará este tipo de documento. Debe tener activo su autenticador
                  de ESART.
                </p>
                <label class="block space-y-1">
                  <span class="text-xs font-semibold text-azul-pizarra">Usuario firmante</span>
                  <select
                    id="candidato-firmante"
                    class="w-full py-2 px-3 border border-gris-bordes rounded-sm text-body-md"
                    [value]="candidato()"
                    (change)="candidato.set($any($event.target).value)"
                  >
                    <option value="">Seleccione…</option>
                    @for (c of candidatos(); track c.usuario_id) {
                      <option [value]="c.usuario_id" [disabled]="!c.totp_activo">
                        {{ c.nombre }}{{ c.totp_activo ? '' : ' (sin autenticador)' }}
                      </option>
                    }
                  </select>
                </label>
                <label class="block space-y-1">
                  <span class="text-xs font-semibold text-azul-pizarra"
                    >Cargo con el que firma</span
                  >
                  <input
                    id="cargo-firmante"
                    class="w-full py-2 px-3 border border-gris-bordes rounded-sm text-body-md"
                    maxlength="150"
                    [value]="cargo()"
                    (input)="cargo.set($any($event.target).value)"
                  />
                </label>
                <label class="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    [checked]="ambosTipos()"
                    (change)="ambosTipos.set($any($event.target).checked)"
                  />
                  También para
                  {{ tipo() === 'OFICIO_REMISORIO' ? 'certificaciones' : 'oficios remisorios' }}
                </label>
                <div class="flex gap-2">
                  @if (firmantes().length) {
                    <button
                      type="button"
                      (click)="autorizando.set(false)"
                      class="flex-1 py-2.5 border border-gris-bordes rounded-sm text-label-lg"
                    >
                      Cancelar
                    </button>
                  }
                  <button
                    type="button"
                    (click)="autorizar()"
                    [disabled]="
                      guardandoAutorizacion() || !candidato() || cargo().trim().length < 3
                    "
                    class="flex-1 py-2.5 bg-azul-institucional text-white rounded-sm font-headline text-label-lg disabled:opacity-70"
                  >
                    {{ guardandoAutorizacion() ? 'Autorizando…' : 'Autorizar firmante' }}
                  </button>
                </div>
              </div>
            } @else if (!firmantes().length) {
              <p class="text-sm text-azul-pizarra" role="status">
                No hay firmantes autorizados para este documento. Un administrador (con «Firma
                documental» en la malla de permisos) debe autorizar al firmante, por ejemplo el
                Director, y este debe tener activo su autenticador.
              </p>
            } @else {
              <label class="block space-y-1">
                <span class="text-xs font-semibold text-azul-pizarra">Firmante autorizado</span>
                <select
                  class="w-full py-2 px-3 border border-gris-bordes rounded-sm text-body-md"
                  [value]="autorizacion()"
                  (change)="autorizacion.set($any($event.target).value)"
                >
                  @for (firmante of firmantes(); track firmante.autorizacion_id) {
                    <option [value]="firmante.autorizacion_id">
                      {{ firmante.nombre }} — {{ firmante.cargo }}
                    </option>
                  }
                </select>
              </label>
              <p class="text-xs text-azul-pizarra/70">
                Se genera el borrador del documento y un código QR de un solo uso que vence en 15
                minutos.
              </p>
              <button
                type="button"
                (click)="generarQr()"
                [disabled]="creando() || !autorizacion()"
                class="w-full inline-flex items-center justify-center gap-2 py-2.5 bg-azul-institucional text-white rounded-sm font-headline text-label-lg disabled:opacity-70"
              >
                <span class="material-symbols-outlined text-[18px]" aria-hidden="true"
                  >qr_code_2</span
                >
                {{ creando() ? 'Generando…' : 'Generar PDF y código QR' }}
              </button>
              @if (puedeAutorizar()) {
                <button
                  type="button"
                  (click)="abrirAutorizacion()"
                  class="w-full text-xs text-azul-institucional underline"
                >
                  Autorizar otro firmante
                </button>
              }
            }
          } @else {
            @switch (estado()?.estado ?? 'PENDIENTE') {
              @case ('APROBADA') {
                <div
                  class="p-4 bg-success/10 border border-success/40 rounded-lg text-sm"
                  role="status"
                >
                  <p class="font-semibold">Documento firmado por {{ estado()?.firmante }}.</p>
                  <p class="text-azul-pizarra/80">
                    La rúbrica quedó en la línea de firma, con fecha y código de verificación.
                  </p>
                </div>
                <button
                  type="button"
                  (click)="descargar()"
                  [disabled]="descargando()"
                  class="w-full inline-flex items-center justify-center gap-2 py-2.5 bg-azul-institucional text-white rounded-sm font-headline text-label-lg disabled:opacity-70"
                >
                  <span class="material-symbols-outlined text-[18px]" aria-hidden="true"
                    >download</span
                  >
                  Descargar PDF firmado
                </button>
              }
              @case ('EXPIRADA') {
                <p
                  class="p-3 bg-warning/10 border border-warning/40 rounded-lg text-sm"
                  role="status"
                >
                  El código QR venció sin firmarse.
                </p>
                <button
                  type="button"
                  (click)="reiniciar()"
                  class="w-full py-2.5 border border-gris-bordes rounded-sm text-label-lg"
                >
                  Generar un nuevo código
                </button>
              }
              @default {
                <div class="flex flex-col items-center gap-2">
                  @if (qr(); as imagen) {
                    <img
                      [src]="imagen"
                      width="220"
                      height="220"
                      alt="Código QR para firmar desde el celular"
                    />
                  }
                  <p class="text-sm text-center">
                    {{ solicitud()?.firmante }} escanea este código con su celular, dibuja su firma
                    y la confirma con su autenticador.
                  </p>
                  <p class="text-xs text-azul-pizarra/60" role="status">
                    {{
                      estado()?.estado === 'ABIERTA'
                        ? 'Abierto en el celular: esperando la firma…'
                        : 'Esperando que se escanee…'
                    }}
                  </p>
                  @if (direccionLocal()) {
                    <p
                      class="p-2 bg-warning/10 border border-warning/40 rounded text-xs"
                      role="alert"
                    >
                      Este código apunta a «localhost» y el celular no podrá abrirlo. Configure
                      URL_BASE_FIRMA_MOVIL con la IP del PC en la red WiFi (ver
                      docs/ESART_FIRMA_MOVIL.md).
                    </p>
                  }
                  <a
                    [href]="urlCelular()"
                    target="_blank"
                    rel="noopener"
                    class="text-xs text-azul-institucional underline break-all"
                  >
                    {{ urlCelular() }}
                  </a>
                </div>
              }
            }
          }
        </div>
      </div>
    </div>
  `,
})
export class SolicitudFirma implements OnInit {
  private readonly firma = inject(FirmaService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  readonly cedula = input.required<string>();
  readonly tipo = input.required<TipoFirmable>();
  readonly cerrar = output<void>();

  protected readonly pasos = [
    { icono: 'description', texto: 'Generar PDF' },
    { icono: 'qr_code_scanner', texto: 'Escanear QR' },
    { icono: 'draw', texto: 'Dibujar firma' },
    { icono: 'task', texto: 'Ubicar y validar' },
  ];
  protected readonly firmantes = signal<FirmanteAutorizado[]>([]);
  // --- Autorizar firmante (permiso "Firma documental" > crear) ---
  protected readonly puedeAutorizar = computed(() =>
    this.sesion.puede('FIRMA_DOCUMENTOS', 'crear'),
  );
  protected readonly autorizando = signal(false);
  protected readonly candidatos = signal<CandidatoFirmante[]>([]);
  protected readonly candidato = signal('');
  protected readonly cargo = signal('Director de la Escuela de Artillería');
  protected readonly ambosTipos = signal(true);
  protected readonly guardandoAutorizacion = signal(false);
  protected readonly cargandoFirmantes = signal(true);
  protected readonly autorizacion = signal('');
  protected readonly creando = signal(false);
  protected readonly descargando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly solicitud = signal<SolicitudFirmaCreada | null>(null);
  protected readonly estado = signal<EstadoSolicitud | null>(null);
  protected readonly qr = signal<string | null>(null);
  protected readonly urlCelular = computed(() => {
    const solicitud = this.solicitud();
    return solicitud ? urlParaCelular(solicitud, window.location.origin) : '';
  });
  protected readonly direccionLocal = computed(
    () => !!this.urlCelular() && esDireccionLocal(this.urlCelular()),
  );
  protected readonly nombreTipo = computed(() =>
    this.tipo() === 'OFICIO_REMISORIO' ? 'Oficio remisorio' : 'Certificación',
  );
  protected readonly pasoActual = computed(() => {
    const estado = this.estado()?.estado;
    if (estado === 'APROBADA') return 3;
    if (estado === 'ABIERTA') return 2;
    return this.solicitud() ? 1 : 0;
  });
  private consulta: Subscription | null = null;

  ngOnInit(): void {
    this.cargarFirmantes();
  }

  private cargarFirmantes(): void {
    this.cargandoFirmantes.set(true);
    this.firma
      .firmantes(this.tipo())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (lista) => {
          this.firmantes.set(lista);
          this.autorizacion.set(lista[0]?.autorizacion_id ?? '');
          this.cargandoFirmantes.set(false);
          // Sin firmantes y con permiso para autorizar: se abre directamente el formulario.
          if (!lista.length && this.puedeAutorizar()) this.abrirAutorizacion();
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error).mensaje);
          this.cargandoFirmantes.set(false);
        },
      });
  }

  protected abrirAutorizacion(): void {
    this.autorizando.set(true);
    this.error.set(null);
    this.firma
      .candidatos()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (lista) => this.candidatos.set(lista),
        error: (error: unknown) => this.error.set(leerErrorApi(error).mensaje),
      });
  }

  /** Autoriza al usuario elegido (para este tipo y, si se marca, también para el otro). */
  protected autorizar(): void {
    const usuario = Number(this.candidato());
    const otro: TipoFirmable =
      this.tipo() === 'CERTIFICACION' ? 'OFICIO_REMISORIO' : 'CERTIFICACION';
    const tipos: TipoFirmable[] = this.ambosTipos() ? [this.tipo(), otro] : [this.tipo()];
    this.guardandoAutorizacion.set(true);
    this.error.set(null);
    // En serie: la primera crea la identidad de firma del usuario; la segunda la reutiliza.
    from(tipos)
      .pipe(
        concatMap((tipo) => this.firma.autorizar(usuario, tipo, this.cargo())),
        toArray(),
        takeUntilDestroyed(this.destruir),
      )
      .subscribe({
        next: () => {
          this.guardandoAutorizacion.set(false);
          this.autorizando.set(false);
          this.cargarFirmantes();
        },
        error: (error: unknown) => {
          this.guardandoAutorizacion.set(false);
          this.error.set(leerErrorApi(error).mensaje);
          // Pudo quedar autorizado para uno de los dos tipos: se recarga la lista.
          this.cargarFirmantes();
        },
      });
  }

  protected generarQr(): void {
    this.creando.set(true);
    this.error.set(null);
    this.firma
      .solicitar(this.cedula(), this.tipo(), this.autorizacion())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (solicitud) => {
          this.creando.set(false);
          this.solicitud.set(solicitud);
          void toDataURL(urlParaCelular(solicitud, window.location.origin), {
            width: 220,
            margin: 1,
            errorCorrectionLevel: 'M',
          }).then((imagen) => this.qr.set(imagen));
          this.consultarEstado(solicitud.solicitud_id);
        },
        error: (error: unknown) => {
          this.creando.set(false);
          this.error.set(leerErrorApi(error).mensaje);
        },
      });
  }

  protected reiniciar(): void {
    this.consulta?.unsubscribe();
    this.solicitud.set(null);
    this.estado.set(null);
    this.qr.set(null);
  }

  protected descargar(): void {
    const documento = this.estado()?.documento_id;
    if (!documento) return;
    this.descargando.set(true);
    this.firma
      .descargarFirmado(documento)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: ({ nombre, contenido }) => {
          const enlace = document.createElement('a');
          enlace.href = URL.createObjectURL(contenido);
          enlace.download = nombre;
          enlace.click();
          URL.revokeObjectURL(enlace.href);
          this.descargando.set(false);
        },
        error: (error: unknown) => {
          this.descargando.set(false);
          this.error.set(leerErrorApi(error).mensaje);
        },
      });
  }

  /** Pregunta el estado cada 3 s hasta que la solicitud se firma, vence o se cierra. */
  private consultarEstado(solicitudId: string): void {
    this.consulta?.unsubscribe();
    this.consulta = interval(INTERVALO_CONSULTA_MS)
      .pipe(
        startWith(0),
        switchMap(() => this.firma.estado(solicitudId)),
        takeUntilDestroyed(this.destruir),
      )
      .subscribe({
        next: (estado) => {
          this.estado.set(estado);
          if (ESTADOS_FINALES.has(estado.estado)) this.consulta?.unsubscribe();
        },
        error: (error: unknown) => this.error.set(leerErrorApi(error).mensaje),
      });
  }
}
