-- Solo para psql: \gexec ejecuta exclusivamente los SELECT generados abajo.
-- Usar en origen sin escritores y copia restaurada; conservar ambas salidas privadas.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SELECT clock_timestamp() AS captura,current_database() AS base,current_user AS rol,
       inet_server_addr() AS servidor,inet_server_port() AS puerto,
       current_setting('transaction_read_only') AS solo_lectura;
SELECT format('SELECT %L AS esquema, %L AS tabla, count(*) AS filas FROM %I.%I;',
              n.nspname,c.relname,n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p') AND n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname,c.relname
\gexec
ROLLBACK;
