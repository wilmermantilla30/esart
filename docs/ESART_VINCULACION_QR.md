# Vinculación QR después del inicio de sesión

> Documento histórico de la vinculación opcional. La política vigente exige vinculación durante el primer login, antes de entregar una sesión completa. Consultar [ESART_INTEGRACION_CUENTAS_TOTP.md](ESART_INTEGRACION_CUENTAS_TOTP.md) para endpoints, pruebas y diagnóstico real. La ruta autenticada /totp se conserva para administrar un factor activo.

Se reutiliza `paginas/totp/Totp`, con la vista `CONFIGURAR` separada de las vistas de verificación LOGIN, DESBLOQUEO y AUTORIZAR_ACCION. No se crea un componente ni un servicio TOTP duplicado. Se mantienen el escudo, colores y modal institucional responsive.

## Abrir la ventana

El usuario inicia sesión con el flujo existente y selecciona **CONFIGURAR AUTENTICADOR** en `/inicio`. El enlace abre `/totp`, protegida por el guard de sesión. Abrir la página consulta estado, pero **no genera un secreto**. La contraseña actual se solicita al titular antes de generar o recuperar su QR. La creación administrativa de usuarios no se modifica y no activa TOTP.

Para incorporarla en otra pantalla autenticada, importar `Totp` en `imports` del componente standalone y mostrarla condicionalmente:

```html
@if (mostrarVinculacion()) {
  <app-totp
    modo="CONFIGURAR"
    [volverAlInicioAlCerrar]="false"
    (cancelar)="mostrarVinculacion.set(false)"
    (completado)="vinculacionConfirmada($event)"
  />
}
```

No necesita usuario, ID, secreto ni URI como entrada. La sesión HttpOnly y el interceptor CSRF existente proporcionan el contexto; el backend obtiene el actor autenticado. `cancelar` no modifica el factor en PostgreSQL. `completado` emite `{modo:'CONFIGURAR'}` solamente tras confirmación exitosa del servidor; el contenedor puede cerrar el modal y actualizar su consulta de estado. No debe ejecutar cambios de usuarios como consecuencia implícita del evento.

`volverAlInicioAlCerrar` vale true para la página `/totp`; establecer false al incrustarla para que el contenedor gestione la navegación. Las otras entradas existentes se reservan a los modos de verificación y no son necesarias para vincular.

## Contratos comprobados

Los endpoints existen tanto bajo `/api/auth` como bajo `/api/v1/auth`. El cliente HTTP compartido actual utiliza `/api/auth`; ambos prefijos resuelven al mismo router.

| Endpoint | Solicitud | Respuesta |
|---|---|---|
| GET /api/v1/auth/totp/estado | Sesión autenticada | `configurado`, `activo`, `fecha_activacion`; sin secretos. |
| POST /api/v1/auth/totp/configurar | Sesión, CSRF, `{contrasena}` | `uri` otpauth y `expira_en`. |
| POST /api/v1/auth/totp/confirmar | Sesión, CSRF, `{codigo}` de seis dígitos ASCII | Estado activo tras verificar el código real. |

Se rechazan campos adicionales, incluido `usuario_id`. Configurar exige contraseña actual, usuario activo y no bloqueado, presupuesto persistente de intentos y cifrado disponible. Confirmar exige sesión y código válido. Los errores y la activación se auditan mediante los servicios existentes. No hay endpoints públicos de vinculación.

Una configuración pendiente válida se recupera con la misma URI y caducidad después de volver a comprobar la contraseña; no se regenera ni se amplía su vigencia al reabrir. Solo una configuración vencida o revocada puede iniciar otra vinculación. Un factor ACTIVO no se reemplaza desde configurar: su revocación conserva las comprobaciones existentes de contraseña más TOTP.

## Estados y secretos

La vista contempla inicial, generación, QR disponible, verificación, código incorrecto, expiración, éxito, sesión requerida y error de conexión. La fecha de caducidad procede del servidor. El temporizador local retira el QR y la clave cuando vence; PostgreSQL conserva la autoridad para aceptar o rechazar el código.

La biblioteca local `qrcode` convierte exclusivamente la URI recibida del backend. Angular no genera secretos. La clave manual se extrae transitoriamente de esa URI, permanece oculta hasta que el usuario pide verla y puede copiarse mediante Clipboard API en contexto seguro. Copiar transfiere una credencial al portapapeles del sistema; la interfaz informa de ello. Si el navegador lo impide, permite transcripción manual. No se escribe en localStorage, sessionStorage ni logs. Tras activación, cancelación o destrucción se limpian QR, clave y visibilidad. No se conserva una captura del QR en las evidencias.

No hay activación automática al generar o escanear el QR. La confirmación requiere el código validado en FastAPI. Sin sesión/configuración operativa el componente muestra el error, impide generar y no presenta un QR ficticio.

## Política de vinculación obligatoria futura

La política actual permite acceso normal a cuentas sin factor activo; las cuentas que ya tienen factor activo conservan el segundo paso del login existente. Esta entrega no cambia JWT, CAPTCHA, roles, permisos ni bloqueo.

Para imponer vinculación obligatoria en una entrega posterior, implementar un contexto temporal restringido **en el backend** después de contraseña y CAPTCHA, con propósito ENROLLMENT y TTL corto. No debe ser un JWT de acceso completo: solo puede consultar/confirmar la vinculación del mismo actor, revocarse al activar y dar paso a la sesión completa una vez validado el código. Los endpoints de negocio deben denegar ese contexto. Añadir pruebas de acceso HTTP directo, caducidad, CSRF, otro actor y reutilización antes de habilitar la política. Un guard Angular o redirección por sí solos no garantizan esa restricción. No se implementó una sesión temporal ficticia en esta entrega.

## Validación y límites de despliegue

Se amplían las pruebas del componente para clave oculta/visible, limpieza después de activación, caducidad, ausencia de sesión y prevención de regeneración visual. El laboratorio PostgreSQL comprueba que dos solicitudes de configurar autenticadas devuelven exactamente la misma URI y caducidad pendiente, y que el contrato rechaza un ID arbitrario. El recorrido Chrome usa QR/URI y códigos generados realmente para cuentas aisladas; no simula respuestas HTTP del flujo funcional.

No se ejecutan migraciones ni se modifican cuentas reales. La puesta en servicio principal sigue condicionada a los permisos, clave externa y revisión administrativa descritos en `ESART_TOTP_IMPLEMENTACION.md`. Una prueba aislada aprobada no acredita que esos requisitos ya estén satisfechos en esart_db.

### Resultado de esta entrega

- Angular: 63 pruebas aprobadas en 14 archivos. Compilación de producción aprobada; se mantiene el aviso CommonJS de qrcode, sin errores de compilación.
- Backend general: 196 aprobadas, 56 omitidas por requerir entornos explícitos. Ruff sin errores.
- PostgreSQL aislado: 41 aprobadas, incluida recuperación idempotente de configuración pendiente, rechazo de usuario_id arbitrario y navegador Chrome real.
- Evidencia nueva: `backend/respaldos/hu06_36baa804a715496491a3f91c9f90f55b/navegador_totp/resultado.json`. QR local válido, retirado tras activar; primer factor 202 sin JWT, segundo factor 200 y consulta de sesión 200. Clúster detenido al finalizar. Sin interceptar HTTP ni inyectar estado privado de Angular.
- Archivos ajustados en esta entrega: `paginas/totp/totp.ts`, `totp.html`, `totp.css`, `totp.spec.ts`; enlace autenticado en `paginas/inicio/inicio.ts` e `inicio.html`; recuperación de pendiente en `backend/aplicacion/servicios/totp.py`; regresiones en `backend/pruebas/test_totp_pg.py` y selector de activación en `backend/herramientas/navegador_totp.mjs`.

No se modifican en esta entrega el CRUD de usuarios, el login, CAPTCHA, roles, permisos, reglas de bloqueo ni migraciones. Se reutiliza el servicio HTTP ya existente.
