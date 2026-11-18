"""Une las ramas HU-10 y TOTP sin reescribir revisiones existentes ni ejecutar DDL."""

revision = "p0010_merge_hu10_totp"
down_revision = ("p0009_gestion_usuarios", "p0005_integracion_totp")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
