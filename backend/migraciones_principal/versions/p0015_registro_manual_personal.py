"""Registro manual de personal militar (componente PERSONAL_CARGUE_MANUAL).

- Agrega la acción de auditoría PERSONAL_REGISTRADO al CHECK de esart.auditoria_eventos.
- No crea tablas ni cambia privilegios: el INSERT por columnas sobre esart.personal_militar
  ya lo otorgó p0011 (cargue por Excel) y el componente PERSONAL_CARGUE_MANUAL existe desde p0005.
"""

from alembic import op

revision = "p0015_registro_manual_personal"
down_revision = "p0014_cursos_del_instructor"
branch_labels = None
depends_on = None

NOMBRE_RESTRICCION = "ck_auditoria_eventos_ck_auditoria_eventos_accion"
# Acciones vigentes tras p0013 (p0014 no las cambió).
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
    "USUARIO_ACTIVADO",
    "USUARIO_DESACTIVADO",
    "CONTRASENA_RESTABLECIDA",
    "CONTRASENA_CAMBIADA",
    "PARAMETROS_ACTUALIZADOS",
    "PLANTILLA_PUBLICADA",
    "PLANTILLA_DESCARGADA",
    "PLANTILLA_RETIRADA",
    "INSTRUCTOR_REGISTRADO",
    "INSTRUCTOR_ACTUALIZADO",
    "INSTRUCTOR_ACTIVADO",
    "INSTRUCTOR_DESACTIVADO",
)
ACCIONES_NUEVAS = ("PERSONAL_REGISTRADO",)


def _restriccion_acciones(acciones: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {NOMBRE_RESTRICCION}")
    op.execute(
        f"ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT {NOMBRE_RESTRICCION} CHECK (accion IN ({lista}))"  # noqa: S608
    )


def upgrade():
    _restriccion_acciones(ACCIONES_ANTERIORES + ACCIONES_NUEVAS)


def downgrade():
    # Falla si ya hay eventos PERSONAL_REGISTRADO (la auditoría es inmutable): es intencional.
    _restriccion_acciones(ACCIONES_ANTERIORES)
