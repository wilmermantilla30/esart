import { HttpErrorResponse } from '@angular/common/http';

import { CODIGO_SIN_CONEXION, leerErrorApi } from './error-api';

describe('leerErrorApi', () => {
  it('lee el formato único de error del contrato', () => {
    const error = new HttpErrorResponse({
      status: 401,
      error: { error: { codigo: 'CREDENCIALES_INVALIDAS', mensaje: 'Usuario o contraseña incorrectos.', detalle: null } },
    });
    expect(leerErrorApi(error)).toEqual({
      codigo: 'CREDENCIALES_INVALIDAS',
      mensaje: 'Usuario o contraseña incorrectos.',
      detalle: null,
      estadoHttp: 401,
    });
  });

  it.each([0, 502, 503, 504])('el estado %s sin cuerpo del contrato se muestra como sin conexión', (estado) => {
    const resultado = leerErrorApi(new HttpErrorResponse({ status: estado, error: 'Bad Gateway' }));
    expect(resultado.codigo).toBe(CODIGO_SIN_CONEXION);
    expect(resultado.mensaje).toContain('No fue posible conectar');
  });

  it('nunca muestra el texto técnico de una respuesta fuera del contrato', () => {
    const resultado = leerErrorApi(new HttpErrorResponse({ status: 500, error: 'Traceback: psycopg error ...' }));
    expect(resultado.codigo).toBe('ERROR_INTERNO');
    expect(resultado.mensaje).not.toContain('Traceback');
  });
});
