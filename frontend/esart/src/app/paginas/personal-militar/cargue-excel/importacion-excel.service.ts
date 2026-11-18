import { inject, Injectable } from '@angular/core';
import { ClienteApiService } from '../../../nucleo/servicios/cliente-api.service';
import { DatosCursoImportacion, DatosFormularioCurso, ResultadoImportacion } from './excel-modelos';
import { UnidadExcel } from './excel-normalizacion';

@Injectable({ providedIn: 'root' })
export class ImportacionExcelService {
  private readonly api = inject(ClienteApiService);
  unidades() {
    return this.api.obtener<UnidadExcel[]>('/catalogos/unidades');
  }
  datosCurso() {
    return this.api.obtener<DatosFormularioCurso>('/importaciones/datos-curso');
  }
  importar(archivo: File, hoja: string, curso: DatosCursoImportacion, codigoTotp = '') {
    const datos = new FormData();
    datos.append('archivo', archivo);
    datos.append('hoja', hoja);
    for (const [campo, valor] of Object.entries(curso)) datos.append(campo, String(valor));
    if (codigoTotp) datos.append('codigo_totp', codigoTotp);
    // Contrato existente §5: multipart, sin fijar Content-Type para conservar el boundary.
    return this.api.enviar<ResultadoImportacion>('/importaciones/excel', datos);
  }
}
