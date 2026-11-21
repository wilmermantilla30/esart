import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';

import { leerErrorApi } from '../../nucleo/modelos/error-api';
import { FirmaRealizada, ResumenFirmaMovil } from '../../nucleo/modelos/firma';
import { FirmaService } from '../../nucleo/servicios/firma.service';

/** Grosor y color del trazo de la rúbrica (en píxeles CSS). */
const GROSOR_TRAZO = 2.6;
const COLOR_TRAZO = '#0f1e5a';

/**
 * Página pública que abre el QR en el celular del firmante (sin sesión de ESART).
 * Muestra el documento, recoge la rúbrica dibujada con el dedo, la aceptación y el código TOTP del
 * firmante. La rúbrica se envía como PNG transparente; el backend la valida, la ubica en la línea de
 * firma y genera el PDF final. El token del enlace es de un solo uso y vence en 15 minutos.
 */
@Component({
  selector: 'esart-firma-movil',
  template: `
    <main class="min-h-dvh bg-gris-claro px-4 py-6 flex justify-center">
      <section class="w-full max-w-lg space-y-4">
        <header class="flex items-center gap-3">
          <span
            class="w-10 h-10 rounded-xl bg-azul-institucional text-white flex items-center justify-center"
          >
            <span class="material-symbols-outlined" aria-hidden="true">draw</span>
          </span>
          <div>
            <h1 class="font-headline font-bold text-negro-institucional text-lg">
              Firma electrónica ESART
            </h1>
            <p class="text-xs text-azul-pizarra/70">Escuela de Artillería</p>
          </div>
        </header>

        @if (cargando()) {
          <p class="text-sm" role="status">Abriendo la solicitud…</p>
        } @else if (firmado(); as firma) {
          <div
            class="p-5 bg-white rounded-xl border border-success/40 space-y-2 text-center"
            role="status"
          >
            <span class="material-symbols-outlined text-success text-[48px]" aria-hidden="true"
              >verified</span
            >
            <p class="font-headline font-bold">Documento firmado</p>
            <p class="text-sm text-azul-pizarra/80">
              Su firma quedó registrada con el código
              <strong>{{ firma.codigo_verificacion }}</strong>. Ya puede cerrar esta página; el
              documento firmado está disponible en el equipo que mostró el código QR.
            </p>
          </div>
        } @else if (resumen(); as datos) {
          @if (!disponible()) {
            <p class="p-4 bg-warning/10 border border-warning/40 rounded-xl text-sm" role="alert">
              Esta solicitud ya no está disponible ({{ datos.estado.toLowerCase() }}). Pida que
              generen un nuevo código QR.
            </p>
          } @else {
            <div class="p-4 bg-white rounded-xl border border-gris-bordes text-sm space-y-1">
              <p>
                <span class="text-azul-pizarra/60">Documento:</span>
                {{ datos.tipo === 'OFICIO_REMISORIO' ? 'Oficio remisorio' : 'Certificación' }}
                {{ datos.numero }}
              </p>
              <p><span class="text-azul-pizarra/60">Artillero:</span> {{ datos.artillero }}</p>
              <p>
                <span class="text-azul-pizarra/60">Firmante:</span> {{ datos.firmante }} —
                {{ datos.cargo }}
              </p>
              <a
                [href]="urlBorrador()"
                target="_blank"
                rel="noopener"
                class="mt-2 inline-flex items-center gap-1 text-azul-institucional font-semibold underline"
              >
                <span class="material-symbols-outlined text-[18px]" aria-hidden="true"
                  >picture_as_pdf</span
                >
                Revisar el documento antes de firmar
              </a>
            </div>

            <div class="p-4 bg-white rounded-xl border border-gris-bordes space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-sm font-semibold">Dibuje su firma</span>
                <button
                  type="button"
                  (click)="borrar()"
                  class="text-xs text-azul-institucional underline"
                >
                  Borrar
                </button>
              </div>
              <canvas
                #lienzo
                class="w-full h-48 rounded-lg border-2 border-dashed border-azul-institucional/50 bg-white touch-none"
                aria-label="Área para dibujar la firma con el dedo"
                (pointerdown)="empezar($event)"
                (pointermove)="trazar($event)"
                (pointerup)="terminar($event)"
                (pointercancel)="terminar($event)"
                (pointerleave)="terminar($event)"
              ></canvas>
              <p class="text-xs text-azul-pizarra/60">
                Su rúbrica se ubicará en la línea de firma del documento.
              </p>
            </div>

            <div class="p-4 bg-white rounded-xl border border-gris-bordes space-y-3">
              <label class="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  class="mt-1"
                  [checked]="acepto()"
                  (change)="acepto.set($any($event.target).checked)"
                />
                <span>{{ datos.texto_consentimiento }}</span>
              </label>
              <label class="block space-y-1">
                <span class="text-sm font-semibold">Código del autenticador</span>
                <input
                  inputmode="numeric"
                  autocomplete="one-time-code"
                  maxlength="6"
                  placeholder="000000"
                  class="w-full py-3 px-3 border border-gris-bordes rounded-lg text-center text-xl tracking-[0.4em]"
                  [value]="codigo()"
                  (input)="codigo.set($any($event.target).value.replace(/\\D/g, '').slice(0, 6))"
                />
              </label>
              @if (error(); as mensaje) {
                <p class="p-3 bg-error/10 border border-error/40 rounded-lg text-sm" role="alert">
                  {{ mensaje }}
                </p>
              }
              <button
                type="button"
                (click)="firmar()"
                [disabled]="!puedeFirmar()"
                class="w-full py-3 bg-azul-institucional text-white rounded-lg font-headline font-semibold disabled:opacity-60"
              >
                {{ enviando() ? 'Firmando…' : 'Firmar documento' }}
              </button>
            </div>
          }
        } @else if (error(); as mensaje) {
          <p class="p-4 bg-error/10 border border-error/40 rounded-xl text-sm" role="alert">
            {{ mensaje }}
          </p>
        }
      </section>
    </main>
  `,
})
export class FirmaMovil implements AfterViewInit {
  private readonly firma = inject(FirmaService);
  private readonly destruir = inject(DestroyRef);
  private readonly token = inject(ActivatedRoute).snapshot.paramMap.get('token') ?? '';
  private readonly lienzo = viewChild<ElementRef<HTMLCanvasElement>>('lienzo');

  protected readonly cargando = signal(true);
  protected readonly resumen = signal<ResumenFirmaMovil | null>(null);
  protected readonly firmado = signal<FirmaRealizada | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly acepto = signal(false);
  protected readonly codigo = signal('');
  protected readonly hayTrazo = signal(false);
  protected readonly enviando = signal(false);
  protected readonly urlBorrador = computed(() => this.firma.urlBorrador(this.token));
  protected readonly disponible = computed(() =>
    ['PENDIENTE', 'ABIERTA'].includes(this.resumen()?.estado ?? ''),
  );
  protected readonly puedeFirmar = computed(
    () => this.hayTrazo() && this.acepto() && /^\d{6}$/.test(this.codigo()) && !this.enviando(),
  );
  private dibujando = false;
  private ultimo: { x: number; y: number } | null = null;

  constructor() {
    this.firma
      .abrir(this.token)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (resumen) => {
          this.resumen.set(resumen);
          this.cargando.set(false);
          // El lienzo aparece después de este cambio: se prepara en el siguiente ciclo.
          queueMicrotask(() => setTimeout(() => this.prepararLienzo()));
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error).mensaje);
          this.cargando.set(false);
        },
      });
  }

  ngAfterViewInit(): void {
    this.prepararLienzo();
  }

  /** Ajusta la resolución del lienzo a la pantalla (nítido en celulares con densidad 2x/3x). */
  private prepararLienzo(): void {
    const lienzo = this.lienzo()?.nativeElement;
    if (!lienzo || lienzo.dataset['listo']) return;
    const densidad = Math.min(window.devicePixelRatio || 1, 3);
    const { width, height } = lienzo.getBoundingClientRect();
    lienzo.width = Math.max(1, Math.round(width * densidad));
    lienzo.height = Math.max(1, Math.round(height * densidad));
    const contexto = lienzo.getContext('2d');
    if (!contexto) return;
    contexto.scale(densidad, densidad);
    contexto.lineCap = 'round';
    contexto.lineJoin = 'round';
    contexto.lineWidth = GROSOR_TRAZO;
    contexto.strokeStyle = COLOR_TRAZO;
    lienzo.dataset['listo'] = '1';
  }

  private punto(evento: PointerEvent): { x: number; y: number } {
    const caja = (evento.target as HTMLCanvasElement).getBoundingClientRect();
    return { x: evento.clientX - caja.left, y: evento.clientY - caja.top };
  }

  protected empezar(evento: PointerEvent): void {
    this.prepararLienzo();
    (evento.target as HTMLElement).setPointerCapture?.(evento.pointerId);
    this.dibujando = true;
    this.ultimo = this.punto(evento);
    evento.preventDefault();
  }

  protected trazar(evento: PointerEvent): void {
    if (!this.dibujando || !this.ultimo) return;
    const contexto = this.lienzo()?.nativeElement.getContext('2d');
    if (!contexto) return;
    const actual = this.punto(evento);
    contexto.beginPath();
    contexto.moveTo(this.ultimo.x, this.ultimo.y);
    contexto.lineTo(actual.x, actual.y);
    contexto.stroke();
    this.ultimo = actual;
    this.hayTrazo.set(true);
    evento.preventDefault();
  }

  protected terminar(_evento: PointerEvent): void {
    this.dibujando = false;
    this.ultimo = null;
  }

  protected borrar(): void {
    const lienzo = this.lienzo()?.nativeElement;
    lienzo?.getContext('2d')?.clearRect(0, 0, lienzo.width, lienzo.height);
    this.hayTrazo.set(false);
  }

  protected firmar(): void {
    const lienzo = this.lienzo()?.nativeElement;
    if (!lienzo || !this.puedeFirmar()) return;
    this.enviando.set(true);
    this.error.set(null);
    this.firma
      .firmar(this.token, lienzo.toDataURL('image/png'), this.codigo(), this.acepto())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (resultado) => {
          this.enviando.set(false);
          this.firmado.set(resultado);
        },
        error: (error: unknown) => {
          this.enviando.set(false);
          this.codigo.set('');
          this.error.set(leerErrorApi(error).mensaje);
        },
      });
  }
}
