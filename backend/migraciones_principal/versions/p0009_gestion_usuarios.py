"""Gestión de usuarios desde la web y cambio obligatorio de contraseña.

- La cuenta de la API puede cambiar la contraseña (hash), activar/desactivar y marcar
  "requiere cambio de contraseña" en esart_ref.usuarios. Nada más de esa tabla.
- La auditoría admite las acciones nuevas: activar, desactivar, restablecer y cambiar contraseña.
"""

from alembic import op

revision = "p0009_gestion_usuarios"
down_revision = "p0008_malla_editable"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"

ACCIONES_ANTERIORES = (
    "LOGIN_EXITOSO",
    "LOGIN_FALLIDO",
    "USUARIO_BLOQUEADO",
    "USUARIO_DESBLOQUEADO",
    "CIERRE_SESION",
    "CONSULTA_ARTILLERO",
    "CONSULTA_HABILITADOS",
    "CONSULTA_NO_HABILITADOS",
    "CONSULTA_RESUMEN",
    "ACCESO_DENEGADO",
    "PERMISOS_ROL_MODIFICADOS",
    "PERMISOS_USUARIO_MODIFICADOS",
    "USUARIO_CREADO",
    "IMPORTACION_EXCEL",
)
ACCIONES_NUEVAS = (
    "USUARIO_ACTIVADO",
    "USUARIO_DESACTIVADO",
    "CONTRASENA_RESTABLECIDA",
    "CONTRASENA_CAMBIADA",
)


# Nombre real con el que p0007 creó la restricción (la convención de nombres le antepuso el
# prefijo "ck_<tabla>_"). Se conserva el mismo nombre al recrearla.
NOMBRE_RESTRICCION = "ck_auditoria_eventos_ck_auditoria_eventos_accion"


def _restriccion_acciones(acciones: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {NOMBRE_RESTRICCION}")
    op.execute(
        "ALTER TABLE esart.auditoria_eventos "
        f"ADD CONSTRAINT {NOMBRE_RESTRICCION} CHECK (accion IN ({lista}))"  # noqa: S608
    )


def upgrade():
    _restriccion_acciones(ACCIONES_ANTERIORES + ACCIONES_NUEVAS)
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT UPDATE (contrasena_hash, activo, requiere_cambio_contrasena, actualizado_en)
              ON esart_ref.usuarios TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            REVOKE UPDATE (contrasena_hash, activo, requiere_cambio_contrasena, actualizado_en)
              ON esart_ref.usuarios FROM {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
    # Solo funciona si no hay eventos con las acciones nuevas (la auditoría es inmutable).
    _restriccion_acciones(ACCIONES_ANTERIORES)
