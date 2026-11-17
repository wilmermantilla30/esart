-- SOLO LECTURA. Ejecutar en la misma conexión DBCode donde se insertaron las políticas.
SELECT current_database() AS base,
       current_user AS rol,
       inet_server_addr() AS servidor,
       inet_server_port() AS puerto,
       pg_postmaster_start_time() AS inicio_instancia;

SELECT codigo, activa, requiere_totp, vigencia_segundos
FROM seguridad.politicas_accion
WHERE codigo IN ('LOGIN_TOTP', 'DESBLOQUEO_TOTP')
ORDER BY codigo;

-- La API usa 127.0.0.1:5432/esart_db.
-- Si DBCode ve las filas y una conexión nueva no, revisar la transacción pendiente.
-- Confirmarla solo después de comprobar que contiene los INSERT previstos.
