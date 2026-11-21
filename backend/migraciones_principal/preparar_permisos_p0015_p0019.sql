-- Ejecutar con psql como administrador de PostgreSQL 18 conectado a esart_db.
-- Prepara propiedad y ACL. No ejecuta Alembic ni escribe filas de la aplicación.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path TO pg_catalog, pg_temp;
SET LOCAL lock_timeout TO '5s';

DO $permisos$
DECLARE
    revision text;
    posicion integer;
    migrador oid := to_regrole('esart_migrador');
    api oid := to_regrole('esart_aplicacion');
    objeto record;
    secuencia text;
    firma oid := to_regnamespace('esart_firma');
    tablas_heredadas constant text[] := ARRAY[
        'asignaciones_rol', 'auditoria_cambios', 'auditoria_eventos', 'autorizaciones_firmantes',
        'certificados', 'consentimientos_firma', 'desafios_autenticacion', 'evidencias',
        'firmas_certificado', 'identidades', 'permisos_firma', 'plantillas_certificado',
        'rol_permiso', 'roles_firma', 'sesiones_firma', 'solicitudes_firma', 'totp_factores',
        'totp_recuperacion', 'validaciones_criptograficas', 'verificaciones_publicas',
        'versiones_certificado'
    ];
    auth constant text[] := ARRAY['sesiones_firma', 'totp_factores', 'totp_recuperacion'];
    nombre text;
    transferir boolean;
BEGIN
    IF current_database() <> 'esart_db'
       OR current_setting('server_version_num')::integer / 10000 <> 18
       OR NOT EXISTS (SELECT FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
        RAISE EXCEPTION 'Ejecutar como administrador PostgreSQL 18 en esart_db';
    END IF;
    IF NOT EXISTS (
        SELECT FROM pg_roles WHERE oid = migrador
          AND rolcanlogin AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) OR api IS NULL THEN
        RAISE EXCEPTION 'Se requieren los roles existentes esart_migrador sin atributos elevados y esart_aplicacion';
    END IF;
    IF (SELECT count(*) FROM esart.alembic_version) <> 1 THEN
        RAISE EXCEPTION 'Alembic debe tener exactamente una revisión activa';
    END IF;
    SELECT version_num INTO STRICT revision FROM esart.alembic_version;
    posicion := array_position(ARRAY[
        'p0014_cursos_del_instructor', 'p0015_registro_manual_personal', 'p0016_cursos_artilleros',
        'p0017_restablecer_totp_admin', 'p0018_firma_documental', 'p0019_firma_movil'
    ], revision);
    IF posicion IS NULL THEN
        RAISE EXCEPTION 'Revisión fuera del tramo autorizado: %', revision;
    END IF;
    RAISE NOTICE 'Revisión de partida: %', revision;
    IF posicion = 6 THEN
        RETURN;
    END IF;

    GRANT CONNECT ON DATABASE esart_db TO esart_migrador;
    GRANT USAGE ON SCHEMA esart TO esart_migrador;
    GRANT SELECT, UPDATE ON esart.alembic_version TO esart_migrador;

    IF posicion <= 3 THEN
        SELECT c.relowner INTO STRICT objeto FROM pg_class c
        WHERE c.oid = 'esart.auditoria_eventos'::regclass AND c.relkind = 'r';
        IF NOT pg_has_role(migrador, objeto.relowner, 'USAGE') THEN
            RAISE NOTICE 'Propiedad esart.auditoria_eventos: % -> esart_migrador',
                pg_get_userbyid(objeto.relowner);
            ALTER TABLE ONLY esart.auditoria_eventos OWNER TO esart_migrador;
        END IF;
    END IF;

    -- p0016: delegación por columna y secuencia, más lectura para el INSERT ... SELECT.
    IF posicion <= 2 THEN
        GRANT SELECT (id) ON esart.hoja_vida_artillero TO esart_migrador WITH GRANT OPTION;
        GRANT SELECT (curso_id) ON esart.hoja_vida_artillero TO esart_migrador;
        GRANT INSERT (hoja_vida_id, tipo_curso_id, nombre, institucion, fecha_inicio, fecha_fin, aprobado),
              SELECT (id) ON esart.artillero_cursos TO esart_migrador WITH GRANT OPTION;
        GRANT SELECT (hoja_vida_id) ON esart.artillero_cursos TO esart_migrador;
        GRANT SELECT (id, tipo_curso_id, nombre, fecha_inicio, fecha_fin, estado)
            ON esart.cursos TO esart_migrador;
        GRANT SELECT (id, nombre) ON esart.tipos_curso TO esart_migrador;
        secuencia := pg_get_serial_sequence('esart.artillero_cursos', 'id');
        IF secuencia IS NULL THEN
            RAISE EXCEPTION 'Falta la secuencia propia de esart.artillero_cursos.id requerida por p0016';
        END IF;
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO esart_migrador WITH GRANT OPTION', secuencia);
        RAISE NOTICE 'Secuencia p0016: %', secuencia;
    END IF;

    IF posicion <= 3 THEN
        GRANT USAGE ON SCHEMA seguridad TO esart_migrador;
        GRANT INSERT (codigo, nombre, descripcion, modulo, permiso_requerido, requiere_totp, activa, vigencia_segundos),
              UPDATE (permiso_requerido, requiere_totp, activa, vigencia_segundos),
              SELECT (codigo, permiso_requerido, requiere_totp, activa, vigencia_segundos)
              ON seguridad.politicas_accion TO esart_migrador;
    END IF;

    IF posicion <= 4 THEN
        GRANT USAGE ON SCHEMA esart_ref TO esart_migrador;
        GRANT REFERENCES (id) ON esart_ref.usuarios TO esart_migrador;
        GRANT MAINTAIN ON esart.componentes TO esart_migrador;
        GRANT SELECT (id, codigo, ruta_angular, componente_padre_id),
              INSERT (codigo, nombre, ruta_angular, orden, activo) ON esart.componentes TO esart_migrador;
        GRANT SELECT (id, codigo) ON esart.roles TO esart_migrador;
        GRANT SELECT (rol_id, componente_id),
              INSERT (rol_id, componente_id, puede_acceder, puede_crear, puede_leer, puede_actualizar, puede_eliminar)
              ON esart.rol_permisos TO esart_migrador;

        -- En las instalaciones con SERIAL, INSERT invoca nextval con los permisos del usuario.
        FOR objeto IN
            SELECT c.oid::regclass AS tabla
            FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE (c.oid IN ('esart.componentes'::regclass, 'esart.rol_permisos'::regclass)
                   OR (posicion <= 3 AND c.oid = to_regclass('seguridad.politicas_accion')))
              AND a.attname = 'id' AND a.attidentity = '' AND NOT a.attisdropped
        LOOP
            secuencia := pg_get_serial_sequence(objeto.tabla::text, 'id');
            IF secuencia IS NOT NULL THEN
                EXECUTE format('GRANT USAGE ON SEQUENCE %s TO esart_migrador', secuencia);
                RAISE NOTICE 'Secuencia SERIAL de %: %', objeto.tabla, secuencia;
            END IF;
        END LOOP;

        IF firma IS NULL THEN
            -- p0018 crea el esquema y sus objetos. CREATE sobre la base es necesario en esta rama.
            GRANT CREATE ON DATABASE esart_db TO esart_migrador;
        ELSE
            GRANT USAGE ON SCHEMA esart_firma TO esart_migrador WITH GRANT OPTION;
            IF to_regclass('esart_firma.documentos') IS NULL
               OR to_regclass('esart_firma.versiones_documento') IS NULL
               OR to_regprocedure('esart_firma.rechazar_autenticacion_heredada()') IS NULL THEN
                GRANT CREATE ON SCHEMA esart_firma TO esart_migrador;
            END IF;
            FOREACH nombre IN ARRAY tablas_heredadas LOOP
                IF NOT EXISTS (SELECT FROM pg_class WHERE relnamespace = firma AND relname = nombre AND relkind = 'r') THEN
                    RAISE EXCEPTION 'Falta la tabla ordinaria heredada esart_firma.%', nombre;
                END IF;
            END LOOP;
            FOR objeto IN
                SELECT oid, relname, relowner, relacl, relkind FROM pg_class
                WHERE relnamespace = firma AND relkind IN ('r', 'p', 'v', 'm', 'f')
            LOOP
                IF objeto.relkind <> 'r'
                   OR NOT (objeto.relname = ANY(tablas_heredadas || ARRAY['documentos', 'versiones_documento'])) THEN
                    RAISE EXCEPTION 'Objeto fuera del alcance revisado de REVOKE de p0018: esart_firma.%', objeto.relname;
                END IF;
                -- Un grant de un tercero no se puede retirar tomando solo la propiedad.
                IF EXISTS (
                    SELECT FROM (
                        SELECT a.grantor, a.grantee, a.privilege_type FROM aclexplode(objeto.relacl) a
                        UNION ALL
                        SELECT a.grantor, a.grantee, a.privilege_type
                        FROM pg_attribute c CROSS JOIN LATERAL aclexplode(c.attacl) a
                        WHERE c.attrelid = objeto.oid
                    ) a
                    WHERE a.grantor <> objeto.relowner AND (
                        (a.grantee = 0 AND a.privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE'))
                        OR (a.grantee = api AND objeto.relname = ANY(auth))
                    )
                ) THEN
                    RAISE EXCEPTION 'ACL de otro otorgante requiere revisión: esart_firma.%', objeto.relname;
                END IF;
                transferir := EXISTS (
                    SELECT FROM (
                        SELECT a.grantee, a.privilege_type FROM aclexplode(objeto.relacl) a
                        UNION ALL
                        SELECT a.grantee, a.privilege_type
                        FROM pg_attribute c CROSS JOIN LATERAL aclexplode(c.attacl) a
                        WHERE c.attrelid = objeto.oid
                    ) a
                    WHERE (a.grantee = 0 AND a.privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE'))
                       OR (a.grantee = api AND objeto.relname = ANY(auth))
                ) OR CASE objeto.relname
                    WHEN 'identidades' THEN NOT EXISTS (
                        SELECT FROM pg_constraint WHERE conrelid = objeto.oid AND conname = 'fk_identidades_usuario'
                    ) OR to_regclass('esart_firma.uq_identidades_usuario') IS NULL
                    WHEN 'evidencias' THEN NOT EXISTS (
                        SELECT FROM pg_constraint WHERE conrelid = objeto.oid AND conname = 'fk_evidencias_documento'
                    ) OR to_regclass('esart_firma.ix_evidencias_documento') IS NULL
                    WHEN 'solicitudes_firma' THEN (
                        SELECT count(*) FROM pg_constraint WHERE conrelid = objeto.oid
                          AND conname IN ('fk_solicitudes_version_documento', 'ck_solicitudes_objeto_unico')
                    ) <> 2 OR to_regclass('esart_firma.uq_solicitudes_documento_firmante') IS NULL
                       OR EXISTS (
                           SELECT FROM pg_attribute WHERE attrelid = objeto.oid
                             AND attname IN ('certificado_id', 'version_id') AND attnotnull
                       )
                    WHEN 'desafios_autenticacion' THEN NOT EXISTS (
                        SELECT FROM pg_constraint WHERE conrelid = objeto.oid AND conname = 'ck_desafios_solo_firma'
                    )
                    ELSE false
                END;
                RAISE NOTICE 'Firma: %, propietario actual %, cambio de propietario necesario: %',
                    objeto.relname, pg_get_userbyid(objeto.relowner),
                    transferir AND NOT pg_has_role(migrador, objeto.relowner, 'USAGE');
                IF transferir AND NOT pg_has_role(migrador, objeto.relowner, 'USAGE') THEN
                    EXECUTE format('ALTER TABLE ONLY esart_firma.%I OWNER TO esart_migrador', objeto.relname);
                END IF;
                EXECUTE format('GRANT SELECT, MAINTAIN ON esart_firma.%I TO esart_migrador', objeto.relname);
                IF objeto.relname = ANY(auth) AND NOT EXISTS (
                    SELECT FROM pg_trigger WHERE tgrelid = objeto.oid AND tgname = 'trg_autenticacion_heredada'
                ) THEN
                    EXECUTE format('GRANT TRIGGER ON esart_firma.%I TO esart_migrador', objeto.relname);
                END IF;
            END LOOP;
            IF to_regprocedure('esart_firma.rechazar_autenticacion_heredada()') IS NOT NULL
               AND EXISTS (
                   SELECT FROM pg_class c WHERE c.relnamespace = firma AND c.relname = ANY(auth)
                     AND NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = c.oid AND tgname = 'trg_autenticacion_heredada')
               ) THEN
                GRANT EXECUTE ON FUNCTION esart_firma.rechazar_autenticacion_heredada() TO esart_migrador;
            END IF;
            IF to_regclass('esart_firma.documentos') IS NOT NULL THEN
                GRANT SELECT, INSERT, UPDATE (estado, version_actual, emitido_en)
                    ON esart_firma.documentos TO esart_migrador WITH GRANT OPTION;
                GRANT REFERENCES (id) ON esart_firma.documentos TO esart_migrador;
            END IF;
            IF to_regclass('esart_firma.versiones_documento') IS NOT NULL THEN
                GRANT SELECT, INSERT ON esart_firma.versiones_documento TO esart_migrador WITH GRANT OPTION;
                GRANT REFERENCES (documento_id, id) ON esart_firma.versiones_documento TO esart_migrador;
            ELSE
                GRANT EXECUTE ON FUNCTION esart_firma.bloquear_mutacion_evidencia() TO esart_migrador;
            END IF;
            GRANT SELECT, INSERT ON esart_firma.evidencias, esart_firma.auditoria_eventos
                TO esart_migrador WITH GRANT OPTION;
            IF EXISTS (
                SELECT FROM pg_attribute WHERE attrelid = 'esart_firma.identidades'::regclass
                  AND attname = 'usuario_id' AND NOT attisdropped
            ) THEN
                GRANT SELECT (id, usuario_externo_id, nombre_mostrado, activo, usuario_id),
                      INSERT (usuario_externo_id, nombre_mostrado, usuario_id)
                    ON esart_firma.identidades TO esart_migrador WITH GRANT OPTION;
            END IF;
            FOREACH nombre IN ARRAY ARRAY['identidades', 'auditoria_eventos'] LOOP
                secuencia := pg_get_serial_sequence(format('esart_firma.%I', nombre), 'id');
                IF secuencia IS NULL THEN
                    RAISE EXCEPTION 'Falta la secuencia propia de esart_firma.%.id requerida por p0018', nombre;
                END IF;
                EXECUTE format('GRANT USAGE ON SEQUENCE %s TO esart_migrador WITH GRANT OPTION', secuencia);
                RAISE NOTICE 'Secuencia p0018: %', secuencia;
            END LOOP;
        END IF;
        IF to_regclass('esart_firma.documentos') IS NULL THEN
            GRANT REFERENCES (id) ON esart.personal_militar, esart.cursos TO esart_migrador;
        END IF;
    END IF;

    -- Si no existe el esquema, el migrador será propietario de los objetos creados en p0018.
    IF firma IS NOT NULL THEN
        GRANT USAGE ON SCHEMA esart_firma TO esart_migrador;
        GRANT SELECT, INSERT ON esart_firma.solicitudes_firma, esart_firma.autorizaciones_firmantes,
            esart_firma.consentimientos_firma, esart_firma.desafios_autenticacion, esart_firma.firmas_certificado
            TO esart_migrador WITH GRANT OPTION;
        GRANT UPDATE (estado, abierta_en, decidida_en, motivo_rechazo) ON esart_firma.solicitudes_firma
            TO esart_migrador WITH GRANT OPTION;
        GRANT UPDATE (revocado_en) ON esart_firma.autorizaciones_firmantes
            TO esart_migrador WITH GRANT OPTION;
    END IF;
END
$permisos$;

-- Propietarios efectivos tras la preparación. Los NOTICE registran las transferencias.
SELECT n.nspname AS esquema, c.relname AS objeto, c.relkind AS clase,
       pg_get_userbyid(c.relowner) AS propietario
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (n.nspname = 'esart_firma' AND c.relkind IN ('r', 'S'))
   OR (n.nspname, c.relname) IN (
       ('esart', 'alembic_version'), ('esart', 'auditoria_eventos'), ('esart', 'hoja_vida_artillero'),
       ('esart', 'artillero_cursos'), ('esart', 'cursos'), ('esart', 'tipos_curso'), ('esart', 'componentes'),
       ('esart', 'roles'), ('esart', 'rol_permisos'), ('esart', 'personal_militar'),
       ('esart_ref', 'usuarios'), ('seguridad', 'politicas_accion')
   )
ORDER BY esquema, objeto;

SELECT 'esquema' AS clase, nspname AS objeto, pg_get_userbyid(nspowner) AS propietario
FROM pg_namespace WHERE nspname IN ('esart', 'esart_ref', 'esart_firma', 'seguridad')
UNION ALL
SELECT 'función', oid::regprocedure::text, pg_get_userbyid(proowner)
FROM pg_proc
WHERE oid IN (to_regprocedure('esart_firma.bloquear_mutacion_evidencia()'),
              to_regprocedure('esart_firma.rechazar_autenticacion_heredada()'))
ORDER BY clase, objeto;

COMMIT;
