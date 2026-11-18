import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  CursosDelInstructor,
  DatosInstructor,
  Especialidad,
  EstadoInstructores,
  Instructor,
  MilitarParaInstructor,
  NuevoInstructor,
} from '../modelos/instructores';
import { ClienteApiService, PREFIJO_API } from './cliente-api.service';

/** Dirección de la foto; la versión evita que el navegador muestre una foto anterior. */
export function urlFotoInstructor(instructor: Pick<Instructor, 'id' | 'version'>): string {
  return `${PREFIJO_API}/instructores/${instructor.id}/foto?v=${encodeURIComponent(instructor.version)}`;
}

/** Iniciales para el avatar cuando no hay foto (máximo dos letras). */
export function inicialesInstructor(instructor: Pick<Instructor, 'nombres' | 'apellidos'>): string {
  const primera = (texto: string | null) => (texto ?? '').trim().charAt(0).toUpperCase();
  return `${primera(instructor.nombres)}${primera(instructor.apellidos)}` || '?';
}

/** Panel de instructores de la Escuela (componente INSTRUCTORES). */
@Injectable({ providedIn: 'root' })
export class InstructoresService {
  private readonly api = inject(ClienteApiService);

  listar(
    texto: string,
    especialidad: string,
    estado: EstadoInstructores,
  ): Observable<Instructor[]> {
    return this.api.obtener<Instructor[]>('/instructores', {}, { texto, especialidad, estado });
  }

  especialidades(): Observable<Especialidad[]> {
    return this.api.obtener<Especialidad[]>('/instructores/especialidades');
  }

  buscarMilitar(cedula: string): Observable<MilitarParaInstructor> {
    return this.api.obtener<MilitarParaInstructor>(
      `/instructores/militar/${encodeURIComponent(cedula)}`,
    );
  }

  registrar(nuevo: NuevoInstructor): Observable<Instructor> {
    return this.api.enviar<Instructor>('/instructores', nuevo);
  }

  actualizar(id: number, datos: DatosInstructor): Observable<Instructor> {
    return this.api.reemplazar<Instructor>(`/instructores/${id}`, datos);
  }

  /** Multipart: sin fijar Content-Type para que el navegador ponga el boundary. */
  cambiarFoto(id: number, foto: File): Observable<Instructor> {
    const datos = new FormData();
    datos.append('archivo', foto);
    return this.api.reemplazar<Instructor>(`/instructores/${id}/foto`, datos);
  }

  quitarFoto(id: number): Observable<Instructor> {
    return this.api.eliminar<Instructor>(`/instructores/${id}/foto`);
  }

  /** Cursos donde es comandante y donde participa con otro rol. */
  cursos(id: number): Observable<CursosDelInstructor> {
    return this.api.obtener<CursosDelInstructor>(`/instructores/${id}/cursos`);
  }

  cambiarEstado(id: number, activo: boolean): Observable<Instructor> {
    return this.api.enviar<Instructor>(`/instructores/${id}/${activo ? 'activar' : 'desactivar'}`);
  }
}
