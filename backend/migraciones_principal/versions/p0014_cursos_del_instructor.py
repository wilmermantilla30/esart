"""Lectura de los cursos de cada instructor (detalle del panel de instructores).

Solo permisos de lectura para la cuenta de la API:
- esart.cursos: nombre, estado y comandante (p0011 solo dio lo que necesitaba la importación).
- esart.cursos_instructores: en qué cursos participa cada instructor y con qué rol.
No crea tablas ni cambia datos.
"""

from alembic import op

revision = "p0014_cursos_del_instructor"
down_revision = "p0013_panel_instructores"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"


def upgrade():
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT (id, codigo, nombre, tipo_curso_id, comandante_id, fecha_inicio, fecha_fin, estado)
              ON esart.cursos TO {CUENTA_APLICACION};
            GRANT SELECT (curso_id, instructor_id, rol_en_curso)
              ON esart.cursos_instructores TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            REVOKE SELECT (nombre, comandante_id, estado) ON esart.cursos FROM {CUENTA_APLICACION};
            REVOKE SELECT (curso_id, instructor_id, rol_en_curso)
              ON esart.cursos_instructores FROM {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
