# Restablecimiento administrativo de admin.esart

**Preparado para revisión. No ejecutado; pendiente de autorización expresa.** Este procedimiento no es un endpoint y no usa la conexión permanente de FastAPI para restablecer administradores.

## Destino y efecto propuesto

- Base única: esart_db.
- Tabla: esart_ref.usuarios.
- Identidad fija: id **1**, usuario **admin.esart**, activo.
- Debe conservar la asignación existente de **ADMINISTRADOR activo** en esart.usuario_roles/esart.roles.
- Se actualiza exclusivamente **contrasena_hash**; no se cambian activo, fechas, bloqueo, documento, roles, permisos ni otras cuentas.

El login ya busca el usuario sin distinguir mayúsculas, comprueba bcrypt y exige usuario y rol activos. El mecanismo que se reutiliza es aplicacion.seguridad.contrasenas: generar_hash_contrasena y verificar_contrasena, bcrypt directo de costo 12, con sal aleatoria. La nueva entrada debe ser no vacía y de hasta 72 bytes UTF-8. No se copia ADMIN_HASH_CONTRASENA, no se cambia .env y no se usa generar_hash.py, que muestra resultados en terminal.

La sentencia parametrizada propuesta es:

```sql
UPDATE esart_ref.usuarios
SET contrasena_hash = :hash_generado_en_memoria
WHERE id = 1 AND usuario = 'admin.esart' AND activo IS TRUE;
```

El marcador se rellena con SQLAlchemy; no es SQL para ejecutar pegando un hash. El valor nunca se imprime ni se guarda en archivos. No hay INSERT, DDL, GRANT, migraciones ni cambios de otras tablas.

## Sesión administrativa separada

El comando solo acepta una URL asyncpg hacia esart_db en **ESART_ADMIN_URL**, suministrada temporalmente mediante un mecanismo local protegido. No lee la URL de backend/.env ni acepta una URL/contraseña como argumento CLI. Debe ser una conexión directa del propietario de usuarios o un superusuario. Comprueba current_user=session_user y rechaza esart_aplicacion incluso si dispone de permisos de columna. No basta con ejecutar SET ROLE.

No conceder nuevos privilegios al backend para este restablecimiento. No publicar esta URL en Git, .env, historial, capturas o informes. Si el operador necesita introducirla localmente, desde backend en una terminal confiable:

```powershell
$conexionProtegida = Read-Host 'URL administrativa asyncpg de esart_db' -AsSecureString
try {
    $env:ESART_ADMIN_URL = [System.Net.NetworkCredential]::new('', $conexionProtegida).Password
    .venv/Scripts/python.exe -m herramientas.restablecer_admin
} finally {
    Remove-Item Env:ESART_ADMIN_URL -ErrorAction SilentlyContinue
    $conexionProtegida.Dispose()
}
```

Este ejemplo ejecuta **solo el plan de lectura**, sin pedir nueva contraseña ni actualizar nada. Una conexión administrativa ya disponible en el gestor local de secretos puede suministrar la variable sin reintroducirla. No se necesitan credenciales por chat. La existencia de una sesión DBCode no hace accesible automáticamente esa conexión al proceso Python.

## Comando de actualización, solo después de aprobación

Con ESART_ADMIN_URL configurada de forma efímera en esa sesión administrativa:

```powershell
.venv/Scripts/python.exe -m herramientas.restablecer_admin --aplicar
```

No se ejecutó este comando durante la preparación. El operador debe:

1. Revisar el plan que verifica base, operador y cuenta/rol activos.
2. Introducir la nueva contraseña mediante getpass y repetirla mediante una segunda entrada oculta. No usar tuberías, redirecciones ni grabaciones de terminal. Se rechaza el fallback de getpass que podría mostrar la entrada.
3. Escribir exactamente la confirmación:

```text
RESTABLECER admin.esart ID 1 EN esart_db
```

Escribir simplemente «sí», pulsar Enter o pasar --aplicar no sustituye esa confirmación. No hay flag para omitirla. Borrar ESART_ADMIN_URL de la sesión al terminar, también si hay un error.

## Transacción y comprobaciones

El plan previo usa READ ONLY. Después de la confirmación se abre una transacción SQLAlchemy y se comprueban de nuevo la sesión administrativa y el usuario. Se bloquea la fila objetivo FOR UPDATE y se toman bloqueos de lectura sobre sus relaciones de roles para evitar que cambien durante la operación.

Se rechazan triggers de usuario habilitados o reglas de reescritura en usuarios: podrían cambiar fechas u otras tablas. No se deshabilita ningún automatismo para eludir esa revisión. Se genera bcrypt en memoria y se ejecuta el único UPDATE parametrizado. Debe afectar exactamente una fila.

Antes de COMMIT se relee la fila desde PostgreSQL, se verifica la nueva contraseña con el hash realmente almacenado y se compara cada otro campo con su valor previo. Cualquier diferencia o fallo provoca excepción y rollback. El mensaje de éxito se emite después de salir correctamente del contexto transaccional; un fallo de confirmación del servidor no se comunica como éxito. Una desconexión durante COMMIT puede requerir la comprobación posterior para determinar el resultado; no repetir a ciegas.

El CLI desactiva el registro del proceso, utiliza echo=False/hide_parameters y no imprime excepciones completas del controlador. Los resultados contienen únicamente estado, nunca contraseñas, hashes ni tokens. No usar depuradores/trazas que capturen variables locales. Se descartan las referencias a la clave al terminar; Python no garantiza borrado físico de memoria.

No se modifican tablas de sesiones. Por ello este cambio **no revoca los JWT o sesiones previamente emitidos**. Cualquier revocación exige un alcance autorizado distinto.

## Comprobación posterior

Después del COMMIT autorizado, el operador puede repetir la comprobación local de solo lectura:

```powershell
.venv/Scripts/python.exe -m herramientas.crear_administrador_inicial --usuario admin.esart --verificar-contrasena
```

Esta última herramienta usa la conexión de aplicación existente para leer, solicita la clave oculta y compara, sin modificarla ni crear otra cuenta. No usar su opción de alta --aplicar.

Posteriormente probar POST /api/auth/login mediante el formulario Angular o un cliente seguro que no almacene el cuerpo ni las cookies en logs. La respuesta esperada es 200 con cookie HttpOnly. Un login real crea una fila de sesión y actualiza último acceso: **no forma parte del UPDATE de contraseña ni se ejecutó ahora**, pues requiere distinguir esa escritura normal de la operación limitada solicitada.

No se garantiza un HTTP 200 solo por verificar el hash: también intervienen configuración JWT, permisos, sesión y cookies. Si hay otro error se diagnostica sin desactivar autenticación, inventar usuarios o cambiar claves de configuración.

## Evidencia de preparación

Se revisaron Usuario, UsuarioRoles, Rol, el servicio iniciar_sesion y las funciones bcrypt existentes. Las pruebas offline cubren rechazo de destino/cuenta de aplicación/SET ROLE, identidad o rol no válidos, confirmación exacta, automatismos, UPDATE restringido, rechazo de cambios de fechas y verificación del hash releído. No se usó PostgreSQL para ejecutar ese UPDATE, no se solicitó la contraseña real y no se ejecutó Alembic.

Resultados: **161 pruebas aprobadas, 15 omitidas**, con flags de integración de escritura deshabilitados. Ruff limpio en el comando y sus pruebas; compilación Python y ayuda CLI correctas. Esto valida la preparación, no un restablecimiento real ni un login HTTP exitoso.
