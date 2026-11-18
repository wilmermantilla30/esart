import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { PanelEstadisticas, Semestre } from '../modelos/estadisticas';
import { ClienteApiService } from './cliente-api.service';

/** Estadísticas del panel principal (componente DASHBOARD). */
@Injectable({ providedIn: 'root' })
export class EstadisticasService {
  private readonly api = inject(ClienteApiService);

  /** Sin año ni semestre: todo el histórico. */
  panel(anio: number | null, semestre: Semestre | null): Observable<PanelEstadisticas> {
    return this.api.obtener<PanelEstadisticas>('/estadisticas/panel', {}, { anio, semestre });
  }
}
