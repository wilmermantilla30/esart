import { HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  FormatoPlantilla,
  NuevaPlantilla,
  ParametrosSeguridad,
  Plantilla,
  ReglaHabilitacion,
  SimulacionRegla,
  ValoresRegla,
} from '../modelos/parametros';
import { ClienteApiService } from './cliente-api.service';

/** Archivo descargado, listo para entregarlo al navegador. */
export interface ArchivoDescargado {
  nombre: string;
  contenido: Blob;
}

/**
 * Nombre del archivo desde Content-Disposition. El backend lo envía como
 * filename*=UTF-8''<nombre codificado> (RFC 5987); si no viene, se usa el de respaldo.
 */
export function nombreDesdeCabecera(cabecera: string | null, respaldo: string): string {
  const coincidencia = cabecera?.match(/filename\*=UTF-8''([^;]+)/i);
  if (!coincidencia) return respaldo;
  try {
    return decodeURIComponent(coincidencia[1]);
  } catch {
    return respaldo;
  }
}

/** Panel de Parámetros: regla de habilitación, plantillas y seguridad (solo consulta). */
@Injectable({ providedIn: 'root' })
export class ParametrosService {
  private readonly api = inject(ClienteApiService);

  // --- Cursos y Capacitaciones: regla APTO / NO APTO ---

  obtenerRegla(): Observable<ReglaHabilitacion> {
    return this.api.obtener<ReglaHabilitacion>('/parametros/habilitacion');
  }

  /** Qué pasaría con la propuesta, sin guardar nada. */
  simularRegla(valores: ValoresRegla): Observable<SimulacionRegla> {
    return this.api.enviar<SimulacionRegla>('/parametros/habilitacion/simular', valores);
  }

  /** Guarda la regla. Sin código responde 409 TOTP_REQUERIDO y se reintenta con él. */
  guardarRegla(
    valores: ValoresRegla,
    version: string | null,
    codigoTotp = '',
  ): Observable<ReglaHabilitacion> {
    return this.api.reemplazar<ReglaHabilitacion>('/parametros/habilitacion', {
      ...valores,
      version,
      codigo_totp: codigoTotp,
    });
  }

  // --- Plantillas y Formatos ---

  listarPlantillas(formato: FormatoPlantilla | null = null): Observable<Plantilla[]> {
    return this.api.obtener<Plantilla[]>('/parametros/plantillas', {}, { formato });
  }

  publicarPlantilla(nueva: NuevaPlantilla): Observable<Plantilla> {
    const datos = new FormData();
    datos.append('archivo', nueva.archivo);
    datos.append('nombre_oficial', nueva.nombre_oficial);
    datos.append('version', nueva.version);
    datos.append('descripcion', nueva.descripcion);
    // Multipart: sin fijar Content-Type para que el navegador ponga el boundary.
    return this.api.enviar<Plantilla>('/parametros/plantillas', datos);
  }

  descargarPlantilla(plantilla: Plantilla): Observable<ArchivoDescargado> {
    return this.api.descargarArchivo(`/parametros/plantillas/${plantilla.id}/descarga`).pipe(
      map((respuesta: HttpResponse<Blob>) => ({
        nombre: nombreDesdeCabecera(
          respuesta.headers.get('Content-Disposition'),
          plantilla.nombre_archivo,
        ),
        contenido: respuesta.body ?? new Blob(),
      })),
    );
  }

  retirarPlantilla(id: number): Observable<void> {
    return this.api.enviar<void>(`/parametros/plantillas/${id}/retirar`);
  }

  // --- Parámetros de Seguridad (solo consulta) ---

  obtenerSeguridad(): Observable<ParametrosSeguridad> {
    return this.api.obtener<ParametrosSeguridad>('/parametros/seguridad');
  }
}
