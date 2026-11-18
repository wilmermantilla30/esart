// Automatización DOM/CDP: sin interceptar HTTP, inyectar Angular ni resolver CAPTCHA en cliente.
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const tabs = await (await fetch(`http://127.0.0.1:${process.env.ESART_CDP_PUERTO}/json`)).json();
const tab = tabs.find(t => t.type === 'page');
const ws = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise(resolve => { ws.onopen = resolve; });
let id = 0;
const pendientes = new Map();
const respuestas = [];
ws.onmessage = evento => {
  const d = JSON.parse(evento.data);
  if (d.id) { pendientes.get(d.id)?.(d); pendientes.delete(d.id); }
  if (d.method === 'Network.responseReceived') respuestas.push(d.params);
};
const call = (method, params = {}) => new Promise(resolve => {
  pendientes.set(++id, resolve); ws.send(JSON.stringify({ id, method, params }));
});
const evaluar = async expression => {
  const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.error || r.result?.exceptionDetails) throw Error('Falló una operación DOM de la prueba pública');
  return r.result.result.value;
};
const esperar = async (predicado, mensaje) => {
  for (let n = 0; n < 300; n++) {
    if (await predicado()) return;
    await new Promise(r => setTimeout(r, 100));
  }
  throw Error(mensaje);
};
const deRuta = ruta => respuestas.filter(r => new URL(r.response.url).pathname === ruta);
const cuerpo = async entrada => {
  for (let n = 0; n < 100; n++) {
    const r = await call('Network.getResponseBody', { requestId: entrada.requestId });
    if (!r.error) return JSON.parse(r.result.body);
    await new Promise(r => setTimeout(r, 50));
  }
  throw Error('Respuesta HTTP no disponible para verificación');
};
const exigir = (condicion, mensaje) => { if (!condicion) throw Error(mensaje); };
const nombre = process.env.ESART_USUARIO_PUBLICO;
// Lectura SQL del laboratorio: nunca devuelve contraseñas ni credenciales de conexión.
const leerContador = () => Number(execFileSync(
  fileURLToPath(new URL('../.venv/Scripts/python.exe',import.meta.url)), ['-c', `
import asyncio, os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.engine import make_url
async def main():
 u=make_url(os.environ['ESART_SEGURIDAD_TEST_URL'])
 assert u.host=='127.0.0.1' and u.port!=5432
 datos=Path(os.environ['ESART_SEGURIDAD_TEST_DIR']).resolve()
 assert (datos.parent/'ESART_SOLO_PRUEBAS').is_file()
 assert os.environ['ESART_USUARIO_PUBLICO'].startswith('hu06.')
 e=create_async_engine(u,hide_parameters=True,connect_args={'ssl':False})
 try:
  async with e.connect() as c:
   await c.execute(text('SET TRANSACTION READ ONLY'))
   assert await c.scalar(text('SELECT current_database()'))==u.database
   print(await c.scalar(text('SELECT intentos_fallidos_consecutivos FROM esart_ref.usuarios WHERE usuario=:u'),{'u':os.environ['ESART_USUARIO_PUBLICO']}))
 finally: await e.dispose()
asyncio.run(main())
`],{encoding:'utf8',timeout:15000}));
const contadoresSql=[];
try {
  await call('Network.enable');
  await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1400, deviceScaleFactor: 1, mobile: false });
  await call('Page.navigate', { url: process.env.ESART_FRONTEND_PUBLICO + '/inicio-sesion' });
  await esperar(() => evaluar(`!!document.querySelector('#nombre-usuario')`), 'No cargó Angular');
  await evaluar(`(()=>{const i=document.querySelector('#nombre-usuario');i.value=${JSON.stringify(nombre)};i.dispatchEvent(new Event('input',{bubbles:true}))})()`);
  let captchaIncorrectoProbado = false;
  async function enviarCaptcha(codigo) {
    await evaluar(`(()=>{const m=document.querySelector('app-captcha');const p=m.querySelector('#captcha-contrasena');p.value='incorrecta-solo-prueba';p.dispatchEvent(new Event('input',{bubbles:true}));const i=m.querySelector('#codigo-captcha');i.value=${JSON.stringify(codigo)};i.dispatchEvent(new Event('input',{bubbles:true}));const c=m.querySelector('input[type="checkbox"]');if(!c.checked)c.click()})()`);
    await esperar(() => evaluar(`(()=>{const b=[...document.querySelectorAll('app-captcha button')].find(b=>b.textContent.includes('Validar e Ingresar'));return !!b&&!b.disabled})()`), 'Modal no permite enviar');
    await evaluar(`[...document.querySelectorAll('app-captcha button')].find(b=>b.textContent.includes('Validar e Ingresar')).click()`);
  }
  for (let numero = 1; numero <= 7; numero++) {
    if (numero <= 3) {
      await evaluar(`(()=>{const i=document.querySelector('#contrasena');i.value='incorrecta-solo-prueba';i.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('button[type="submit"]').click()})()`);
    } else {
      await esperar(() => evaluar(`!!document.querySelector('app-captcha img[width="312"]')?.naturalWidth`), 'CAPTCHA automatico no visible');
      if (numero === 4) {
        const original = fs.readFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/captcha_efimero.txt','ascii');
        const incorrecto = (original[0] === 'A' ? 'C' : 'A') + original.slice(1);
        const antes = deRuta('/api/auth/login').length;
        await enviarCaptcha(incorrecto);
        await esperar(() => deRuta('/api/auth/login').length > antes, 'No se envio CAPTCHA incorrecto');
        const rechazo = await cuerpo(deRuta('/api/auth/login').at(-1));
        exigir(rechazo.error.codigo === 'CAPTCHA_INVALIDO' && rechazo.error.detalle.captcha_validado === false, 'No rechazo CAPTCHA incorrecto');
        const contador = leerContador(); contadoresSql.push(contador);
        exigir(contador === 3,'CAPTCHA incorrecto cambio contador SQL');
        await esperar(() => evaluar(`!!document.querySelector('app-captcha img[width="312"]')?.naturalWidth&&!document.querySelector('#captcha-contrasena').disabled`), 'No regenero sin cerrar modal');
        captchaIncorrectoProbado = true;
        const fotoCaptcha = await call('Page.captureScreenshot');
        fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/captcha_reintento.png',Buffer.from(fotoCaptcha.result.data,'base64'));
      }
      const codigo = fs.readFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/captcha_efimero.txt','ascii');
      fs.unlinkSync(process.env.ESART_EVIDENCIA_PUBLICA+'/captcha_efimero.txt');
      await enviarCaptcha(codigo);
    }
    const indice = numero - 1 + (numero >= 4 ? 1 : 0);
    await esperar(() => deRuta('/api/auth/login').length > indice, 'No llego respuesta login');
    exigir(deRuta('/api/auth/login')[indice].response.status === (numero === 7 ? 423 : 401), 'Estado inesperado');
    const contador = leerContador();contadoresSql.push(contador);
    exigir(contador === numero,'No persistio contador SQL esperado');
    if(numero >= 3 && numero < 7) {
      await esperar(() => evaluar(`!!document.querySelector('app-captcha img[width="312"]')?.naturalWidth&&!document.querySelector('#captcha-contrasena').disabled`), 'No mantuvo CAPTCHA requerido');
    } else if(numero < 3) {
      await esperar(() => evaluar(`!document.querySelector('button[type="submit"]').disabled`), 'Envio pendiente');
    }
  }
  const bloqueo = await cuerpo(deRuta('/api/auth/login')[7]);
  const detalle = bloqueo.error.detalle;
  exigir(detalle.intentos_fallidos_consecutivos === null, 'Se filtró el contador histórico');
  exigir(detalle.intento_actual?.envios_registrados === 1, 'No llegó el registro del envío actual');
  exigir(detalle.segundos_restantes === 10800, 'Plazo distinto de tres horas');
  exigir(deRuta('/api/auth/captcha').length === 5, 'No se exigió CAPTCHA desde el cuarto');
  await esperar(() => evaluar(`document.querySelector('app-ventana-bloqueo')?.innerText.includes('1 registrado (este envío)')`), 'No se muestran los datos públicos del envío');
  exigir(await evaluar(`document.querySelector('app-ventana-bloqueo').innerText.includes(${JSON.stringify(detalle.intento_actual.direccion_ip_observada)})`), 'No se presenta la IP observada del envío');
  const cookies = await call('Network.getCookies');
  exigir(!cookies.result.cookies.some(c => c.name === 'esart_sesion'), 'La prueba obtuvo una sesión autenticada');
  await new Promise(r => setTimeout(r, 600));
  let foto = await call('Page.captureScreenshot');
  fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA + '/bloqueo.png', Buffer.from(foto.result.data, 'base64'));
  const lecturasAntes = deRuta('/api/auth/bloqueo').length;
  await call('Page.reload', { ignoreCache: true });
  await esperar(() => deRuta('/api/auth/bloqueo').length > lecturasAntes, 'No se recuperó el bloqueo al recargar');
  const recuperado = await cuerpo(deRuta('/api/auth/bloqueo').at(-1));
  exigir(recuperado.bloqueado === true, 'Se perdió el bloqueo');
  exigir(JSON.stringify(recuperado.intento_actual) === JSON.stringify(detalle.intento_actual), 'Cambió la instantánea al recargar');
  exigir(recuperado.bloqueado_hasta === detalle.bloqueado_hasta, 'Cambió el plazo al recargar');
  await esperar(() => evaluar(`document.querySelector('app-ventana-bloqueo')?.innerText.includes('1 registrado (este envío)')`), 'El modal no se restauró');
  exigir(deRuta('/api/auth/login').length === 8, 'Recargar provocó intentos adicionales');
  const ajeno = await evaluar(`fetch('/api/auth/bloqueo?nombre_usuario=otra.cuenta',{headers:{'X-ESART-Usuario':'otra.cuenta'}}).then(r=>r.json())`);
  exigir(ajeno.usuario_intentado === nombre, 'Un nombre del cliente sustituyó el contexto');
  exigir(ajeno.intentos_fallidos_consecutivos === null && ajeno.direccion_ip === null, 'Se filtró historia de cuenta');
  await new Promise(r => setTimeout(r, 600));
  foto = await call('Page.captureScreenshot');
  fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA + '/recarga.png', Buffer.from(foto.result.data, 'base64'));
  await call('Network.clearBrowserCookies');
  const sinCookie = await evaluar(`fetch('/api/auth/bloqueo?nombre_usuario='+encodeURIComponent(${JSON.stringify(nombre)})).then(r=>r.json())`);
  exigir(sinCookie.bloqueado === false && !sinCookie.intento_actual, 'Consulta arbitraria sin comprobante');
  const resultado = { flujo: 'DOM Angular -> proxy -> FastAPI -> PostgreSQL aislado',
    estados_login: deRuta('/api/auth/login').map(r => r.response.status), captcha_emitidos: 5, captcha_automatico: true, captcha_incorrecto_regenerado: captchaIncorrectoProbado,
    sin_sesion_jwt: true, contadores_sql: contadoresSql, bloqueo: detalle, recuperado, sin_cookie: sinCookie,
    sin_intercepcion_http: true, sin_inyeccion_angular: true };
  fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA + '/resultado.json', JSON.stringify(resultado, null, 2));
} catch (error) {
  const diagnostico = {
    rutas: respuestas.map(r=>({ruta:new URL(r.response.url).pathname,estado:r.response.status})).filter(r=>r.ruta.startsWith('/api/')),
    modal: await evaluar(`(()=>{const m=document.querySelector('app-captcha');return {visible:!!m,texto:m?.innerText,passwordDisabled:m?.querySelector('#captcha-contrasena')?.disabled,imagen:!!m?.querySelector('img[width="312"]')?.naturalWidth}})()`),
  };
  fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/diagnostico_fallo.json',JSON.stringify(diagnostico,null,2));
  throw error;
} finally { ws.close(); }
