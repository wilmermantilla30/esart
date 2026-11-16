import { contrasenaValida, generarContrasenaTemporal, revisarContrasena } from './contrasenas';

describe('reglas de contraseña', () => {
  it('rechaza las mismas contraseñas débiles que el backend', () => {
    for (const debil of ['corta1', 'solamenteletras', '1234567890123', 'a1'.repeat(40)]) {
      expect(contrasenaValida(debil)).toBe(false);
    }
    expect(contrasenaValida('ClaveSegura2026')).toBe(true);
  });

  it('marca qué regla falla', () => {
    const reglas = revisarContrasena('soloLetrasLargas');
    expect(reglas[0]!.cumple).toBe(true);
    expect(reglas[1]!.cumple).toBe(false);
  });

  it('la contraseña generada siempre cumple y no se repite', () => {
    const generadas = new Set(Array.from({ length: 50 }, () => generarContrasenaTemporal()));
    expect(generadas.size).toBe(50);
    for (const contrasena of generadas) {
      expect(contrasenaValida(contrasena)).toBe(true);
      expect(contrasena).toHaveLength(12);
      expect(contrasena).not.toMatch(/[01OlI]/);
    }
  });
});
