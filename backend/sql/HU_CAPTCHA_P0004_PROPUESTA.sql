-- SOLO REVISION: generado offline, sin conexion.
-- Aplicar mediante Alembic tras autorizacion; no ejecutar manualmente.
CREATE TABLE esart.desafios_captcha (
    id VARCHAR(43) NOT NULL, 
    contexto VARCHAR(64) NOT NULL, 
    respuesta_hmac VARCHAR(64) NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    expira_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    consumido_en TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT captcha_plazo CHECK (expira_en > creado_en), 
    CONSTRAINT captcha_consumo CHECK (consumido_en IS NULL OR consumido_en >= creado_en)
);

CREATE INDEX ix_desafios_captcha_expira ON esart.desafios_captcha (expira_en);

ALTER TABLE esart.auditoria_acceso ALTER COLUMN intento_id DROP NOT NULL;

ALTER TABLE esart.auditoria_acceso ADD COLUMN captcha_id VARCHAR(43);

ALTER TABLE esart.auditoria_acceso ADD COLUMN origen_hmac VARCHAR(64);

ALTER TABLE esart.auditoria_acceso ADD CONSTRAINT fk_auditoria_captcha FOREIGN KEY(captcha_id) REFERENCES esart.desafios_captcha (id);

ALTER TABLE esart.auditoria_acceso ADD CONSTRAINT auditoria_referencia CHECK (intento_id IS NOT NULL OR captcha_id IS NOT NULL OR origen_hmac IS NOT NULL);

DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='esart_aplicacion') THEN
        GRANT SELECT,INSERT ON esart.desafios_captcha TO esart_aplicacion;
        GRANT UPDATE(consumido_en) ON esart.desafios_captcha TO esart_aplicacion;
      END IF;
    END $$;

