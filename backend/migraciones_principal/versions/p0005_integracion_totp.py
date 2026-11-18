"""Propuesta incremental para las siete tablas TOTP ya existentes. No crea tablas."""

from alembic import op

revision = "p0005_integracion_totp"
down_revision = "p0004_captcha_local"
branch_labels = None
depends_on = None


def upgrade():
    # Las tablas deben haber sido inventariadas y respaldadas por el operador.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM unnest(ARRAY['usuario_totp','totp_recuperacion','desafios',
        'autorizaciones','politicas_accion','auditoria','auditoria_cambios']) t
        WHERE to_regclass('seguridad.' || t) IS NULL) THEN
        RAISE EXCEPTION 'Falta una tabla seguridad inventariada; no recrear automáticamente';
      END IF;
    END $$""")
    for tabla in ("usuario_totp", "totp_recuperacion", "desafios", "autorizaciones", "auditoria"):
        # Una validación fallida revierte la migración: jamás borrar huérfanos.
        op.execute(
            f"ALTER TABLE seguridad.{tabla} ADD CONSTRAINT fk_{tabla}_usuario_esart "
            "FOREIGN KEY(usuario_id) REFERENCES esart_ref.usuarios(id) NOT VALID"
        )
        op.execute(f"ALTER TABLE seguridad.{tabla} VALIDATE CONSTRAINT fk_{tabla}_usuario_esart")
    op.execute(
        "ALTER TABLE seguridad.desafios ADD CONSTRAINT uq_desafio_contexto "
        "UNIQUE(id,usuario_id,politica_id,operacion_hash)"
    )
    op.execute(
        "ALTER TABLE seguridad.autorizaciones ADD CONSTRAINT fk_autorizacion_contexto "
        "FOREIGN KEY(desafio_id,usuario_id,politica_id,operacion_hash) "
        "REFERENCES seguridad.desafios(id,usuario_id,politica_id,operacion_hash) NOT VALID"
    )
    op.execute("ALTER TABLE seguridad.autorizaciones VALIDATE CONSTRAINT fk_autorizacion_contexto")
    op.execute("""CREATE FUNCTION seguridad.impedir_cambio_auditoria() RETURNS trigger
       LANGUAGE plpgsql AS $$ BEGIN
       RAISE EXCEPTION 'Auditoria de seguridad solo admite inserciones';
       END $$""")
    for tabla in ("auditoria", "auditoria_cambios"):
        op.execute(
            f"CREATE TRIGGER seguridad_auditoria_inmutable BEFORE UPDATE OR DELETE ON seguridad.{tabla} "
            "FOR EACH ROW EXECUTE FUNCTION seguridad.impedir_cambio_auditoria()"
        )
        op.execute(
            f"CREATE TRIGGER seguridad_auditoria_no_truncate BEFORE TRUNCATE ON seguridad.{tabla} "
            "FOR EACH STATEMENT EXECUTE FUNCTION seguridad.impedir_cambio_auditoria()"
        )
    op.execute("""INSERT INTO seguridad.politicas_accion(codigo,nombre,modulo,requiere_totp)
       VALUES ('LOGIN_TOTP','Segundo factor de login','SEGURIDAD',true),
              ('DESBLOQUEO_TOTP','Desbloqueo con factor previamente vinculado','SEGURIDAD',true)
       ON CONFLICT(codigo) DO NOTHING""")
    permisos = """GRANT USAGE ON SCHEMA seguridad TO esart_aplicacion;
       GRANT SELECT ON seguridad.politicas_accion TO esart_aplicacion;
       GRANT SELECT,INSERT ON seguridad.usuario_totp,seguridad.totp_recuperacion,
         seguridad.desafios,seguridad.autorizaciones,seguridad.auditoria,
         seguridad.auditoria_cambios TO esart_aplicacion;
       GRANT UPDATE(secreto_cifrado,estado,activado_en,expira_configuracion_en,revocado_en,
         ultimo_intervalo_aceptado,actualizado_en) ON seguridad.usuario_totp TO esart_aplicacion;
       GRANT UPDATE(usado_en,revocado_en) ON seguridad.totp_recuperacion TO esart_aplicacion;
       GRANT UPDATE(estado,intentos,verificado_en,consumido_en) ON seguridad.desafios TO esart_aplicacion;
       GRANT UPDATE(resultado,consumida_en) ON seguridad.autorizaciones TO esart_aplicacion;
       GRANT USAGE,SELECT ON SEQUENCE seguridad.usuario_totp_id_seq,seguridad.totp_recuperacion_id_seq,
         seguridad.auditoria_id_seq,seguridad.auditoria_cambios_id_seq TO esart_aplicacion;
       REVOKE UPDATE,DELETE,TRUNCATE ON seguridad.auditoria,seguridad.auditoria_cambios FROM esart_aplicacion;
    """
    for sentencia in permisos.split(";"):
        if sentencia.strip():
            op.execute(sentencia)


def downgrade():
    raise RuntimeError("La reversión TOTP requiere un plan autorizado; no borrar autenticadores ni auditoría")
