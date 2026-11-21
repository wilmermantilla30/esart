"""El curso del cargue por Excel se registra también en esart.artillero_cursos.

Problema: la importación (p0011) guardaba el curso en esart.cursos y en el historial
(esart.hoja_vida_artillero), pero la regla de habilitación y la columna "Curso" del listado leen
esart.artillero_cursos. El curso cargado no aparecía y no habilitaba a nadie.

Esta revisión:
1. Da a la cuenta de la API lo que necesita la corrección del servicio:
   - SELECT (id) en hoja_vida_artillero (para RETURNING id al insertar el historial).
   - INSERT por columnas en artillero_cursos, SELECT (id) (SQLAlchemy usa RETURNING id al insertar
     una sola fila) y uso de su secuencia.
2. Repara lo ya importado: por cada fila del historial con curso EN_CURSO o CULMINADO y sin
   registro en artillero_cursos, crea ese registro (aprobado = CULMINADO). Es idempotente.

El downgrade solo revoca permisos: los cursos reparados son datos válidos y se conservan.
"""

from alembic import op

# Máximo 32 caracteres: alembic_version.version_num es varchar(32).
revision = "p0016_cursos_artilleros"
down_revision = "p0015_registro_manual_personal"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"
COLUMNAS = "hoja_vida_id, tipo_curso_id, nombre, institucion, fecha_inicio, fecha_fin, aprobado"

SQL_REPARAR = f"""
    INSERT INTO esart.artillero_cursos ({COLUMNAS})
    SELECT hv.id, c.tipo_curso_id, coalesce(c.nombre, tc.nombre), 'Escuela de Artillería',
           c.fecha_inicio, c.fecha_fin, c.estado = 'CULMINADO'
    FROM esart.hoja_vida_artillero hv
    JOIN esart.cursos c ON c.id = hv.curso_id
    LEFT JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    WHERE c.estado IN ('EN_CURSO', 'CULMINADO')
      AND c.fecha_inicio IS NOT NULL
      AND coalesce(c.nombre, tc.nombre) IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM esart.artillero_cursos ac WHERE ac.hoja_vida_id = hv.id)
"""  # noqa: S608


def upgrade():
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT (id) ON esart.hoja_vida_artillero TO {CUENTA_APLICACION};
            GRANT INSERT ({COLUMNAS}) ON esart.artillero_cursos TO {CUENTA_APLICACION};
            GRANT SELECT (id) ON esart.artillero_cursos TO {CUENTA_APLICACION};
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO {CUENTA_APLICACION}',
                           pg_get_serial_sequence('esart.artillero_cursos', 'id'));
          END IF;
        END $$;
    """)  # noqa: S608
    op.execute(SQL_REPARAR)


def downgrade():
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            REVOKE INSERT ({COLUMNAS}) ON esart.artillero_cursos FROM {CUENTA_APLICACION};
            REVOKE SELECT (id) ON esart.artillero_cursos FROM {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
