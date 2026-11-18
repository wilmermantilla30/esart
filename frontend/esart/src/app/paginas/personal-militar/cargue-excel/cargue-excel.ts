import { DatePipe } from '@angular/common';
import { Totp } from '../../totp/totp';
import { DatosCurso } from './datos-curso';
import {
  Component,
  computed,
  DestroyRef,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, EMPTY, firstValueFrom, Observable, tap, throwError, timeout } from 'rxjs';
import { leerErrorApi } from '../../../nucleo/modelos/error-api';
import {
  AnalisisExcel,
  DatosCursoImportacion,
  HojaExcel,
  Incidencia,
  ResultadoImportacion,
} from './excel-modelos';
import { ImportacionExcelService } from './importacion-excel.service';
import { UnidadExcel } from './excel-normalizacion';
import { VerificacionService } from '../../../nucleo/servicios/verificacion.service';
import { archivoExcelNoDisponible, conservarArchivoExcel } from './archivo-excel';
import {
  ajustarRectangulo,
  BordeVentana,
  BORDES_VENTANA,
  RectVentana,
  rectanguloMaximo,
  redimensionarRectangulo,
} from './ventana-excel';

/** Respuestas del backend que se resuelven con el código del autenticador. */
const CODIGOS_TOTP = new Set(['TOTP_REQUERIDO', 'TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);

@Component({
  imports: [DatePipe, Totp, DatosCurso],
  selector: 'app-cargue-excel',
  styleUrl: './cargue-excel.css',
  templateUrl: './cargue-excel.html',
})
export class CargueExcel {
  private readonly api = inject(ImportacionExcelService);
  private readonly verificacion = inject(VerificacionService);
  private readonly destruir = inject(DestroyRef);
  private worker?: Worker;
  private temporizador?: ReturnType<typeof setTimeout>;
  private unidades: UnidadExcel[] | null = null;
  private focoAnterior?: HTMLElement;
  private entradasArrastre = 0;
  private geometriaAnterior: RectVentana | null = null;
  private gestoTamano: {
    id: number;
    borde: BordeVentana;
    x: number;
    y: number;
    rect: RectVentana;
  } | null = null;
  readonly geometria = signal<RectVentana | null>(null);
  readonly redimensionando = signal(false);
  readonly bordes = BORDES_VENTANA;
  readonly dialogo = viewChild<ElementRef<HTMLDialogElement>>('dialogo');
  readonly entrada = viewChild<ElementRef<HTMLInputElement>>('entrada');
  readonly archivo = signal<File | null>(null);
  readonly fecha = signal<Date | null>(null);
  readonly hojas = signal<HojaExcel[]>([]);
  readonly hoja = signal('');
  readonly analisis = signal<AnalisisExcel | null>(null);
  readonly ocupado = signal(false);
  readonly enviando = signal(false);
  readonly arrastrando = signal(false);
  readonly maximizada = signal(false);
  readonly minimizada = signal(false);
  readonly visible = signal(false);
  readonly confirmar = signal(false);
  readonly requiereTotp = signal(false);
  readonly errorTotp = signal('');
  /** Datos válidos del curso o null mientras el formulario esté incompleto. */
  readonly curso = signal<DatosCursoImportacion | null>(null);
  readonly formularioCurso = viewChild(DatosCurso);
  readonly dialogoTotp = viewChild<ElementRef<HTMLDialogElement>>('dialogoTotp');
  readonly error = signal('');
  readonly resultado = signal<ResultadoImportacion | null>(null);
  readonly busqueda = signal('');
  readonly filtro = signal('todos');
  readonly columnaFiltro = signal<number | null>(null);
  readonly pagina = signal(1);
  readonly filaActiva = signal<number | null>(null);
  readonly paginaIncidencias = signal(1);
  readonly tamanoPagina = 20;
  readonly errores = computed(
    () => this.analisis()?.incidencias.filter((i) => i.nivel === 'Error') ?? [],
  );
  readonly filasConErrores = computed(
    () =>
      new Set(
        this.errores()
          .filter((i) => i.indice >= 0)
          .map((i) => i.fila),
      ),
  );
  readonly errorEstructural = computed(() => {
    const numeros = new Set(this.analisis()?.filas.map((f) => f.numero));
    return this.errores().some((i) => !numeros.has(i.fila) || i.indice < 0);
  });
  readonly completos = computed(() =>
    !this.analisis()?.validado
      ? null
      : this.errorEstructural()
        ? 0
        : (this.analisis()?.filas.length ?? 0) - this.filasConErrores().size,
  );
  readonly incompletos = computed(() =>
    this.completos() === null ? null : (this.analisis()?.filas.length ?? 0) - this.completos()!,
  );
  readonly columnasFallidas = computed(() => new Set(this.errores().map((i) => i.columna)).size);
  readonly filasFiltradas = computed(() => {
    const texto = this.busqueda().toLocaleLowerCase();
    const errores = this.filasConErrores();
    const columna = this.columnaFiltro();
    const relacionadas = new Set(
      this.errores()
        .filter((i) => i.indice === columna)
        .map((i) => i.fila),
    );
    return (this.analisis()?.filas ?? []).filter(
      (f) =>
        (!texto || f.valores.some((v) => v.toLocaleLowerCase().includes(texto))) &&
        (this.filtro() === 'todos' ||
          (this.filtro() === 'errores'
            ? this.errorEstructural() || errores.has(f.numero)
            : !this.errorEstructural() && !errores.has(f.numero))) &&
        (columna === null || relacionadas.has(f.numero)),
    );
  });
  readonly paginas = computed(() =>
    Math.max(1, Math.ceil(this.filasFiltradas().length / this.tamanoPagina)),
  );
  readonly filasPagina = computed(() =>
    this.filasFiltradas().slice(
      (this.pagina() - 1) * this.tamanoPagina,
      this.pagina() * this.tamanoPagina,
    ),
  );
  readonly incidenciasPagina = computed(() =>
    (this.analisis()?.incidencias ?? []).slice(
      (this.paginaIncidencias() - 1) * 30,
      this.paginaIncidencias() * 30,
    ),
  );
  readonly paginasIncidencias = computed(() =>
    Math.max(1, Math.ceil((this.analisis()?.incidencias.length ?? 0) / 30)),
  );
  readonly puedeImportar = computed(
    () =>
      !!this.archivo() &&
      !!this.hoja() &&
      !!this.analisis()?.validado &&
      !this.errores().length &&
      !!this.analisis()?.filas.length &&
      !!this.curso() &&
      !this.ocupado() &&
      !this.enviando() &&
      !this.resultado(),
  );
  readonly celdasErroneas = computed(
    () => new Set(this.errores().map((i) => `${i.fila}:${i.indice}`)),
  );

  constructor() {
    this.destruir.onDestroy(() => {
      this.worker?.terminate();
      clearTimeout(this.temporizador);
      this.terminarTamano();
    });
  }
  abrir() {
    this.focoAnterior = document.activeElement as HTMLElement;
    this.visible.set(true);
    this.minimizada.set(false);
    this.dialogo()?.nativeElement.showModal();
    if (!this.geometria()) {
      const rect = this.dialogo()?.nativeElement.getBoundingClientRect();
      const viewport = this.viewport();
      const ancho = rect?.width || Math.min(1600, viewport.ancho * 0.9);
      const alto = rect?.height || viewport.alto * 0.88;
      this.geometria.set(
        ajustarRectangulo(
          {
            x: rect?.width ? rect.x : (viewport.ancho - ancho) / 2,
            y: rect?.height ? rect.y : (viewport.alto - alto) / 2,
            ancho,
            alto,
          },
          viewport,
        ),
      );
    }
    this.ajustarViewport();
  }
  cerrar() {
    if (this.enviando() || this.ocupado()) return;
    this.cerrarTotp();
    this.curso.set(null);
    this.terminarTamano();
    this.limpiarArrastre();
    this.confirmar.set(false);
    this.dialogo()?.nativeElement.close();
    this.visible.set(false);
    this.minimizada.set(false);
    this.focoAnterior?.focus();
  }
  minimizar() {
    this.terminarTamano();
    this.limpiarArrastre();
    this.dialogo()?.nativeElement.close();
    this.minimizada.set(true);
  }
  cancelarDialogo(event: Event) {
    event.preventDefault();
    this.cerrar();
  }
  buscarArchivo() {
    if (!this.ocupado() && !this.enviando()) this.entrada()?.nativeElement.click();
  }
  async seleccionar(event: Event) {
    const entrada = event.target as HTMLInputElement;
    const archivo = entrada.files?.[0];
    if (archivo) await this.cargar(archivo);
    // No se limpia el selector hasta haber leído y conservado el archivo en memoria.
    entrada.value = '';
  }
  entrarZona(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (!this.aceptaArrastre(event)) return;
    this.entradasArrastre++;
    this.arrastrando.set(true);
  }
  sobreZona(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    const acepta = this.aceptaArrastre(event);
    if (event.dataTransfer) event.dataTransfer.dropEffect = acepta ? 'copy' : 'none';
    this.arrastrando.set(acepta);
  }
  salirZona(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    // Los eventos de los hijos también burbujean: se equilibran antes de apagar el borde.
    this.entradasArrastre = Math.max(0, this.entradasArrastre - 1);
    if (!this.entradasArrastre) this.arrastrando.set(false);
  }
  private aceptaArrastre(event: DragEvent): boolean {
    return (
      !this.ocupado() &&
      !this.enviando() &&
      !this.redimensionando() &&
      this.dentroVentana(event) &&
      Array.from(event.dataTransfer?.types ?? []).includes('Files')
    );
  }
  private limpiarArrastre() {
    this.entradasArrastre = 0;
    this.arrastrando.set(false);
  }
  soltar(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    this.limpiarArrastre();
    if (this.ocupado() || this.enviando() || this.redimensionando() || !this.dentroVentana(event))
      return;
    if (event.dataTransfer?.files.length !== 1) {
      this.error.set('Seleccione un único archivo Excel.');
      return;
    }
    void this.cargar(event.dataTransfer.files[0]);
  }
  private dentroVentana(event: DragEvent): boolean {
    const rect = this.dialogo()?.nativeElement.getBoundingClientRect();
    return (
      !rect?.width ||
      !Number.isFinite(event.clientX) ||
      (event.clientX >= rect.left &&
        event.clientX <= rect.right &&
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom)
    );
  }
  private viewport() {
    return { ancho: window.innerWidth, alto: window.innerHeight };
  }
  ajustarViewport() {
    this.terminarTamano();
    const rect = this.geometria();
    if (rect)
      this.geometria.set(
        this.maximizada()
          ? rectanguloMaximo(this.viewport())
          : ajustarRectangulo(rect, this.viewport()),
      );
  }
  alternarMaximizada() {
    this.terminarTamano();
    const rect = this.geometria();
    if (!rect) return;
    if (this.maximizada()) {
      this.geometria.set(ajustarRectangulo(this.geometriaAnterior ?? rect, this.viewport()));
      this.maximizada.set(false);
    } else {
      this.geometriaAnterior = { ...rect };
      this.geometria.set(rectanguloMaximo(this.viewport()));
      this.maximizada.set(true);
    }
  }
  iniciarTamano(event: PointerEvent, borde: BordeVentana) {
    if (event.button !== 0 || !event.isPrimary || this.arrastrando()) return;
    const rect = this.geometria();
    if (!rect) return;
    event.preventDefault();
    event.stopPropagation();
    this.gestoTamano = {
      id: event.pointerId,
      borde,
      x: event.clientX,
      y: event.clientY,
      rect: { ...rect },
    };
    this.redimensionando.set(true);
    this.dialogo()?.nativeElement.setPointerCapture(event.pointerId);
  }
  moverTamano(event: PointerEvent) {
    const gesto = this.gestoTamano;
    if (!gesto || event.pointerId !== gesto.id) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = redimensionarRectangulo(
      gesto.rect,
      gesto.borde,
      event.clientX - gesto.x,
      event.clientY - gesto.y,
      this.viewport(),
    );
    if (
      rect.x === gesto.rect.x &&
      rect.y === gesto.rect.y &&
      rect.ancho === gesto.rect.ancho &&
      rect.alto === gesto.rect.alto
    )
      return;
    this.maximizada.set(false);
    this.geometria.set(rect);
    this.geometriaAnterior = { ...rect };
  }
  terminarTamano(event?: PointerEvent) {
    if (event && event.pointerId !== this.gestoTamano?.id) return;
    const id = this.gestoTamano?.id;
    this.gestoTamano = null;
    this.redimensionando.set(false);
    const dialogo = this.dialogo()?.nativeElement;
    if (id !== undefined && dialogo?.hasPointerCapture(id)) dialogo.releasePointerCapture(id);
  }
  quitar() {
    if (this.ocupado() || this.enviando()) return;
    this.cerrarTotp();
    this.limpiarArrastre();
    this.worker?.terminate();
    this.archivo.set(null);
    this.hojas.set([]);
    this.hoja.set('');
    this.analisis.set(null);
    this.resultado.set(null);
    this.error.set('');
    this.confirmar.set(false);
    this.fecha.set(null);
  }
  async cargar(archivo: File) {
    if (this.ocupado() || this.enviando()) return;
    this.error.set('');
    const extension = archivo.name.split('.').pop()?.toLowerCase();
    if (!['xlsx', 'xls'].includes(extension ?? '')) {
      this.error.set('Solo se permiten archivos .xlsx y .xls.');
      return;
    }
    if (!archivo.size || archivo.size > 20 * 1024 * 1024) {
      this.error.set('El archivo debe contener datos y no superar 20 MB.');
      return;
    }
    this.quitar();
    this.archivo.set(archivo);
    this.fecha.set(new Date());
    this.ocupado.set(true);
    try {
      this.worker = new Worker(new URL('./excel.worker', import.meta.url), { type: 'module' });
      this.worker.onmessage = ({ data }) => {
        clearTimeout(this.temporizador);
        this.ocupado.set(false);
        if (data.tipo === 'error') {
          this.error.set(data.mensaje);
          this.enviando.set(false);
          return;
        }
        if (data.tipo === 'hojas') {
          this.hojas.set(data.hojas);
          if (data.hojas.length === 1) this.cambiarHoja(data.hojas[0].nombre);
        }
        if (data.tipo === 'analisis') {
          this.analisis.set(data.analisis);
          this.pagina.set(1);
          this.paginaIncidencias.set(1);
        }
      };
      this.worker.onerror = () => {
        clearTimeout(this.temporizador);
        this.ocupado.set(false);
        this.enviando.set(false);
        this.error.set('No se pudo iniciar el lector Excel. Intente nuevamente.');
      };
      const buffer = await archivo.arrayBuffer();
      // File toma una copia de los bytes antes de transferir el buffer al Worker.
      // La vista previa y el POST usan exactamente el contenido que se pudo leer.
      this.archivo.set(conservarArchivoExcel(archivo, buffer));
      this.esperarWorker();
      this.worker.postMessage({ tipo: 'abrir', buffer, extension }, [buffer]);
    } catch (error) {
      this.ocupado.set(false);
      this.worker?.terminate();
      this.archivo.set(null);
      this.analisis.set(null);
      this.error.set(
        archivoExcelNoDisponible(error)
          ? 'El archivo cambió o ya no está disponible. Vuelva a seleccionarlo y valide de nuevo.'
          : 'No fue posible leer el archivo Excel. Vuelva a seleccionarlo e intente de nuevo.',
      );
    }
  }
  private esperarWorker() {
    clearTimeout(this.temporizador);
    this.temporizador = setTimeout(() => {
      this.worker?.terminate();
      this.ocupado.set(false);
      this.enviando.set(false);
      this.analisis.set(null);
      this.error.set('El procesamiento excedió 60 segundos. Seleccione un archivo más pequeño.');
    }, 60000);
  }
  cambiarHoja(nombre: string) {
    if (this.ocupado() || this.enviando()) return;
    this.hoja.set(nombre);
    this.analisis.set(null);
    this.resultado.set(null);
    this.confirmar.set(false);
    this.error.set('');
    this.reiniciarFiltros();
    if (nombre) {
      this.ocupado.set(true);
      this.esperarWorker();
      this.worker?.postMessage({ tipo: 'analizar', hoja: nombre, validar: false });
    }
  }
  async validar() {
    if (!this.hoja() || this.ocupado() || this.enviando()) return;
    this.ocupado.set(true);
    this.error.set('');
    this.confirmar.set(false);
    this.resultado.set(null);
    try {
      this.unidades = await firstValueFrom(this.api.unidades().pipe(timeout(15000)));
    } catch {
      this.unidades = null;
    }
    if (this.destruir.destroyed) return;
    this.esperarWorker();
    this.worker?.postMessage({
      tipo: 'analizar',
      hoja: this.hoja(),
      validar: true,
      unidades: this.unidades,
    });
  }
  reiniciarFiltros() {
    this.busqueda.set('');
    this.filtro.set('todos');
    this.columnaFiltro.set(null);
    this.pagina.set(1);
    this.filaActiva.set(null);
  }
  filtrar(tipo: string) {
    this.filtro.set(tipo);
    this.columnaFiltro.set(null);
    this.pagina.set(1);
  }
  filtrarColumna(indice: number) {
    this.filtro.set('errores');
    this.columnaFiltro.set(indice);
    this.pagina.set(1);
  }
  localizar(incidencia: Incidencia) {
    this.reiniciarFiltros();
    const posicion = this.filasFiltradas().findIndex((f) => f.numero === incidencia.fila);
    if (posicion < 0) {
      this.dialogo()
        ?.nativeElement.querySelector('#diagnostico')
        ?.scrollIntoView({ block: 'nearest' });
      return;
    }
    this.pagina.set(Math.floor(posicion / this.tamanoPagina) + 1);
    this.filaActiva.set(incidencia.fila);
    requestAnimationFrame(() => {
      const fila = this.dialogo()?.nativeElement.querySelector<HTMLElement>(
        `#excel-fila-${incidencia.fila}`,
      );
      fila?.scrollIntoView({ block: 'nearest' });
      fila?.focus();
    });
  }
  async descargarErrores() {
    const incidencias = this.analisis()?.incidencias;
    if (!incidencias?.length) return;
    const { utils, writeFileXLSX } = await import('xlsx');
    const libro = utils.book_new();
    utils.book_append_sheet(
      libro,
      utils.json_to_sheet(
        incidencias.map((i) => ({
          Hoja: this.hoja(),
          Fila: i.fila,
          Columna: i.columna,
          Valor: i.valor,
          Motivo: i.motivo,
          Severidad: i.nivel,
        })),
      ),
      'Incidencias',
    );
    writeFileXLSX(libro, 'incidencias-esart.xlsx');
  }
  importar() {
    if (!this.puedeImportar() || !this.confirmar()) return;
    const archivo = this.archivo();
    const curso = this.curso();
    if (!archivo || !this.hoja() || !curso) return;
    this.confirmar.set(false);
    this.enviando.set(true);
    this.error.set('');
    this.enviar(archivo, this.hoja(), curso);
  }
  /** La ventana TOTP envía el código con el mismo archivo, hoja y curso ya confirmados. */
  readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    const archivo = this.archivo();
    const hoja = this.hoja();
    const curso = this.curso();
    if (!archivo || !hoja || !curso) {
      this.cerrarTotp();
      return EMPTY;
    }
    this.enviando.set(true);
    return this.api.importar(archivo, hoja, curso, codigo).pipe(
      tap((resultado) => {
        this.enviando.set(false);
        this.aplicarResultado(resultado);
      }),
      catchError((error: unknown) => {
        this.enviando.set(false);
        // Código inválido o límite de intentos: se informa dentro de la ventana TOTP.
        if (!archivoExcelNoDisponible(error) && CODIGOS_TOTP.has(leerErrorApi(error).codigo)) {
          return throwError(() => error);
        }
        this.cerrarTotp();
        this.manejarError(error);
        return EMPTY;
      }),
    );
  };
  private abrirTotp(mensaje = '') {
    this.errorTotp.set(mensaje);
    this.requiereTotp.set(true);
    const dialogo = this.dialogoTotp()?.nativeElement;
    if (dialogo && !dialogo.open) dialogo.showModal();
  }
  cerrarTotp() {
    this.requiereTotp.set(false);
    this.errorTotp.set('');
    const dialogo = this.dialogoTotp()?.nativeElement;
    if (dialogo?.open) dialogo.close();
  }
  cancelarTotp() {
    this.cerrarTotp();
    this.error.set('Verificación cancelada. No se guardó ningún registro.');
  }
  private aplicarResultado(resultado: ResultadoImportacion) {
    if (resultado.estado !== 'APLICADA') {
      this.error.set('El servidor no confirmó la aplicación de la importación.');
      return;
    }
    this.resultado.set(resultado);
    this.verificacion.notificarPersonalActualizado();
    this.formularioCurso()?.recargar();
  }
  private enviar(archivo: File, hoja: string, curso: DatosCursoImportacion) {
    this.api
      .importar(archivo, hoja, curso)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (resultado) => {
          this.enviando.set(false);
          this.aplicarResultado(resultado);
        },
        error: (error: unknown) => {
          this.enviando.set(false);
          const codigo = archivoExcelNoDisponible(error) ? '' : leerErrorApi(error).codigo;
          if (CODIGOS_TOTP.has(codigo)) {
            this.abrirTotp(codigo === 'TOTP_REQUERIDO' ? '' : leerErrorApi(error).mensaje);
            return;
          }
          this.manejarError(error);
        },
      });
  }
  private manejarError(error: unknown) {
    if (archivoExcelNoDisponible(error)) {
      this.archivo.set(null);
      this.analisis.set(null);
      this.hojas.set([]);
      this.hoja.set('');
      this.error.set(
        'El archivo cambió o ya no está disponible. Vuelva a seleccionarlo y valide de nuevo.',
      );
      return;
    }
    const fallo = leerErrorApi(error);
    this.error.set(
      fallo.codigo === 'SIN_CONEXION' && fallo.estadoHttp === 0
        ? 'No se pudo enviar el archivo. Compruebe la conexión con el servidor; si el archivo cambió, vuelva a seleccionarlo. No se reintentó la importación.'
        : fallo.estadoHttp === 404 || fallo.estadoHttp === 501
          ? 'El servicio de importación aún no está disponible. No se confirmó ninguna importación.'
          : fallo.mensaje,
    );
    const detalle = fallo.detalle?.['errores'];
    if (Array.isArray(detalle) && this.analisis()) {
      const incidencias: Incidencia[] = detalle.map((i) => {
        const fila = this.analisis()!.filas.find((fila) => fila.numero === Number(i.fila));
        const indice = this.analisis()!.columnas.findIndex(
          (c) => c.campo === i.columna || c.nombre === i.columna,
        );
        return {
          fila: fila?.numero ?? Number(i.fila),
          columna: String(i.columna),
          indice,
          valor: typeof i.valor === 'string' ? i.valor : (fila?.valores[indice] ?? ''),
          motivo: String(i.motivo),
          nivel: 'Error',
        };
      });
      this.analisis.update((a) => {
        if (!a) return a;
        const todas = [...a.incidencias, ...incidencias];
        return {
          ...a,
          incidencias: todas,
          columnas: a.columnas.map((columna, indice) => ({
            ...columna,
            errores: todas.filter((i) => i.indice === indice && i.nivel === 'Error').length,
          })),
        };
      });
    }
  }
}
