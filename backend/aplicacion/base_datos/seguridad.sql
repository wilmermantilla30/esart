
BEGIN;

CREATE SCHEMA IF NOT EXISTS seguridad;

-- 1. AUTENTICADOR VINCULADO
CREATE TABLE seguridad.usuario_totp (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL UNIQUE,
    secreto_cifrado TEXT NOT NULL,
    estado VARCHAR(15) NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado IN ('PENDIENTE','ACTIVO','REVOCADO')),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activado_en TIMESTAMPTZ,
    expira_configuracion_en TIMESTAMPTZ,
    revocado_en TIMESTAMPTZ,
    ultimo_intervalo_aceptado BIGINT,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. RECUPERACIÓN DE EMERGENCIA
CREATE TABLE seguridad.totp_recuperacion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    codigo_hash TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    usado_en TIMESTAMPTZ,
    revocado_en TIMESTAMPTZ
);

CREATE INDEX idx_totp_recuperacion_usuario
ON seguridad.totp_recuperacion(usuario_id);

-- 3. POLÍTICAS DE AUTORIZACIÓN
CREATE TABLE seguridad.politicas_accion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo VARCHAR(100) NOT NULL UNIQUE,
    nombre VARCHAR(160) NOT NULL,
    descripcion TEXT,
    modulo VARCHAR(80) NOT NULL,
    permiso_requerido VARCHAR(100),
    requiere_totp BOOLEAN NOT NULL DEFAULT TRUE,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    vigencia_segundos INTEGER NOT NULL DEFAULT 120
        CHECK (vigencia_segundos BETWEEN 30 AND 600),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. DESAFÍOS DE AUTORIZACIÓN
CREATE TABLE seguridad.desafios (
    id UUID PRIMARY KEY,
    usuario_id BIGINT NOT NULL,
    politica_id BIGINT NOT NULL
        REFERENCES seguridad.politicas_accion(id),
    recurso_tipo VARCHAR(100),
    recurso_id VARCHAR(150),
    operacion_hash VARCHAR(64) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado IN (
            'PENDIENTE','VERIFICADO',
            'CONSUMIDO','EXPIRADO','CANCELADO'
        )),
    intentos INTEGER NOT NULL DEFAULT 0
        CHECK (intentos >= 0),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_en TIMESTAMPTZ NOT NULL,
    verificado_en TIMESTAMPTZ,
    consumido_en TIMESTAMPTZ,
    ip_origen INET,
    correlacion_id UUID
);

CREATE INDEX idx_desafios_usuario_estado
ON seguridad.desafios(usuario_id, estado);

-- 5. AUTORIZACIONES DE OPERACIONES
CREATE TABLE seguridad.autorizaciones (
    id UUID PRIMARY KEY,
    desafio_id UUID NOT NULL UNIQUE
        REFERENCES seguridad.desafios(id),
    usuario_id BIGINT NOT NULL,
    politica_id BIGINT NOT NULL
        REFERENCES seguridad.politicas_accion(id),
    operacion_hash VARCHAR(64) NOT NULL,
    autorizada_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_en TIMESTAMPTZ NOT NULL,
    consumida_en TIMESTAMPTZ,
    resultado VARCHAR(20) NOT NULL DEFAULT 'AUTORIZADA'
        CHECK (resultado IN (
            'AUTORIZADA','CONSUMIDA','REVOCADA'
        ))
);

-- 6. AUDITORÍA GENERAL
CREATE TABLE seguridad.auditoria (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evento_id UUID NOT NULL UNIQUE,
    correlacion_id UUID,
    usuario_id BIGINT,
    actor_tipo VARCHAR(30) NOT NULL DEFAULT 'USUARIO',
    modulo VARCHAR(80) NOT NULL,
    accion VARCHAR(100) NOT NULL,
    recurso_tipo VARCHAR(100),
    recurso_id VARCHAR(150),
    autorizacion_id UUID
        REFERENCES seguridad.autorizaciones(id),
    resultado VARCHAR(30) NOT NULL,
    motivo TEXT,
    ip_origen INET,
    agente_usuario TEXT,
    fecha_evento TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_auditoria_usuario_fecha
ON seguridad.auditoria(usuario_id, fecha_evento DESC);

CREATE INDEX idx_auditoria_recurso
ON seguridad.auditoria(recurso_tipo, recurso_id);

CREATE INDEX idx_auditoria_correlacion
ON seguridad.auditoria(correlacion_id);

-- 7. CAMBIOS DE INFORMACIÓN
CREATE TABLE seguridad.auditoria_cambios (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auditoria_id BIGINT NOT NULL
        REFERENCES seguridad.auditoria(id),
    campo VARCHAR(120) NOT NULL,
    valor_anterior JSONB,
    valor_nuevo JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. POLÍTICAS INICIALES
INSERT INTO seguridad.politicas_accion
(codigo, nombre, modulo, requiere_totp)
VALUES
('CURSO_APROBAR', 'Aprobar curso', 'CURSOS', TRUE),
('CURSO_REPROBAR', 'Reprobar curso', 'CURSOS', TRUE),
('CURSO_ELIMINAR', 'Eliminar curso', 'CURSOS', TRUE),
('CURSO_CARGUE_EXCEL', 'Confirmar cargue masivo', 'CURSOS', TRUE),
('CURSO_MODIFICAR_APROBACION', 'Modificar aprobación', 'CURSOS', TRUE),
('PERSONAL_ELIMINAR', 'Eliminar personal', 'PERSONAL', TRUE),
('PERSONAL_CARGUE_EXCEL', 'Confirmar cargue de personal', 'PERSONAL', TRUE)
ON CONFLICT (codigo) DO NOTHING;

COMMIT;
