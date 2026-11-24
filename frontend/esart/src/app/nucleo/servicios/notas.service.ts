import { HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { EntregaDeMateria, MisMaterias } from '../modelos/notas';
import { ClienteApiService } from './cliente-api.service';
import { ArchivoDescargado, nombreDesdeCabecera } from './parametros.service';

/** Carga de notas del instructor (S2-12): sus materias, la plantilla y la entrega. */
@Injectable({ providedIn: 'root' })
export class NotasService {
  private readonly api = inject(ClienteApiService);

  misMaterias(): Observable<MisMaterias> {
    return this.api.obtener<MisMaterias>('/notas/mis-materias');
  }

  descargarPlantilla(cursoId: number, mallaId: number): Observable<ArchivoDescargado> {
    return this.api.descargarArchivo(`/notas/plantilla/${cursoId}/${mallaId}`).pipe(
      map((respuesta: HttpResponse<Blob>) => ({
        nombre: nombreDesdeCabecera(respuesta.headers.get('Content-Disposition'), 'Notas.xlsx'),
        contenido: respuesta.body ?? new Blob(),
      })),
    );
  }

  entrega(cursoId: number, mallaId: number): Observable<EntregaDeMateria> {
    return this.api.obtener<EntregaDeMateria>(`/notas/entregas/${cursoId}/${mallaId}`);
  }

  /** Sube la planilla llena. Queda EN_REVISION hasta que el Inspector la apruebe. */
  subir(cursoId: number, mallaId: number, archivo: File): Observable<EntregaDeMateria> {
    const datos = new FormData();
    datos.append('archivo', archivo);
    // Multipart: sin fijar Content-Type para que el navegador ponga el boundary.
    return this.api.enviar<EntregaDeMateria>(`/notas/entregas/${cursoId}/${mallaId}`, datos);
  }
}
