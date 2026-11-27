import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  CursoListado,
  DetalleCurso,
  FiltrosCursos,
  InstructorDisponible,
  ResultadosCurso,
} from '../modelos/cursos';
import { ClienteApiService } from './cliente-api.service';

/** Módulo Cursos (S2-02): lista, detalle e instructor titular de cada materia; resultados (S2-15). */
@Injectable({ providedIn: 'root' })
export class CursosService {
  private readonly api = inject(ClienteApiService);

  listar(filtros: FiltrosCursos): Observable<CursoListado[]> {
    return this.api.obtener<CursoListado[]>(
      '/cursos',
      {},
      {
        estado: filtros.estado,
        tipo: filtros.tipo,
        texto: filtros.texto.trim(),
      },
    );
  }

  detalle(cursoId: number): Observable<DetalleCurso> {
    return this.api.obtener<DetalleCurso>(`/cursos/${cursoId}`);
  }

  instructoresDisponibles(): Observable<InstructorDisponible[]> {
    return this.api.obtener<InstructorDisponible[]>('/cursos/instructores-disponibles');
  }

  /** Pone, cambia o quita (null) el instructor titular de una materia del curso. */
  asignarInstructor(
    cursoId: number,
    mallaId: number,
    instructorId: number | null,
  ): Observable<DetalleCurso> {
    return this.api.reemplazar<DetalleCurso>(`/cursos/${cursoId}/materias/${mallaId}/instructor`, {
      instructor_id: instructorId,
    });
  }

  /** Liga la malla vigente de su tipo a un curso en curso que se creó sin malla. */
  asignarMallaVigente(cursoId: number): Observable<DetalleCurso> {
    return this.api.enviar<DetalleCurso>(`/cursos/${cursoId}/malla`);
  }

  /** Nota final y puesto: guardados si el curso se cerró, si no provisionales. */
  resultados(cursoId: number): Observable<ResultadosCurso> {
    return this.api.obtener<ResultadosCurso>(`/cursos/${cursoId}/resultados`);
  }

  /** Cierra el curso. Sin código responde TOTP_REQUERIDO. */
  cerrar(cursoId: number, codigoTotp = ''): Observable<ResultadosCurso> {
    return this.api.enviar<ResultadosCurso>(`/cursos/${cursoId}/cerrar`, {
      codigo_totp: codigoTotp,
    });
  }
}
