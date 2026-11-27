"""S2-09: mallas curriculares y tipos de curso editables desde el panel de Parámetros.

- MALLAS_CURRICULARES pasa a ser hijo de PARAMETROS_HABILITACION (sigue sin ruta, es un permiso
  especial): quien lo tenga entra a Parámetros y ve solo la pestaña "Mallas curriculares".
- Política TOTP MALLAS_MODIFICAR: crear un tipo de curso y guardar una versión de malla exigen el
  código del autenticador (decisión de la Escuela, 2026-11-21).
- Acción de auditoría TIPO_CURSO_CREADO. Las versiones nuevas reutilizan MALLA_CURRICULAR_CARGADA
  (S2-01), ahora con el antes y el después de la malla.
- La cuenta de la API puede crear tipos de curso (no editarlos ni borrarlos).
"""

from alembic import op

revision = "p0020_mallas_en_parametros"
down_revision = "p0019_nota_minima_aprobacion"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"
POLITICA_TOTP = "MALLAS_MODIFICAR"

# Mismo nombre de restricción que recrearon p0007, p0009, p0012, p0013, p0015 y p0017.
NOMBRE_RESTRICCION = "ck_auditoria_eventos_ck_auditoria_eventos_accion"
# Acciones vigentes tras p0017 (p0018 y p0019 no las cambiaron).
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
    "MALLA_CURRICULAR_CARGADA",
)
ACCIONES_NUEVAS = ("TIPO_CURSO_CREADO",)
# Columnas que la API llena al crear un tipo de curso (activo toma su valor por defecto).
COLUMNAS_TIPO_CURSO = "codigo, nombre, tipo, modalidad, duracion_semanas"


def _restriccion_acciones(acciones: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {NOMBRE_RESTRICCION}")
    op.execute(
        f"ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT {NOMBRE_RESTRICCION} CHECK (accion IN ({lista}))"  # noqa: S608
    )


def upgrade():
    op.execute("""
        UPDATE esart.componentes
        SET componente_padre_id = (SELECT id FROM esart.componentes WHERE codigo = 'PARAMETROS_HABILITACION')
        WHERE codigo = 'MALLAS_CURRICULARES'
    """)
    op.execute(f"""
        DO $$
        BEGIN
          IF to_regclass('seguridad.politicas_accion') IS NOT NULL THEN
            INSERT INTO seguridad.politicas_accion (codigo, nombre, modulo, requiere_totp)
            VALUES ('{POLITICA_TOTP}', 'Crear tipos de curso y versiones de malla curricular',
                    'PARAMETROS', true)
            ON CONFLICT (codigo) DO NOTHING;
          END IF;
        END $$;
    """)  # noqa: S608
    _restriccion_acciones(ACCIONES_ANTERIORES + ACCIONES_NUEVAS)
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT (tipo, modalidad, duracion_semanas) ON esart.tipos_curso TO {CUENTA_APLICACION};
            GRANT INSERT ({COLUMNAS_TIPO_CURSO}) ON esart.tipos_curso TO {CUENTA_APLICACION};
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO {CUENTA_APLICACION}',
                           pg_get_serial_sequence('esart.tipos_curso', 'id'));
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
             AND pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'esart.tipos_curso'::regclass))
                 <> '{CUENTA_APLICACION}' THEN
            REVOKE INSERT ({COLUMNAS_TIPO_CURSO}) ON esart.tipos_curso FROM {CUENTA_APLICACION};
            REVOKE SELECT (tipo, modalidad, duracion_semanas) ON esart.tipos_curso FROM {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
    # Solo funciona si no hay eventos con la acción nueva (la auditoría es inmutable).
    _restriccion_acciones(ACCIONES_ANTERIORES)
    op.execute(f"""
        DO $$
        BEGIN
          IF to_regclass('seguridad.politicas_accion') IS NOT NULL THEN
            DELETE FROM seguridad.politicas_accion WHERE codigo = '{POLITICA_TOTP}';
          END IF;
        END $$;
    """)  # noqa: S608
    op.execute("UPDATE esart.componentes SET componente_padre_id = NULL WHERE codigo = 'MALLAS_CURRICULARES'")
