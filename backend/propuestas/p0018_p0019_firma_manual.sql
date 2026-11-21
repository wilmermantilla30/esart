-- =====================================================================================
-- ESART — p0018 (firma documental conciliada) + p0019 (permisos de la firma desde el celular)
-- Ejecución MANUAL como postgres sobre esart_db. NO EJECUTAR DESDE LA APLICACIÓN.
-- Generado por herramientas/generar_sql_p0018_p0019.py desde las migraciones (no editar a mano).
--
-- ANTES: sacar un respaldo de esart_db (ver docs/ESART_FIRMA_MOVIL.md, sección "Aplicar en esart_db").
--
-- Todo va en UNA transacción: si una guarda falla, PostgreSQL revierte todo y no queda nada a medias.
-- Las guardas abortan si la estructura de esart_firma no es exactamente la inventariada, si ya se
-- ejecutó antes, o si la autenticación heredada tiene datos. Al final se verifica que los conteos de
-- las 21 tablas y los 5 roles / 8 permisos sigan idénticos.
--
-- No modifica esart.alembic_version: esart_db sigue marcando p0014 porque p0015/p0016 también se
-- aplicaron a mano y p0017 (TOTP administrativo) no está aplicada. Si en el futuro se usa Alembic,
-- p0018 detectará sus objetos y se detendrá sin tocar nada (ver la documentación).
-- =====================================================================================

\set ON_ERROR_STOP on

-- Estado ANTES (solo lectura)
SELECT 'antes' AS momento, count(*) FILTER (WHERE relkind = 'r') AS tablas_esart_firma
FROM pg_class WHERE relnamespace = to_regnamespace('esart_firma');
SELECT 'roles_firma' AS tabla, count(*) FROM esart_firma.roles_firma
UNION ALL SELECT 'permisos_firma', count(*) FROM esart_firma.permisos_firma;

BEGIN;

-- 1. Guardas previas -----------------------------------------------------------------
DO $guardas$
DECLARE
  t record;
  actual text;
  faltantes text[];
BEGIN
  IF to_regnamespace('esart_firma') IS NULL THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: no existe el esquema esart_firma (este script es para la base con el esquema heredado).';
  END IF;
  -- Objetos nuevos ausentes (si existen, el script ya se ejecutó o hay otro origen: no repetir).
  IF to_regclass('esart_firma.documentos') IS NOT NULL OR to_regclass('esart_firma.versiones_documento') IS NOT NULL
     OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('esart_firma.identidades') AND attname = 'usuario_id' AND NOT attisdropped)
     OR to_regprocedure('esart_firma.rechazar_autenticacion_heredada()') IS NOT NULL THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: ya existen objetos de p0018 (documentos, identidades.usuario_id o la función nueva). No se ejecuta dos veces.';
  END IF;
  -- Huella exacta de las 21 tablas heredadas (columnas en orden, tipos, NOT NULL y restricciones).
  FOR t IN SELECT * FROM (VALUES
      ('asignaciones_rol', 'id:bigint:true,identidad_id:bigint:true,rol_id:bigint:true,vigente_desde:timestamp with time zone:true,vigente_hasta:timestamp with time zone:false,asignado_por:bigint:false,motivo:text:false', ARRAY['asignaciones_rol_asignado_por_fkey', 'asignaciones_rol_check', 'asignaciones_rol_identidad_id_fkey', 'asignaciones_rol_pkey', 'asignaciones_rol_rol_id_fkey']::text[]),
      ('auditoria_cambios', 'id:bigint:true,evento_id:uuid:true,entidad:text:true,clave_registro:text:true,campos_anteriores_filtrados:jsonb:false,campos_nuevos_filtrados:jsonb:false,registrado_en:timestamp with time zone:true', ARRAY['auditoria_cambios_evento_id_fkey', 'auditoria_cambios_pkey']::text[]),
      ('auditoria_eventos', 'id:bigint:true,evento_id:uuid:true,ocurrido_en:timestamp with time zone:true,actor_id:bigint:false,sesion_id:uuid:false,correlacion_id:uuid:false,accion:text:true,recurso_tipo:text:true,recurso_id:text:false,resultado:text:true,ip:inet:false,agente_usuario:text:false,detalle_filtrado:jsonb:true,hash_anterior:character(64):false,hash_evento:character(64):true', ARRAY['auditoria_eventos_actor_id_fkey', 'auditoria_eventos_evento_id_key', 'auditoria_eventos_hash_anterior_check', 'auditoria_eventos_hash_evento_check', 'auditoria_eventos_pkey', 'auditoria_eventos_resultado_check', 'auditoria_eventos_sesion_id_fkey']::text[]),
      ('autorizaciones_firmantes', 'id:uuid:true,identidad_id:bigint:true,tipo_certificado:text:true,cargo:text:true,grado:text:false,vigente_desde:timestamp with time zone:true,vigente_hasta:timestamp with time zone:false,documento_autorizacion_sha256:character(64):false,concedido_por:bigint:false,revocado_en:timestamp with time zone:false', ARRAY['autorizaciones_firmantes_check', 'autorizaciones_firmantes_concedido_por_fkey', 'autorizaciones_firmantes_identidad_id_fkey', 'autorizaciones_firmantes_pkey']::text[]),
      ('certificados', 'id:uuid:true,numero:text:true,tipo:text:true,personal_militar_ref:text:false,curso_ref:text:false,datos_emitidos:jsonb:true,plantilla_id:uuid:false,estado:text:true,version_actual:integer:true,creado_por:bigint:true,creado_en:timestamp with time zone:true,emitido_en:timestamp with time zone:false,revocado_en:timestamp with time zone:false,motivo_revocacion:text:false,codigo_verificacion_hash:character(64):false', ARRAY['certificados_check', 'certificados_codigo_verificacion_hash_check', 'certificados_codigo_verificacion_hash_key', 'certificados_creado_por_fkey', 'certificados_estado_check', 'certificados_numero_key', 'certificados_pkey', 'certificados_plantilla_id_fkey', 'certificados_version_actual_check']::text[]),
      ('consentimientos_firma', 'id:uuid:true,solicitud_id:uuid:true,texto_aceptado:text:true,version_texto:text:true,documento_sha256:character(64):true,confirmado_en:timestamp with time zone:true,ip:inet:false,agente_usuario:text:false,desafio_id:uuid:true', ARRAY['consentimientos_firma_desafio_id_fkey', 'consentimientos_firma_desafio_id_key', 'consentimientos_firma_documento_sha256_check', 'consentimientos_firma_pkey', 'consentimientos_firma_solicitud_id_fkey', 'consentimientos_firma_solicitud_id_key']::text[]),
      ('desafios_autenticacion', 'id:uuid:true,identidad_id:bigint:true,sesion_id:uuid:false,proposito:text:true,recurso_id:uuid:false,token_hash:text:false,intentos:smallint:true,max_intentos:smallint:true,creado_en:timestamp with time zone:true,expira_en:timestamp with time zone:true,validado_en:timestamp with time zone:false,consumido_en:timestamp with time zone:false', ARRAY['desafios_autenticacion_check', 'desafios_autenticacion_identidad_id_fkey', 'desafios_autenticacion_intentos_check', 'desafios_autenticacion_max_intentos_check', 'desafios_autenticacion_pkey', 'desafios_autenticacion_proposito_check', 'desafios_autenticacion_sesion_id_fkey', 'desafios_autenticacion_token_hash_key']::text[]),
      ('evidencias', 'id:uuid:true,certificado_id:uuid:false,evento_id:uuid:false,clase:text:true,archivo_sha256:character(64):true,ubicacion_segura:text:true,creado_en:timestamp with time zone:true,retener_hasta:date:false', ARRAY['evidencias_archivo_sha256_check', 'evidencias_certificado_id_fkey', 'evidencias_check', 'evidencias_evento_id_fkey', 'evidencias_pkey']::text[]),
      ('firmas_certificado', 'id:uuid:true,solicitud_id:uuid:true,consentimiento_id:uuid:true,metodo:text:true,rubrica_archivo_sha256:character(64):false,rubrica_ubicacion_segura:text:false,certificado_x509_sha256:character(64):false,perfil_pades:text:false,firmado_en:timestamp with time zone:true,pdf_resultante_sha256:character(64):true,pdf_resultante_ubicacion_segura:text:true', ARRAY['firmas_certificado_check', 'firmas_certificado_consentimiento_id_fkey', 'firmas_certificado_consentimiento_id_key', 'firmas_certificado_metodo_check', 'firmas_certificado_pdf_resultante_sha256_check', 'firmas_certificado_pkey', 'firmas_certificado_solicitud_id_fkey', 'firmas_certificado_solicitud_id_key']::text[]),
      ('identidades', 'id:bigint:true,usuario_externo_id:text:true,nombre_mostrado:text:true,activo:boolean:true,creado_en:timestamp with time zone:true,actualizado_en:timestamp with time zone:true', ARRAY['identidades_pkey', 'identidades_usuario_externo_id_key']::text[]),
      ('permisos_firma', 'id:bigint:true,codigo:text:true,descripcion:text:true', ARRAY['permisos_firma_codigo_key', 'permisos_firma_pkey']::text[]),
      ('plantillas_certificado', 'id:uuid:true,codigo:text:true,version:integer:true,nombre:text:true,archivo_sha256:character(64):true,ubicacion_segura:text:true,activa:boolean:true,creada_por:bigint:false,creado_en:timestamp with time zone:true', ARRAY['plantillas_certificado_archivo_sha256_check', 'plantillas_certificado_codigo_version_key', 'plantillas_certificado_creada_por_fkey', 'plantillas_certificado_pkey', 'plantillas_certificado_version_check']::text[]),
      ('rol_permiso', 'rol_id:bigint:true,permiso_id:bigint:true', ARRAY['rol_permiso_permiso_id_fkey', 'rol_permiso_pkey', 'rol_permiso_rol_id_fkey']::text[]),
      ('roles_firma', 'id:bigint:true,codigo:text:true,descripcion:text:true', ARRAY['roles_firma_codigo_key', 'roles_firma_pkey']::text[]),
      ('sesiones_firma', 'id:uuid:true,identidad_id:bigint:true,refresh_token_hash:text:true,creado_en:timestamp with time zone:true,expira_en:timestamp with time zone:true,revocado_en:timestamp with time zone:false,ip:inet:false,agente_usuario:text:false', ARRAY['sesiones_firma_check', 'sesiones_firma_identidad_id_fkey', 'sesiones_firma_pkey', 'sesiones_firma_refresh_token_hash_key']::text[]),
      ('solicitudes_firma', 'id:uuid:true,certificado_id:uuid:true,version_id:uuid:true,firmante_id:bigint:true,autorizacion_id:uuid:true,orden_firma:integer:true,estado:text:true,token_qr_hash:character(64):true,creada_por:bigint:true,creada_en:timestamp with time zone:true,expira_en:timestamp with time zone:true,abierta_en:timestamp with time zone:false,decidida_en:timestamp with time zone:false,motivo_rechazo:text:false', ARRAY['solicitudes_firma_autorizacion_id_fkey', 'solicitudes_firma_certificado_id_version_id_firmante_id_ord_key', 'solicitudes_firma_certificado_id_version_id_fkey', 'solicitudes_firma_check', 'solicitudes_firma_creada_por_fkey', 'solicitudes_firma_estado_check', 'solicitudes_firma_firmante_id_fkey', 'solicitudes_firma_orden_firma_check', 'solicitudes_firma_pkey', 'solicitudes_firma_token_qr_hash_check', 'solicitudes_firma_token_qr_hash_key']::text[]),
      ('totp_factores', 'id:uuid:true,identidad_id:bigint:true,secreto_cifrado:bytea:true,clave_version:text:true,algoritmo:text:true,periodo_segundos:integer:true,digitos:smallint:true,ultimo_paso_aceptado:bigint:false,estado:text:true,creado_en:timestamp with time zone:true,activado_en:timestamp with time zone:false,revocado_en:timestamp with time zone:false', ARRAY['totp_factores_algoritmo_check', 'totp_factores_digitos_check', 'totp_factores_estado_check', 'totp_factores_identidad_id_fkey', 'totp_factores_periodo_segundos_check', 'totp_factores_pkey']::text[]),
      ('totp_recuperacion', 'id:uuid:true,factor_id:uuid:true,codigo_hash:text:true,consumido_en:timestamp with time zone:false,creado_en:timestamp with time zone:true', ARRAY['totp_recuperacion_factor_id_fkey', 'totp_recuperacion_pkey']::text[]),
      ('validaciones_criptograficas', 'id:uuid:true,firma_id:uuid:true,validador:text:true,algoritmo:text:false,integridad_valida:boolean:false,cadena_certificados_valida:boolean:false,revocacion_valida:boolean:false,sello_tiempo_valido:boolean:false,resultado:text:true,detalle:jsonb:true,evidencia_ubicacion_segura:text:false,comprobado_en:timestamp with time zone:true', ARRAY['validaciones_criptograficas_firma_id_fkey', 'validaciones_criptograficas_pkey', 'validaciones_criptograficas_resultado_check']::text[]),
      ('verificaciones_publicas', 'id:bigint:true,certificado_id:uuid:false,codigo_consultado_hash:character(64):false,resultado:text:true,consultado_en:timestamp with time zone:true,ip:inet:false,agente_usuario:text:false', ARRAY['verificaciones_publicas_certificado_id_fkey', 'verificaciones_publicas_pkey', 'verificaciones_publicas_resultado_check']::text[]),
      ('versiones_certificado', 'id:uuid:true,certificado_id:uuid:true,numero_version:integer:true,archivo_sha256:character(64):true,ubicacion_segura:text:true,tamano_bytes:bigint:true,mime_type:text:true,creado_por:bigint:true,creado_en:timestamp with time zone:true', ARRAY['versiones_certificado_archivo_sha256_check', 'versiones_certificado_certificado_id_fkey', 'versiones_certificado_certificado_id_id_key', 'versiones_certificado_certificado_id_numero_version_key', 'versiones_certificado_creado_por_fkey', 'versiones_certificado_mime_type_check', 'versiones_certificado_numero_version_check', 'versiones_certificado_pkey', 'versiones_certificado_tamano_bytes_check']::text[])
    ) AS v(tabla, columnas, restricciones)
  LOOP
    IF to_regclass('esart_firma.' || t.tabla) IS NULL THEN
      RAISE EXCEPTION 'p0018 abortada sin cambios: falta la tabla heredada esart_firma.%', t.tabla;
    END IF;
    SELECT string_agg(a.attname || ':' || format_type(a.atttypid, a.atttypmod) || ':' ||
                      CASE WHEN a.attnotnull THEN 'true' ELSE 'false' END, ',' ORDER BY a.attnum)
      INTO actual
      FROM pg_attribute a WHERE a.attrelid = to_regclass('esart_firma.' || t.tabla) AND a.attnum > 0 AND NOT a.attisdropped;
    IF actual IS DISTINCT FROM t.columnas THEN
      RAISE EXCEPTION 'p0018 abortada sin cambios: esart_firma.% no coincide con el inventario (columnas/tipos/nulabilidad).', t.tabla;
    END IF;
    SELECT array_agg(r) INTO faltantes FROM unnest(t.restricciones) r
      WHERE NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = to_regclass('esart_firma.' || t.tabla) AND k.conname = r);
    IF faltantes IS NOT NULL THEN
      RAISE EXCEPTION 'p0018 abortada sin cambios: esart_firma.% no tiene las restricciones %', t.tabla, faltantes;
    END IF;
  END LOOP;
  IF to_regprocedure('esart_firma.bloquear_mutacion_evidencia()') IS NULL THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: falta la función heredada esart_firma.bloquear_mutacion_evidencia().';
  END IF;
  -- Un solo mecanismo de autenticación: la autenticación heredada debe estar vacía.
  IF EXISTS (SELECT 1 FROM esart_firma.totp_factores) OR EXISTS (SELECT 1 FROM esart_firma.totp_recuperacion)
     OR EXISTS (SELECT 1 FROM esart_firma.sesiones_firma) THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: totp_factores, totp_recuperacion o sesiones_firma tienen registros; decidir su migración a TOTP de ESART antes.';
  END IF;
  IF EXISTS (SELECT 1 FROM esart_firma.desafios_autenticacion WHERE proposito <> 'FIRMAR') THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: hay desafíos heredados de login/MFA.';
  END IF;
  IF EXISTS (SELECT 1 FROM esart.componentes WHERE codigo = 'FIRMA_DOCUMENTOS'
             AND (ruta_angular IS NOT NULL OR componente_padre_id IS NOT NULL)) THEN
    RAISE EXCEPTION 'p0018 abortada sin cambios: existe un componente FIRMA_DOCUMENTOS distinto (con ruta o padre).';
  END IF;
END
$guardas$;

-- Huella de los datos heredados antes de cambiar nada (se compara al final).
CREATE TEMP TABLE p0018_huella ON COMMIT DROP AS
SELECT 'conteo:' || c.relname AS clave,
       (xpath('/row/n/text()', query_to_xml('SELECT count(*) AS n FROM esart_firma.' || quote_ident(c.relname), false, true, '')))[1]::text AS valor
FROM pg_class c
WHERE c.relnamespace = to_regnamespace('esart_firma') AND c.relkind = 'r'
  AND c.relname IN ('asignaciones_rol', 'auditoria_cambios', 'auditoria_eventos', 'autorizaciones_firmantes', 'certificados', 'consentimientos_firma', 'desafios_autenticacion', 'evidencias', 'firmas_certificado', 'identidades', 'permisos_firma', 'plantillas_certificado', 'rol_permiso', 'roles_firma', 'sesiones_firma', 'solicitudes_firma', 'totp_factores', 'totp_recuperacion', 'validaciones_criptograficas', 'verificaciones_publicas', 'versiones_certificado')
UNION ALL SELECT 'md5:roles_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.roles_firma t
UNION ALL SELECT 'md5:permisos_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.permisos_firma t
UNION ALL SELECT 'md5:rol_permiso', md5(coalesce(string_agg(t::text, '|' ORDER BY rol_id, permiso_id), '')) FROM esart_firma.rol_permiso t
UNION ALL SELECT 'md5:asignaciones_rol', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.asignaciones_rol t;

-- 2. p0018: conciliación (solo adiciones) --------------------------------------------
ALTER TABLE esart_firma.identidades ADD COLUMN usuario_id bigint;

ALTER TABLE esart_firma.identidades ADD CONSTRAINT fk_identidades_usuario
          FOREIGN KEY (usuario_id) REFERENCES esart_ref.usuarios(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX uq_identidades_usuario ON esart_firma.identidades (usuario_id) WHERE usuario_id IS NOT NULL;

CREATE TABLE esart_firma.documentos (
          id uuid PRIMARY KEY,
          tipo varchar(30) NOT NULL CONSTRAINT ck_documentos_tipo CHECK (tipo IN ('CERTIFICACION', 'OFICIO_REMISORIO')),
          numero varchar(80) NOT NULL CONSTRAINT uq_documentos_numero UNIQUE,
          personal_id bigint NOT NULL CONSTRAINT fk_documentos_personal REFERENCES esart.personal_militar(id) ON DELETE RESTRICT,
          curso_id bigint CONSTRAINT fk_documentos_curso REFERENCES esart.cursos(id) ON DELETE RESTRICT,
          datos_emitidos jsonb NOT NULL,
          estado varchar(24) NOT NULL DEFAULT 'BORRADOR'
            CONSTRAINT ck_documentos_estado CHECK (estado IN ('BORRADOR','PENDIENTE_FIRMA','FIRMADO','EMITIDO','ANULADO')),
          version_actual integer NOT NULL DEFAULT 1 CONSTRAINT ck_documentos_version CHECK (version_actual > 0),
          creado_por bigint NOT NULL CONSTRAINT fk_documentos_creado_por REFERENCES esart_ref.usuarios(id) ON DELETE RESTRICT,
          creado_en timestamptz NOT NULL DEFAULT now(),
          emitido_en timestamptz
        );

CREATE INDEX ix_documentos_personal_fecha ON esart_firma.documentos (personal_id, creado_en DESC);

CREATE TABLE esart_firma.versiones_documento (
          id uuid PRIMARY KEY,
          documento_id uuid NOT NULL CONSTRAINT fk_versiones_documento_documento
            REFERENCES esart_firma.documentos(id) ON DELETE RESTRICT,
          numero_version integer NOT NULL CONSTRAINT ck_versiones_documento_numero CHECK (numero_version > 0),
          sha256 char(64) NOT NULL CONSTRAINT ck_versiones_documento_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
          ubicacion_privada text NOT NULL,
          tamano_bytes bigint NOT NULL CONSTRAINT ck_versiones_documento_tamano CHECK (tamano_bytes > 0),
          mime_type varchar(40) NOT NULL DEFAULT 'application/pdf'
            CONSTRAINT ck_versiones_documento_mime CHECK (mime_type = 'application/pdf'),
          creado_por bigint NOT NULL CONSTRAINT fk_versiones_documento_creado_por
            REFERENCES esart_ref.usuarios(id) ON DELETE RESTRICT,
          creado_en timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_versiones_documento_numero UNIQUE (documento_id, numero_version),
          CONSTRAINT uq_versiones_documento_id UNIQUE (documento_id, id)
        );

CREATE TRIGGER trg_inmutable BEFORE DELETE OR UPDATE ON esart_firma.versiones_documento
        FOR EACH ROW EXECUTE FUNCTION esart_firma.bloquear_mutacion_evidencia();

ALTER TABLE esart_firma.evidencias ADD COLUMN documento_id uuid;

ALTER TABLE esart_firma.evidencias ADD CONSTRAINT fk_evidencias_documento
          FOREIGN KEY (documento_id) REFERENCES esart_firma.documentos(id) ON DELETE RESTRICT;

CREATE INDEX ix_evidencias_documento ON esart_firma.evidencias (documento_id) WHERE documento_id IS NOT NULL;

ALTER TABLE esart_firma.solicitudes_firma ADD COLUMN documento_id uuid, ADD COLUMN documento_version_id uuid;

ALTER TABLE esart_firma.solicitudes_firma ADD CONSTRAINT fk_solicitudes_version_documento
          FOREIGN KEY (documento_id, documento_version_id)
          REFERENCES esart_firma.versiones_documento(documento_id, id) ON DELETE RESTRICT;

ALTER TABLE esart_firma.solicitudes_firma ALTER COLUMN certificado_id DROP NOT NULL, ALTER COLUMN version_id DROP NOT NULL;

ALTER TABLE esart_firma.solicitudes_firma ADD CONSTRAINT ck_solicitudes_objeto_unico CHECK (
          (certificado_id IS NOT NULL AND version_id IS NOT NULL
             AND documento_id IS NULL AND documento_version_id IS NULL)
          OR (certificado_id IS NULL AND version_id IS NULL
             AND documento_id IS NOT NULL AND documento_version_id IS NOT NULL));

CREATE UNIQUE INDEX uq_solicitudes_documento_firmante ON esart_firma.solicitudes_firma
          (documento_id, documento_version_id, firmante_id, orden_firma) WHERE documento_id IS NOT NULL;

ALTER TABLE esart_firma.desafios_autenticacion ADD CONSTRAINT ck_desafios_solo_firma
          CHECK (proposito = 'FIRMAR');

CREATE FUNCTION esart_firma.rechazar_autenticacion_heredada() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'Mecanismo heredado deshabilitado (%): la autenticación y el TOTP son los de ESART.',
            TG_TABLE_NAME;
        END $$;

CREATE TRIGGER trg_autenticacion_heredada BEFORE INSERT OR UPDATE ON esart_firma.totp_factores
            FOR EACH ROW EXECUTE FUNCTION esart_firma.rechazar_autenticacion_heredada();

CREATE TRIGGER trg_autenticacion_heredada BEFORE INSERT OR UPDATE ON esart_firma.totp_recuperacion
            FOR EACH ROW EXECUTE FUNCTION esart_firma.rechazar_autenticacion_heredada();

CREATE TRIGGER trg_autenticacion_heredada BEFORE INSERT OR UPDATE ON esart_firma.sesiones_firma
            FOR EACH ROW EXECUTE FUNCTION esart_firma.rechazar_autenticacion_heredada();

REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA esart_firma FROM PUBLIC;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='esart_aplicacion') THEN
            GRANT USAGE ON SCHEMA esart_firma TO esart_aplicacion;
            GRANT SELECT, INSERT ON esart_firma.documentos, esart_firma.versiones_documento,
              esart_firma.evidencias, esart_firma.auditoria_eventos TO esart_aplicacion;
            GRANT UPDATE (estado, version_actual, emitido_en) ON esart_firma.documentos TO esart_aplicacion;
            GRANT SELECT (id, usuario_externo_id, nombre_mostrado, activo, usuario_id),
                  INSERT (usuario_externo_id, nombre_mostrado, usuario_id)
              ON esart_firma.identidades TO esart_aplicacion;
            EXECUTE format('GRANT USAGE ON SEQUENCE %s, %s TO esart_aplicacion',
              pg_get_serial_sequence('esart_firma.identidades', 'id'),
              pg_get_serial_sequence('esart_firma.auditoria_eventos', 'id'));
            REVOKE ALL ON esart_firma.totp_factores, esart_firma.totp_recuperacion, esart_firma.sesiones_firma
              FROM esart_aplicacion;
          END IF;
        END $$;

INSERT INTO esart.componentes(codigo,nombre,ruta_angular,orden,activo)
        VALUES ('FIRMA_DOCUMENTOS','Firma documental',NULL,120,true)
        ON CONFLICT (codigo) DO NOTHING;

INSERT INTO esart.rol_permisos(rol_id,componente_id,puede_acceder,puede_crear,puede_leer,puede_actualizar,puede_eliminar)
        SELECT r.id,c.id,(r.codigo='ADMINISTRADOR'),(r.codigo='ADMINISTRADOR'),(r.codigo='ADMINISTRADOR'),false,false
        FROM esart.roles r CROSS JOIN esart.componentes c
        WHERE c.codigo='FIRMA_DOCUMENTOS'
        ON CONFLICT (rol_id,componente_id) DO NOTHING;

-- 3. p0019: permisos de la API para la firma desde el celular -----------------------
DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'esart_aplicacion') THEN
    GRANT SELECT, INSERT ON esart_firma.solicitudes_firma TO esart_aplicacion;
    GRANT UPDATE (estado, abierta_en, decidida_en, motivo_rechazo) ON esart_firma.solicitudes_firma TO esart_aplicacion;
    GRANT SELECT, INSERT ON esart_firma.autorizaciones_firmantes TO esart_aplicacion;
    GRANT UPDATE (revocado_en) ON esart_firma.autorizaciones_firmantes TO esart_aplicacion;
    GRANT SELECT, INSERT ON esart_firma.consentimientos_firma TO esart_aplicacion;
    GRANT SELECT, INSERT ON esart_firma.desafios_autenticacion TO esart_aplicacion;
    GRANT SELECT, INSERT ON esart_firma.firmas_certificado TO esart_aplicacion;
          END IF;
        END $$;

-- 4. Comprobación final (si algo cambió, se revierte todo) ---------------------------
DO $comprobacion$
DECLARE
  diferencias text;
BEGIN
  -- Las filas de roles/permisos y los conteos se recalculan y se comparan con la huella previa.
  -- (Las tablas heredadas ahora tienen columnas extra: el md5 se calcula solo con las originales.)
  WITH ahora AS (
    SELECT 'conteo:' || c.relname AS clave,
           (xpath('/row/n/text()', query_to_xml('SELECT count(*) AS n FROM esart_firma.' || quote_ident(c.relname), false, true, '')))[1]::text AS valor
    FROM pg_class c
    WHERE c.relnamespace = to_regnamespace('esart_firma') AND c.relkind = 'r'
      AND 'conteo:' || c.relname IN (SELECT clave FROM p0018_huella)
    UNION ALL SELECT 'md5:roles_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.roles_firma t
    UNION ALL SELECT 'md5:permisos_firma', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.permisos_firma t
    UNION ALL SELECT 'md5:rol_permiso', md5(coalesce(string_agg(t::text, '|' ORDER BY rol_id, permiso_id), '')) FROM esart_firma.rol_permiso t
    UNION ALL SELECT 'md5:asignaciones_rol', md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM esart_firma.asignaciones_rol t
  )
  SELECT string_agg(h.clave, ', ') INTO diferencias
  FROM p0018_huella h LEFT JOIN ahora a ON a.clave = h.clave
  WHERE a.valor IS DISTINCT FROM h.valor;
  IF diferencias IS NOT NULL THEN
    RAISE EXCEPTION 'p0018 revertida: cambió el contenido heredado (%)', diferencias;
  END IF;
  IF (SELECT count(*) FROM pg_class WHERE relnamespace = to_regnamespace('esart_firma') AND relkind = 'r') <> 23 THEN
    RAISE EXCEPTION 'p0018 revertida: esart_firma debía quedar con 23 tablas (21 heredadas + 2 nuevas).';
  END IF;
END
$comprobacion$;

COMMIT;

-- Estado DESPUÉS (solo lectura)
SELECT 'despues' AS momento, count(*) FILTER (WHERE relkind = 'r') AS tablas_esart_firma
FROM pg_class WHERE relnamespace = to_regnamespace('esart_firma');
SELECT 'roles_firma' AS tabla, count(*) FROM esart_firma.roles_firma
UNION ALL SELECT 'permisos_firma', count(*) FROM esart_firma.permisos_firma
UNION ALL SELECT 'documentos (nueva)', count(*) FROM esart_firma.documentos;
SELECT codigo, nombre FROM esart.componentes WHERE codigo = 'FIRMA_DOCUMENTOS';
