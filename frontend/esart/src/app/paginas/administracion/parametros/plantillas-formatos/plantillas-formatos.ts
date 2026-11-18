import { DatePipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  inject,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';

import { ErrorApi, leerErrorApi } from '../../../../nucleo/modelos/error-api';
import { FormatoPlantilla, Plantilla } from '../../../../nucleo/modelos/parametros';
import { ParametrosService } from '../../../../nucleo/servicios/parametros.service';
import { SesionService } from '../../../../nucleo/servicios/sesion.service';

const COMPONENTE = 'PARAMETROS_HABILITACION';
export const TAMANO_MAXIMO_BYTES = 25 * 1024 * 1024;

/** Presentación de cada formato: color institucional por tipo (verde Excel, rojo PDF, azul Word). */
export interface EstiloFormato {
  etiqueta: string;
  icono: string;
  tarjeta: string;
  icono_caja: string;
  insignia: string;
  ficha: string;
  pie: string;
  boton: string;
  filtro: string;
  punto: string;
}

const ESTILO_EXCEL: Omit<EstiloFormato, 'etiqueta'> = {
  icono: 'table_view',
  tarjeta: 'border-emerald-200 hover:border-emerald-400',
  icono_caja: 'bg-emerald-50 border-emerald-200 text-emerald-600',
  insignia: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  ficha: 'bg-emerald-50/50 border-emerald-100',
  pie: 'bg-emerald-50/30 border-emerald-100',
  boton: 'text-emerald-700 border-emerald-300 hover:bg-emerald-50',
  filtro: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  punto: 'bg-emerald-500',
};

export const ESTILOS_FORMATO: Record<FormatoPlantilla, EstiloFormato> = {
  XLSX: { etiqueta: 'Excel XLSX', ...ESTILO_EXCEL },
  XLS: { etiqueta: 'Excel XLS', ...ESTILO_EXCEL },
  PDF: {
    etiqueta: 'PDF',
    icono: 'picture_as_pdf',
    tarjeta: 'border-rose-200 hover:border-rose-400',
    icono_caja: 'bg-rose-50 border-rose-200 text-rose-600',
    insignia: 'bg-rose-100 text-rose-800 border-rose-200',
    ficha: 'bg-rose-50/50 border-rose-100',
    pie: 'bg-rose-50/30 border-rose-100',
    boton: 'text-rose-700 border-rose-300 hover:bg-rose-50',
    filtro: 'text-rose-700 bg-rose-50 border-rose-200',
    punto: 'bg-rose-500',
  },
  DOCX: {
    etiqueta: 'Word DOCX',
    icono: 'article',
    tarjeta: 'border-blue-200 hover:border-blue-400',
    icono_caja: 'bg-blue-50 border-blue-200 text-blue-600',
    insignia: 'bg-blue-100 text-blue-800 border-blue-200',
    ficha: 'bg-blue-50/50 border-blue-100',
    pie: 'bg-blue-50/30 border-blue-100',
    boton: 'text-blue-700 border-blue-300 hover:bg-blue-50',
    filtro: 'text-blue-700 bg-blue-50 border-blue-200',
    punto: 'bg-blue-500',
  },
};

/** Filtros de la barra superior: Excel agrupa .xlsx y .xls. */
export type FiltroFormato = 'TODOS' | 'EXCEL' | 'PDF' | 'WORD';
const FORMATOS_POR_FILTRO: Record<Exclude<FiltroFormato, 'TODOS'>, FormatoPlantilla[]> = {
  EXCEL: ['XLSX', 'XLS'],
  PDF: ['PDF'],
  WORD: ['DOCX'],
};

/** Formato según la extensión del archivo elegido (el backend vuelve a comprobar el contenido). */
export function formatoPorNombre(nombre: string): FormatoPlantilla | null {
  const extension = nombre.toLowerCase().split('.').pop();
  const formatos: Record<string, FormatoPlantilla> = {
    xlsx: 'XLSX',
    xls: 'XLS',
    pdf: 'PDF',
    docx: 'DOCX',
  };
  return (extension && formatos[extension]) || null;
}

/** Tamaño legible: 45,2 KB, 4,8 MB. */
export function tamanoLegible(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kilos = bytes / 1024;
  if (kilos < 1024) return `${kilos.toLocaleString('es-CO', { maximumFractionDigits: 1 })} KB`;
  return `${(kilos / 1024).toLocaleString('es-CO', { maximumFractionDigits: 1 })} MB`;
}

/**
 * Pestaña "Plantillas y Formatos": repositorio de documentos institucionales.
 * Publicar exige el permiso "crear" del componente y retirar el permiso "eliminar".
 */
@Component({
  selector: 'esart-plantillas-formatos',
  imports: [DatePipe, FormsModule],
  templateUrl: './plantillas-formatos.html',
})
export class PlantillasFormatosPestana {
  private readonly parametros = inject(ParametrosService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  /** Cantidad de archivos vigentes, para la insignia de la pestaña. */
  readonly cantidad = output<number>();

  protected readonly estilos = ESTILOS_FORMATO;
  protected readonly tamanoLegible = tamanoLegible;
  protected readonly puedePublicar = computed(() => this.sesion.puede(COMPONENTE, 'crear'));
  protected readonly puedeRetirar = computed(() => this.sesion.puede(COMPONENTE, 'eliminar'));

  protected readonly plantillas = signal<Plantilla[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);
  protected readonly ocupado = signal<number | null>(null);

  protected readonly filtro = signal<FiltroFormato>('TODOS');
  protected readonly visibles = computed(() => {
    const filtro = this.filtro();
    return filtro === 'TODOS'
      ? this.plantillas()
      : this.plantillas().filter((plantilla) =>
          FORMATOS_POR_FILTRO[filtro].includes(plantilla.formato),
        );
  });
  protected readonly conteo = computed(() => {
    const contar = (formatos: FormatoPlantilla[]) =>
      this.plantillas().filter((plantilla) => formatos.includes(plantilla.formato)).length;
    return {
      TODOS: this.plantillas().length,
      EXCEL: contar(FORMATOS_POR_FILTRO.EXCEL),
      PDF: contar(FORMATOS_POR_FILTRO.PDF),
      WORD: contar(FORMATOS_POR_FILTRO.WORD),
    };
  });

  // --- Ventana "Subir plantilla" ---
  protected readonly subiendo = signal(false);
  protected readonly publicando = signal(false);
  protected readonly errorSubida = signal<string | null>(null);
  protected readonly archivo = signal<File | null>(null);
  protected readonly arrastrando = signal(false);
  protected readonly nombreOficial = signal('');
  protected readonly version = signal('v1.0');
  protected readonly descripcion = signal('');
  protected readonly formatoElegido = computed(() => {
    const archivo = this.archivo();
    return archivo ? formatoPorNombre(archivo.name) : null;
  });
  protected readonly puedeEnviar = computed(
    () =>
      !!this.archivo() &&
      !!this.formatoElegido() &&
      this.nombreOficial().trim().length >= 3 &&
      /^[\w .-]{1,30}$/.test(this.version().trim()) &&
      !this.publicando(),
  );
  private readonly entradaArchivo = viewChild<ElementRef<HTMLInputElement>>('entradaArchivo');

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.parametros
      .listarPlantillas()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (plantillas) => {
          this.plantillas.set(plantillas);
          this.cantidad.emit(plantillas.length);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  descargar(plantilla: Plantilla): void {
    this.ocupado.set(plantilla.id);
    this.error.set(null);
    this.parametros
      .descargarPlantilla(plantilla)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: ({ nombre, contenido }) => {
          // Enlace temporal en memoria: el archivo nunca se abre dentro de la página.
          const enlace = document.createElement('a');
          enlace.href = URL.createObjectURL(contenido);
          enlace.download = nombre;
          enlace.click();
          URL.revokeObjectURL(enlace.href);
          this.ocupado.set(null);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.ocupado.set(null);
        },
      });
  }

  protected retirar(plantilla: Plantilla): void {
    if (
      !confirm(
        `¿Retirar "${plantilla.nombre_oficial}" (${plantilla.version})? Dejará de ofrecerse para descarga; ` +
          'queda guardada en el historial.',
      )
    ) {
      return;
    }
    this.ocupado.set(plantilla.id);
    this.error.set(null);
    this.parametros
      .retirarPlantilla(plantilla.id)
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: () => {
          this.ocupado.set(null);
          this.aviso.set(`Plantilla "${plantilla.nombre_oficial}" retirada.`);
          this.cargar();
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.ocupado.set(null);
        },
      });
  }

  // --- Subir ---

  abrirSubida(): void {
    this.subiendo.set(true);
    this.errorSubida.set(null);
    this.archivo.set(null);
    this.nombreOficial.set('');
    this.version.set('v1.0');
    this.descripcion.set('');
  }

  protected cerrarSubida(): void {
    this.subiendo.set(false);
    this.archivo.set(null);
  }

  protected examinar(): void {
    this.entradaArchivo()?.nativeElement.click();
  }

  protected archivoElegido(evento: Event): void {
    const entrada = evento.target as HTMLInputElement;
    this.elegir(entrada.files?.[0] ?? null);
    entrada.value = '';
  }

  protected soltar(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(false);
    this.elegir(evento.dataTransfer?.files?.[0] ?? null);
  }

  protected sobre(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(true);
  }

  protected publicar(): void {
    const archivo = this.archivo();
    if (!archivo || !this.puedeEnviar()) return;
    this.publicando.set(true);
    this.errorSubida.set(null);
    this.parametros
      .publicarPlantilla({
        archivo,
        nombre_oficial: this.nombreOficial().trim(),
        version: this.version().trim(),
        descripcion: this.descripcion().trim(),
      })
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (plantilla) => {
          this.publicando.set(false);
          this.cerrarSubida();
          this.aviso.set(`Plantilla "${plantilla.nombre_oficial}" publicada.`);
          this.cargar();
        },
        error: (error: unknown) => {
          this.publicando.set(false);
          this.errorSubida.set(leerErrorApi(error).mensaje);
        },
      });
  }

  /** Validación rápida en el navegador; el backend comprueba de nuevo el contenido real. */
  private elegir(archivo: File | null): void {
    this.errorSubida.set(null);
    if (!archivo) return;
    if (!formatoPorNombre(archivo.name)) {
      this.archivo.set(null);
      this.errorSubida.set(
        'Solo se admiten archivos Excel (.xlsx, .xls), PDF (.pdf) y Word (.docx).',
      );
      return;
    }
    if (archivo.size > TAMANO_MAXIMO_BYTES) {
      this.archivo.set(null);
      this.errorSubida.set('El archivo supera el tamaño máximo de 25 MB.');
      return;
    }
    this.archivo.set(archivo);
    if (!this.nombreOficial().trim()) {
      // Sugerencia editable: el nombre del archivo sin extensión ni guiones bajos.
      this.nombreOficial.set(
        archivo.name
          .replace(/\.[^.]+$/, '')
          .replace(/[_-]+/g, ' ')
          .trim(),
      );
    }
  }
}
