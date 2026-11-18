# Diagnóstico del entorno operativo local

16 de noviembre de 2026. Solicitud: adjunto 0cb8c5b9.

**Actualización:** la autorización posterior fue recibida y la prueba real completó el criterio de aceptación. Véase `ESART_PRUEBA_OPERATIVA_CAPTCHA_BLOQUEO.md`. El resto de este documento conserva el diagnóstico previo y sus límites.

## Evidencia obtenida sin modificar datos

La conexión local del backend apunta a `esart_db` como `esart_aplicacion`. FastAPI en `127.0.0.1:8081/api/salud` y el proxy `localhost:4200/api/salud` responden 200 con base de datos disponible.

`prueba.seguridad` tiene contador 3 y `bloqueado_hasta=NULL`. Los ocho intentos más recientes consultados figuran como `CAPTCHA_INVALIDO`, con `captcha_requerido=true` y `captcha_validado=false`. No se trata de siete contraseñas que hayan llegado a verificarse.

Los desafíos recientes vinculados al contexto de esa cuenta incluyen consumos ocurridos entre tres y siete segundos después de crearse, anteriores a su expiración. Para los doce desafíos recientes, la auditoría consultada devolvió doce emisiones, una regeneración y ocho eventos `CAPTCHA_RECHAZADO`. Este último evento se escribe al comprobar la solución del desafío; los caminos de reutilización y vencimiento tienen eventos distintos. Esto acota el fallo a una solución que no supera forma/comparación, sin demostrar todavía por qué el usuario ve un rechazo reiterado. No basta atribuirlo a caducidad o a los errores de regeneración anteriores.

El módulo JavaScript realmente servido por Angular contiene `revisionCaptcha`, `captcha-contrasena` y el tratamiento de 409. Se verificó la respuesta HTTP del módulo, no solo el archivo en disco. Esto no prueba qué código conserva una pestaña antigua ni que el proceso FastAPI ejecutado tenga idéntica configuración a la lectura local: falta correlacionar el próximo desafío HTTP con su fila PostgreSQL.

No se leyeron ni publicaron contraseñas, hashes de credenciales, claves de firma, soluciones CAPTCHA o tokens. No se cambió código de producción, diseño, esquema, datos de usuarios ni configuración en esta revisión. No se provocaron nuevos fallos o bloqueos.

## Consultas reproducibles

Ejecutar con la conexión existente del proyecto, en transacción de solo lectura; nunca imprimir cadenas de conexión:

```sql
BEGIN TRANSACTION READ ONLY;
SELECT current_database(), current_user;
SELECT usuario, intentos_fallidos_consecutivos, bloqueado_hasta
FROM esart_ref.usuarios WHERE usuario = :usuario_prueba;

SELECT i.id, i.fecha, i.motivo_fallo, i.captcha_requerido, i.captcha_validado
FROM esart.intentos_inicio_sesion i
JOIN esart_ref.usuarios u ON u.id=i.usuario_id
WHERE u.usuario=:usuario_prueba
ORDER BY i.fecha DESC,i.id DESC LIMIT 8;

-- :contexto se calcula internamente con seudonimo('usuario', nombre normalizado).
-- No sustituirlo por el nombre ni imprimir la clave de firma usada para calcularlo.
SELECT creado_en, consumido_en,
       extract(epoch FROM (consumido_en-creado_en)) AS segundos_hasta_consumo,
       consumido_en < expira_en AS dentro_del_plazo
FROM esart.desafios_captcha WHERE contexto=:contexto
ORDER BY creado_en DESC LIMIT 8;

SELECT evento,count(*)
FROM esart.auditoria_acceso
WHERE captcha_id IN (
 SELECT id FROM esart.desafios_captcha WHERE contexto=:contexto
 ORDER BY creado_en DESC LIMIT 12
) GROUP BY evento;
COMMIT;
```

Los parámetros se vinculan desde SQLAlchemy; las consultas no requieren ni realizan migraciones.

## Prueba real pendiente

Se solicitó identificar la cuenta autorizada para bloquear en esart_db. Para registrar la secuencia desde cero en `prueba.seguridad`, hace falta autorización explícita para reiniciar únicamente su contador y bloqueo, pues actualmente está en tres. No se asumió autorización para modificar su estado existente. No se necesita su contraseña real.

Una vez recibida:

1. Registrar el estado inicial y comprobar nuevamente base, usuario y permisos de conexión. Preparar cualquier reinicio de esos dos campos en transacción limitada al ID y nombre confirmados, sin afectar otros usuarios o tablas.
2. Abrir Chrome con perfil dedicado contra el Angular existente en 4200, sin iniciar otro FastAPI ni cambiar el proxy operativo.
3. Introducir contraseñas controladas incorrectas. Resolver la imagen efectivamente visible; no utilizar el capturador de soluciones del laboratorio ni sustituir respuestas HTTP.
4. Correlacionar cada CAPTCHA con su ID enviado y su fila en esart_db, sin publicar el ID ni su solución en el informe. Revisar si coincide la imagen mostrada con la respuesta vigente, el nombre de contexto, consumo, caducidad y resultado.
5. Registrar por envío: comprobación CAPTCHA, si se llegó a comprobar la contraseña, HTTP, contador SQL, fecha de bloqueo y componente visible. La secuencia esperada es 1,2,3,3,4,5,6,7, con el cuarto envío reservado a un CAPTCHA incorrecto.
6. Verificar 423 en el mismo séptimo fallo comprobado, plazo de tres horas, apertura de VentanaBloqueo y persistencia al recargar. No usar la contraseña correcta ni modificar contraseñas/TOTP.
7. Corregir únicamente la causa demostrada por esa reproducción y volver a probar. Conservar diseño y controles. No sustituir este criterio por resultados aislados previos.

Hasta completar esta prueba con autorización, los resultados aislados anteriores no constituyen aceptación operativa de este encargo.
