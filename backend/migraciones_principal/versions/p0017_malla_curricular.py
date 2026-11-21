"""S2-01: malla curricular versionada por tipo de curso y escala de notas de 0 a 5.

Decisiones de la Escuela (docs/backlog_sprint2_esart.xlsx, hoja Decisiones):
- Cada tipo de curso tiene su malla; al editarla se crea una VERSIÓN nueva y la anterior queda
  HISTÓRICA. Un curso queda ligado a la versión vigente cuando se crea (trigger), así cambiar la
  malla nunca altera las materias de un curso ya iniciado. Los cursos anteriores quedan sin malla
  (solo aprobado / no aprobado).
- Cada materia de la malla es evaluable o "sin nota" (Tiempo del comandante, Entrenamiento físico):
  las que no tienen nota no cuentan en el promedio del curso.
- La nota mínima ya no vive en cada fila de la malla: será un parámetro general (S2-10).
- Todas las notas van de 0 a 5 con 2 decimales (antes 0 a 100). Una sola habilitación por materia.

Las tablas de la fase 1 (materias, malla_curricular, notas_materia, habilitaciones,
notas_finales_egresado, egresados_curso) están vacías: si la malla ya tuviera filas, la migración
se detiene en vez de inventar a qué versión pertenecen.
"""

from alembic import op

revision = "p0017_malla_curricular"
down_revision = "p0016_cursos_artilleros_importacion"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"

# Mismo nombre de restricción que recrearon p0007, p0009, p0012, p0013 y p0015.
NOMBRE_RESTRICCION = "ck_auditoria_eventos_ck_auditoria_eventos_accion"
# Acciones vigentes tras p0015 (p0016 no las cambió).
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
    "PERSONAL_REGISTRADO",
)
ACCIONES_NUEVAS = ("MALLA_CURRICULAR_CARGADA",)

# (tabla, restricción, columna) de cada nota que pasa a la escala 0 a 5.
NOTAS = (
    ("notas_materia", "notas_materia_nota_check", "nota"),
    ("notas_materia", "notas_materia_nota_habilitacion_check", "nota_habilitacion"),
    ("habilitaciones", "habilitaciones_nota_obtenida_check", "nota_obtenida"),
    ("notas_finales_egresado", "notas_finales_egresado_nota_check", "nota"),
    ("notas_finales_egresado", "notas_finales_egresado_nota_habilitacion_check", "nota_habilitacion"),
    ("egresados_curso", "egresados_curso_nota_final_check", "nota_final"),
    ("inscripciones_curso", "inscripciones_curso_nota_final_check", "nota_final"),
)

# Al crear un curso sin versión de malla se le asigna la vigente de su tipo. Si se indica una,
# debe ser del mismo tipo de curso (evita notas sobre materias de otro curso).
FUNCION_ASIGNAR_MALLA = """
    CREATE FUNCTION esart.asignar_malla_vigente() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.malla_version_id IS NULL THEN
        SELECT v.id INTO NEW.malla_version_id
        FROM esart.versiones_malla v
        WHERE v.tipo_curso_id = NEW.tipo_curso_id AND v.estado = 'VIGENTE';
      ELSIF NOT EXISTS (
        SELECT 1 FROM esart.versiones_malla v
        WHERE v.id = NEW.malla_version_id AND v.tipo_curso_id = NEW.tipo_curso_id
      ) THEN
        RAISE EXCEPTION 'La versión de malla % no pertenece al tipo de curso %',
          NEW.malla_version_id, NEW.tipo_curso_id;
      END IF;
      RETURN NEW;
    END $$
"""


def _restriccion_acciones(acciones: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {NOMBRE_RESTRICCION}")
    op.execute(
        f"ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT {NOMBRE_RESTRICCION} CHECK (accion IN ({lista}))"  # noqa: S608
    )


def _escala_notas(maximo: int) -> None:
    """Reemplaza el CHECK de cada nota. Si alguna nota guardada quedara fuera de la escala nueva,
    PostgreSQL rechaza el CHECK y toda la migración se revierte (nada se recorta en silencio)."""
    for tabla, restriccion, columna in NOTAS:
        op.execute(f"ALTER TABLE esart.{tabla} DROP CONSTRAINT {restriccion}")
        op.execute(
            f"ALTER TABLE esart.{tabla} ADD CONSTRAINT {restriccion} "
            f"CHECK ({columna} >= 0 AND {columna} <= {maximo})"
        )


def _exigir_vacia(tabla: str) -> None:
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM esart.{tabla}) THEN
            RAISE EXCEPTION 'esart.{tabla} tiene datos: esta migración solo reestructura tablas vacías';
          END IF;
        END $$;
    """)  # noqa: S608


def upgrade():
    for tabla in ("malla_curricular", "notas_materia", "habilitaciones", "notas_finales_egresado"):
        _exigir_vacia(tabla)

    # Versiones de la malla de cada tipo de curso: solo una VIGENTE por tipo.
    op.execute("""
        CREATE TABLE esart.versiones_malla (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY,
            tipo_curso_id BIGINT NOT NULL,
            numero INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
            observacion TEXT,
            creado_por_id BIGINT,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT versiones_malla_pkey PRIMARY KEY (id),
            CONSTRAINT fk_versiones_malla_tipo_curso_id FOREIGN KEY (tipo_curso_id)
              REFERENCES esart.tipos_curso (id),
            CONSTRAINT fk_versiones_malla_creado_por_id FOREIGN KEY (creado_por_id)
              REFERENCES esart_ref.usuarios (id) ON DELETE SET NULL,
            CONSTRAINT ck_versiones_malla_estado CHECK (estado IN ('VIGENTE', 'HISTORICA')),
            CONSTRAINT ck_versiones_malla_numero CHECK (numero >= 1),
            CONSTRAINT ck_versiones_malla_anio CHECK (anio BETWEEN 2000 AND 2100)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_versiones_malla_numero ON esart.versiones_malla (tipo_curso_id, numero)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_versiones_malla_vigente ON esart.versiones_malla (tipo_curso_id) "
        "WHERE estado = 'VIGENTE'"
    )

    # Cada fila de la malla pertenece a una versión; área y módulo vienen del documento de la Escuela.
    op.execute(
        "ALTER TABLE esart.malla_curricular DROP CONSTRAINT malla_curricular_nota_minima_aprobacion_check"
    )
    op.execute("ALTER TABLE esart.malla_curricular DROP COLUMN nota_minima_aprobacion")
    op.execute("""
        ALTER TABLE esart.malla_curricular
          ADD COLUMN version_id BIGINT NOT NULL,
          ADD COLUMN area VARCHAR(100),
          ADD COLUMN modulo VARCHAR(100),
          ADD COLUMN evaluable BOOLEAN NOT NULL DEFAULT true,
          ADD CONSTRAINT fk_malla_curricular_version_id FOREIGN KEY (version_id)
            REFERENCES esart.versiones_malla (id),
          ADD CONSTRAINT ck_malla_curricular_orden CHECK (orden >= 1)
    """)
    # La misma materia puede estar en varias versiones, pero una sola vez en cada una.
    op.execute("DROP INDEX esart.uq_malla_tipo_materia")
    op.execute(
        "CREATE UNIQUE INDEX uq_malla_version_materia ON esart.malla_curricular (version_id, materia_id)"
    )
    op.execute("CREATE UNIQUE INDEX uq_malla_version_orden ON esart.malla_curricular (version_id, orden)")
    # Catálogo único: no puede haber dos materias con el mismo nombre (sin distinguir mayúsculas).
    op.execute("CREATE UNIQUE INDEX uq_materias_nombre ON esart.materias (upper(nombre))")

    _escala_notas(5)
    op.execute("ALTER TABLE esart.habilitaciones DROP CONSTRAINT habilitaciones_numero_habilitacion_check")
    op.execute(
        "ALTER TABLE esart.habilitaciones ADD CONSTRAINT habilitaciones_numero_habilitacion_check "
        "CHECK (numero_habilitacion = 1)"
    )

    # Versión de malla de cada curso (NULL en los cursos anteriores a la malla en la plataforma).
    op.execute("""
        ALTER TABLE esart.cursos
          ADD COLUMN malla_version_id BIGINT,
          ADD CONSTRAINT fk_cursos_malla_version_id FOREIGN KEY (malla_version_id)
            REFERENCES esart.versiones_malla (id)
    """)
    op.execute("CREATE INDEX ix_cursos_malla_version_id ON esart.cursos (malla_version_id)")
    op.execute(FUNCION_ASIGNAR_MALLA)
    op.execute("""
        CREATE TRIGGER tg_cursos_asignar_malla BEFORE INSERT ON esart.cursos
        FOR EACH ROW EXECUTE FUNCTION esart.asignar_malla_vigente()
    """)

    _restriccion_acciones(ACCIONES_ANTERIORES + ACCIONES_NUEVAS)

    # Permisos mínimos de la API: leer y cargar mallas; una versión solo cambia de estado
    # (VIGENTE -> HISTORICA), nunca se borra ni se reescriben sus materias.
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT, INSERT ON esart.materias TO {CUENTA_APLICACION};
            GRANT SELECT, INSERT ON esart.versiones_malla TO {CUENTA_APLICACION};
            GRANT UPDATE (estado) ON esart.versiones_malla TO {CUENTA_APLICACION};
            GRANT SELECT, INSERT ON esart.malla_curricular TO {CUENTA_APLICACION};
            GRANT SELECT (malla_version_id) ON esart.cursos TO {CUENTA_APLICACION};
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO {CUENTA_APLICACION}',
                           pg_get_serial_sequence('esart.materias', 'id'));
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO {CUENTA_APLICACION}',
                           pg_get_serial_sequence('esart.versiones_malla', 'id'));
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO {CUENTA_APLICACION}',
                           pg_get_serial_sequence('esart.malla_curricular', 'id'));
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    for tabla in ("malla_curricular", "notas_materia", "habilitaciones", "notas_finales_egresado"):
        _exigir_vacia(tabla)
    # Si la cuenta de la API es la dueña de las tablas (equipos de desarrollo), no se le revoca
    # nada: perdería el acceso a sus propias tablas y la siguiente subida fallaría.
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}')
             AND pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'esart.materias'::regclass))
                 <> '{CUENTA_APLICACION}' THEN
            REVOKE SELECT, INSERT ON esart.materias FROM {CUENTA_APLICACION};
            REVOKE SELECT, INSERT ON esart.malla_curricular FROM {CUENTA_APLICACION};
            REVOKE SELECT (malla_version_id) ON esart.cursos FROM {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
    # Solo funciona si no hay eventos con la acción nueva (la auditoría es inmutable).
    _restriccion_acciones(ACCIONES_ANTERIORES)
    op.execute("DROP TRIGGER tg_cursos_asignar_malla ON esart.cursos")
    op.execute("DROP FUNCTION esart.asignar_malla_vigente()")
    op.execute("ALTER TABLE esart.cursos DROP COLUMN malla_version_id")
    op.execute("ALTER TABLE esart.habilitaciones DROP CONSTRAINT habilitaciones_numero_habilitacion_check")
    op.execute(
        "ALTER TABLE esart.habilitaciones ADD CONSTRAINT habilitaciones_numero_habilitacion_check "
        "CHECK (numero_habilitacion >= 1 AND numero_habilitacion <= 2)"
    )
    _escala_notas(100)
    op.execute("DROP INDEX esart.uq_materias_nombre")
    op.execute("DROP INDEX esart.uq_malla_version_orden")
    op.execute("DROP INDEX esart.uq_malla_version_materia")
    op.execute("""
        ALTER TABLE esart.malla_curricular
          DROP CONSTRAINT ck_malla_curricular_orden,
          DROP COLUMN version_id,
          DROP COLUMN area,
          DROP COLUMN modulo,
          DROP COLUMN evaluable,
          ADD COLUMN nota_minima_aprobacion NUMERIC(4, 2) NOT NULL,
          ADD CONSTRAINT malla_curricular_nota_minima_aprobacion_check
            CHECK (nota_minima_aprobacion >= 0 AND nota_minima_aprobacion <= 100)
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_malla_tipo_materia ON esart.malla_curricular (tipo_curso_id, materia_id)"
    )
    op.execute("DROP TABLE esart.versiones_malla")
