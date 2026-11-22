import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { NotaMinimaTarjeta } from './nota-minima/nota-minima';
import { ParametrosSeguridadPestana } from './parametros-seguridad/parametros-seguridad';
import { PlantillasFormatosPestana } from './plantillas-formatos/plantillas-formatos';
import { ReglaHabilitacionPestana } from './regla-habilitacion/regla-habilitacion';

export type PestanaParametros = 'seguridad' | 'cursos' | 'plantillas';

const PESTANAS: ReadonlyArray<{
  valor: PestanaParametros;
  texto: string;
  icono: string;
  titulo: string;
}> = [
  {
    valor: 'seguridad',
    texto: 'Parámetros de Seguridad',
    icono: 'verified_user',
    titulo: 'Parámetros de Seguridad del Sistema',
  },
  {
    valor: 'cursos',
    texto: 'Cursos y Capacitaciones',
    icono: 'school',
    titulo: 'Cursos y Capacitaciones — Regla de habilitación y nota mínima',
  },
  {
    valor: 'plantillas',
    texto: 'Plantillas y Formatos',
    icono: 'file_copy',
    titulo: 'Plantillas y Formatos Institucionales',
  },
];

/** Pestaña inicial si la dirección no trae una válida (?pestana=...). */
const PESTANA_INICIAL: PestanaParametros = 'plantillas';

/**
 * Parámetros del sistema (componente PARAMETROS_HABILITACION), con el diseño de la Escuela:
 * - Parámetros de Seguridad: solo consulta.
 * - Cursos y Capacitaciones: la regla APTO / NO APTO y la nota mínima de aprobación (S2-10).
 * - Plantillas y Formatos: repositorio de documentos institucionales.
 * La pestaña elegida queda en la dirección (?pestana=...) para poder recargar o compartirla.
 */
@Component({
  selector: 'esart-parametros',
  imports: [
    NotaMinimaTarjeta,
    ParametrosSeguridadPestana,
    PlantillasFormatosPestana,
    ReglaHabilitacionPestana,
  ],
  templateUrl: './parametros.html',
})
export class Parametros {
  private readonly enrutador = inject(Router);
  private readonly ruta = inject(ActivatedRoute);
  private readonly sesion = inject(SesionService);

  protected readonly pestanas = PESTANAS;
  protected readonly pestana = signal<PestanaParametros>(this.pestanaDeLaDireccion());
  protected readonly actual = computed(() =>
    PESTANAS.find((opcion) => opcion.valor === this.pestana())!,
  );
  protected readonly cantidadPlantillas = signal<number | null>(null);
  protected readonly puedePublicar = computed(() =>
    this.sesion.puede('PARAMETROS_HABILITACION', 'crear'),
  );

  private readonly plantillas = viewChild(PlantillasFormatosPestana);

  protected cambiar(pestana: PestanaParametros): void {
    this.pestana.set(pestana);
    void this.enrutador.navigate([], {
      relativeTo: this.ruta,
      queryParams: { pestana },
      replaceUrl: true,
    });
  }

  protected subirPlantilla(): void {
    this.plantillas()?.abrirSubida();
  }

  private pestanaDeLaDireccion(): PestanaParametros {
    const valor = this.ruta.snapshot.queryParamMap.get('pestana');
    return PESTANAS.some((opcion) => opcion.valor === valor)
      ? (valor as PestanaParametros)
      : PESTANA_INICIAL;
  }
}
