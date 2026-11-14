-- =============================================================================
-- ESART - Esquema de referencia de la base de datos esart_db
-- Version del contrato: 0.1 (2026-11-14)
--
-- QUE ES ESTE ARCHIVO:
--   Traduccion a SQL del documento docs/contrato_esquema_bd.md.
--   Es solo REFERENCIA para que ambos desarrolladores vean el esquema completo.
--   La fuente de verdad en ejecucion seran las migraciones de Alembic.
--
-- REQUISITOS: PostgreSQL 13 o superior (gen_random_uuid() viene incluido).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Funcion comun: actualiza fecha_actualizacion en cada UPDATE.
-- Se reutiliza en todas las tablas de negocio para no repetir logica.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION actualizar_fecha_actualizacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- 1. ORGANIZACION Y PERSONAL
-- =============================================================================

CREATE TABLE unidades_militares (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo              VARCHAR(20)  NOT NULL UNIQUE,
    nombre              VARCHAR(200) NOT NULL,
    sigla               VARCHAR(30),
    -- Jerarquia: una unidad puede depender de otra (brigada -> batallon).
    unidad_superior_id  UUID REFERENCES unidades_militares(id),
    activa              BOOLEAN      NOT NULL DEFAULT true,
    fecha_creacion      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_unidades_militares_unidad_superior ON unidades_militares(unidad_superior_id);

CREATE TABLE personal_militar (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Solo cedula de ciudadania, guardada sin puntos ni espacios.
    numero_documento    VARCHAR(10)  NOT NULL UNIQUE
                        CHECK (numero_documento ~ '^[0-9]{6,10}$'),
    primer_nombre       VARCHAR(60)  NOT NULL,
    segundo_nombre      VARCHAR(60),
    primer_apellido     VARCHAR(60)  NOT NULL,
    segundo_apellido    VARCHAR(60),
    grado               VARCHAR(40)  NOT NULL,
    categoria           VARCHAR(20)  NOT NULL
                        CHECK (categoria IN ('OFICIAL','SUBOFICIAL','SOLDADO_PROFESIONAL','CIVIL')),
    arma                VARCHAR(40),
    unidad_militar_id   UUID REFERENCES unidades_militares(id),
    estado_servicio     VARCHAR(20)  NOT NULL
                        CHECK (estado_servicio IN ('ACTIVO','RETIRADO','SUSPENDIDO','COMISION','LICENCIA')),
    fecha_creacion      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_personal_militar_estado_servicio ON personal_militar(estado_servicio);
CREATE INDEX ix_personal_militar_unidad_militar ON personal_militar(unidad_militar_id);

CREATE TABLE hoja_vida_artillero (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Relacion 1 a 1 con personal_militar.
    personal_militar_id UUID NOT NULL UNIQUE REFERENCES personal_militar(id),
    especialidad        VARCHAR(100),
    fecha_ingreso_arma  DATE,
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- =============================================================================
-- 2. SEGURIDAD (se crea antes que formacion porque importaciones_excel
--    referencia a usuarios, y los cursos referencian a importaciones_excel)
-- =============================================================================

CREATE TABLE roles (
    id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo  VARCHAR(30)  NOT NULL UNIQUE,
    nombre  VARCHAR(100) NOT NULL,
    activo  BOOLEAN      NOT NULL DEFAULT true
);

CREATE TABLE permisos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo      VARCHAR(50)  NOT NULL UNIQUE,
    descripcion VARCHAR(200) NOT NULL
);

CREATE TABLE roles_permisos (
    rol_id     UUID NOT NULL REFERENCES roles(id),
    permiso_id UUID NOT NULL REFERENCES permisos(id),
    PRIMARY KEY (rol_id, permiso_id)
);

CREATE TABLE usuarios (
    id                             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre_usuario                 VARCHAR(60)  NOT NULL,
    nombre_completo                VARCHAR(200) NOT NULL,
    -- Hash bcrypt. Nunca se expone por API ni se escribe en logs.
    hash_contrasena                VARCHAR(100) NOT NULL,
    rol_id                         UUID NOT NULL REFERENCES roles(id),
    activo                         BOOLEAN NOT NULL DEFAULT true,
    -- Contador para captcha (desde el 3.er fallo) y bloqueo (al 7.o fallo).
    intentos_fallidos_consecutivos INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta                TIMESTAMPTZ,
    fecha_ultimo_acceso            TIMESTAMPTZ,
    fecha_creacion                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion            TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Unicidad sin distinguir mayusculas: "Admin" y "admin" son el mismo usuario.
CREATE UNIQUE INDEX ux_usuarios_nombre_usuario ON usuarios (lower(nombre_usuario));
CREATE INDEX ix_usuarios_rol ON usuarios(rol_id);

CREATE TABLE intentos_inicio_sesion (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre_usuario_intentado VARCHAR(60) NOT NULL,
    -- Nulo cuando el usuario intentado no existe.
    usuario_id               UUID REFERENCES usuarios(id),
    direccion_ip             INET,
    exitoso                  BOOLEAN NOT NULL,
    motivo_fallo             VARCHAR(40),
    fecha                    TIMESTAMPTZ NOT NULL DEFAULT now()
    -- IMPORTANTE: nunca se guarda la contrasena intentada.
);
CREATE INDEX ix_intentos_inicio_sesion_ip_fecha ON intentos_inicio_sesion(direccion_ip, fecha);
CREATE INDEX ix_intentos_inicio_sesion_usuario_fecha ON intentos_inicio_sesion(usuario_id, fecha);

CREATE TABLE sesiones_usuario (
    -- El id es el "jti" del JWT: permite revocar una sesion concreta.
    id                     UUID PRIMARY KEY,
    usuario_id             UUID NOT NULL REFERENCES usuarios(id),
    fecha_inicio           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Se usa para cerrar la sesion tras 30 minutos sin actividad.
    fecha_ultima_actividad TIMESTAMPTZ NOT NULL DEFAULT now(),
    direccion_ip           INET,
    agente_usuario         VARCHAR(300),
    revocada               BOOLEAN NOT NULL DEFAULT false,
    fecha_revocacion       TIMESTAMPTZ
);
CREATE INDEX ix_sesiones_usuario_usuario ON sesiones_usuario(usuario_id);


-- =============================================================================
-- 3. IMPORTACION Y AUDITORIA
-- =============================================================================

CREATE TABLE importaciones_excel (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id          UUID NOT NULL REFERENCES usuarios(id),
    nombre_archivo      VARCHAR(255) NOT NULL,
    -- Evita aplicar dos veces el mismo archivo.
    hash_sha256_archivo CHAR(64)     NOT NULL,
    fecha               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    filas_totales       INTEGER      NOT NULL DEFAULT 0,
    filas_validas       INTEGER      NOT NULL DEFAULT 0,
    filas_rechazadas    INTEGER      NOT NULL DEFAULT 0,
    estado              VARCHAR(20)  NOT NULL
                        CHECK (estado IN ('PROCESANDO','APLICADA','RECHAZADA')),
    -- Lista de errores: [{"hoja":..., "fila":..., "columna":..., "motivo":...}]
    errores             JSONB
);
CREATE INDEX ix_importaciones_excel_hash ON importaciones_excel(hash_sha256_archivo);

CREATE TABLE auditoria_eventos (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    usuario_id                  UUID REFERENCES usuarios(id),
    -- Copia del nombre por si el usuario se renombra o desactiva despues.
    nombre_usuario              VARCHAR(60),
    accion                      VARCHAR(40) NOT NULL
                                CHECK (accion IN (
                                    'LOGIN_EXITOSO','LOGIN_FALLIDO','USUARIO_BLOQUEADO',
                                    'USUARIO_DESBLOQUEADO','CONSULTA_ARTILLERO',
                                    'CONSULTA_HABILITADOS','CONSULTA_NO_HABILITADOS',
                                    'IMPORTACION_EXCEL','CIERRE_SESION')),
    numero_documento_consultado VARCHAR(10),
    resultado                   VARCHAR(20),
    direccion_ip                INET,
    agente_usuario              VARCHAR(300),
    -- Prohibido guardar contrasenas o tokens en este campo.
    detalle                     JSONB
);
CREATE INDEX ix_auditoria_eventos_fecha ON auditoria_eventos(fecha);
CREATE INDEX ix_auditoria_eventos_usuario_fecha ON auditoria_eventos(usuario_id, fecha);
CREATE INDEX ix_auditoria_eventos_documento ON auditoria_eventos(numero_documento_consultado);

-- La auditoria es inmutable: ningun registro se puede modificar ni borrar.
CREATE OR REPLACE FUNCTION impedir_modificacion_auditoria()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'La tabla auditoria_eventos es inmutable: no se permite % ', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_auditoria_eventos_inmutable
    BEFORE UPDATE OR DELETE ON auditoria_eventos
    FOR EACH ROW EXECUTE FUNCTION impedir_modificacion_auditoria();


-- =============================================================================
-- 4. FORMACION Y CERTIFICACIONES
-- =============================================================================

CREATE TABLE tipos_curso (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo                 VARCHAR(30)  NOT NULL UNIQUE,
    nombre                 VARCHAR(200) NOT NULL,
    descripcion            TEXT,
    -- Contemplado para la verificacion por sistema; aun no se usa.
    tipo_sistema           VARCHAR(50),
    -- NULL = el curso aprobado no vence.
    vigencia_meses         INTEGER CHECK (vigencia_meses > 0),
    nota_minima_aprobacion NUMERIC(4,2) CHECK (nota_minima_aprobacion BETWEEN 0 AND 5),
    activo                 BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE artillero_cursos (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hoja_vida_artillero_id UUID NOT NULL REFERENCES hoja_vida_artillero(id),
    tipo_curso_id          UUID NOT NULL REFERENCES tipos_curso(id),
    numero_cohorte         VARCHAR(30),
    fecha_inicio           DATE,
    fecha_fin              DATE,
    estado                 VARCHAR(20) NOT NULL
                           CHECK (estado IN ('EN_CURSO','APROBADO','REPROBADO','RETIRADO','ANULADO')),
    nota_final             NUMERIC(4,2) CHECK (nota_final BETWEEN 0 AND 5),
    numero_acta            VARCHAR(50),
    institucion            VARCHAR(200),
    importacion_excel_id   UUID REFERENCES importaciones_excel(id),
    fecha_creacion         TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio),
    -- Evita duplicados al reimportar el mismo curso.
    UNIQUE (hoja_vida_artillero_id, tipo_curso_id, numero_cohorte)
);
CREATE INDEX ix_artillero_cursos_evaluacion
    ON artillero_cursos(hoja_vida_artillero_id, tipo_curso_id, estado);
CREATE INDEX ix_artillero_cursos_tipo_curso ON artillero_cursos(tipo_curso_id);

CREATE TABLE tipos_certificacion (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo          VARCHAR(30)  NOT NULL UNIQUE,
    nombre          VARCHAR(200) NOT NULL,
    entidad_emisora VARCHAR(200),
    -- Contemplado para la verificacion por sistema; aun no se usa.
    tipo_sistema    VARCHAR(50),
    activo          BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE artillero_certificaciones (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hoja_vida_artillero_id UUID NOT NULL REFERENCES hoja_vida_artillero(id),
    tipo_certificacion_id  UUID NOT NULL REFERENCES tipos_certificacion(id),
    numero_certificado     VARCHAR(50),
    fecha_expedicion       DATE NOT NULL,
    -- NULL = no vence. "Vencida" se calcula en la consulta, no se guarda.
    fecha_vencimiento      DATE,
    estado                 VARCHAR(20) NOT NULL
                           CHECK (estado IN ('ACTIVA','SUSPENDIDA','REVOCADA')),
    importacion_excel_id   UUID REFERENCES importaciones_excel(id),
    fecha_creacion         TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_expedicion)
);
CREATE INDEX ix_artillero_certificaciones_evaluacion
    ON artillero_certificaciones(hoja_vida_artillero_id, tipo_certificacion_id, estado, fecha_vencimiento);
CREATE INDEX ix_artillero_certificaciones_tipo ON artillero_certificaciones(tipo_certificacion_id);


-- =============================================================================
-- 5. HABILITACION
-- =============================================================================

CREATE TABLE sistemas_artilleria (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo                  VARCHAR(30)  NOT NULL UNIQUE,
    nombre                  VARCHAR(200) NOT NULL,
    tipo_sistema            VARCHAR(50)  NOT NULL,
    calibre_milimetros      NUMERIC(6,2),
    -- Contemplado pero apagado: se enciende por dato, sin cambiar codigo.
    verificacion_habilitada BOOLEAN NOT NULL DEFAULT false,
    activo                  BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE requisitos_habilitacion (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- NULL = requisito general (el unico que se usa en el Sprint 1).
    sistema_artilleria_id UUID REFERENCES sistemas_artilleria(id),
    tipo_requisito        VARCHAR(20) NOT NULL
                          CHECK (tipo_requisito IN ('CURSO','CERTIFICACION')),
    tipo_curso_id         UUID REFERENCES tipos_curso(id),
    tipo_certificacion_id UUID REFERENCES tipos_certificacion(id),
    descripcion           VARCHAR(300) NOT NULL,
    activo                BOOLEAN NOT NULL DEFAULT true,
    -- Coherencia: cada requisito apunta exactamente a un curso O a una certificacion.
    CHECK (
        (tipo_requisito = 'CURSO'         AND tipo_curso_id IS NOT NULL AND tipo_certificacion_id IS NULL)
     OR (tipo_requisito = 'CERTIFICACION' AND tipo_certificacion_id IS NOT NULL AND tipo_curso_id IS NULL)
    )
);
CREATE INDEX ix_requisitos_habilitacion_sistema ON requisitos_habilitacion(sistema_artilleria_id);


-- =============================================================================
-- 6. HOJA DE VIDA: CARGOS (tablas ya creadas; uso en segunda entrega)
-- =============================================================================

CREATE TABLE tipos_cargo (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo      VARCHAR(30)  NOT NULL UNIQUE,
    nombre      VARCHAR(200) NOT NULL,
    descripcion TEXT,
    activo      BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE artillero_cargos (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hoja_vida_artillero_id UUID NOT NULL REFERENCES hoja_vida_artillero(id),
    tipo_cargo_id          UUID NOT NULL REFERENCES tipos_cargo(id),
    unidad_militar_id      UUID REFERENCES unidades_militares(id),
    fecha_inicio           DATE NOT NULL,
    -- NULL = cargo actual.
    fecha_fin              DATE,
    numero_resolucion      VARCHAR(50),
    observaciones          TEXT,
    fecha_creacion         TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
);
CREATE INDEX ix_artillero_cargos_hoja_vida ON artillero_cargos(hoja_vida_artillero_id);


-- =============================================================================
-- 7. SEGUNDA ENTREGA: INSTRUCTORES Y NOTAS POR MATERIA
--    (documentado ahora para no redisenar despues; se crea en la segunda entrega)
-- =============================================================================

CREATE TABLE instructores (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Nulo cuando el instructor es externo y no esta en personal_militar.
    personal_militar_id UUID REFERENCES personal_militar(id),
    numero_documento    VARCHAR(10) NOT NULL UNIQUE
                        CHECK (numero_documento ~ '^[0-9]{6,10}$'),
    nombre_completo     VARCHAR(200) NOT NULL,
    grado               VARCHAR(40),
    activo              BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE materias_curso (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo_curso_id      UUID NOT NULL REFERENCES tipos_curso(id),
    codigo             VARCHAR(30)  NOT NULL,
    nombre             VARCHAR(200) NOT NULL,
    intensidad_horaria INTEGER CHECK (intensidad_horaria > 0),
    activa             BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (tipo_curso_id, codigo)
);

CREATE TABLE artillero_notas_materia (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artillero_curso_id UUID NOT NULL REFERENCES artillero_cursos(id),
    materia_curso_id   UUID NOT NULL REFERENCES materias_curso(id),
    instructor_id      UUID REFERENCES instructores(id),
    nota               NUMERIC(4,2) NOT NULL CHECK (nota BETWEEN 0 AND 5),
    observaciones      TEXT,
    UNIQUE (artillero_curso_id, materia_curso_id)
);
CREATE INDEX ix_artillero_notas_materia_instructor ON artillero_notas_materia(instructor_id);


-- =============================================================================
-- 8. TRIGGERS DE fecha_actualizacion (reutilizan la funcion comun)
-- =============================================================================
CREATE TRIGGER tr_unidades_militares_fecha        BEFORE UPDATE ON unidades_militares        FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_actualizacion();
CREATE TRIGGER tr_personal_militar_fecha          BEFORE UPDATE ON personal_militar          FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_actualizacion();
CREATE TRIGGER tr_hoja_vida_artillero_fecha       BEFORE UPDATE ON hoja_vida_artillero       FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_actualizacion();
CREATE TRIGGER tr_usuarios_fecha                  BEFORE UPDATE ON usuarios                  FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_actualizacion();
CREATE TRIGGER tr_artillero_cursos_fecha          BEFORE UPDATE ON artillero_cursos          FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_actualizacion();
CREATE TRIGGER tr_artillero_certificaciones_fecha BEFORE UPDATE ON artillero_certificaciones FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_actualizacion();
CREATE TRIGGER tr_artillero_cargos_fecha          BEFORE UPDATE ON artillero_cargos          FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_actualizacion();


-- =============================================================================
-- 9. PERMISOS DEL USUARIO DE BASE DE DATOS DE LA APLICACION
--    La aplicacion NO se conecta como superusuario. Sobre la auditoria
--    solo puede insertar y leer (refuerza la inmutabilidad).
--    Reemplazar esart_aplicacion por el usuario real.
-- =============================================================================
-- REVOKE UPDATE, DELETE, TRUNCATE ON auditoria_eventos FROM esart_aplicacion;
-- GRANT  INSERT, SELECT          ON auditoria_eventos TO   esart_aplicacion;
