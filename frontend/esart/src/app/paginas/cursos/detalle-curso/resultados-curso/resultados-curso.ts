import { DatePipe, DecimalPipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  OnInit,
  ElementRef,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Observable, catchError, tap, throwError } from 'rxjs';

import { ResultadoAlumno, ResultadosCurso } from '../../../../nucleo/modelos/cursos';
import { ErrorApi, leerErrorApi } from '../../../../nucleo/modelos/error-api';
import { CursosService } from '../../../../nucleo/servicios/cursos.service';
import { SesionService } from '../../../../nucleo/servicios/sesion.service';
import { Totp } from '../../../totp/totp';

const COMPONENTE = 'CURSOS';
/** Errores que se muestran dentro de la ventana del autenticador (el usuario reintenta ahí). */
const CODIGOS_TOTP = new Set(['TOTP_INVALIDO', 'INTENTOS_LIMITADOS']);

/** Conteo de aprobados, reprobados y alumnos sin resultado todavía. */
export function resumenResultados(alumnos: ReadonlyArray<ResultadoAlumno>): {
  aprobados: number;
  reprobados: number;
  pendientes: number;
} {
  return {
    aprobados: alumnos.filter((alumno) => alumno.resultado === 'APROBADO').length,
    reprobados: alumnos.filter((alumno) => alumno.resultado === 'REPROBADO').length,
    pendientes: alumnos.filter((alumno) => alumno.resultado === null).length,
  };
}

/** Lo que impide cerrar el curso, en una sola lista (del curso y de cada alumno). */
export function pendientesDelCierre(resultados: ResultadosCurso): string[] {
  return [
    ...resultados.pendientes,
    ...resultados.alumnos.flatMap((alumno) =>
      alumno.pendientes.map((pendiente) => `${alumno.apellidos} ${alumno.nombres}: ${pendiente}`),
    ),
  ];
}

/**
 * Sección "Resultados" del detalle del curso (S2-15).
 *
 * Muestra la nota final, el resultado y el puesto de cada alumno: PROVISIONALES mientras falten
 * notas, habilitaciones o decisiones del Consejo, y GUARDADOS desde que el curso se cierra. Quien
 * tiene CURSOS "actualizar" cierra el curso con el autenticador cuando todo está completo.
 */
@Component({
  selector: 'esart-resultados-curso',
  imports: [DatePipe, DecimalPipe, Totp],
  templateUrl: './resultados-curso.html',
  styles: `
    .ventana-totp {
      width: 100vw;
      height: 100dvh;
      max-width: none;
      max-height: none;
      margin: 0;
      padding: 0;
      border: 0;
      background: none;
    }
    .ventana-totp::backdrop {
      background: none;
    }
  `,
})
export class ResultadosCursoSeccion implements OnInit {
  private readonly servicio = inject(CursosService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);

  readonly cursoId = input.required<number>();
  /** Avisa al detalle que el curso se cerró (cambia su estado). */
  readonly cerrado = output<void>();

  protected readonly puedeCerrarPermiso = computed(() =>
    this.sesion.puede(COMPONENTE, 'actualizar'),
  );
  protected readonly resultados = signal<ResultadosCurso | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal<ErrorApi | null>(null);
  protected readonly aviso = signal<string | null>(null);
  protected readonly confirmando = signal(false);
  protected readonly cerrando = signal(false);
  protected readonly verPendientes = signal(false);

  protected readonly resumen = computed(() => resumenResultados(this.resultados()?.alumnos ?? []));
  protected readonly listaPendientes = computed(() => {
    const datos = this.resultados();
    return datos ? pendientesDelCierre(datos) : [];
  });

  protected readonly requiereTotp = signal(false);
  protected readonly errorTotp = signal('');
  private readonly ventanaTotp = viewChild<ElementRef<HTMLDialogElement>>('ventanaTotp');

  /** El id del curso llega como input: se carga cuando ya está disponible. */
  ngOnInit(): void {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.servicio
      .resultados(this.cursoId())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (datos) => {
          this.resultados.set(datos);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  /** Primer intento sin código: el backend responde TOTP_REQUERIDO y se abre el autenticador. */
  protected cerrar(): void {
    if (this.cerrando()) return;
    this.confirmando.set(false);
    this.cerrando.set(true);
    this.error.set(null);
    this.servicio
      .cerrar(this.cursoId())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (datos) => this.cursoCerrado(datos),
        error: (error: unknown) => {
          this.cerrando.set(false);
          const fallo = leerErrorApi(error);
          if (fallo.codigo === 'TOTP_REQUERIDO') {
            this.abrirTotp();
            return;
          }
          this.error.set(fallo);
        },
      });
  }

  /** La ventana del autenticador reenvía el cierre con el código. */
  protected readonly verificarCodigoTotp = (codigo: string): Observable<unknown> => {
    this.cerrando.set(true);
    return this.servicio.cerrar(this.cursoId(), codigo).pipe(
      tap((datos) => {
        this.cerrarTotp();
        this.cursoCerrado(datos);
      }),
      catchError((error: unknown) => {
        this.cerrando.set(false);
        if (CODIGOS_TOTP.has(leerErrorApi(error).codigo)) {
          return throwError(() => error);
        }
        this.cerrarTotp();
        this.error.set(leerErrorApi(error));
        return EMPTY;
      }),
    );
  };

  protected cancelarTotp(): void {
    this.cerrarTotp();
    this.aviso.set('Verificación cancelada. El curso sigue abierto.');
  }

  protected cerrarTotp(): void {
    this.requiereTotp.set(false);
    this.errorTotp.set('');
    const ventana = this.ventanaTotp()?.nativeElement;
    if (ventana?.open) ventana.close();
  }

  private cursoCerrado(datos: ResultadosCurso): void {
    this.cerrando.set(false);
    this.resultados.set(datos);
    const resumen = resumenResultados(datos.alumnos);
    this.aviso.set(
      `Curso cerrado: ${resumen.aprobados} aprobado(s) y ${resumen.reprobados} reprobado(s). ` +
        'Los aprobados ya cuentan para la verificación APTO / NO APTO.',
    );
    this.cerrado.emit();
  }

  private abrirTotp(): void {
    this.errorTotp.set('');
    this.requiereTotp.set(true);
    // La ventana se abre después de que Angular pinte el componente del autenticador.
    queueMicrotask(() => {
      const ventana = this.ventanaTotp()?.nativeElement;
      if (ventana && !ventana.open) ventana.showModal();
    });
  }
}
