-- SOLO REVISION. Generado offline: ninguna conexion ni ejecucion.
-- Aplicar unicamente mediante Alembic tras autorizacion, no ejecutar este archivo a mano.
ALTER TABLE esart.intentos_inicio_sesion ADD COLUMN captcha_requerido BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE esart.intentos_inicio_sesion ADD COLUMN captcha_validado BOOLEAN;

CREATE TABLE esart.limites_inicio_ip (
    clave VARCHAR(64) NOT NULL, 
    inicio TIMESTAMP WITH TIME ZONE NOT NULL, 
    intentos INTEGER NOT NULL, 
    CONSTRAINT pk_limites_inicio_ip PRIMARY KEY (clave), 
    CONSTRAINT ck_limites_inicio_ip_intentos_ip_positivos CHECK (intentos >= 0)
);

CREATE TABLE esart.estados_acceso_anonimos (
    clave VARCHAR(64) NOT NULL, 
    intentos_fallidos_consecutivos INTEGER DEFAULT 0 NOT NULL, 
    bloqueado_hasta TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_estados_acceso_anonimos PRIMARY KEY (clave), 
    CONSTRAINT ck_estados_acceso_anonimos_fallos_anonimos CHECK (intentos_fallidos_consecutivos >= 0)
);

CREATE TABLE esart.auditoria_acceso (
    id BIGINT GENERATED ALWAYS AS IDENTITY, 
    intento_id BIGINT NOT NULL, 
    evento VARCHAR(32) NOT NULL, 
    fecha TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_auditoria_acceso PRIMARY KEY (id), 
    CONSTRAINT fk_auditoria_acceso_intento_id_intentos_inicio_sesion FOREIGN KEY(intento_id) REFERENCES esart.intentos_inicio_sesion (id)
);

DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='esart_aplicacion') THEN
        GRANT USAGE ON SCHEMA esart,esart_ref TO esart_aplicacion;
        GRANT SELECT,INSERT,UPDATE ON esart.limites_inicio_ip,esart.estados_acceso_anonimos
          TO esart_aplicacion;
        GRANT SELECT,INSERT ON esart.auditoria_acceso TO esart_aplicacion;
        REVOKE UPDATE,DELETE,TRUNCATE ON esart.auditoria_acceso FROM esart_aplicacion,PUBLIC;
        GRANT USAGE ON SEQUENCE esart.auditoria_acceso_id_seq TO esart_aplicacion;
      END IF;
    END $$;

