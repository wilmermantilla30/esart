import { claveValores } from './regla-habilitacion/regla-habilitacion';
import {
  ESTILOS_FORMATO,
  formatoPorNombre,
  tamanoLegible,
} from './plantillas-formatos/plantillas-formatos';

describe('Panel de Parámetros', () => {
  it('reconoce los cuatro formatos admitidos por la extensión', () => {
    expect(formatoPorNombre('Plantilla.XLSX')).toBe('XLSX');
    expect(formatoPorNombre('viejo.xls')).toBe('XLS');
    expect(formatoPorNombre('manual.pdf')).toBe('PDF');
    expect(formatoPorNombre('acta.docx')).toBe('DOCX');
    expect(formatoPorNombre('macro.xlsm')).toBeNull();
    expect(formatoPorNombre('programa.exe')).toBeNull();
    expect(formatoPorNombre('sin_extension')).toBeNull();
  });

  it('muestra el tamaño en B, KB o MB', () => {
    expect(tamanoLegible(512)).toBe('512 B');
    expect(tamanoLegible(46284)).toBe('45,2 KB');
    expect(tamanoLegible(5 * 1024 * 1024)).toBe('5 MB');
  });

  it('cada formato tiene su color: verde Excel, rojo PDF, azul Word', () => {
    expect(ESTILOS_FORMATO.XLSX.tarjeta).toContain('emerald');
    expect(ESTILOS_FORMATO.XLS.tarjeta).toContain('emerald');
    expect(ESTILOS_FORMATO.PDF.tarjeta).toContain('rose');
    expect(ESTILOS_FORMATO.DOCX.tarjeta).toContain('blue');
  });

  it('la simulación vale para la misma regla sin importar el orden de los cursos', () => {
    const base = {
      cursos_habilitantes: ['SACME', 'SACLI'],
      meses_vigencia_reentrenamiento: 12,
      dias_alerta_vencimiento: 60,
      exige_apto_para_disparar: true,
    };
    expect(claveValores(base)).toBe(
      claveValores({ ...base, cursos_habilitantes: ['SACLI', 'SACME'] }),
    );
    expect(claveValores(base)).not.toBe(claveValores({ ...base, dias_alerta_vencimiento: 30 }));
  });
});
