import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { InsigniaEstado } from '../../../compartido/insignia-estado/insignia-estado';
import { SolicitudFirma } from './solicitud-firma';
import { ErrorApi, leerErrorApi } from '../../../nucleo/modelos/error-api';
import {
  DOCUMENTOS_ARTILLERO,
  RespuestaVerificacion,
  TipoDocumentoArtillero,
} from '../../../nucleo/modelos/verificacion';
import { VerificacionService } from '../../../nucleo/servicios/verificacion.service';

/** Parámetro de la URL con la cédula a verificar (lo usa el listado de habilitados). */
export const PARAMETRO_CEDULA = 'cedula';

/** Cédula escrita por el usuario: dígitos, con puntos, espacios o guiones opcionales. */
const PATRON_CEDULA = /^[\d.\s-]{5,20}$/;

/**
 * Verificar artillero (componente PERSONAL_VERIFICAR): consulta por cédula y muestra
 * APTO / NO APTO con el detalle de cada criterio, sus cursos y sus reentrenamientos.
 *
 * Desde la ficha se genera un documento PDF (diploma, oficio remisorio o certificación): el
 * backend lo arma con ReportLab mediante su script maestro (aplicacion/reportes/maestro.py).
 */
@Component({
  selector: 'esart-verificar-artillero',
  imports: [ReactiveFormsModule, NgTemplateOutlet, InsigniaEstado, SolicitudFirma],
  templateUrl: './verificar-artillero.html',
})
export class VerificarArtillero {
  private readonly verificacion = inject(VerificacionService);
  private readonly enrutador = inject(Router);
  private readonly rutaActual = inject(ActivatedRoute);

  protected readonly formulario = inject(NonNullableFormBuilder).group({
    cedula: ['', [Validators.required, Validators.pattern(PATRON_CEDULA)]],
  });

  protected readonly consultando = signal(false);
  protected readonly resultado = signal<RespuestaVerificacion | null>(null);
  protected readonly error = signal<ErrorApi | null>(null);

  // --- Generar documento ---
  protected readonly documentos = DOCUMENTOS_ARTILLERO;
  protected readonly tipoDocumento = signal<TipoDocumentoArtillero>('CERTIFICACION');
  protected readonly generando = signal(false);
  protected readonly errorDocumento = signal<string | null>(null);
  /** Cédula tal como se consultó: la del resultado puede venir enmascarada (****1234). */
  protected cedulaConsultada = '';
  /** Ventana "Firmar desde el celular" (solo certificación y oficio remisorio). */
  protected readonly firmandoEnCelular = signal(false);
  protected readonly esFirmable = computed(() =>
    ['CERTIFICACION', 'OFICIO_REMISORIO'].includes(this.tipoDocumento()),
  );

  protected readonly obligatorios = computed(() =>
    (this.resultado()?.criterios ?? []).filter((c) => c.tipo === 'OBLIGATORIO'),
  );
  protected readonly alternativos = computed(() =>
    (this.resultado()?.criterios ?? []).filter((c) => c.tipo === 'ALTERNATIVO'),
  );

  constructor() {
    // Si se llega desde el listado (?cedula=...), se verifica de una vez.
    const cedula = this.rutaActual.snapshot.queryParamMap.get(PARAMETRO_CEDULA);
    if (cedula) {
      this.formulario.controls.cedula.setValue(cedula);
      this.verificar();
    }
  }

  protected campoInvalido(): boolean {
    const campo = this.formulario.controls.cedula;
    return campo.invalid && (campo.touched || campo.dirty);
  }

  protected verificar(): void {
    if (this.consultando()) {
      return;
    }
    if (this.formulario.invalid) {
      this.formulario.markAllAsTouched();
      return;
    }
    const cedula = this.formulario.controls.cedula.value.trim();
    this.cedulaConsultada = cedula;
    this.errorDocumento.set(null);
    this.consultando.set(true);
    this.error.set(null);
    this.resultado.set(null);
    // La cédula queda en la URL para poder recargar o volver a la misma verificación.
    void this.enrutador.navigate([], {
      relativeTo: this.rutaActual,
      queryParams: { [PARAMETRO_CEDULA]: cedula },
      replaceUrl: true,
    });
    this.verificacion.verificarArtillero(cedula).subscribe({
      next: (respuesta) => {
        this.resultado.set(respuesta);
        this.consultando.set(false);
      },
      error: (error: unknown) => {
        this.error.set(leerErrorApi(error));
        this.consultando.set(false);
      },
    });
  }

  protected elegirDocumento(valor: string): void {
    this.tipoDocumento.set(valor as TipoDocumentoArtillero);
    this.errorDocumento.set(null);
  }

  /** Pide el PDF al backend y lo descarga con un enlace temporal en memoria. */
  protected generarDocumento(): void {
    if (this.generando() || !this.resultado() || !this.cedulaConsultada) {
      return;
    }
    this.generando.set(true);
    this.errorDocumento.set(null);
    this.verificacion.generarDocumento(this.cedulaConsultada, this.tipoDocumento()).subscribe({
      next: ({ nombre, contenido }) => {
        const enlace = document.createElement('a');
        enlace.href = URL.createObjectURL(contenido);
        enlace.download = nombre;
        enlace.click();
        URL.revokeObjectURL(enlace.href);
        this.generando.set(false);
      },
      error: (error: unknown) => {
        this.errorDocumento.set(leerErrorApi(error).mensaje);
        this.generando.set(false);
      },
    });
  }

  protected limpiar(): void {
    this.errorDocumento.set(null);
    this.formulario.reset();
    this.resultado.set(null);
    this.error.set(null);
    void this.enrutador.navigate([], { relativeTo: this.rutaActual, queryParams: {}, replaceUrl: true });
  }

  /** Fecha AAAA-MM-DD del backend en formato legible (16-nov-2027), sin desfase por zona horaria. */
  protected fecha(valor: string | null): string {
    if (!valor) {
      return '—';
    }
    const [anio, mes, dia] = valor.slice(0, 10).split('-').map(Number);
    return new Date(anio!, mes! - 1, dia!).toLocaleDateString('es-CO', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  }
}
