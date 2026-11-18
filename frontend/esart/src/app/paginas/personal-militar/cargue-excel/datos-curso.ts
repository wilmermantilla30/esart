import {
  Component,
  computed,
  DestroyRef,
  inject,
  input,
  OnInit,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { leerErrorApi } from '../../../nucleo/modelos/error-api';
import { DatosCursoImportacion, ESTADOS_CURSO, EstadoCurso, OpcionCatalogo } from './excel-modelos';
import { ImportacionExcelService } from './importacion-excel.service';

/**
 * Datos del curso que se crea con la importación. El número lo asigna el servidor por tipo de
 * curso ("SACLI 01", "SACLI 02", "COFUO 01"…); aquí solo se muestra el del tipo elegido.
 */
@Component({
  imports: [ReactiveFormsModule],
  selector: 'app-datos-curso',
  styleUrl: './datos-curso.css',
  templateUrl: './datos-curso.html',
})
export class DatosCurso implements OnInit {
  private readonly api = inject(ImportacionExcelService);
  private readonly destruir = inject(DestroyRef);
  private readonly fb = inject(NonNullableFormBuilder);
  readonly deshabilitado = input(false);
  /** Emite los datos válidos o null mientras el formulario esté incompleto. */
  readonly cambio = output<DatosCursoImportacion | null>();
  readonly estados = ESTADOS_CURSO;
  readonly tipos = signal<OpcionCatalogo[]>([]);
  readonly instructores = signal<OpcionCatalogo[]>([]);
  /** Tipo elegido en el selector: define qué número de curso se muestra. */
  private readonly tipoElegido = signal('');
  /** Número que tendrá el curso: el siguiente del tipo elegido (vacío mientras no haya tipo). */
  readonly siguienteCodigo = computed(
    () => this.tipos().find((t) => String(t.id) === this.tipoElegido())?.siguiente_codigo ?? '',
  );
  readonly cargando = signal(false);
  readonly errorCarga = signal('');
  readonly formulario = this.fb.group({
    tipo_curso_id: ['', Validators.required],
    nombre_curso: ['', [Validators.required, Validators.maxLength(200)]],
    comandante_id: ['', Validators.required],
    fecha_inicio: ['', Validators.required],
    fecha_fin: ['', Validators.required],
    estado_curso: ['EN_CURSO' as EstadoCurso, Validators.required],
    observacion_curso: ['', Validators.maxLength(2000)],
  });

  constructor() {
    this.formulario.valueChanges
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe(() => this.cambio.emit(this.valor()));
  }
  ngOnInit(): void {
    this.recargar();
  }
  /** Vuelve a pedir catálogos y el número siguiente (por ejemplo, tras una importación). */
  recargar(): void {
    this.cargando.set(true);
    this.errorCarga.set('');
    this.api
      .datosCurso()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (datos) => {
          this.cargando.set(false);
          this.tipos.set(datos.tipos_curso);
          this.instructores.set(datos.instructores);
        },
        error: (error: unknown) => {
          this.cargando.set(false);
          this.errorCarga.set(leerErrorApi(error).mensaje);
        },
      });
  }
  /** Al elegir el tipo se precarga su nombre; el usuario puede editarlo después. */
  elegirTipo(id: string): void {
    const tipo = this.tipos().find((t) => String(t.id) === id);
    this.tipoElegido.set(id);
    this.formulario.patchValue({ tipo_curso_id: id, nombre_curso: tipo?.nombre ?? '' });
  }
  fechasInvalidas(): boolean {
    const { fecha_inicio, fecha_fin } = this.formulario.getRawValue();
    return !!fecha_inicio && !!fecha_fin && fecha_fin < fecha_inicio;
  }
  valor(): DatosCursoImportacion | null {
    const datos = this.formulario.getRawValue();
    if (this.formulario.invalid || this.fechasInvalidas() || !datos.nombre_curso.trim())
      return null;
    return {
      tipo_curso_id: Number(datos.tipo_curso_id),
      nombre_curso: datos.nombre_curso.trim(),
      comandante_id: Number(datos.comandante_id),
      fecha_inicio: datos.fecha_inicio,
      fecha_fin: datos.fecha_fin,
      estado_curso: datos.estado_curso,
      observacion_curso: datos.observacion_curso.trim(),
    };
  }
}
