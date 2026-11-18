// Automatización del usuario de prueba: no intercepta HTTP ni usa métodos privados Angular.
import fs from 'node:fs';
import crypto from 'node:crypto';
let tabs;
for(let n=0;n<50;n++){
  try{tabs=await (await fetch(`http://127.0.0.1:${process.env.ESART_CDP_PUERTO}/json`)).json();if(tabs.some(t=>t.type==='page'))break;}catch{}
  await new Promise(r=>setTimeout(r,100));
}
if(!tabs?.some(t=>t.type==='page'))throw Error('Chrome no publicó una página disponible');
const ws = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise(r => { ws.onopen = r; });
let secuencia = 0; const pendientes = new Map(); const respuestas = [];
ws.onmessage = e => { const d = JSON.parse(e.data);
  if (d.id) { pendientes.get(d.id)?.(d); pendientes.delete(d.id); }
  if (d.method === 'Network.responseReceived') respuestas.push(d.params);
};
const call = (method, params = {}) => new Promise(r => { pendientes.set(++secuencia, r); ws.send(JSON.stringify({id:secuencia,method,params})); });
const dom = async expression => { const r = await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(r.error || r.result?.exceptionDetails) throw Error('Falló una operación DOM TOTP'); return r.result.result.value; };
const esperar = async (fn, mensaje) => { for(let n=0;n<400;n++){if(await fn())return; await new Promise(r=>setTimeout(r,100));}throw Error(mensaje); };
const rutas = ruta => respuestas.filter(r=>new URL(r.response.url).pathname===ruta);
const cuerpo = async r => {for(let n=0;n<100;n++){const b=await call('Network.getResponseBody',{requestId:r.requestId});if(!b.error)return JSON.parse(b.result.body);await new Promise(r=>setTimeout(r,50));}throw Error('Falta respuesta TOTP');};
const exigir = (c,m)=>{if(!c)throw Error(m);};
const escribir = async (selector, valor) => dom(`(()=>{const i=document.querySelector(${JSON.stringify(selector)});i.value=${JSON.stringify(valor)};i.dispatchEvent(new Event('input',{bubbles:true}))})()`);
const pulsar = async texto => {
  await esperar(()=>dom(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.toLowerCase().includes(${JSON.stringify(texto.toLowerCase())}));return !!b&&!b.disabled})()`),'Botón no disponible');
  return dom(`(()=>{[...document.querySelectorAll('button')].find(b=>b.textContent.toLowerCase().includes(${JSON.stringify(texto.toLowerCase())})).click()})()`);
};
const codigoActual = (secreto, futuro=0) => {
  const alfabeto='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits='';
  for(const c of secreto.replace(/=+$/,''))bits+=alfabeto.indexOf(c).toString(2).padStart(5,'0');
  const bytes=[];for(let i=0;i+8<=bits.length;i+=8)bytes.push(parseInt(bits.slice(i,i+8),2));
  const contador=Buffer.alloc(8);contador.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)+futuro));
  const hash=crypto.createHmac('sha1',Buffer.from(bytes)).update(contador).digest();
  return String((hash.readUInt32BE(hash[19]&15)&0x7fffffff)%1000000).padStart(6,'0');
};
const ingresarCodigo = async codigo => {for(let i=0;i<6;i++)await escribir(`#totp-${i}`,codigo[i]);};
const captura = async nombre => {await new Promise(r=>setTimeout(r,500));const r=await call('Page.captureScreenshot');fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/'+nombre,Buffer.from(r.result.data,'base64'));};
const url=process.env.ESART_FRONTEND_PUBLICO;
const sinCookieSesion=async()=>{const r=await call('Network.getCookies',{urls:[url+'/api/auth/yo']});return !(r.result.cookies??[]).some(c=>c.name==='esart_sesion');};
const progreso = datos => fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/progreso.json',JSON.stringify(datos,null,2));
const esperarManual = async fn => { for(let n=0;n<6000;n++){if(await fn())return;await new Promise(r=>setTimeout(r,100));}throw Error('Se agotó el tiempo de validación manual del CAPTCHA'); };
try {
  await call('Network.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1280,height:1100,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:url+'/inicio-sesion'});
  await esperar(()=>dom(`!!document.querySelector('#nombre-usuario')`),'No cargó login');
  await escribir('#nombre-usuario',process.env.ESART_USUARIO_PUBLICO);
  let secreto;
  if(process.env.ESART_ESCENARIO_TOTP==='totp'){
    await escribir('#contrasena',process.env.ESART_CREDENCIAL_PRUEBA);await pulsar('Acceder al Sistema ESART');
    await esperar(()=>rutas('/api/auth/login').length===1,'No llegó login inicial');
    exigir(rutas('/api/auth/login')[0].response.status===202,'Se emitió sesión antes de vincular');
    exigir(await sinCookieSesion(),'Se emitió JWT antes de vincular el autenticador');
    await esperar(()=>rutas('/api/auth/totp/login/configurar').length===1,'No llegó configuración');
    exigir(await dom(`fetch('/api/auth/yo').then(r=>r.status)`)===401,'Hubo sesión antes de vincular');
    const configuracion=await cuerpo(rutas('/api/auth/totp/login/configurar')[0]);
    exigir(rutas('/api/auth/totp/login/configurar')[0].response.status===200,'Prueba de identidad rechazada');
    secreto=new URL(configuracion.uri).searchParams.get('secret');
    await esperar(()=>dom(`document.querySelector('.totp-qr')?.naturalWidth===240`),'QR local no se generó');
    await ingresarCodigo(codigoActual(secreto));await pulsar('VERIFICAR Y ACTIVAR');
    await esperar(()=>rutas('/api/auth/totp/login/vincular').length===1,'No se confirmó factor');
    exigir(rutas('/api/auth/totp/login/vincular')[0].response.status===200,'Código de vinculación rechazado');
    await esperar(()=>dom(`document.body.innerText.includes('Autenticador activado')&&!document.querySelector('.totp-qr')`),'QR no se retiró al activar');
    await pulsar('He guardado los códigos');
    await captura('activado.png');
    const estado=await dom(`fetch('/api/auth/totp/estado').then(r=>r.json())`);
    exigir(estado.activo===true&&!('uri'in estado)&&!('secreto'in estado),'Estado filtró secreto');
    const salida=await dom(`fetch('/api/auth/cerrar-sesion',{method:'POST',headers:{'X-CSRF-Token':decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('esart_csrf=')).split('=')[1])}}).then(r=>r.status)`);
    exigir(salida===204,'Logout no confirmó revocación');
    await call('Page.navigate',{url:url+'/inicio-sesion'});
    await esperar(()=>dom(`!!document.querySelector('#nombre-usuario')`),'No volvió al login');
    await escribir('#nombre-usuario',process.env.ESART_USUARIO_PUBLICO);
    await escribir('#contrasena',process.env.ESART_CREDENCIAL_PRUEBA);await pulsar('Acceder al Sistema ESART');
    await esperar(()=>rutas('/api/auth/login').length===2,'No llegó primer factor');
    exigir(rutas('/api/auth/login')[1].response.status===202,'Se omitió segundo factor');
    exigir(await sinCookieSesion(),'Se emitió JWT antes del segundo factor');
    await esperar(()=>dom(`document.querySelectorAll('app-totp .totp-digitos input').length===6`),'No abrió ventana TOTP');
    exigir(await dom(`fetch('/api/auth/yo').then(r=>r.status)`)===401,'Hubo sesión antes de TOTP');
    await captura('segundo_factor.png');
    await ingresarCodigo(codigoActual(secreto,1));await pulsar('Verificar código');
    await esperar(()=>rutas('/api/auth/totp/login/confirmar').length===1,'No se envió segundo factor');
    exigir(rutas('/api/auth/totp/login/confirmar')[0].response.status===200,'Segundo factor no completó acceso');
    await esperar(()=>dom(`location.pathname==='/dashboard'`),'No navegó después de 2FA');
    exigir(await dom(`fetch('/api/auth/yo').then(r=>r.status)`)===200,'JWT final no funciona');
    let bloqueo = {};
    if(process.env.ESART_CAPTCHA_MANUAL==='true'){
      await dom(`fetch('/api/auth/cerrar-sesion',{method:'POST',headers:{'X-CSRF-Token':decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('esart_csrf=')).split('=')[1])}})`);
      await call('Page.navigate',{url:url+'/inicio-sesion'});
      await esperar(()=>dom(`!!document.querySelector('#nombre-usuario')`),'No volvió al login para validar bloqueo');
      await escribir('#nombre-usuario',process.env.ESART_USUARIO_PUBLICO);
      const antes=rutas('/api/auth/login').length;
      for(let n=1;n<=3;n++){
        await escribir('#contrasena','incorrecta-solo-prueba');await pulsar('Acceder al Sistema ESART');
        await esperar(()=>rutas('/api/auth/login').length>=antes+n,'No llegó rechazo de contraseña');
        exigir(rutas('/api/auth/login')[antes+n-1].response.status===401,'Rechazo inesperado de contraseña');
        await esperar(()=>dom(`!document.querySelector('button[type="submit"]')?.disabled`),'Login pendiente');
      }
      await esperar(()=>dom(`!!document.querySelector('app-captcha img[width="312"]')?.naturalWidth`),'No apareció CAPTCHA al tercer fallo');
      progreso({etapa:'captcha_incorrecto',fallos_contrasena:3});
      await escribir('#captcha-contrasena','incorrecta-solo-prueba');
      await escribir('#codigo-captcha','000000'); // Respuesta inválida: el generador no usa 0.
      await dom(`(()=>{const c=document.querySelector('app-captcha input[type="checkbox"]');if(!c.checked)c.click()})()`);
      let previo=rutas('/api/auth/login').length;
      await pulsar('Validar e Ingresar');
      await esperar(()=>rutas('/api/auth/login').length>previo,'No se envió CAPTCHA incorrecto');
      exigir((await cuerpo(rutas('/api/auth/login').at(-1))).error.codigo==='CAPTCHA_INVALIDO','CAPTCHA incorrecto aceptado');
      await esperar(()=>dom(`!document.querySelector('#codigo-captcha')?.disabled`),'No se renovó CAPTCHA');
      await new Promise(r=>setTimeout(r,500));
      const captcha=await cuerpo(rutas('/api/auth/captcha').at(-1));
      progreso({etapa:'esperando_expiracion_captcha',fallos_contrasena:3,expira_en:captcha.expira_en,
        instruccion:'No enviar todavía. La prueba espera los cinco minutos de caducidad real.'});
      while(Date.now()<=Date.parse(captcha.expira_en)+200)await new Promise(r=>setTimeout(r,500));
      await escribir('#captcha-contrasena','incorrecta-solo-prueba');await escribir('#codigo-captcha','000000');
      previo=rutas('/api/auth/login').length;
      const imagenes=rutas('/api/auth/captcha').length;
      await pulsar('Validar e Ingresar');
      await esperar(()=>rutas('/api/auth/captcha').length>imagenes,'CAPTCHA vencido no se renovó');
      exigir(rutas('/api/auth/login').length===previo,'El cliente envió contraseña con CAPTCHA vencido');
      progreso({etapa:'captcha_expirado_renovado',fallos_contrasena:3});
      let revisadas=rutas('/api/auth/login').length, fallos=3;
      while(fallos<7){
        await new Promise(r=>setTimeout(r,300));
        await esperar(()=>dom(`!!document.querySelector('#captcha-contrasena')`),'Falta ventana CAPTCHA');
        await esperar(()=>dom(`!document.querySelector('#codigo-captcha')?.disabled`),'CAPTCHA cargando');
        await escribir('#captcha-contrasena','incorrecta-solo-prueba');
        progreso({etapa:'captcha_manual',fallos_contrasena:fallos,instruccion:'Resuelva el CAPTCHA en Chrome, marque la casilla y pulse Validar e Ingresar.'});
        await esperarManual(()=>rutas('/api/auth/login').length>revisadas);
        const respuesta=rutas('/api/auth/login')[revisadas++], datos=await cuerpo(respuesta);
        if(datos.error?.codigo==='CAPTCHA_INVALIDO')continue;
        fallos++;
        exigir(respuesta.response.status===(fallos===7?423:401),'No se conservó el umbral de bloqueo');
        progreso({etapa:'contrasena_rechazada',fallos_contrasena:fallos,http:respuesta.response.status});
      }
      await esperar(()=>dom(`!!document.querySelector('app-ventana-bloqueo')`),'No apareció VentanaBloqueo');
      const datos=await cuerpo(rutas('/api/auth/login').at(-1));
      const horas=(Date.parse(datos.error.detalle.bloqueado_hasta)-Date.parse(datos.error.detalle.ahora_servidor))/3600000;
      exigir(Math.abs(horas-3)<0.001,'Duración de bloqueo distinta de tres horas');
      exigir(await dom(`fetch('/api/auth/yo').then(r=>r.status)`)===401,'Cuenta bloqueada accedió a sesión');
      await captura('bloqueo_septimo.png');
      await call('Page.reload');
      await esperar(()=>dom(`!!document.querySelector('app-ventana-bloqueo')`),'Se perdió el bloqueo tras recargar');
      progreso({etapa:'bloqueo_persistente',fallos_contrasena:7});
      await pulsar('Desbloquear con autenticador');
      await esperar(()=>rutas('/api/auth/desbloqueo/solicitar').length===1,'No se solicitó desbloqueo');
      await esperar(()=>dom(`document.querySelectorAll('app-totp .totp-digitos input').length===6`),'Falta ventana de desbloqueo');
      await ingresarCodigo(codigoActual(secreto));await pulsar('Verificar código');
      await esperar(()=>rutas('/api/auth/desbloqueo/confirmar').length===1,'No se confirmó desbloqueo');
      exigir(rutas('/api/auth/desbloqueo/confirmar')[0].response.status===200,'No funcionó desbloqueo TOTP');
      exigir(await sinCookieSesion(),'Desbloquear emitió JWT');
      exigir(await dom(`fetch('/api/auth/yo').then(r=>r.status)`)===401,'Desbloquear inició sesión');
      await esperar(()=>dom(`!document.querySelector('app-totp')&&!document.querySelector('app-ventana-bloqueo')`),'No se cerró bloqueo');
      bloqueo={captcha_desde_tercer_fallo:true,captcha_incorrecto_rechazado:true,captcha_expirado_renovado_sin_envio:true,
        bloqueo_septimo:423,duracion_bloqueo_horas:horas,captcha_resuelto_por_usuario:true,
        bloqueo_persiste_al_recargar:true,desbloqueo_totp:200,desbloqueo_sin_jwt:true};
      progreso({etapa:'completada',...bloqueo});
    }
    fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/resultado.json',JSON.stringify({
      escenario:'vinculacion_qr_y_login',qr_local_valido:true,qr_retirado:true,
      primer_login:202,sin_jwt_antes_de_vincular:true,primer_factor_2fa:202,sin_jwt_antes_de_totp:true,segundo_factor:200,
      consulta_sesion:200,logout:204,sin_intercepcion_http:true,sin_inyeccion_angular:true,...bloqueo},null,2));
  }else{
    secreto=process.env.ESART_SECRETO_PRUEBA;
    for(let n=1;n<=7;n++){
      if(n<=3){await escribir('#contrasena','incorrecta-solo-prueba');await pulsar('Acceder al Sistema ESART');}else{await escribir('#captcha-contrasena','incorrecta-solo-prueba');}
      if(n>=4){
        await esperar(()=>dom(`!!document.querySelector('app-captcha img[width="312"]')?.naturalWidth`),'No llegó CAPTCHA');
        const codigo=fs.readFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/captcha_efimero.txt','ascii');
        fs.unlinkSync(process.env.ESART_EVIDENCIA_PUBLICA+'/captcha_efimero.txt');
        await escribir('#codigo-captcha',codigo);await dom(`(()=>{const c=document.querySelector('app-captcha input[type="checkbox"]');if(!c.checked)c.click()})()`);
        await pulsar('Validar e Ingresar');
      }
      await esperar(()=>rutas('/api/auth/login').length>=n,'No llegó rechazo');
      exigir(rutas('/api/auth/login')[n-1].response.status===(n===7?423:401),'No se aplicó bloqueo');
      if(n<7)await esperar(()=>dom(`!document.querySelector('button[type="submit"]')?.disabled && (document.querySelector('app-captcha') ? !!document.querySelector('app-captcha img[width="312"]')?.naturalWidth : true)`),'Envío pendiente');
    }
    await esperar(()=>dom(`!!document.querySelector('app-ventana-bloqueo')`),'No abrió bloqueo');
    await pulsar('Desbloquear con autenticador');
    await esperar(()=>rutas('/api/auth/desbloqueo/solicitar').length===1,'No llegó desafío desbloqueo');
    await esperar(()=>dom(`document.querySelectorAll('app-totp .totp-digitos input').length===6`),'No abrió TOTP desbloqueo');
    await captura('desbloqueo.png');
    await ingresarCodigo(codigoActual(secreto,1));await pulsar('Verificar código');
    await esperar(()=>rutas('/api/auth/desbloqueo/confirmar').length===1,'No llegó desbloqueo');
    exigir(rutas('/api/auth/desbloqueo/confirmar')[0].response.status===200,'TOTP no desbloqueó');
    await esperar(()=>dom(`!document.querySelector('app-totp')&&!document.querySelector('app-ventana-bloqueo')&&!document.querySelector('button[type="submit"]').disabled`),'No habilitó login');
    exigir(await dom(`fetch('/api/auth/yo').then(r=>r.status)`)===401,'Desbloquear emitió sesión');
    fs.writeFileSync(process.env.ESART_EVIDENCIA_PUBLICA+'/resultado.json',JSON.stringify({
      escenario:'desbloqueo_totp',bloqueo_septimo:423,captcha_desde_cuarto:true,
      desafio:202,desbloqueo:200,sin_jwt:true,login_habilitado:true,
      sin_intercepcion_http:true,sin_inyeccion_angular:true},null,2));
  }
} finally {ws.close();}
// Chrome puede mantener pendiente el cierre CDP; todas las aserciones y escrituras ya finalizaron.
process.exit(0);
