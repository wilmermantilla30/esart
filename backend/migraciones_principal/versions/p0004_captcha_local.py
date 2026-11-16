"""Desafíos CAPTCHA locales y auditoría correlacionada. No aplicada a principal sin aprobación."""

import sqlalchemy as sa
from alembic import op

revision = "p0004_captcha_local"
down_revision = "p0003_control_intentos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "desafios_captcha",
        sa.Column("id", sa.String(43), primary_key=True),
        sa.Column("contexto", sa.String(64), nullable=False),
        sa.Column("respuesta_hmac", sa.String(64), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumido_en", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expira_en > creado_en", name="captcha_plazo"),
        sa.CheckConstraint("consumido_en IS NULL OR consumido_en >= creado_en", name="captcha_consumo"),
        schema="esart",
    )
    op.create_index("ix_desafios_captcha_expira", "desafios_captcha", ["expira_en"], schema="esart")
    op.alter_column(
        "auditoria_acceso", "intento_id", existing_type=sa.BigInteger(), nullable=True, schema="esart"
    )
    op.add_column("auditoria_acceso", sa.Column("captcha_id", sa.String(43), nullable=True), schema="esart")
    op.add_column("auditoria_acceso", sa.Column("origen_hmac", sa.String(64), nullable=True), schema="esart")
    op.create_foreign_key(
        "fk_auditoria_captcha",
        "auditoria_acceso",
        "desafios_captcha",
        ["captcha_id"],
        ["id"],
        source_schema="esart",
        referent_schema="esart",
    )
    op.create_check_constraint(
        "auditoria_referencia",
        "auditoria_acceso",
        "intento_id IS NOT NULL OR captcha_id IS NOT NULL OR origen_hmac IS NOT NULL",
        schema="esart",
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='esart_aplicacion') THEN
        GRANT SELECT,INSERT ON esart.desafios_captcha TO esart_aplicacion;
        GRANT UPDATE(consumido_en) ON esart.desafios_captcha TO esart_aplicacion;
      END IF;
    END $$""")


def downgrade():
    raise RuntimeError("No borrar desafíos ni auditoría: preparar reversión expresamente autorizada")
