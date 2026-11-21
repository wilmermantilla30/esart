# ESART — infraestructura documental para firma auditable

## Hallazgos de esquema

En la base local se confirmó, en transacción de solo lectura, PostgreSQL 18.7,
`esart_db` en `127.0.0.1`, con entorno `desarrollo`. Las cuentas reales están en
`esart_ref.usuarios`; roles y permisos en `esart.roles`, `esart.usuario_roles`,
`esart.rol_permisos` y `esart.componentes`; personal y cursos en
`esart.personal_militar` y `esart.cursos`. El esquema `esart_firma` no existe.

El SQL previo proponía identidades, roles, sesiones y TOTP propios, sin vincular
claves foráneas con el modelo real. Se retiró como script ejecutable y quedó como
aviso. La nueva revisión Alembic `p0018_firma_documental` utiliza usuarios y roles
existentes; no copia contraseñas, JWT ni factores TOTP.

## Qué prepara p0018

- Documentos genéricos de tipo certificación u oficio, relacionados con personal,
  curso (opcional) y la cuenta ESART que los genera.
- Versiones PDF con SHA-256, ruta privada y tamaño. Las versiones son inmutables.
- Autorizaciones de firmante referidas a usuarios reales de ESART.
- Solicitudes, consentimiento, firma/evidencia y eventos con correlación e IP.
- Componente `FIRMA_DOCUMENTOS`, concedido por defecto al rol administrador; los
  demás roles requieren asignación explícita en la malla.
- Guardas que rechazan producción, superusuario, base distinta, servidor remoto,
  esquema preexistente o componente ya existente. El downgrade exige que no queden
  documentos ni evidencias.

## Persistencia incluida

La configuración `DOCUMENTOS_PERSISTENCIA_HABILITADA` queda apagada por defecto.
Al habilitarla después de migrar, la generación existente de certificados y oficios
guarda el PDF original en `backend/almacen_privado/documentos` (o en la ruta privada
configurada), registra su versión inicial, huella, evento y evidencia en la misma
transacción, y conserva la descarga original. El endpoint privado de lectura verifica
el hash y permite acceso al emisor o a quien tenga permiso de lectura documental.
Los diplomas conservan el flujo actual y no se guardan en este esquema.

## Pendiente antes de habilitar

- p0018 no se ha aplicado; las tablas aún no existen.
- No hay endpoints de solicitud QR, autenticación móvil, captura de rúbrica,
  autorización de ubicación o emisión final. La persistencia no habilita una firma.
- Debe definirse quién puede autorizar firmantes y asignar la malla de permisos.
- Debe configurarse una ruta de almacenamiento con ACL privada y política de respaldo.
- El celular necesitará una URL HTTPS accesible desde su red para el flujo posterior.
- Una rúbrica visual no es una firma digital PAdES.

## Respaldo y autorización de migración

El respaldo previo no se pudo completar porque la cuenta migradora no existía y la
única URL configurada apuntaba al superusuario `postgres`. Se quitó esa URL de
`backend/.env`; `URL_BASE_DATOS` de la aplicación quedó intacta. La contraseña expuesta
aún debe rotarse. No hubo respaldo nuevo ni escritura en PostgreSQL.

La revisión y el código están preparados, pero la migración debe permanecer pendiente
hasta rotar la credencial expuesta en una salida de diagnóstico, configurar un usuario
migrador no-superusuario, producir/verificar el respaldo y recibir autorización expresa
para aplicar p0018 en la base local de desarrollo.

## Verificaciones ejecutadas

- Pruebas unitarias del almacenamiento privado: 3 aprobadas.
- Pruebas del almacenamiento y generadores PDF: 13 aprobadas, 2 omitidas por las
  condiciones de esas pruebas.
- `ruff` y compilación Python: correctos.
- Alembic identifica `p0018_firma_documental` como único head.
- No se ejecutó la migración ni se modificó PostgreSQL.
