import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { NuevoPersonal, OpcionesRegistroPersonal, PersonalRegistrado } from '../modelos/personal';
import { ClienteApiService } from './cliente-api.service';

/**
 * Registro manual de un efectivo en personal_militar.
 * El backend exige sesión, CSRF y la operación "crear" de PERSONAL_CARGUE_MANUAL.
 */
@Injectable({ providedIn: 'root' })
export class RegistroPersonalService {
  private readonly api = inject(ClienteApiService);

  /** Categorías con sus grados y unidades activas para los selectores. */
  opciones(): Observable<OpcionesRegistroPersonal> {
    return this.api.obtener<OpcionesRegistroPersonal>('/personal/opciones-registro');
  }

  /** 201 con el registro; 409 DOCUMENTO_EXISTENTE si la cédula ya está registrada. */
  registrar(nuevo: NuevoPersonal): Observable<PersonalRegistrado> {
    return this.api.enviar<PersonalRegistrado>('/personal', nuevo);
  }
}
