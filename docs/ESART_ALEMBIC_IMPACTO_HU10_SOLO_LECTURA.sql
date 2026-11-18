-- SOLO LECTURA. Generado de constantes AST; no importa ni ejecuta la migraci?n.
-- Ejecutar como propietario, sin escritores, y conservar ambos resultados completos.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;
SELECT clock_timestamp() AS captura, current_database() AS base,current_user AS rol,
 inet_server_addr() AS servidor,inet_server_port() AS puerto,
 current_setting('transaction_read_only') AS solo_lectura;
WITH previsto(codigo,nombre,ruta,orden,padre,activo) AS (VALUES
  ('DASHBOARD','Panel principal','/dashboard',10,NULL,true),
  ('PERSONAL_MILITAR','Personal militar','/personal',20,NULL,true),
  ('PERSONAL_VERIFICAR','Verificar artillero','/personal/verificar',21,'PERSONAL_MILITAR',true),
  ('PERSONAL_HABILITADOS','Habilitados','/personal/habilitados',22,'PERSONAL_MILITAR',true),
  ('PERSONAL_CARGUE_EXCEL','Cargue masivo por Excel','/personal/cargue-excel',23,'PERSONAL_MILITAR',true),
  ('PERSONAL_CARGUE_MANUAL','Registro manual de personal','/personal/cargue-manual',24,'PERSONAL_MILITAR',true),
  ('HOJAS_VIDA','Hojas de vida','/hojas-vida',30,NULL,false),
  ('CURSOS','Cursos académicos','/cursos',40,NULL,false),
  ('NOTAS','Notas académicas','/notas',50,NULL,false),
  ('REENTRENAMIENTOS','Reentrenamientos','/reentrenamientos',60,NULL,false),
  ('CERTIFICACIONES','Certificaciones','/certificaciones',70,NULL,false),
  ('DOCTRINA','Documentos de doctrina','/doctrina',80,NULL,false),
  ('USUARIOS','Gestión de usuarios','/administracion/usuarios',90,NULL,true),
  ('PARAMETROS_HABILITACION','Parámetros de habilitación','/administracion/parametros',95,NULL,true),
  ('PERMISOS','Malla de permisos','/administracion/permisos',100,NULL,true),
  ('AUDITORIA','Auditoría','/administracion/auditoria',110,NULL,true),
  ('VER_DOCUMENTO_COMPLETO','Ver cédula completa',NULL,1000,NULL,true)
)
SELECT p.*,c.nombre AS nombre_actual,c.ruta_angular AS ruta_actual,
 c.orden AS orden_actual,cp.codigo AS padre_actual,c.activo AS activo_actual,
 CASE WHEN c.id IS NULL THEN 'INSERTAR'
 WHEN ROW(c.nombre,c.ruta_angular,c.orden,cp.codigo,c.activo)
 IS DISTINCT FROM ROW(p.nombre,p.ruta,p.orden,p.padre,p.activo) THEN 'SOBRESCRIBIR'
 ELSE 'SIN_CAMBIO_LOGICO' END AS impacto
FROM previsto p LEFT JOIN esart.componentes c USING(codigo)
LEFT JOIN esart.componentes cp ON cp.id=c.componente_padre_id ORDER BY p.orden;
WITH previsto(rol,componente,acceder,crear,leer,actualizar,eliminar) AS (VALUES
  ('ADMINISTRADOR','DASHBOARD',true,false,true,false,false),
  ('ADMINISTRADOR','PERSONAL_MILITAR',true,false,true,false,false),
  ('ADMINISTRADOR','PERSONAL_VERIFICAR',true,false,true,false,false),
  ('ADMINISTRADOR','PERSONAL_HABILITADOS',true,false,true,false,false),
  ('ADMINISTRADOR','PERSONAL_CARGUE_EXCEL',true,true,true,false,false),
  ('ADMINISTRADOR','PERSONAL_CARGUE_MANUAL',true,true,true,true,false),
  ('ADMINISTRADOR','USUARIOS',true,true,true,true,true),
  ('ADMINISTRADOR','PARAMETROS_HABILITACION',true,false,true,true,false),
  ('ADMINISTRADOR','PERMISOS',true,false,true,true,false),
  ('ADMINISTRADOR','AUDITORIA',true,false,true,false,false),
  ('ADMINISTRADOR','VER_DOCUMENTO_COMPLETO',true,false,true,false,false),
  ('USUARIO','DASHBOARD',true,false,true,false,false),
  ('USUARIO','PERSONAL_MILITAR',true,false,true,false,false),
  ('USUARIO','PERSONAL_VERIFICAR',true,false,true,false,false),
  ('USUARIO','PERSONAL_HABILITADOS',true,false,true,false,false),
  ('USUARIO','VER_DOCUMENTO_COMPLETO',true,false,true,false,false)
)
SELECT p.*,rp.puede_acceder AS acceder_actual,rp.puede_crear AS crear_actual,
 rp.puede_leer AS leer_actual,rp.puede_actualizar AS actualizar_actual,
 rp.puede_eliminar AS eliminar_actual,
 CASE WHEN rp.rol_id IS NULL THEN 'INSERTAR_PREDETERMINADO'
 ELSE 'CONSERVAR_EXISTENTE' END AS impacto
FROM previsto p LEFT JOIN esart.roles r ON r.codigo=p.rol
LEFT JOIN esart.componentes c ON c.codigo=p.componente
LEFT JOIN esart.rol_permisos rp ON rp.rol_id=r.id AND rp.componente_id=c.id
ORDER BY p.rol,p.componente;
-- No se modifican las excepciones por usuario en este upgrade.
SELECT count(*) AS excepciones_usuario FROM esart.usuario_permisos;
ROLLBACK;
