# Diagnóstico de POST /api/auth/login — 503

Fecha: **16 de noviembre de 2026**, zona America/Bogota. Inspección del código y de PostgreSQL en READ ONLY. No se modificaron Angular, controles de seguridad, datos, permisos, configuración ni historial Alembic.

## Causa exacta reproducida

La ruta POST /api/auth/login llama a servicios/autenticacion.iniciar_sesion, que comienza llamando a servicios/seguridad_login.preparar. Esta función comprueba la disponibilidad de la estructura requerida por la nueva política antes de comprobar credenciales o crear registros.

La consulta de disponibilidad devolvió false y el servicio lanzó:

```json
{
  "error": {
    "codigo": "SEGURIDAD_NO_DISPONIBLE",
    "mensaje": "Inicio de sesión temporalmente no disponible.",
    "detalle": null
  }
}
```

Estado HTTP: **503**. El manejador de ErrorAplicacion conserva ese estado y lo serializa en el formato contractual. Es un rechazo explícito de disponibilidad del subsistema de seguridad; FastAPI puede iniciar y PostgreSQL puede responder SELECT 1 al mismo tiempo.

Se reprodujo la excepción del servicio con una sesión SQLAlchemy ligada a una transacción READ ONLY de esart_db/esart_aplicacion. No se envió contraseña, no se llamó al endpoint de login de producción, no se alteraron contadores, sesiones o registros de auditoría. Evidencia: [ESART_LOGIN_503_DIAGNOSTICO.json](ESART_LOGIN_503_DIAGNOSTICO.json).

## Estado real encontrado

| Dependencia | Estado físico |
|---|---|
| esart_ref.usuarios | Existe, SELECT autorizado |
| usuarios.intentos_fallidos_consecutivos | Existe, integer |
| usuarios.bloqueado_hasta | Existe, timestamptz |
| esart.roles / esart.usuario_roles | Existen, SELECT autorizado |
| esart.sesiones_usuario | Existe, SELECT autorizado |
| esart.intentos_inicio_sesion | Existe con sus siete columnas originales |
| intentos_inicio_sesion.captcha_requerido | **Falta** |
| intentos_inicio_sesion.captcha_validado | **Falta** |
| esart.limites_inicio_ip | **Falta** |
| esart.estados_acceso_anonimos | **Falta** |
| esart.auditoria_acceso | **Falta** |
| esart.alembic_version | Existe, pero esart_aplicacion no tiene SELECT |

Los modelos Python ya declaran las tablas/columnas nuevas; declarar un modelo no crea su tabla. El código de seguridad está adelantado respecto del esquema físico. La revisión que cubre exactamente las diferencias es **p0003_control_intentos**, cuyo padre es p0002_seguridad_sesiones. No se infiere la revisión física actual del head local: debe consultarla el propietario porque la cuenta operativa no puede leer version_num.

La guardia actual comprueba las tres tablas y captcha_validado. captcha_requerido también falta y es necesaria para registrar intentos después de la migración, aunque no sea una condición independiente en esa guardia. Quitar solo la guardia sustituiría este 503 por errores SQL o dejaría incompletos los controles; no se propone hacerlo.

## Componentes que no originan este 503

- La contraseña de admin.esart no se comprueba antes del rechazo: este resultado no permite concluir que sea correcta o incorrecta.
- El contador o un bloqueo vigente tampoco se consultan antes de la guardia.
- La validación CAPTCHA no se invoca en este punto.
- No hay indicio de fallo de red/proxy como causa de esta excepción: se reproduce directamente en el servicio usando PostgreSQL real.
- La configuración JWT no produce esta excepción concreta. Una falla distinta posterior debe diagnosticarse por separado.

## CAPTCHA: pendiente adicional, distinto del 503

La ruta inyecta obtener_verificador_captcha; su implementación actual devuelve CaptchaNoDisponible, cuyo verificar siempre responde false. No es un proveedor real ni una vía para aceptar autenticación simulada.

Una vez disponible p0003, esa guardia podrá superarse. Sin embargo, después de tres fallos de credenciales el cuarto intento necesita un desafío real del servidor. Mientras el otro proceso no integre ese proveedor, dichos intentos serán rechazados con 401 y captcha_requerido=true, sin comprobar contraseña. **Ese rechazo CAPTCHA no es este 503.** Su respuesta no debe eludirse con un booleano calculado por Angular.

El CAPTCHA inválido consume cuota IP y auditoría, pero no incrementa el contador de credenciales. El séptimo fallo de credenciales con CAPTCHA válido cuando corresponde provoca el bloqueo de tres horas. Los contratos se detallan en [HU_SEGURIDAD_CONTRATO_API.md](HU_SEGURIDAD_CONTRATO_API.md).

## Corrección propuesta, sin ejecutarla

1. El propietario debe consultar mediante SELECT la revisión física y confirmar el destino:

```sql
SELECT current_database(), current_user;
SELECT version_num FROM esart.alembic_version;
```

2. Revisar compatibilidad con p0002 y las diferencias anteriores. Si la revisión no coincide con el padre esperado, detenerse y conciliar; no hacer stamp ni aplicar DDL manualmente para aparentar un historial.
3. Confirmar un respaldo recuperable del estado actual y revisar [p0003_control_intentos.py](../backend/migraciones_principal/versions/p0003_control_intentos.py) y el [SQL de revisión](../backend/sql/HU_SEGURIDAD_P0003_PROPUESTA.sql). El SQL no debe ejecutarse a mano como sustituto de Alembic.
4. **Obtener autorización expresa** antes de aplicar la migración. Solo entonces, con ESART_MIGRACIONES_URL administrativa temporal y desde backend, el comando propuesto es:

```powershell
.venv/Scripts/python.exe -m alembic upgrade p0003_control_intentos
```

5. Verificar las tres tablas, ambas columnas y los permisos de objeto incluidos en la revisión. FastAPI sigue usando esart_aplicacion; no necesita ser propietario o superusuario. No ampliar sus privilegios globales.
6. Coordinar la implementación del verificador CAPTCHA real con el otro proceso y reiniciar los procesos si es necesario. Las opciones de límite IP tienen defaults válidos —30 solicitudes/900 segundos— y no corrigen objetos ausentes.
7. Con autorización para la prueba funcional —un login real escribe sesión/último acceso o intentos— comprobar HTTP y cookies contra el sistema real. No certificar el funcionamiento integral solo porque desaparezca el 503.

No se ejecutó ninguno de los pasos de escritura. Tampoco se ejecutó alembic current en este diagnóstico: el env.py actual contiene CREATE SCHEMA IF NOT EXISTS antes de configurar el contexto; no se trató ese comando como una inspección garantizada de solo lectura. Se consultaron los catálogos directamente y se dejó la revisión física como pendiente de acceso del propietario.

## Resultado

**Corrección necesaria: conciliar y desplegar la estructura de p0003 con autorización; completar después la conexión al CAPTCHA real.** No es necesario tocar Angular para resolver esta causa de disponibilidad. No se desactivó la guardia ni se modificaron contraseñas, roles, usuarios o unidades.
