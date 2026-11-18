import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { InsigniaEstado } from '../../../compartido/insignia-estado/insignia-estado';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import { FiltroEstado, PaginaHabilitacion } from '../../../nucleo/modelos/verificacion';
import { VerificacionService } from '../../../nucleo/servicios/verificacion.service';
import { PARAMETRO_CEDULA } from '../verificar-artillero/verificar-artillero';

/** Filas por página del listado (el backend admite hasta 200). */
const TAMANO_PAGINA = 25;

/** Opciones del filtro de estado (el valor es el que entiende el backend). */
const OPCIONES_ESTADO: ReadonlyArray<{ valor: FiltroEstado; texto: string }> = [
  { valor: '', texto: 'Todos' },
  { valor: 'APTO', texto: 'APTO' },
  { valor: 'NO_APTO', texto: 'NO APTO' },
  { valor: 'POR_VENCER', texto: 'Reentrenamiento por vencer' },
];

/**
 * Habilitados (componente PERSONAL_HABILITADOS): listado de artilleros con su estado,
 * filtros por estado y texto, y acceso al detalle de cada uno.
 */
@Component({
  selector: 'esart-habilitados',
  imports: [FormsModule, RouterLink, InsigniaEstado],
  templateUrl: './habilitados.html',
})
export class Habilitados {
  private readonly verificacion = inject(VerificacionService);

  protected readonly opcionesEstado = OPCIONES_ESTADO;
  protected readonly parametroCedula = PARAMETRO_CEDULA;

  protected estado: FiltroEstado = '';
  protected texto = '';
  protected readonly pagina = signal(1);

  protected readonly cargando = signal(false);
  protected readonly datos = signal<PaginaHabilitacion | null>(null);
  protected readonly error = signal<ErrorApi | null>(null);

  constructor() {
    this.verificacion.personalActualizado$
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.cargar());
    // Se puede llegar con el filtro ya puesto, por ejemplo desde el panel (?estado=POR_VENCER).
    const estadoInicial = inject(ActivatedRoute).snapshot.queryParamMap.get(
      'estado',
    ) as FiltroEstado | null;
    if (estadoInicial && OPCIONES_ESTADO.some((opcion) => opcion.valor === estadoInicial)) {
      this.estado = estadoInicial;
    }
    this.cargar();
  }

  /** Aplica los filtros desde la primera página. */
  protected buscar(): void {
    this.pagina.set(1);
    this.cargar();
  }

  protected limpiarFiltros(): void {
    this.estado = '';
    this.texto = '';
    this.buscar();
  }

  protected irAPagina(pagina: number): void {
    this.pagina.set(pagina);
    this.cargar();
  }

  private cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.verificacion
      .listarHabilitacion({
        estado: this.estado,
        texto: this.texto,
        pagina: this.pagina(),
        tamano_pagina: TAMANO_PAGINA,
      })
      .subscribe({
        next: (respuesta) => {
          this.datos.set(respuesta);
          this.cargando.set(false);
        },
        error: (error: unknown) => {
          this.error.set(leerErrorApi(error));
          this.cargando.set(false);
        },
      });
  }

  /** Fecha AAAA-MM-DD en formato legible, sin desfase por zona horaria. */
  protected fecha(valor: string | null): string {
    if (!valor) {
      return '—';
    }
    const [anio, mes, dia] = valor.split('-').map(Number);
    return new Date(anio!, mes! - 1, dia!).toLocaleDateString('es-CO', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  }
}
