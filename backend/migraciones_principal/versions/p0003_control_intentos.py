"""Control persistente de intentos, ventana IP y auditoría de acceso; pendiente de aprobación principal."""

import sqlalchemy as sa
from alembic import op

revision = "p0003_control_intentos"
down_revision = "p0002_seguridad_sesiones"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "intentos_inicio_sesion",
        sa.Column("captcha_requerido", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="esart",
    )
    op.add_column(
        "intentos_inicio_sesion", sa.Column("captcha_validado", sa.Boolean(), nullable=True), schema="esart"
    )
    op.create_table(
        "limites_inicio_ip",
        sa.Column("clave", sa.String(64), primary_key=True),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.CheckConstraint("intentos >= 0", name="intentos_ip_positivos"),
        schema="esart",
    )
    op.create_table(
        "estados_acceso_anonimos",
        sa.Column("clave", sa.String(64), primary_key=True),
        sa.Column(
            "intentos_fallidos_consecutivos", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("intentos_fallidos_consecutivos >= 0", name="fallos_anonimos"),
        schema="esart",
    )
    op.create_table(
        "auditoria_acceso",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "intento_id", sa.BigInteger(), sa.ForeignKey("esart.intentos_inicio_sesion.id"), nullable=False
        ),
        sa.Column("evento", sa.String(32), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        schema="esart",
    )
    # Solo objetos de esta HU. No conceder permisos generales sobre usuarios ni contraseñas.
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='esart_aplicacion') THEN
        GRANT USAGE ON SCHEMA esart,esart_ref TO esart_aplicacion;
        GRANT SELECT,INSERT,UPDATE ON esart.limites_inicio_ip,esart.estados_acceso_anonimos
          TO esart_aplicacion;
        GRANT SELECT,INSERT ON esart.auditoria_acceso TO esart_aplicacion;
        REVOKE UPDATE,DELETE,TRUNCATE ON esart.auditoria_acceso FROM esart_aplicacion,PUBLIC;
        GRANT USAGE ON SEQUENCE esart.auditoria_acceso_id_seq TO esart_aplicacion;
      END IF;
    END $$""")


def downgrade():
    raise RuntimeError("Conservar intentos y auditoría: reversión requiere un procedimiento aprobado")
