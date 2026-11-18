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
  WHERE version='dbcode_hu03_hu04_v1' AND huella_manifiesto='b039ade13bfe7f3420b19804ae47d2bfa83d7059c005f5adf6b37f1c171b8c89';
 IF esperado IS NULL THEN RAISE EXCEPTION 'Registro ausente o manifiesto distinto'; END IF;
 WITH g(s,n) AS (VALUES ('esart','artillero_cargos'),('esart','artillero_certificaciones'),('esart','artillero_cursos'),('esart','auditoria_eventos'),('esart','componentes'),('esart','hoja_vida_artillero'),('esart','importaciones_excel'),('esart','intentos_inicio_sesion'),('esart','permisos'),('esart','personal_militar'),('esart','requisitos_habilitacion'),('esart','rol_permisos'),('esart','roles'),('esart','roles_permisos'),('esart','sesiones_usuario'),('esart','tipos_cargo'),('esart','tipos_certificacion'),('esart','tipos_curso'),('esart','tipos_unidad'),('esart','usuario_permisos'),('esart_ref','sistemas_artilleria'),('esart_ref','unidades_militares'),('esart_ref','usuarios'),('esart','integraciones_control'))
 SELECT jsonb_build_object(
  'columnas',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,'c',a.attname,
    'tipo',format_type(a.atttypid,a.atttypmod),'null',NOT a.attnotnull,
    'identidad',a.attidentity::text,'generada',a.attgenerated::text,'collation',a.attcollation::regcollation::text,
    'defecto',pg_get_expr(d.adbin,d.adrelid)) ORDER BY ns.nspname,cl.relname,a.attnum)
    FROM pg_attribute a JOIN pg_class cl ON cl.oid=a.attrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text
    LEFT JOIN pg_attrdef d ON d.adrelid=cl.oid AND d.adnum=a.attnum WHERE a.attnum>0 AND NOT a.attisdropped),
  'constraints',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,'nombre',co.conname,
     'def',pg_get_constraintdef(co.oid),'validada',co.convalidated) ORDER BY ns.nspname,cl.relname,co.conname)
    FROM pg_constraint co JOIN pg_class cl ON cl.oid=co.conrelid
    JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text),
  'indices',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,
     'def',pg_get_indexdef(ix.indexrelid),
     'valido',ix.indisvalid) ORDER BY ns.nspname,cl.relname,ix.indexrelid::regclass::text)
    FROM pg_index ix JOIN pg_class cl ON cl.oid=ix.indrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text),
  'triggers',(SELECT jsonb_agg(jsonb_build_object('s',ns.nspname,'t',cl.relname,'nombre',tg.tgname,
     'def',pg_get_triggerdef(tg.oid),'estado',tg.tgenabled::text) ORDER BY ns.nspname,cl.relname,tg.tgname)
    FROM pg_trigger tg JOIN pg_class cl ON cl.oid=tg.tgrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    JOIN g ON g.s=ns.nspname::text AND g.n=cl.relname::text WHERE NOT tg.tgisinternal),
  'funciones',(SELECT jsonb_agg(jsonb_build_object('nombre',p.proname,'cuerpo',p.prosrc,
     'seguridad',p.prosecdef,'config',p.proconfig) ORDER BY p.proname)
    FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace WHERE ns.nspname='esart'
     AND p.proname IN ('actualizar_fecha_hu0304','inmutabilidad_auditoria_hu0304')),
  'vista',(SELECT jsonb_build_object('def',pg_get_viewdef(cl.oid),'opciones',cl.reloptions)
    FROM pg_class cl JOIN pg_namespace ns ON ns.oid=cl.relnamespace
    WHERE ns.nspname='esart' AND cl.relname='v_unidades_api')
 ) INTO actual;
 IF actual IS DISTINCT FROM esperado THEN RAISE EXCEPTION 'La estructura difiere de la registrada'; END IF;
END $estructura$;

DO $integridad$
DECLARE d JSONB := '{"roles": [{"codigo": "ADMINISTRADOR", "nombre": "Administrador", "descripcion": "Administra usuarios y mallas de permisos", "activo": true}, {"codigo": "USUARIO", "nombre": "Usuario", "descripcion": "Acceso segun permisos asignados", "activo": true}], "cargos": [{"nombre": "Comandante de pieza", "descripcion": "Oficial o suboficial responsable de la operacion y empleo tactico de una pieza de artilleria.", "cuenta_para_coofu": true, "activo": true}, {"nombre": "Comandante de Bateria", "descripcion": "Oficial responsable del mando, control y empleo operacional de una bateria de artilleria.", "cuenta_para_coofu": true, "activo": true}, {"nombre": "Armamento Mayor", "descripcion": "Suboficial tecnico responsable del mantenimiento y control del armamento de la unidad.", "cuenta_para_coofu": false, "activo": true}, {"nombre": "Tecnico Mantenimiento", "descripcion": "Especialista tecnico en mantenimiento de sistemas y equipos de artilleria.", "cuenta_para_coofu": false, "activo": true}, {"nombre": "Coordinador de Fuegos", "descripcion": "Oficial responsable de planear, coordinar y controlar el empleo del fuego de artilleria en apoyo de la maniobra.", "cuenta_para_coofu": true, "activo": true}], "cursos": [{"codigo": "TECNICA", "nombre": "Tecnico profesional en mantenimiento mecanico aplicado a la operacion de armas de artilleria", "tipo": "EDUCACION_SUPERIOR", "modalidad": "PRESENCIAL", "duracion_semanas": 43, "activo": true}, {"codigo": "COOFU", "nombre": "Coordinador de Fuegos", "tipo": "EDUCACION_MILITAR", "modalidad": "VIRTUAL", "duracion_semanas": 2, "activo": true}, {"codigo": "SACLI", "nombre": "Curso sistemas de artilleria liviana", "tipo": "EDUCACION_MILITAR", "modalidad": "PRESENCIAL", "duracion_semanas": 10, "activo": true}, {"codigo": "SACME", "nombre": "Curso sistemas de artilleria mediana", "tipo": "EDUCACION_MILITAR", "modalidad": "PRESENCIAL", "duracion_semanas": 11, "activo": true}, {"codigo": "COSET", "nombre": "Curso control y seguimiento al tiro", "tipo": "EDUCACION_MILITAR", "modalidad": "PRESENCIAL", "duracion_semanas": 10, "activo": true}, {"codigo": "ADA", "nombre": "Curso de artilleria de defensa aerea", "tipo": "EDUCACION_MILITAR", "modalidad": "PRESENCIAL", "duracion_semanas": 8, "activo": true}, {"codigo": "OA", "nombre": "Curso observacion adelantada", "tipo": "EDUCACION_MILITAR", "modalidad": "PRESENCIAL", "duracion_semanas": 5, "activo": true}, {"codigo": "CAPINTE", "nombre": "Curso capacitacion intermedia", "tipo": "EDUCACION_MILITAR", "modalidad": "PRESENCIAL", "duracion_semanas": 12, "activo": true}, {"codigo": "COMANDO", "nombre": "Especializacion del arma — curso Comando", "tipo": "ESPECIALIZACION", "modalidad": "PRESENCIAL", "duracion_semanas": 4, "activo": true}, {"codigo": "INTERMEDIO", "nombre": "Especializacion del arma — curso Intermedio", "tipo": "ESPECIALIZACION", "modalidad": "PRESENCIAL", "duracion_semanas": 5, "activo": true}, {"codigo": "COTAC", "nombre": "Especializacion del arma — curso COTAC", "tipo": "ESPECIALIZACION", "modalidad": "PRESENCIAL", "duracion_semanas": 2, "activo": true}, {"codigo": "CAPAVAN", "nombre": "Especializacion del arma — curso CAPAVAN", "tipo": "ESPECIALIZACION", "modalidad": "PRESENCIAL", "duracion_semanas": 2, "activo": true}, {"codigo": "ALFEREZ", "nombre": "Especializacion del arma — curso Alfereces", "tipo": "ESPECIALIZACION", "modalidad": "PRESENCIAL", "duracion_semanas": 5, "activo": true}, {"codigo": "DRAGONEANTES", "nombre": "Especializacion del arma — curso Dragoneantes", "tipo": "ESPECIALIZACION", "modalidad": "PRESENCIAL", "duracion_semanas": 8, "activo": true}], "permisos": [{"codigo": "gestionar_sistemas", "descripcion": "Crear, editar y dar de baja sistemas de artilleria."}, {"codigo": "ver_sistemas", "descripcion": "Consultar la ficha tecnica de cada sistema."}, {"codigo": "estado_ubicacion", "descripcion": "Ver el estado operacional y la posicion geografica de cada sistema en el mapa."}, {"codigo": "gestionar_operadores", "descripcion": "Asignar y cambiar los soldados operadores de cada sistema de artilleria."}, {"codigo": "graficar_blancos", "descripcion": "Graficar blancos, rangos efectivos de fuego y zonas de impacto sobre el mapa."}, {"codigo": "graficar_rutas", "descripcion": "Dibujar y consultar rutas de desplazamiento de sistemas de artilleria."}, {"codigo": "graficar_plan_operacion", "descripcion": "Dibujar planes de operacion sobre el mapa con sistemas asignados."}, {"codigo": "calculos_balisticos", "descripcion": "Ejecutar calculos de tiro: elevacion, deriva, carga y correcciones."}, {"codigo": "configurar_tablas_balisticas", "descripcion": "Gestionar tablas balisticas y parametros de municion por tipo de sistema."}, {"codigo": "misiones_fuego", "descripcion": "Crear, ejecutar y consultar misiones de fuego de artilleria."}, {"codigo": "aprobar_mision", "descripcion": "Aprobar o rechazar ordenes de fuego (nivel comando)."}, {"codigo": "cancelar_mision", "descripcion": "Cancelar una mision de fuego que ya se encuentra en ejecucion."}, {"codigo": "gestionar_municion", "descripcion": "Registrar consumo, altas y bajas de municion. Gestionar stock."}, {"codigo": "ver_municion", "descripcion": "Consultar existencias de municion y alertas de minimos."}, {"codigo": "gestionar_inventario", "descripcion": "Administrar repuestos, insumos y partes de los sistemas."}, {"codigo": "ver_inventario", "descripcion": "Consultar el inventario de repuestos e insumos."}, {"codigo": "ver_mantenimiento", "descripcion": "Consultar historial de mantenimientos realizados y proximas fechas programadas."}, {"codigo": "registrar_mantenimiento", "descripcion": "Cargar la ejecucion de un mantenimiento: fecha, tipo y nivel realizado."}, {"codigo": "programar_mantenimiento", "descripcion": "Agendar fechas de proximos mantenimientos preventivos."}, {"codigo": "infografia_sistema", "descripcion": "Ver la tarjeta completa del sistema al hacer clic en el mapa: comandante, operadores, municion, disparos, mantenimiento y certificaciones."}, {"codigo": "ver_infografia_personal", "descripcion": "Ver unicamente la seccion de personal y certificaciones en la infografia del sistema."}, {"codigo": "historial_sistemas", "descripcion": "Consultar historial de movimientos, mantenimientos y disparos realizados."}, {"codigo": "exportar_historial", "descripcion": "Descargar el historial de sistemas en formato Excel o PDF."}, {"codigo": "gestionar_unidades", "descripcion": "Registrar nuevas unidades militares en el sistema (batallones, baterias, etc.). Util para agregar unidades a las que se asignan sistemas de artilleria."}, {"codigo": "modulo_esart", "descripcion": "Acceso total al modulo de la Escuela de Artilleria: cursos, instructores, alumnos, malla curricular y reentrenamientos."}, {"codigo": "ver_personal_esart", "descripcion": "Consultar personal y certificaciones de la ESART sin poder modificar."}, {"codigo": "gestionar_doctrina", "descripcion": "Subir, editar y desactivar documentos PDF de doctrina artillera (balistica, protocolos, manuales ejercito, doctrina ejercito, manuales sistemas)."}, {"codigo": "ver_doctrina", "descripcion": "Consultar y descargar los documentos PDF de doctrina artillera disponibles."}, {"codigo": "reportes_enviar_ver", "descripcion": "Acceso completo al modulo de reportes: enviar, recibir y consultar informes."}, {"codigo": "reportes_solo_enviar", "descripcion": "Enviar informes unicamente, sin acceso a los recibidos."}, {"codigo": "reportes_solo_ver", "descripcion": "Consultar informes recibidos sin poder enviar."}, {"codigo": "reportes_exportar", "descripcion": "Generar y descargar reportes en PDF o Excel."}, {"codigo": "ver_auditoria", "descripcion": "Consultar el log de actividad: quien hizo que accion y cuando."}, {"codigo": "ver_dashboard", "descripcion": "Acceder al panel general con indicadores del teatro de operaciones."}, {"codigo": "configurar_alertas", "descripcion": "Definir umbrales de alerta: dias sin mantenimiento, stock minimo, disparos acumulados."}, {"codigo": "recibir_alertas", "descripcion": "Recibir notificaciones automaticas cuando se superen los umbrales configurados."}], "tipos": [{"codigo": "BAACA", "nombre": "Batallón de Artillería", "activo": true}, {"codigo": "BAADA", "nombre": "Batallón de Artillería de Defensa Aérea", "activo": true}, {"codigo": "BATAR", "nombre": "Batería de Artillería", "activo": true}, {"codigo": "BR", "nombre": "Brigada", "activo": true}, {"codigo": "CECFU", "nombre": "Centro de Coordinación de Fuegos", "activo": true}, {"codigo": "CEDOC", "nombre": "Centro de Educación y Doctrina", "activo": true}, {"codigo": "CEM", "nombre": "Centro de Educación Militar", "activo": true}, {"codigo": "DIV", "nombre": "División", "activo": true}, {"codigo": "ESART", "nombre": "Escuela de Artillería", "activo": true}], "unidades": [{"codigo": "CEDOC", "nombre": "Centro de Educación y Doctrina", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "CEDOC"}, {"codigo": "DAAVA", "nombre": "División de Aviación y Asalto Aéreo", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV01", "nombre": "Primera División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV02", "nombre": "Segunda División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV03", "nombre": "Tercera División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV04", "nombre": "Cuarta División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV05", "nombre": "Quinta División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV06", "nombre": "Sexta División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV07", "nombre": "Séptima División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIV08", "nombre": "Octava División", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "DIVFE", "nombre": "División de Fuerzas Especiales", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": "DIV"}, {"codigo": "FUTOM", "nombre": "Fuerza de Tarea Omega", "sigla": null, "activa": true, "superior_codigo": null, "tipo_codigo": null}, {"codigo": "BR01", "nombre": "Primera Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR03", "nombre": "Tercera Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV03", "tipo_codigo": "BR"}, {"codigo": "BR04", "nombre": "Cuarta Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV07", "tipo_codigo": "BR"}, {"codigo": "BR05", "nombre": "Quinta Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV02", "tipo_codigo": "BR"}, {"codigo": "BR08", "nombre": "Octava Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR09", "nombre": "Novena Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR10", "nombre": "Décima Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV01", "tipo_codigo": "BR"}, {"codigo": "BR13", "nombre": "Décimo Tercera Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV05", "tipo_codigo": "BR"}, {"codigo": "BR18", "nombre": "Décimo Octava Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV08", "tipo_codigo": "BR"}, {"codigo": "BR27", "nombre": "Vigésimo Séptima Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV06", "tipo_codigo": "BR"}, {"codigo": "BR30", "nombre": "Trigésima Brigada", "sigla": null, "activa": true, "superior_codigo": "DIV02", "tipo_codigo": "BR"}, {"codigo": "CEMIL", "nombre": "Centro de Educación Militar", "sigla": null, "activa": true, "superior_codigo": "CEDOC", "tipo_codigo": "CEM"}, {"codigo": "BAACA1", "nombre": "Batallón de Artillería de Campaña N°1", "sigla": null, "activa": true, "superior_codigo": "BR01", "tipo_codigo": "BAACA"}, {"codigo": "BAACA10", "nombre": "Batallón de Artillería de Campaña N°10", "sigla": null, "activa": true, "superior_codigo": "BR10", "tipo_codigo": "BAACA"}, {"codigo": "BAACA13", "nombre": "Batallón de Artillería de Campaña N°13", "sigla": null, "activa": true, "superior_codigo": "BR13", "tipo_codigo": "BAACA"}, {"codigo": "BAACA18", "nombre": "Batallón de Artillería de Campaña N°18", "sigla": null, "activa": true, "superior_codigo": "BR18", "tipo_codigo": "BAACA"}, {"codigo": "BAACA2", "nombre": "Batallón de Artillería de Campaña N°2", "sigla": null, "activa": true, "superior_codigo": "BR10", "tipo_codigo": "BAACA"}, {"codigo": "BAACA27", "nombre": "Batallón de Artillería de Campaña N°27", "sigla": null, "activa": true, "superior_codigo": "BR27", "tipo_codigo": "BAACA"}, {"codigo": "BAACA3", "nombre": "Batallón de Artillería de Campaña N°3", "sigla": null, "activa": true, "superior_codigo": "BR03", "tipo_codigo": "BAACA"}, {"codigo": "BAACA30", "nombre": "Batallón de Artillería de Campaña N°30", "sigla": null, "activa": true, "superior_codigo": "BR30", "tipo_codigo": "BAACA"}, {"codigo": "BAACA4", "nombre": "Batallón de Artillería de Campaña N°4", "sigla": null, "activa": true, "superior_codigo": "BR04", "tipo_codigo": "BAACA"}, {"codigo": "BAACA5", "nombre": "Batallón de Artillería de Campaña N°5", "sigla": null, "activa": true, "superior_codigo": "BR05", "tipo_codigo": "BAACA"}, {"codigo": "BAACA6", "nombre": "Batallón de Artillería de Campaña N°6", "sigla": null, "activa": true, "superior_codigo": "BR05", "tipo_codigo": "BAACA"}, {"codigo": "BAACA8", "nombre": "Batallón de Artillería de Campaña N°8", "sigla": null, "activa": true, "superior_codigo": "BR08", "tipo_codigo": "BAACA"}, {"codigo": "BAACA9", "nombre": "Batallón de Artillería de Campaña N°9", "sigla": null, "activa": true, "superior_codigo": "BR09", "tipo_codigo": "BAACA"}, {"codigo": "BAADA1", "nombre": "Batallón de Artillería de Defensa Aérea N°1", "sigla": null, "activa": true, "superior_codigo": "BR10", "tipo_codigo": "BAADA"}, {"codigo": "BAADA2", "nombre": "Batallón de Artillería de Defensa Aérea N°2", "sigla": null, "activa": true, "superior_codigo": "BR05", "tipo_codigo": "BAADA"}, {"codigo": "ESART", "nombre": "Escuela de Artillería", "sigla": null, "activa": true, "superior_codigo": "CEMIL", "tipo_codigo": "ESART"}]}'::jsonb; grupo TEXT; n TEXT; clave TEXT; r JSONB; real JSONB; k TEXT;
        rel RECORD; locales TEXT; uniones TEXT; huerfanos BIGINT;
BEGIN
 FOR grupo,n,clave IN SELECT * FROM (VALUES ('roles','roles','codigo'),('cargos','tipos_cargo','nombre'),
  ('cursos','tipos_curso','codigo'),('permisos','permisos','codigo'),('tipos','tipos_unidad','codigo')) x LOOP
  FOR r IN SELECT value FROM jsonb_array_elements(d->grupo) LOOP
   EXECUTE format('SELECT to_jsonb(t) FROM esart.%I t WHERE %I=$1',n,clave) INTO real USING r->>clave;
   IF real IS NULL THEN RAISE EXCEPTION 'Referencia faltante: % / %',grupo,r->>clave; END IF;
   FOR k IN SELECT jsonb_object_keys(r) LOOP
    IF real->k IS DISTINCT FROM r->k THEN RAISE EXCEPTION 'Referencia incompatible: % / % / %',grupo,r->>clave,k; END IF;
   END LOOP;
  END LOOP;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(d->'unidades') LOOP
  SELECT jsonb_build_object('codigo',u.codigo,'nombre',u.nombre,'sigla',u.sigla,'activa',u.activa,
                           'superior_codigo',p.codigo,'tipo_codigo',t.codigo) INTO real
  FROM esart_ref.unidades_militares u LEFT JOIN esart_ref.unidades_militares p ON p.id=u.unidad_superior_id
  LEFT JOIN esart.tipos_unidad t ON t.id=u.tipo_unidad_id WHERE u.codigo=r->>'codigo';
  IF real IS DISTINCT FROM r THEN RAISE EXCEPTION 'Unidad/jerarquia no coincide con matriz: %',r->>'codigo'; END IF;
 END LOOP;
 IF (SELECT count(*) FROM esart_ref.unidades_militares)<>40 OR
    (SELECT count(*) FROM esart_ref.unidades_militares WHERE tipo_unidad_id IS NOT NULL)<>39 OR
    NOT EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE codigo='FUTOM' AND tipo_unidad_id IS NULL) THEN
  RAISE EXCEPTION 'Se requieren 40 unidades, 39 clasificadas y FUTOM pendiente; no se borran excedentes';
 END IF;
 IF EXISTS(SELECT 1 FROM esart_ref.unidades_militares WHERE uuid_publico IS NULL) THEN
  RAISE EXCEPTION 'Falta UUID publico de una unidad';
 END IF;
 IF EXISTS(WITH RECURSIVE j AS (
   SELECT id,unidad_superior_id,ARRAY[id] camino,false ciclo FROM esart_ref.unidades_militares
   UNION ALL SELECT p.id,p.unidad_superior_id,j.camino||p.id,p.id=ANY(j.camino)
   FROM j JOIN esart_ref.unidades_militares p ON p.id=j.unidad_superior_id WHERE NOT j.ciclo
  ) SELECT 1 FROM j WHERE ciclo) THEN RAISE EXCEPTION 'Ciclo en jerarquia'; END IF;
 IF EXISTS(SELECT 1 FROM pg_constraint co JOIN pg_namespace ns ON ns.oid=co.connamespace
           WHERE ns.nspname IN ('esart','esart_ref') AND NOT co.convalidated) OR
    EXISTS(SELECT 1 FROM pg_index ix JOIN pg_class cl ON cl.oid=ix.indrelid
           JOIN pg_namespace ns ON ns.oid=cl.relnamespace
           WHERE ns.nspname IN ('esart','esart_ref') AND NOT ix.indisvalid) THEN
  RAISE EXCEPTION 'Restriccion no validada o indice invalido';
 END IF;
 -- Verificar independientemente TODAS las FK institucionales, sin mostrar filas privadas.
 FOR rel IN SELECT co.oid,co.conname,co.conrelid,co.confrelid,
   sn.nspname s,sc.relname t,dn.nspname ds,dc.relname dt,co.conkey,co.confkey
  FROM pg_constraint co JOIN pg_class sc ON sc.oid=co.conrelid JOIN pg_namespace sn ON sn.oid=sc.relnamespace
  JOIN pg_class dc ON dc.oid=co.confrelid JOIN pg_namespace dn ON dn.oid=dc.relnamespace
  WHERE co.contype='f' AND sn.nspname IN ('esart','esart_ref') LOOP
  SELECT string_agg(format('o.%I IS NOT NULL',a.attname),' AND ' ORDER BY x.pos),
         string_agg(format('o.%I=d.%I',a.attname,b.attname),' AND ' ORDER BY x.pos)
   INTO locales,uniones FROM unnest(rel.conkey,rel.confkey) WITH ORDINALITY AS x(a,b,pos)
   JOIN pg_attribute a ON a.attrelid=rel.conrelid AND a.attnum=x.a
   JOIN pg_attribute b ON b.attrelid=rel.confrelid AND b.attnum=x.b;
  EXECUTE format('SELECT count(*) FROM %I.%I o WHERE %s AND NOT EXISTS(SELECT 1 FROM %I.%I d WHERE %s)',
                 rel.s,rel.t,locales,rel.ds,rel.dt,uniones) INTO huerfanos;
  IF huerfanos<>0 THEN RAISE EXCEPTION 'Huerfanos en %.% / %',rel.s,rel.t,rel.conname; END IF;
 END LOOP;
END $integridad$;


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
SELECT t.tabla,has_table_privilege(current_user,t.tabla,'SELECT') lectura,
 has_table_privilege(current_user,t.tabla,'INSERT') insercion,
 has_table_privilege(current_user,t.tabla,'UPDATE') actualizacion
 FROM (VALUES ('esart_ref.unidades_militares'),('esart.tipos_unidad'),('esart.tipos_cargo'),
 ('esart.tipos_curso'),('esart.roles'),('esart.permisos')) AS t(tabla);
RESET ROLE;
SELECT version,metodo,huella_manifiesto,aplicada_en,operador,resumen
FROM esart.integraciones_control WHERE version='dbcode_hu03_hu04_v1';
COMMIT;
-- No se ejecutan INSERT, UPDATE, pruebas destructivas ni consultas a bases alternativas.
