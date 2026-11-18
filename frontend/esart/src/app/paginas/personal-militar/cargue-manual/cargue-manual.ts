import { Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { leerErrorApi } from '../../../nucleo/modelos/error-api';
import {
  Genero,
  NuevoPersonal,
  OpcionCategoria,
  OpcionUnidad,
  PersonalRegistrado,
} from '../../../nucleo/modelos/personal';
import { RegistroPersonalService } from '../../../nucleo/servicios/registro-personal.service';
import { SesionService } from '../../../nucleo/servicios/sesion.service';

/** Cédula: solo dígitos, 5 a 15 (misma regla del backend). */
const PATRON_CEDULA = /^\d{5,15}$/;
/** Unidad que se preselecciona si existe (Escuela de Artillería). */
const CODIGO_UNIDAD_POR_DEFECTO = 'ESART';
/** Ruta del panel del módulo, a donde lleva "Cancelar". */
const RUTA_PANEL = '/personal';

/**
 * Registro manual de un efectivo en esart.personal_militar (componente PERSONAL_CARGUE_MANUAL).
 *
 * - Grado y categoría vienen del backend: al elegir un grado se fija su categoría y, si se cambia
 *   la categoría, se borra un grado que no le corresponda.
 * - Tras guardar muestra el resumen y dos accesos: "Registrar como instructor" y "Crear usuario".
 *   Cada uno aparece solo si el usuario tiene la operación "crear" en INSTRUCTORES / USUARIOS;
 *   las rutas destino tienen su guarda y el backend vuelve a verificar cada petición.
 */
@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-cargue-manual',
  styleUrl: './cargue-manual.css',
  templateUrl: './cargue-manual.html',
})
export class CargueManual {
  private readonly api = inject(RegistroPersonalService);
  private readonly sesion = inject(SesionService);
  private readonly enrutador = inject(Router);
  private readonly destruir = inject(DestroyRef);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly categorias = signal<OpcionCategoria[]>([]);
  protected readonly unidades = signal<OpcionUnidad[]>([]);
  protected readonly cargando = signal(true);
  protected readonly errorCarga = signal('');
  protected readonly guardando = signal(false);
  protected readonly errorGuardar = signal('');
  /** Último efectivo registrado: mientras exista se muestra el resumen con los accesos. */
  protected readonly registrado = signal<PersonalRegistrado | null>(null);

  /** Accesos posteriores al registro, según la malla de permisos del usuario. */
  protected readonly puedeInstructores = computed(() => this.sesion.puede('INSTRUCTORES', 'crear'));
  protected readonly puedeUsuarios = computed(() => this.sesion.puede('USUARIOS', 'crear'));

  protected readonly formulario = this.fb.group({
    documento_identidad: ['', [Validators.required, Validators.pattern(PATRON_CEDULA)]],
    nombres: ['', [Validators.required, Validators.maxLength(150)]],
    apellidos: ['', [Validators.required, Validators.maxLength(150)]],
    grado: ['', Validators.required],
    genero: ['' as Genero | '', Validators.required],
    categoria: ['', Validators.required],
    unidad_actual_id: [''],
    especialidad_actual: ['', Validators.maxLength(100)],
    activo: [true],
  });

  constructor() {
    this.cargarOpciones();
  }

  /** Pide categorías, grados y unidades; preselecciona la Escuela de Artillería. */
  protected cargarOpciones(): void {
    this.cargando.set(true);
    this.errorCarga.set('');
    this.api
      .opciones()
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (opciones) => {
          this.categorias.set(opciones.categorias);
          this.unidades.set(opciones.unidades);
          this.preseleccionarUnidad();
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.errorCarga.set(leerErrorApi(error).mensaje);
          this.cargando.set(false);
        },
      });
  }

  /** Al elegir un grado se fija la categoría a la que pertenece. */
  protected elegirGrado(sigla: string): void {
    const categoria = this.categorias().find((c) => c.grados.some((g) => g.codigo === sigla));
    if (categoria) this.formulario.controls.categoria.setValue(categoria.codigo);
  }

  /** Si la nueva categoría no incluye el grado elegido, el grado se borra. */
  protected elegirCategoria(codigo: string): void {
    const categoria = this.categorias().find((c) => c.codigo === codigo);
    const grado = this.formulario.controls.grado.value;
    if (grado && !categoria?.grados.some((g) => g.codigo === grado)) {
      this.formulario.controls.grado.setValue('');
    }
  }

  /** Muestra el error de un campo solo después de que el usuario lo tocó. */
  protected invalido(campo: keyof typeof this.formulario.controls): boolean {
    const control = this.formulario.controls[campo];
    return control.invalid && (control.touched || control.dirty);
  }

  protected guardar(): void {
    if (this.guardando()) return;
    if (this.formulario.invalid) {
      this.formulario.markAllAsTouched();
      return;
    }
    this.guardando.set(true);
    this.errorGuardar.set('');
    this.api
      .registrar(this.solicitud())
      .pipe(takeUntilDestroyed(this.destruir))
      .subscribe({
        next: (registro) => {
          this.guardando.set(false);
          this.registrado.set(registro);
        },
        error: (error: unknown) => {
          this.guardando.set(false);
          this.errorGuardar.set(leerErrorApi(error).mensaje);
        },
      });
  }

  /** Limpia el formulario para registrar otro efectivo. */
  protected registrarOtro(): void {
    this.registrado.set(null);
    this.errorGuardar.set('');
    this.formulario.reset();
    this.preseleccionarUnidad();
  }

  protected cancelar(): void {
    void this.enrutador.navigateByUrl(RUTA_PANEL);
  }

  /** Cuerpo del POST: textos sin espacios sobrantes; opcionales vacíos como null. */
  private solicitud(): NuevoPersonal {
    const v = this.formulario.getRawValue();
    const limpiar = (texto: string) => texto.split(/\s+/).filter(Boolean).join(' ');
    return {
      documento_identidad: v.documento_identidad.replace(/[\s.-]/g, ''),
      nombres: limpiar(v.nombres),
      apellidos: limpiar(v.apellidos),
      grado: v.grado,
      genero: v.genero as Genero,
      categoria: v.categoria,
      unidad_actual_id: v.unidad_actual_id ? Number(v.unidad_actual_id) : null,
      especialidad_actual: limpiar(v.especialidad_actual) || null,
      activo: v.activo,
    };
  }

  private preseleccionarUnidad(): void {
    const escuela = this.unidades().find((u) => u.codigo === CODIGO_UNIDAD_POR_DEFECTO);
    if (escuela) this.formulario.controls.unidad_actual_id.setValue(String(escuela.id));
  }
}
