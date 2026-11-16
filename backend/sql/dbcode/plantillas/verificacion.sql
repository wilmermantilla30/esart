-- SOLO LECTURA. Ejecutar completo en DBCode después de COMMIT del instalador.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL search_path=pg_catalog;
SET LOCAL timezone='UTC';
DO $identidad$
BEGIN
 IF current_database()<>'esart_db' OR current_user<>'postgres' THEN
  RAISE EXCEPTION 'Verificacion administrativa requiere esart_db / postgres';
 END IF;
END $identidad$;

DO $estructura$
DECLARE esperado JSONB; actual JSONB;
BEGIN
 IF to_regclass('esart.integraciones_control') IS NULL THEN
  RAISE EXCEPTION 'No existe registro de instalacion; no se certifica el despliegue';
 END IF;
 SELECT estructura INTO esperado FROM esart.integraciones_control
  WHERE version=__VERSION__ AND huella_manifiesto=__FIRMA__;
 IF esperado IS NULL THEN RAISE EXCEPTION 'Registro ausente o manifiesto distinto'; END IF;
 __ESTRUCTURA_INTO__
 IF actual IS DISTINCT FROM esperado THEN RAISE EXCEPTION 'La estructura difiere de la registrada'; END IF;
END $estructura$;

__ASERCIONES__

-- Dependencias conservadas y estructura física efectiva, sin datos personales.
SELECT ns.nspname esquema,cl.relname tabla,co.conname,pg_get_constraintdef(co.oid) definicion
FROM pg_constraint co JOIN pg_class cl ON cl.oid=co.conrelid
JOIN pg_namespace ns ON ns.oid=cl.relnamespace
WHERE co.contype='f' AND co.confrelid='esart_ref.unidades_militares'::regclass
ORDER BY 1,2,3;
SELECT table_schema,table_name,column_name,data_type,is_nullable,column_default,is_identity
FROM information_schema.columns WHERE table_schema IN ('esart','esart_ref')
ORDER BY table_schema,table_name,ordinal_position;

SELECT 'cargos' catalogo,count(*) total FROM esart.tipos_cargo
UNION ALL SELECT 'cursos',count(*) FROM esart.tipos_curso
UNION ALL SELECT 'roles',count(*) FROM esart.roles
UNION ALL SELECT 'permisos',count(*) FROM esart.permisos
UNION ALL SELECT 'tipos_unidad',count(*) FROM esart.tipos_unidad
UNION ALL SELECT 'unidades',count(*) FROM esart_ref.unidades_militares;

SELECT codigo,nombre,tipo_codigo,tipo_nombre,superior_codigo,superior_nombre,clasificacion_pendiente
FROM esart.v_unidades_api ORDER BY codigo;

-- Jerarquía real: raíz antes que descendientes. No modifica la tabla.
WITH RECURSIVE arbol AS (
 SELECT id,unidad_superior_id,codigo,nombre,0 nivel,ARRAY[codigo::text] ruta
 FROM esart_ref.unidades_militares WHERE unidad_superior_id IS NULL
 UNION ALL
 SELECT u.id,u.unidad_superior_id,u.codigo,u.nombre,a.nivel+1,a.ruta||u.codigo::text
 FROM arbol a JOIN esart_ref.unidades_militares u ON u.unidad_superior_id=a.id
)
SELECT nivel,codigo,nombre,ruta FROM arbol ORDER BY ruta;

-- Guardar estos hashes antes y después de repetir el instalador: deben coincidir
-- en ausencia de escrituras externas. Incluyen identificadores y todas las fechas.
SELECT 'unidades' entidad,md5(coalesce(string_agg(to_jsonb(u)::text,'' ORDER BY u.codigo),'')) huella
FROM esart_ref.unidades_militares u
UNION ALL SELECT 'tipos',md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY t.codigo),'')) FROM esart.tipos_unidad t
UNION ALL SELECT 'cargos',md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY t.nombre),'')) FROM esart.tipos_cargo t
UNION ALL SELECT 'cursos',md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY t.codigo),'')) FROM esart.tipos_curso t
UNION ALL SELECT 'roles',md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY t.codigo),'')) FROM esart.roles t
UNION ALL SELECT 'permisos',md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY t.codigo),'')) FROM esart.permisos t;
DO $estado_secuencia$
DECLARE sec TEXT; r RECORD;
BEGIN
 sec:=pg_get_serial_sequence('esart_ref.unidades_militares','id');
 EXECUTE format('SELECT last_value,is_called FROM %s',sec) INTO r;
 RAISE NOTICE 'Secuencia %, last_value %, is_called %',sec,r.last_value,r.is_called;
END $estado_secuencia$;

-- Prueba efectiva sin cambiar conexión de FastAPI ni solicitar otra contraseña.
SET LOCAL ROLE esart_aplicacion;
SELECT current_database() base,current_user cuenta_operativa,count(*) unidades,
       count(tipo_codigo) clasificadas FROM esart.v_unidades_api;
SELECT * FROM esart.v_unidades_api WHERE codigo='FUTOM';
__LECTURA_Y_ESCRITURA__
RESET ROLE;
SELECT version,metodo,huella_manifiesto,aplicada_en,operador,resumen
FROM esart.integraciones_control WHERE version=__VERSION__;
COMMIT;
-- No se ejecutan INSERT, UPDATE, pruebas destructivas ni consultas a bases alternativas.
