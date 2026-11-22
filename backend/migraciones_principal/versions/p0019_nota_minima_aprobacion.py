"""S2-10: nota mínima de aprobación configurable en Parámetros.

Decisiones de la Escuela (docs/backlog_sprint2_esart.xlsx, hojas Decisiones y Por confirmar):
- Escala de 0 a 5 con 2 decimales; el valor inicial es 3,00.
- Se cambia desde el panel de Parámetros con el código del autenticador (TOTP) y queda auditado.
- Un cambio aplica SOLO a los cursos que se creen después: cada curso guarda la nota mínima que
  estaba vigente al crearse. Así, los resultados ya aprobados por el Inspector no se recalculan.

Cambios:
- Parámetro NOTA_MINIMA_APROBACION en esart.parametros_habilitacion (la misma tabla de la regla
  APTO / NO APTO, que ya tiene el permiso de edición de la cuenta de la API).
- Columna esart.cursos.nota_minima_aprobacion (0 a 5). Un trigger la llena con el valor vigente
  al crear el curso, igual que la versión de la malla (p0017).
- Los cursos que ya tienen malla quedan con 3,00, la nota con que se crearon. Los anteriores a la
  malla quedan en NULL: solo registran aprobado / no aprobado.
"""

from alembic import op

revision = "p0019_nota_minima_aprobacion"
down_revision = "p0018_permisos_notas"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"
CODIGO_PARAMETRO = "NOTA_MINIMA_APROBACION"
NOTA_INICIAL = "3.00"

# Al crear un curso sin nota mínima se le copia la vigente. Si el parámetro falta, el curso no se
# crea: es mejor un error visible que un curso sin regla de aprobación.
FUNCION_ASIGNAR_NOTA = f"""
    CREATE FUNCTION esart.asignar_nota_minima_vigente() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.nota_minima_aprobacion IS NULL THEN
        SELECT (p.valor #>> '{{}}')::numeric(3, 2) INTO NEW.nota_minima_aprobacion
        FROM esart.parametros_habilitacion p
        WHERE p.codigo = '{CODIGO_PARAMETRO}';
        IF NEW.nota_minima_aprobacion IS NULL THEN
          RAISE EXCEPTION 'Falta el parámetro {CODIGO_PARAMETRO}';
        END IF;
      END IF;
      RETURN NEW;
    END $$
"""  # noqa: S608


def upgrade():
    op.execute(f"""
        INSERT INTO esart.parametros_habilitacion (codigo, valor, descripcion)
        VALUES ('{CODIGO_PARAMETRO}', '{NOTA_INICIAL}'::jsonb,
                'Nota mínima para aprobar una materia y el curso (escala 0 a 5). Cada curso guarda la '
                'vigente al crearse: un cambio solo aplica a los cursos nuevos.')
        ON CONFLICT (codigo) DO NOTHING
    """)  # noqa: S608

    op.execute("""
        ALTER TABLE esart.cursos
          ADD COLUMN nota_minima_aprobacion NUMERIC(3, 2),
          ADD CONSTRAINT ck_cursos_nota_minima_aprobacion
            CHECK (nota_minima_aprobacion >= 0 AND nota_minima_aprobacion <= 5)
    """)
    # Los cursos con malla se crearon con la regla de 3,00 (S2-01).
    op.execute(
        f"UPDATE esart.cursos SET nota_minima_aprobacion = {NOTA_INICIAL} WHERE malla_version_id IS NOT NULL"  # noqa: S608
    )

    op.execute(FUNCION_ASIGNAR_NOTA)
    op.execute("""
        CREATE TRIGGER tg_cursos_asignar_nota_minima BEFORE INSERT ON esart.cursos
        FOR EACH ROW EXECUTE FUNCTION esart.asignar_nota_minima_vigente()
    """)

    # La API lee la nota de cada curso (la edición del parámetro ya la tiene desde p0006).
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT (nota_minima_aprobacion) ON esart.cursos TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    # Si la cuenta de la API es la dueña de las tablas (equipos de desarrollo), no se le revoca
    # nada: perdería el acceso a su propia tabla (mismo cuidado que p0017).
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}')
             AND pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'esart.cursos'::regclass))
                 <> '{CUENTA_APLICACION}' THEN
            REVOKE SELECT (nota_minima_aprobacion) ON esart.cursos FROM {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
    op.execute("DROP TRIGGER tg_cursos_asignar_nota_minima ON esart.cursos")
    op.execute("DROP FUNCTION esart.asignar_nota_minima_vigente()")
    op.execute("ALTER TABLE esart.cursos DROP COLUMN nota_minima_aprobacion")
    op.execute(f"DELETE FROM esart.parametros_habilitacion WHERE codigo = '{CODIGO_PARAMETRO}'")  # noqa: S608
