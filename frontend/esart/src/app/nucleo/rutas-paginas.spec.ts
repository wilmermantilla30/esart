import { esRutaInternaSegura } from './rutas-paginas';

describe('esRutaInternaSegura', () => {
  it.each(['/inicio', '/unidades?pagina=2'])('acepta la ruta interna %s', (ruta) => {
    expect(esRutaInternaSegura(ruta)).toBe(true);
  });

  it.each(['//sitio-malicioso.com', '/\\sitio-malicioso.com', 'https://sitio-malicioso.com', 'inicio', '', null])(
    'rechaza %s (evita redirección a otro sitio)',
    (ruta) => {
      expect(esRutaInternaSegura(ruta)).toBe(false);
    },
  );
});
