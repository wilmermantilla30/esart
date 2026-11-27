import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { SesionService } from '../../../nucleo/servicios/sesion.service';
import { MallasCurricularesPestana } from './mallas-curriculares/mallas-curriculares';
import { NotaMinimaTarjeta } from './nota-minima/nota-minima';
import { ParametrosSeguridadPestana } from './parametros-seguridad/parametros-seguridad';
import { PlantillasFormatosPestana } from './plantillas-formatos/plantillas-formatos';
import { ReglaHabilitacionPestana } from './regla-habilitacion/regla-habilitacion';

export type PestanaParametros = 'seguridad' | 'cursos' | 'mallas' | 'plantillas';

export interface OpcionPestana {
  valor: PestanaParametros;
  texto: string;
  icono: string;
  titulo: string;
  /** Componente de la malla de permisos que da acceso a la pestaña. */
  componente: string;
}

export const PESTANAS: ReadonlyArray<OpcionPestana> = [
  {
    valor: 'seguridad',
    texto: 'Parámetros de Seguridad',
    icono: 'verified_user',
    titulo: 'Parámetros de Seguridad del Sistema',
    componente: 'PARAMETROS_HABILITACION',
  },
  {
    valor: 'cursos',
    texto: 'Cursos y Capacitaciones',
    icono: 'school',
    titulo: 'Cursos y Capacitaciones — Regla de habilitación y nota mínima',
    componente: 'PARAMETROS_HABILITACION',
  },
  {
    valor: 'mallas',
    texto: 'Mallas curriculares',
    icono: 'menu_book',
    titulo: 'Mallas curriculares por tipo de curso',
    componente: 'MALLAS_CURRICULARES',
  },
  {
    valor: 'plantillas',
    texto: 'Plantillas y Formatos',
    icono: 'file_copy',
    titulo: 'Plantillas y Formatos Institucionales',
    componente: 'PARAMETROS_HABILITACION',
  },
];

/** Pestaña preferida si la dirección no trae una válida (?pestana=...) y el usuario puede verla. */
const PESTANA_INICIAL: PestanaParametros = 'plantillas';

/**
 * Pestaña que se abre: la de la dirección si el usuario puede verla; si no, la inicial; si
 * tampoco, la primera que tenga (por ejemplo, solo "Mallas curriculares").
 */
export function pestanaAbierta(
  pedida: string | null,
  visibles: ReadonlyArray<OpcionPestana>,
): PestanaParametros {
  const valores = visibles.map((opcion) => opcion.valor);
  if (valores.includes(pedida as PestanaParametros)) return pedida as PestanaParametros;
  return valores.includes(PESTANA_INICIAL) ? PESTANA_INICIAL : (valores[0] ?? PESTANA_INICIAL);
}

/**
 * Parámetros del sistema, con el diseño de la Escuela:
 * - Parámetros de Seguridad: solo consulta.
 * - Cursos y Capacitaciones: la regla APTO / NO APTO y la nota mínima de aprobación (S2-10).
 * - Mallas curriculares: tipos de curso y versiones de su malla (S2-09).
 * - Plantillas y Formatos: repositorio de documentos institucionales.
 * Cada pestaña se muestra solo si el usuario tiene su componente: quien recibe por excepción
 * MALLAS_CURRICULARES ve únicamente esa. La pestaña elegida queda en la dirección (?pestana=...).
 */
@Component({
  selector: 'esart-parametros',
  imports: [
    MallasCurricularesPestana,
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

  protected readonly pestanas = PESTANAS.filter((opcion) =>
    this.sesion.tienePermiso(opcion.componente),
  );
  protected readonly pestana = signal<PestanaParametros>(
    pestanaAbierta(this.ruta.snapshot.queryParamMap.get('pestana'), this.pestanas),
  );
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
}
