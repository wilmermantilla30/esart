"""Panel de instructores de la Escuela de Artillería (militares y civiles, con foto y especialidades).

- esart.instructores ya existía (diseño p0001 + foto de p0011) pero exigía un usuario de ESART.
  Un instructor no necesita entrar a la plataforma, y puede ser civil:
    * MILITAR: se liga a Personal militar (personal_id); nombre y grado salen de ahí.
    * CIVIL: guarda su documento, nombres, apellidos y profesión.
  usuario_id queda opcional (los instructores que ya tenían usuario se conservan).
- Catálogo inicial de especialidades (provisional, mientras la Escuela valida la lista oficial).
- Componente INSTRUCTORES en la malla: el administrador lo gestiona; el usuario lo consulta.
- Permisos mínimos de la API y acciones nuevas de auditoría.
"""

from alembic import op
from sqlalchemy import text

revision = "p0013_panel_instructores"
down_revision = "p0012_panel_parametros"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"

# Lista provisional entregada por SS.Mantilla el 2026-11-17 (se ampliará con la Escuela).
ESPECIALIDADES = (
    ("OA", "Observación adelantada"),
    ("ACL", "Artillería de Campaña Liviana"),
    ("ACM", "Artillería de Campaña Mediana"),
    ("RSOP", "RSOP"),
    ("CDT", "Centro Director de Tiro"),
    ("TP", "Tiro Predictivo"),
)

NOMBRE_RESTRICCION = "ck_auditoria_eventos_ck_auditoria_eventos_accion"
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
)
ACCIONES_NUEVAS = (
    "INSTRUCTOR_REGISTRADO",
    "INSTRUCTOR_ACTUALIZADO",
    "INSTRUCTOR_ACTIVADO",
    "INSTRUCTOR_DESACTIVADO",
)


def _restriccion_acciones(acciones: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {NOMBRE_RESTRICCION}")
    op.execute(
        f"ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT {NOMBRE_RESTRICCION} CHECK (accion IN ({lista}))"  # noqa: S608
    )


def upgrade():
    # 1. Instructor militar o civil; el usuario de ESART deja de ser obligatorio.
    op.execute("""
        ALTER TABLE esart.instructores
          ALTER COLUMN usuario_id DROP NOT NULL,
          ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) NOT NULL DEFAULT 'MILITAR',
          ADD COLUMN IF NOT EXISTS personal_id BIGINT REFERENCES esart.personal_militar (id),
          ADD COLUMN IF NOT EXISTS documento_identidad VARCHAR(20),
          ADD COLUMN IF NOT EXISTS nombres VARCHAR(100),
          ADD COLUMN IF NOT EXISTS apellidos VARCHAR(100),
          ADD COLUMN IF NOT EXISTS profesion VARCHAR(150),
          ADD COLUMN IF NOT EXISTS actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
    """)
    # Los instructores que ya existían (con usuario) quedan ligados a su militar por la cédula.
    op.execute("""
        UPDATE esart.instructores i
        SET personal_id = p.id
        FROM esart_ref.usuarios u
        JOIN esart.personal_militar p ON p.documento_identidad = u.documento_identidad
        WHERE i.usuario_id = u.id AND i.personal_id IS NULL
    """)
    op.execute("""
        ALTER TABLE esart.instructores
          ADD CONSTRAINT ck_instructores_tipo CHECK (tipo IN ('MILITAR', 'CIVIL')),
          ADD CONSTRAINT ck_instructores_identidad CHECK (
            (tipo = 'MILITAR' AND (personal_id IS NOT NULL OR usuario_id IS NOT NULL))
            OR (tipo = 'CIVIL' AND personal_id IS NULL AND documento_identidad IS NOT NULL
                AND nombres IS NOT NULL AND apellidos IS NOT NULL)
          )
    """)
    # Un militar o un documento civil no se registra dos veces como instructor.
    op.execute(
        "CREATE UNIQUE INDEX uq_instructores_personal ON esart.instructores (personal_id) "
        "WHERE personal_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_instructores_documento_civil ON esart.instructores (documento_identidad) "
        "WHERE tipo = 'CIVIL'"
    )

    # 2. Catálogo provisional de especialidades.
    conexion = op.get_bind()
    for codigo, nombre in ESPECIALIDADES:
        conexion.execute(
            text(
                "INSERT INTO esart.especialidades_instructor (codigo, nombre) "
                "VALUES (:codigo, :nombre) ON CONFLICT (codigo) DO NOTHING"
            ),
            {"codigo": codigo, "nombre": nombre},
        )

    # 3. Menú y malla: ADMINISTRADOR gestiona; USUARIO (el Comandante) consulta.
    op.execute("""
        INSERT INTO esart.componentes (codigo, nombre, ruta_angular, orden, componente_padre_id, activo)
        VALUES ('INSTRUCTORES', 'Instructores', '/instructores', 85, NULL, true)
        ON CONFLICT (codigo) DO NOTHING
    """)
    op.execute("""
        INSERT INTO esart.rol_permisos
          (rol_id, componente_id, puede_acceder, puede_crear, puede_leer, puede_actualizar, puede_eliminar)
        SELECT r.id, c.id, true, r.codigo = 'ADMINISTRADOR', true, r.codigo = 'ADMINISTRADOR', false
        FROM esart.roles r CROSS JOIN esart.componentes c
        WHERE r.codigo IN ('ADMINISTRADOR', 'USUARIO') AND c.codigo = 'INSTRUCTORES'
        ON CONFLICT (rol_id, componente_id) DO NOTHING
    """)

    _restriccion_acciones(ACCIONES_ANTERIORES + ACCIONES_NUEVAS)

    # 4. Permisos mínimos de la API (registrar y editar; nunca borrar instructores).
    op.execute(f"""
        DO $$
        DECLARE
          secuencia text;
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT ON esart.instructores, esart.especialidades_instructor,
              esart.instructores_especialidades TO {CUENTA_APLICACION};
            GRANT INSERT (tipo, personal_id, documento_identidad, nombres, apellidos, profesion,
                          fecha_ingreso_escuela, activo, foto, foto_tipo)
              ON esart.instructores TO {CUENTA_APLICACION};
            GRANT UPDATE (documento_identidad, nombres, apellidos, profesion, fecha_ingreso_escuela,
                          activo, foto, foto_tipo, actualizado_en)
              ON esart.instructores TO {CUENTA_APLICACION};
            GRANT INSERT (instructor_id, especialidad_id, fecha_asignacion, activo)
              ON esart.instructores_especialidades TO {CUENTA_APLICACION};
            GRANT UPDATE (activo, fecha_asignacion)
              ON esart.instructores_especialidades TO {CUENTA_APLICACION};
            FOREACH secuencia IN ARRAY ARRAY[
              pg_get_serial_sequence('esart.instructores', 'id'),
              pg_get_serial_sequence('esart.instructores_especialidades', 'id')
            ] LOOP
              EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO {CUENTA_APLICACION}', secuencia);
            END LOOP;
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    _restriccion_acciones(ACCIONES_ANTERIORES)
    op.execute(
        "DELETE FROM esart.rol_permisos WHERE componente_id = "
        "(SELECT id FROM esart.componentes WHERE codigo = 'INSTRUCTORES')"
    )
    op.execute("DELETE FROM esart.componentes WHERE codigo = 'INSTRUCTORES'")
    op.execute("DROP INDEX IF EXISTS esart.uq_instructores_documento_civil")
    op.execute("DROP INDEX IF EXISTS esart.uq_instructores_personal")
    op.execute("""
        ALTER TABLE esart.instructores
          DROP CONSTRAINT IF EXISTS ck_instructores_identidad,
          DROP CONSTRAINT IF EXISTS ck_instructores_tipo,
          DROP COLUMN IF EXISTS actualizado_en,
          DROP COLUMN IF EXISTS profesion,
          DROP COLUMN IF EXISTS apellidos,
          DROP COLUMN IF EXISTS nombres,
          DROP COLUMN IF EXISTS documento_identidad,
          DROP COLUMN IF EXISTS personal_id,
          DROP COLUMN IF EXISTS tipo
    """)
    # Solo si no hay instructores sin usuario (se crearon después de esta migración).
    op.execute("ALTER TABLE esart.instructores ALTER COLUMN usuario_id SET NOT NULL")
