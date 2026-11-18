# Prueba autorizada sobre la aplicación local real

**Resultado: criterio de aceptación demostrado en esart_db el 16 de noviembre de 2026.**

## Entorno y autorización

Se utilizó exclusivamente `prueba.seguridad`, ID 3, contra Angular existente `http://localhost:4200`, su proxy configurado a FastAPI existente `http://127.0.0.1:8081` y PostgreSQL `esart_db`. No se inició un backend alternativo, no se cambió el proxy y no se utilizó una base aislada para esta aceptación.

El usuario autorizó reiniciar solo contador y bloqueo antes de comenzar y bloquear esa cuenta durante tres horas. Se confirmó destino, identidad activa y ausencia de triggers de usuario. Dentro de una transacción se ejecutó únicamente:

```sql
UPDATE esart_ref.usuarios
SET intentos_fallidos_consecutivos=0, bloqueado_hasta=NULL
WHERE id=3 AND usuario='prueba.seguridad';
```

Se exigió exactamente una fila afectada. La transacción comparó internamente la contraseña del objetivo y las filas de otras cuentas antes/después y comprobó que no cambiaron, sin imprimir ni almacenar sus hashes. Estado anterior del objetivo: contador 3 y bloqueo NULL. Estado inicial confirmado tras commit: contador 0 y bloqueo NULL. No se hicieron otras escrituras SQL administrativas.

## Prueba desde Chrome

Se abrió Chrome real con un perfil dedicado contra la aplicación ya ejecutándose. Se operaron los campos y botones DOM del login y del CAPTCHA. Las imágenes se visualizaron y resolvieron leyendo los seis caracteres de su PNG; no se capturaron secretos del generador, no se usó el mecanismo del laboratorio, no se simuló HTTP y no se deshabilitó ninguna validación.

Se enviaron contraseñas controladas incorrectas, nunca la contraseña real. Cada respuesta se observó mediante CDP y después se consultó PostgreSQL mediante otra conexión READ ONLY.

| Envío | CAPTCHA | Contraseña comprobada | HTTP | Contador PostgreSQL | Bloqueo | Componente |
|---|---|---|---:|---:|---|---|
| 1 | No requerido | Sí, incorrecta | 401 | 1 | NULL | InicioSesion |
| 2 | No requerido | Sí, incorrecta | 401 | 2 | NULL | InicioSesion |
| 3 | No requerido; se exige el próximo | Sí, incorrecta | 401 | 3 | NULL | Captcha automático |
| 4 | Deliberadamente incorrecto | No | 401 CAPTCHA_INVALIDO | 3 | NULL | Captcha, nuevo PNG |
| 5 | Válido | Sí, incorrecta n.º 4 | 401 | 4 | NULL | Captcha, nuevo PNG |
| 6 | Válido | Sí, incorrecta n.º 5 | 401 | 5 | NULL | Captcha, nuevo PNG |
| 7 | Válido | Sí, incorrecta n.º 6 | 401 | 6 | NULL | Captcha, nuevo PNG |
| 8 | Válido | Sí, incorrecta n.º 7 | **423 CUENTA_BLOQUEADA** | **7** | **2026-11-16 23:17:27.961547 UTC** | **VentanaBloqueo; Captcha cerrado** |

La secuencia real es **1 → 2 → 3 → 3 → 4 → 5 → 6 → 7**. Son siete contraseñas comprobadas incorrectas más un envío de CAPTCHA incorrecto; no se necesitó una octava contraseña incorrecta.

El séptimo fallo se registró a `2026-11-16 20:17:27.961547 UTC` (15:17:27 de Bogotá). La respuesta indicó **10800 segundos**, y la fecha persistida de desbloqueo es exactamente tres horas después: **18:17:27 del 16 de noviembre, America/Bogota**.

Se recargó Chrome dos veces. Continuó visible VentanaBloqueo y cerrado Captcha. PostgreSQL mantuvo contador 7 y la misma fecha de desbloqueo; la última fecha del intento no cambió, por lo que recargar no agregó fallos. Se deja deliberadamente la cuenta bloqueada; no se ejecutó un desbloqueo posterior.

## Diagnóstico final y límites de la conclusión

La causa comprobable del contador anterior detenido en tres era que esos envíos no superaban CAPTCHA: la auditoría operativa mostraba `CAPTCHA_RECHAZADO`, no contraseñas comprobadas incorrectas. Los desafíos examinados se consumieron dentro de su vigencia. Con la versión actualmente servida, resolver la imagen visible produjo `captcha_validado=true` en los cuatro envíos siguientes y permitió llegar al séptimo fallo.

**No se reprodujo un rechazo permanente de CAPTCHA con soluciones correctas durante esta prueba real.** No se atribuye retrospectivamente a una equivocación del usuario, a un navegador antiguo o a una clave distinta sin evidencias: no se conservaron las soluciones enviadas en aquellos intentos históricos. Sí queda demostrado que los controles y las correcciones anteriores funcionan en el entorno operativo actual, no solo en aislamiento.

Se observó un mensaje ambiguo existente: tras CAPTCHA válido y contraseña incorrecta, Angular muestra que no pudo validar “el código o las credenciales”, aunque PostgreSQL confirma `captcha_validado=true`. Se documenta esa distinción, pero no se cambia el mensaje ni el CAPTCHA porque esta autorización exige conservarlo.

No fue necesario cambiar código de producción, configuración ni estructura para superar esta aceptación. TOTP/QR, JWT, roles y permisos permanecieron intactos. No se realizaron intentos sobre otras cuentas ni se modificaron contraseñas.

## Evidencia y archivos

Directorio local retenido: `backend/respaldos/captcha_operativo_ab876de0e42443f28c7e84ca03f2d3a0/`.

- `registro_sql.json`: lecturas independientes después de cada envío y después de recargar; contiene fechas, motivo, indicadores CAPTCHA, contador y bloqueo, sin credenciales.
- `resultado.json`: resumen de HTTP observados en CDP, secuencia SQL, plazo de tres horas y componentes observados.
- `bloqueo.png`: ventana abierta tras el 423.
- `recarga.png`: la misma ventana tras recargar la aplicación real.
- No compartir ni incorporar el subdirectorio del perfil Chrome a Git: contiene los datos temporales del navegador de diagnóstico. No se realizaron commits ni push.

Herramientas incorporadas para reproducir la observación: `backend/herramientas/observar_captcha_operativo.mjs` y `backend/herramientas/estado_prueba_seguridad.py`. La primera actúa en el navegador local y solo permite enviar a prueba.seguridad; la segunda es exclusivamente de lectura, exige esart_db y limita la consulta al ID 3 y nombre aprobado. No son endpoints del producto. El reinicio inicial fue una operación separada y acotada a la autorización de esta sesión; no está automatizado en esas herramientas. Ruff de la herramienta Python pasó sin errores.

## Consultas de verificación

```sql
BEGIN TRANSACTION READ ONLY;
SELECT current_database(), current_user;
SELECT id,usuario,intentos_fallidos_consecutivos,bloqueado_hasta
FROM esart_ref.usuarios WHERE id=3 AND usuario='prueba.seguridad';

SELECT fecha,motivo_fallo,captcha_requerido,captcha_validado
FROM esart.intentos_inicio_sesion WHERE usuario_id=3
  AND fecha >= TIMESTAMPTZ '2026-11-16 20:16:04+00'
ORDER BY fecha,id;

SELECT extract(epoch FROM (u.bloqueado_hasta-i.fecha)) AS segundos_bloqueo
FROM esart_ref.usuarios u
JOIN LATERAL (
 SELECT fecha FROM esart.intentos_inicio_sesion
 WHERE usuario_id=u.id AND motivo_fallo='CREDENCIALES_INVALIDAS'
 ORDER BY fecha DESC,id DESC LIMIT 1
) i ON true
WHERE u.id=3 AND u.usuario='prueba.seguridad';
COMMIT;
```

La última consulta debe devolver 10800 mientras no se haya alterado posteriormente el estado por una operación autorizada. Esta entrega demuestra el flujo real solicitado; no vuelve a contabilizar las pruebas aisladas anteriores como si fueran pruebas nuevas sobre la base operativa.
