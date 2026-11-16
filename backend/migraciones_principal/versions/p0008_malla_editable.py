"""Malla de permisos editable desde la pantalla de administración.

La cuenta de la API puede crear, cambiar y quitar permisos por rol (rol_permisos) y excepciones
por usuario (usuario_permisos). Las reglas de protección (el rol ADMINISTRADOR es fijo, nadie se
deja sin acceso a la malla) las aplica el servicio, y cada cambio queda en auditoria_eventos.
"""

from alembic import op

revision = "p0008_malla_editable"
down_revision = "p0007_auditoria_eventos"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"


def upgrade():
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON esart.rol_permisos, esart.usuario_permisos
              TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            REVOKE INSERT, UPDATE, DELETE ON esart.rol_permisos, esart.usuario_permisos
              FROM {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
