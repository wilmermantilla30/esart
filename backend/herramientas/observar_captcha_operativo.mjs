// Diagnóstico DOM del entorno local autorizado. No intercepta ni simula HTTP.
import fs from 'node:fs';
import {createHash} from 'node:crypto';
const manifest=JSON.parse(fs.readFileSync('respaldos/captcha_local_actual.json','utf8'));
const accion=process.argv[2];
const tabs=await(await fetch(`http://127.0.0.1:${manifest.puerto}/json`)).json();
const tab=tabs.find(t=>t.type==='page');
const ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let id=0;const pendientes=new Map(),respuestas=[],envios=[];
ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.id){pendientes.get(d.id)?.(d);pendientes.delete(d.id);}
 if(d.method==='Network.responseReceived')respuestas.push(d.params);
 if(d.method==='Network.requestWillBeSent' && d.params.request.url.endsWith('/api/auth/login')){
  const datos=JSON.parse(d.params.request.postData||'{}');
  if(datos.nombre_usuario!=='prueba.seguridad')throw Error('Cuenta no autorizada');
  envios.push({usuario_correcto:true,contrasena_controlada:datos.contrasena==='Incorrecta-Controlada-ESART-2026!',
    captcha_enviado:!!datos.captcha_id,solucion_longitud:datos.captcha_respuesta?.length||0});
 }};
const call=(method,params={})=>new Promise(r=>{pendientes.set(++id,r);ws.send(JSON.stringify({id,method,params}));});
async function dom(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(r.error||r.result?.exceptionDetails)throw Error('Error DOM');return r.result.result.value;}
async function esperar(f){for(let n=0;n<150;n++){if(await f())return;await new Promise(r=>setTimeout(r,100));}throw Error('Tiempo agotado');}
async function cuerpo(r){for(let n=0;n<50;n++){const v=await call('Network.getResponseBody',{requestId:r.requestId});if(!v.error)return JSON.parse(v.result.body);await new Promise(r=>setTimeout(r,100));}throw Error('Sin respuesta');}
async function escribir(selector,valor){await dom(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled)throw Error('Control no disponible');e.value=${JSON.stringify(valor)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
try{
 await call('Network.enable');await call('Page.enable');
 await call('Emulation.setDeviceMetricsOverride',{width:1280,height:1200,deviceScaleFactor:1,mobile:false});
 if(accion==='abrir'){
  await call('Page.navigate',{url:'http://localhost:4200/inicio-sesion'});
  await esperar(()=>dom(`!!document.querySelector('#nombre-usuario')`));
  await escribir('#nombre-usuario','prueba.seguridad');
 } else if(accion==='enviar'){
  if(await dom(`document.querySelector('#nombre-usuario')?.value.trim()`)!=='prueba.seguridad')throw Error('Cuenta no autorizada; no enviar');
  const modal=await dom(`!!document.querySelector('app-captcha')`);
  await escribir(modal?'#captcha-contrasena':'#contrasena','Incorrecta-Controlada-ESART-2026!');
  if(modal){
   if(!process.argv[3]||!/^[A-Z0-9]{6}$/.test(process.argv[3]))throw Error('Indique solución visible de seis caracteres');
   await escribir('#codigo-captcha',process.argv[3]);
   await dom(`(()=>{const c=document.querySelector('app-captcha input[type="checkbox"]');if(!c.checked)c.click()})()`);
  }
  await esperar(()=>dom(modal?`(()=>{const b=[...document.querySelectorAll('app-captcha button')].find(e=>e.textContent.includes('Validar e Ingresar'));return b&&!b.disabled})()`:`!document.querySelector('button[type="submit"]').disabled`));
  await dom(modal?`[...document.querySelectorAll('app-captcha button')].find(e=>e.textContent.includes('Validar e Ingresar')).click()`:`document.querySelector('button[type="submit"]').click()`);
  await esperar(()=>Promise.resolve(respuestas.some(r=>r.response.url.endsWith('/api/auth/login'))));
  const r=respuestas.find(r=>r.response.url.endsWith('/api/auth/login'));const b=await cuerpo(r);
  const detalle=b.error?.detalle||{};
  console.log(JSON.stringify({http:r.response.status,codigo:b.error?.codigo,captcha_validado:detalle.captcha_validado,
   captcha_requerido:detalle.captcha_requerido,bloqueado_hasta:detalle.bloqueado_hasta,
   segundos_restantes:detalle.segundos_restantes,envios}));
  await new Promise(r=>setTimeout(r,1200));
 } else if(accion==='recargar'){
  await call('Page.reload',{ignoreCache:true});
  await esperar(()=>dom(`!!document.querySelector('app-ventana-bloqueo')`));
 } else if(accion==='cerrar'){
  await call('Browser.close');process.exit(0);
 } else if(accion!=='observar')throw Error('Acción no permitida');
 const estado=await dom(`({captcha:!!document.querySelector('app-captcha'),bloqueo:!!document.querySelector('app-ventana-bloqueo'),totp:!!document.querySelector('app-totp'),png:document.querySelector('app-captcha img[width="312"]')?.src,ancho:document.querySelector('app-captcha img[width="312"]')?.naturalWidth,mensaje:document.querySelector('app-captcha [role="status"]')?.textContent})`);
 if(estado.png?.startsWith('data:image/png;base64,')){
  fs.writeFileSync(manifest.carpeta+'/desafio_visible.png',Buffer.from(estado.png.split(',')[1],'base64'));
  estado.imagen_sha256=createHash('sha256').update(estado.png).digest('hex');
 }delete estado.png;
 const foto=await call('Page.captureScreenshot');
 fs.writeFileSync(manifest.carpeta+'/pantalla_actual.png',Buffer.from(foto.result.data,'base64'));
 console.log(JSON.stringify({interfaz:estado}));
}finally{ws.close();}
