# Firma electrónica desde el celular

Certificaciones y oficios remisorios se firman con la **rúbrica dibujada en el celular** del firmante
autorizado y se confirman con su **código TOTP de ESART**. La rúbrica se estampa en la línea de firma
del PDF, que se genera recién después de firmar. Es una firma electrónica simple con evidencia:
hashes, consentimiento, desafío TOTP y auditoría encadenada. No es una firma digital PAdES con
certificado X.509.

## 1. Flujo

```
PC (ficha del artillero)                      Celular del firmante
1. Generar PDF  ─ borrador v1 + QR (15 min)
2. Escanear QR  ────────────────────────────▶ /firma/<token>: revisa el borrador
3. Dibujar firma                              dibuja la rúbrica, acepta y escribe su TOTP
4. Ubicar y validar ◀──── el PC consulta ──── el backend ubica la rúbrica en la línea de firma,
   «Descargar PDF firmado» (v2)               genera el PDF final y registra la evidencia
```

1. En **Personal militar → Verificar artillero**, elegir *Certificación* u *Oficio remisorio* y pulsar
   **Firmar desde el celular**. Luego elegir el firmante autorizado y pulsar **Generar PDF y código QR**.
2. El firmante escanea el QR con la cámara. Ve el documento, el artillero y su propio nombre, y puede
   abrir el borrador en PDF.
3. Dibuja su firma con el dedo, acepta la declaración y escribe el código de 6 dígitos de su
   autenticador.
4. El PC detecta la firma (consulta cada 3 segundos) y ofrece **Descargar PDF firmado**. La rúbrica
   queda sobre la línea de firma con el nombre, el cargo, la fecha y hora, y el código de
   verificación `F-XXXXXXXX`.

El botón **Generar documento** (sin firma) sigue funcionando igual que antes.

## 2. Quién puede hacer qué

| Acción | Requisito |
|---|---|
| Pedir la firma y ver su estado | Permiso **PERSONAL_VERIFICAR** (leer). Solo quien creó la solicitud ve su estado, salvo FIRMA_DOCUMENTOS. |
| Firmar | Tener una **autorización vigente** en `esart_firma.autorizaciones_firmantes` para ese tipo de documento **y** el autenticador TOTP de ESART **activo**. |
| Autorizar firmantes | Permiso **FIRMA_DOCUMENTOS** (crear). Desde la misma ventana **Firmar desde el celular**: si no hay firmantes se abre el formulario (usuario, cargo y «también para el otro tipo»); si ya hay, con el enlace **Autorizar otro firmante**. Solo se pueden elegir usuarios con el autenticador activo. API: `GET /api/firma/candidatos` y `POST /api/firma/autorizaciones`. |

Autorizar al Director desde la API (con sesión de administrador y CSRF):

```json
POST /api/firma/autorizaciones
{ "usuario_id": 12, "tipo": "CERTIFICACION", "cargo": "Director de la Escuela de Artillería" }
```

Hay que repetirlo con `"tipo": "OFICIO_REMISORIO"` si también firma oficios. El nombre del firmante sale
de Personal militar cuando su usuario tiene la cédula registrada. Para revocar una autorización todavía
no hay pantalla (columna `revocado_en`).

## 3. Seguridad

- **Token del QR:** 256 bits aleatorios, un solo uso, vence en 15 minutos. La base solo guarda su
  sha256, y los logs lo ocultan (`[TOKEN_FIRMA_OCULTO]`).
- **Identidad:** el código TOTP del firmante pasa por el mismo servicio de ESART: límite de intentos,
  protección contra reutilización del código y auditoría de los intentos fallidos. Un código inválido
  responde 422 (nunca 401: el celular no tiene sesión). No se crea ningún TOTP ni sesión paralela; el
  TOTP heredado de `esart_firma` sigue bloqueado.
- **Integridad:** el consentimiento sella el sha256 del borrador que el firmante revisó. El borrador
  se verifica contra su hash antes de mostrarlo y de firmarlo. El PDF final, la rúbrica y el borrador
  quedan como evidencias inmutables con su hash.
- **Rúbrica:** solo PNG, con tamaño y dimensiones acotados y trazo obligatorio. Se re-codifica para
  eliminar los metadatos.
- **Celular sin sesión:** las rutas `/api/firma-movil/*` no usan cookies, por eso no aplica CSRF. Las
  protegen el token y el TOTP.

## 4. Registro en la base (`esart_firma`)

| Paso | Registros |
|---|---|
| Pedir firma | `documentos` (PENDIENTE_FIRMA) + `versiones_documento` v1 (borrador) + evidencia PDF_ORIGINAL + `solicitudes_firma` (sobre el documento) + evento `FIRMA_SOLICITADA` |
| Abrir QR | `solicitudes_firma.estado` = ABIERTA (`abierta_en`); vencida → EXPIRADA |
| Firmar | `desafios_autenticacion` (FIRMAR, validado y consumido) → `consentimientos_firma` (hash del borrador) → `versiones_documento` v2 (PDF firmado) → `firmas_certificado` (RUBRICA_ELECTRONICA, hashes de rúbrica y PDF) → solicitud APROBADA, documento FIRMADO (`version_actual` = 2) → evento `DOCUMENTO_FIRMADO` + evidencias RUBRICA y PDF_FIRMADO |

Los archivos (borrador, rúbrica y PDF firmado) se guardan en `DIRECTORIO_DOCUMENTOS_PRIVADOS`, nunca
en una carpeta pública.

## 5. Requisitos para usarlo

**"Firma documental" en la malla de permisos.** El componente `FIRMA_DOCUMENTOS` lo crea p0018, pero
se puede agregar antes con un script independiente e idempotente (como postgres):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h 127.0.0.1 -U postgres -d esart_db -f propuestas\componente_firma_documentos.sql
```

Después aparece en *Administración → Malla de permisos*, para habilitarlo por rol o por usuario:

- **Leer:** ver todas las solicitudes y descargar cualquier documento firmado.
- **Crear:** autorizar firmantes.

Por defecto lo tiene solo ADMINISTRADOR. p0018 detecta que el componente ya existe y no lo duplica
ni cambia lo que se haya ajustado en la malla.

Habilitar el componente **no** convierte a nadie en firmante: el firmante necesita una autorización
vigente (con su cargo) y su autenticador activo.

**Sin p0018 y p0019** la ventana muestra "La firma desde el celular aún no está habilitada en la base
de datos (faltan las migraciones p0018 y p0019)" (503 `FIRMA_NO_DISPONIBLE`), en lugar de un error
interno. El log del backend indica la causa (`SIN_ESQUEMA_O_USAGE`, `SIN_P0018` o `SIN_P0019`).


1. **Migraciones p0018 y p0019** aplicadas. p0019 solo concede permisos a la API sobre la cadena de
   firma; ninguna de las dos se ha ejecutado en `esart_db` (ver
   `ESART_P0018_CONCILIACION_DEFINITIVA.md`).
2. En `backend/.env`:
   ```
   DOCUMENTOS_PERSISTENCIA_HABILITADA=true
   URL_BASE_FIRMA_MOVIL=http://<IP-del-PC-en-la-WiFi>:4200
   ```
   La IP sale de `ipconfig` (adaptador WiFi), por ejemplo `http://192.168.1.50:4200`. Sin esta
   variable, el QR usa la dirección del navegador y avisa si es `localhost`, que el celular no puede
   abrir.
3. **Frontend accesible en la red WiFi** (el backend sigue solo en 127.0.0.1; el proxy de Angular
   reenvía `/api`):
   ```powershell
   npx ng serve --proxy-config proxy.conf.json --host 0.0.0.0
   ```
   Si Windows lo pregunta, permitir el puerto 4200 en el firewall para redes privadas. El celular y el
   PC deben estar en la **misma red WiFi**.
4. El firmante debe tener activo su autenticador de ESART y una autorización vigente.

## 5b. Aplicar en esart_db (SQL manual de p0018 + p0019)

`backend/propuestas/p0018_p0019_firma_manual.sql` aplica p0018 y p0019 como postgres. Sale de las
propias migraciones (`herramientas/generar_sql_p0018_p0019.py`) y conserva sus guardas:

- **Una sola transacción.** Si algo falla, se revierte todo.
- **Antes de cambiar nada:**
  - si ya se ejecutó, aborta ("No se ejecuta dos veces");
  - si alguna de las 21 tablas heredadas no coincide exactamente con el inventario, aborta;
  - si el TOTP o las sesiones heredadas tienen datos, aborta.
- **Al final:** comprueba que los conteos, los 5 roles y los 8 permisos sigan idénticos.
- **No toca `esart.alembic_version`.** La base sigue marcando p0014, porque p0015 y p0016 también se
  aplicaron a mano y p0017 no está aplicada.

Pasos (desde la carpeta `backend`):

1. **Respaldo** (pide la contraseña de postgres; guardarlo fuera del repositorio):
   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h 127.0.0.1 -U postgres -d esart_db -Fc -f "$env:USERPROFILE\esart_db_antes_p0018.dump"
   ```
2. **Script:**
   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -X -h 127.0.0.1 -U postgres -d esart_db -f propuestas\p0018_p0019_firma_manual.sql
   ```
   Hay que ver `COMMIT`. Al final, `tablas_esart_firma = 23`, `roles_firma = 5` y
   `permisos_firma = 8`. Si sale `ERROR: p0018 abortada sin cambios: ...`, no se cambió nada; el
   mensaje dice qué tabla o condición no coincide.
3. **`backend/.env`:** `DOCUMENTOS_PERSISTENCIA_HABILITADA=true` y `URL_BASE_FIRMA_MOVIL=http://<IP>:4200`.
4. **Reiniciar el backend.** La ventana de firma ya no muestra "aún no está habilitada".
5. **Autorizar al firmante** con `POST /api/firma/autorizaciones`; debe tener su autenticador activo.

Si hubiera que volver atrás, restaurar el respaldo del paso 1 (con el backend detenido):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" -h 127.0.0.1 -U postgres -d esart_db --clean --if-exists "$env:USERPROFILE\esart_db_antes_p0018.dump"
```

Probado con `herramientas/probar_sql_p0018_p0019_aislada.py`: con psql como superusuario, sobre una
copia en p0016 con el esquema heredado (5 roles y 8 permisos). **34/34 comprobaciones**:

- aplicación normal sin cambios en los datos heredados;
- flujo completo de firma sobre la base resultante;
- segunda ejecución abortada;
- estructura distinta abortada sin crear nada;
- componente agregado antes, respetando la malla.

## 6. API

| Ruta | Descripción |
|---|---|
| `GET /api/firma/firmantes?tipo=` | Firmantes vigentes `[{autorizacion_id, usuario_id, nombre, cargo, tipo}]` |
| `POST /api/firma/solicitudes` | `{cedula, tipo, autorizacion_id}` → 201 `{solicitud_id, documento_id, url_firma, url_publica_configurada, expira_en, firmante, cargo}`. 409 `FIRMANTE_SIN_AUTENTICADOR`; 422 `FIRMANTE_NO_AUTORIZADO`; 503 `ALMACENAMIENTO_NO_DISPONIBLE` |
| `GET /api/firma/solicitudes/{id}` | `{estado, estado_documento, documento_id, expira_en, firmante, cargo}` |
| `GET/POST /api/firma/autorizaciones` | Listar o conceder autorizaciones (FIRMA_DOCUMENTOS) |
| `GET /api/firma-movil/{token}` | Resumen para el celular (marca ABIERTA o EXPIRADA). 404 si el enlace no es válido |
| `GET /api/firma-movil/{token}/pdf` | Borrador verificado (`inline`). 409 `SOLICITUD_CERRADA` |
| `POST /api/firma-movil/{token}/firmar` | `{rubrica_png, codigo_totp, acepto}` → `{estado: APROBADA, codigo_verificacion}`. 422 `TOTP_INVALIDO`, `RUBRICA_VACIA`, `RUBRICA_INVALIDA`, `CONSENTIMIENTO_REQUERIDO`; 409 `SOLICITUD_CERRADA`; 429 por exceso de intentos |

El PDF firmado se descarga con `GET /api/verificar/documentos/{documento_id}/archivo`, que entrega la
versión actual.

## 7. Pruebas

- `backend/herramientas/probar_firma_movil_aislada.py`: PostgreSQL efímero, Alembic hasta p0019 y
  servicios reales como `esart_aplicacion`, con un TOTP real generado desde el secreto. **25/25
  comprobaciones**:
  - autorizaciones;
  - firmante sin autenticador y autorización de otro tipo;
  - token guardado solo como hash;
  - apertura y borrador;
  - sin aceptación, rúbrica vacía y TOTP inválido (auditado);
  - firma correcta;
  - token reutilizado y enlace vencido;
  - estado visible solo para su creador;
  - versiones 1 y 2 con hash;
  - texto del PDF final;
  - consentimiento con el hash del borrador;
  - desafío, firma y evidencias;
  - auditoría encadenada verificable.
- `backend/pruebas/test_firma_movil.py`: validación de rúbricas, hash del token, ocultamiento del
  token en los logs, datos del documento ida y vuelta, y PDF con rúbrica.
- Frontend: `solicitud-firma.spec.ts` (QR, consulta de estado y descarga) y `firma-movil.spec.ts`
  (lienzo, validación del código, envío y errores).

## 8. Límites y pendientes

- Firma **electrónica simple** (rúbrica + TOTP + evidencias). Para validez de firma digital
  certificada haría falta PAdES con un certificado X.509 de la Escuela: la tabla `firmas_certificado`
  ya admite el método `PAdES`.
- La rúbrica se ubica sola en la línea de firma del documento; no se arrastra a otra posición.
- Autorizar firmantes se hace desde la ventana de firma; revocarlos todavía no tiene pantalla.
- Probado en laboratorio, no en `esart_db`, que todavía no tiene p0018 ni p0019.
