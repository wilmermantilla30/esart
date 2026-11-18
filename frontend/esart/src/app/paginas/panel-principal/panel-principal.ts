import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { iconoDeComponente } from '../../nucleo/iconos-menu';
import { ErrorApi, leerErrorApi } from '../../nucleo/modelos/error-api';
import {
  CursoEstadistica,
  CursosDelAnio,
  GradoCatalogo,
  PanelEstadisticas,
  Semestre,
} from '../../nucleo/modelos/estadisticas';
import { EstadisticasService } from '../../nucleo/servicios/estadisticas.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';

/**
 * Rampa secuencial (un solo tono, claro -> oscuro) para el mapa de calor de grados.
 * Validada con la guía de visualización: luminosidad monótona y un solo tono.
 */
export const RAMPA_AZUL = [
  '#cde2fb',
  '#9ec5f4',
  '#6da7ec',
  '#3987e5',
  '#256abf',
  '#184f95',
  '#0d366b',
];

/** Color de una celda del mapa de calor (0 = sin color) y si su texto debe ir en blanco. */
export function colorDeCelda(
  valor: number,
  maximo: number,
): { fondo: string; textoClaro: boolean } {
  if (!valor || maximo <= 0) return { fondo: 'transparent', textoClaro: false };
  const paso = Math.min(
    RAMPA_AZUL.length - 1,
    Math.floor((valor / maximo) * (RAMPA_AZUL.length - 1) + 0.5),
  );
  return { fondo: RAMPA_AZUL[paso], textoClaro: paso >= 3 };
}

/** Altura (px) de una barra respecto al máximo de la gráfica. */
export function alturaBarra(valor: number, maximo: number, alturaMaxima: number): number {
  return maximo > 0 ? Math.round((valor / maximo) * alturaMaxima) : 0;
}

/** Porcentaje entero de una parte sobre el total (0 si no hay total). */
export function porcentaje(parte: number, total: number): number {
  return total > 0 ? Math.round((parte * 100) / total) : 0;
}

/** Estados de curso en palabras, con su color (de estado, siempre con texto). */
export const ESTADOS_CURSO: Record<string, { texto: string; clases: string }> = {
  EN_CURSO: {
    texto: 'En curso',
    clases: 'bg-azul-hielo text-azul-institucional border-azul-claro',
  },
  CULMINADO: { texto: 'Culminado', clases: 'bg-success/10 text-success border-success/30' },
  CANCELADO: { texto: 'Cancelado', clases: 'bg-error/10 text-error border-error/30' },
  APLAZADO: { texto: 'Aplazado', clases: 'bg-warning/10 text-warning border-warning/40' },
};

const NOMBRES_CATEGORIA: Record<string, string> = {
  OFICIAL: 'Oficiales',
  SUBOFICIAL: 'Suboficiales',
  SOLDADO_PROFESIONAL: 'Soldados',
  OTRO: 'Otros',
};

/** Columnas del mapa de calor agrupadas por categoría (oficiales, suboficiales, soldados). */
export function gruposDeGrados(
  grados: GradoCatalogo[],
): { categoria: string; grados: GradoCatalogo[] }[] {
  const grupos: { categoria: string; grados: GradoCatalogo[] }[] = [];
  for (const grado of grados) {
    const nombre = NOMBRES_CATEGORIA[grado.categoria] ?? grado.categoria;
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.categoria === nombre) ultimo.grados.push(grado);
    else grupos.push({ categoria: nombre, grados: [grado] });
  }
  return grupos;
}

/** Información del cuadro emergente que acompaña al puntero sobre una gráfica. */
interface CuadroEmergente {
  titulo: string;
  lineas: string[];
  x: number;
  y: number;
}

const ALTURA_BARRAS_ANIO = 150;
/** Porción del curso (40 %) a partir de la cual la celda toma el tono más oscuro. */
const PORCION_MAXIMA_ESCALA = 0.4;

/**
 * Panel principal (componente DASHBOARD): lo primero que ve el Comandante.
 *
 * - Filtros por año y semestre (por fecha de inicio del curso).
 * - Indicadores: cursos en curso hoy, cursos y alumnos del período, egresados y habilitación.
 * - Seguimiento de los cursos en curso con su avance por fechas.
 * - Gráficas: cursos por año y semestre, género por curso y mapa de calor de grados por curso.
 * - Accesos directos a los módulos permitidos.
 */
@Component({
  selector: 'esart-panel-principal',
  imports: [RouterLink, DatePipe, DecimalPipe],
  templateUrl: './panel-principal.html',
})
export class PanelPrincipal {
  private readonly sesion = inject(SesionService);
  private readonly estadisticas = inject(EstadisticasService);
  private readonly destruir = inject(DestroyRef);

  protected readonly usuario = this.sesion.usuario;
  protected readonly iconoDeComponente = iconoDeComponente;
  protected readonly estados = ESTADOS_CURSO;
  protected readonly alturaBarrasAnio = ALTURA_BARRAS_ANIO;

  /** Accesos directos: todos los módulos del menú menos el propio panel. */
  protected readonly accesos = computed(() =>
    (this.sesion.menu() ?? []).filter((modulo) => modulo.codigo !== 'DASHBOARD'),
  );

  // --- Filtros y datos ---
  protected readonly anio = signal<number | null>(null);
  protected readonly semestre = signal<Semestre | null>(null);
  protected readonly datos = signal<PanelEstadisticas | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly cuadro = signal<CuadroEmergente | null>(null);
  /** Vista en tabla de las gráficas (accesible y para copiar cifras). */
  protected readonly verTablas = signal(false);

  /** "Todos" más los años que tienen cursos. */
  protected readonly opcionesAnio = computed<(number | null)[]>(() => [
    null,
    ...(this.datos()?.anios_disponibles ?? []),
  ]);

  protected readonly textoPeriodo = computed(() => {
    const anio = this.anio();
    const semestre = this.semestre();
    const parteSemestre = semestre ? `${semestre === 1 ? '1.er' : '2.º'} semestre` : '';
    if (anio && semestre) return `${parteSemestre} de ${anio}`;
    if (anio) return `Año ${anio}`;
    if (semestre) return `${parteSemestre} (todos los años)`;
    return 'Todo el histórico';
  });

  protected readonly maximoAnio = computed(() =>
    Math.max(
      1,
      ...(this.datos()?.cursos_por_anio ?? []).map((fila) => fila.semestre_1 + fila.semestre_2),
    ),
  );
  protected readonly gruposGrados = computed(() => gruposDeGrados(this.datos()?.grados ?? []));
  /** Cursos del período que tienen alumnos (los que alimentan género y grados). */
  protected readonly cursosConAlumnos = computed(() =>
    (this.datos()?.cursos ?? []).filter((curso) => curso.alumnos > 0),
  );
  protected readonly totalGenero = computed(() =>
    this.cursosConAlumnos().reduce(
      (total, curso) => ({ M: total.M + curso.genero.M, F: total.F + curso.genero.F }),
      { M: 0, F: 0 },
    ),
  );
  protected readonly porcentajeAptos = computed(() => {
    const habilitacion = this.datos()?.habilitacion;
    return habilitacion ? porcentaje(habilitacion.aptos, habilitacion.total) : 0;
  });

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.estadisticas
      .panel(this.anio(), this.semestre())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (datos) => {
          this.datos.set(datos);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  protected elegirAnio(anio: number | null): void {
    if (this.anio() === anio) return;
    this.anio.set(anio);
    this.cargar();
  }

  protected elegirSemestre(semestre: Semestre | null): void {
    if (this.semestre() === semestre) return;
    this.semestre.set(semestre);
    this.cargar();
  }

  // --- Ayudas de las gráficas ---

  protected altura(valor: number): number {
    return alturaBarra(valor, this.maximoAnio(), ALTURA_BARRAS_ANIO);
  }

  protected atenuada(fila: CursosDelAnio): boolean {
    return this.anio() !== null && this.anio() !== fila.anio;
  }

  /**
   * Color de la celda según el PORCENTAJE del curso que representa ese grado (escala de 0 a
   * 40 % o más). Así se comparan cursos de 6 y de 200 alumnos con la misma escala.
   */
  protected celda(curso: CursoEstadistica, valor: number) {
    return colorDeCelda(curso.alumnos ? valor / curso.alumnos : 0, PORCION_MAXIMA_ESCALA);
  }

  protected porcentaje(parte: number, total: number): number {
    return porcentaje(parte, total);
  }

  protected textoEstado(estado: string): string {
    return this.estados[estado]?.texto ?? estado;
  }

  protected clasesEstado(estado: string): string {
    return this.estados[estado]?.clases ?? 'bg-gris-claro text-azul-pizarra border-gris-bordes';
  }

  protected nombresHijos(hijos: { nombre: string }[]): string {
    return hijos.map((hijo) => hijo.nombre).join(' · ');
  }

  // --- Cuadro emergente (hover) ---

  protected mostrarCuadro(evento: MouseEvent, titulo: string, lineas: string[]): void {
    this.cuadro.set({ titulo, lineas, x: evento.clientX, y: evento.clientY });
  }

  protected moverCuadro(evento: MouseEvent): void {
    const actual = this.cuadro();
    if (actual) this.cuadro.set({ ...actual, x: evento.clientX, y: evento.clientY });
  }

  protected ocultarCuadro(): void {
    this.cuadro.set(null);
  }

  protected lineasAnio(fila: CursosDelAnio): string[] {
    return [
      `1.er semestre: ${fila.semestre_1} curso(s)`,
      `2.º semestre: ${fila.semestre_2} curso(s)`,
      'Clic para filtrar este año',
    ];
  }

  protected lineasGenero(curso: CursoEstadistica): string[] {
    const total = curso.genero.M + curso.genero.F;
    return [
      `Hombres: ${curso.genero.M} (${porcentaje(curso.genero.M, total)} %)`,
      `Mujeres: ${curso.genero.F} (${porcentaje(curso.genero.F, total)} %)`,
    ];
  }

  protected lineasGrado(curso: CursoEstadistica, grado: GradoCatalogo): string[] {
    const cantidad = curso.grados[grado.sigla] ?? 0;
    return [
      `${grado.nombre}: ${cantidad} alumno(s)`,
      `${porcentaje(cantidad, curso.alumnos)} % del curso`,
    ];
  }
}
