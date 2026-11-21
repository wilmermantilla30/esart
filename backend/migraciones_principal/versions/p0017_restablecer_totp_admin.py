"""Permite auditar y autorizar el restablecimiento administrativo del autenticador."""

from alembic import op

revision = "p0017_restablecer_totp_admin"
down_revision = "p0016_cursos_artilleros"
branch_labels = None
depends_on = None

ACCION_NUEVA = "TOTP_RESTABLECIDO"
RESTRICCION_ACCIONES = "ck_auditoria_eventos_ck_auditoria_eventos_accion"

ACCIONES = (
    "LOGIN_EXITOSO", "LOGIN_FALLIDO", "USUARIO_BLOQUEADO", "USUARIO_DESBLOQUEADO",
    "CIERRE_SESION", "CONSULTA_ARTILLERO", "CONSULTA_HABILITADOS", "CONSULTA_NO_HABILITADOS",
    "CONSULTA_RESUMEN", "ACCESO_DENEGADO", "PERMISOS_ROL_MODIFICADOS",
    "PERMISOS_USUARIO_MODIFICADOS", "USUARIO_CREADO", "IMPORTACION_EXCEL", "USUARIO_ACTIVADO",
    "USUARIO_DESACTIVADO", "CONTRASENA_RESTABLECIDA", "CONTRASENA_CAMBIADA",
    "PARAMETROS_ACTUALIZADOS", "PLANTILLA_PUBLICADA", "PLANTILLA_DESCARGADA", "PLANTILLA_RETIRADA",
    "INSTRUCTOR_REGISTRADO", "INSTRUCTOR_ACTUALIZADO", "INSTRUCTOR_ACTIVADO", "INSTRUCTOR_DESACTIVADO",
    "PERSONAL_REGISTRADO", ACCION_NUEVA,
)


def upgrade():
    acciones = ", ".join(f"'{accion}'" for accion in ACCIONES)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {RESTRICCION_ACCIONES}")
    op.execute(
        f"ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT {RESTRICCION_ACCIONES} "
        f"CHECK (accion IN ({acciones}))"
    )
    op.execute("""
        INSERT INTO seguridad.politicas_accion
            (codigo, nombre, descripcion, modulo, permiso_requerido, requiere_totp, activa, vigencia_segundos)
        VALUES
            ('USUARIO_RESTABLECER_TOTP', 'Restablecer autenticador de usuario',
             'Restablecimiento administrativo con contraseña y TOTP vigentes', 'SEGURIDAD',
             'usuarios:restablecer_totp', true, true, 120)
        ON CONFLICT (codigo) DO UPDATE SET
            permiso_requerido = EXCLUDED.permiso_requerido,
            requiere_totp = true,
            activa = true,
            vigencia_segundos = EXCLUDED.vigencia_segundos
    """)


def downgrade():
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM esart.auditoria_eventos WHERE accion = '{ACCION_NUEVA}') THEN
            RAISE EXCEPTION 'No se puede revertir: existen eventos TOTP_RESTABLECIDO en auditoría';
          END IF;
        END $$
    """)
    op.execute("DELETE FROM seguridad.politicas_accion WHERE codigo = 'USUARIO_RESTABLECER_TOTP'")
    acciones = ", ".join(f"'{accion}'" for accion in ACCIONES if accion != ACCION_NUEVA)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {RESTRICCION_ACCIONES}")
    op.execute(
        f"ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT {RESTRICCION_ACCIONES} "
        f"CHECK (accion IN ({acciones}))"
    )
