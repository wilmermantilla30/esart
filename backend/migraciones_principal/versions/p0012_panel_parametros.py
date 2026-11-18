"""Panel de Parámetros: repositorio de plantillas y formatos, y auditoría de la regla.

- esart.plantillas_formatos guarda los documentos institucionales (Excel, PDF, Word) dentro de
  la base: así entran en los respaldos y en la misma transacción que su auditoría.
  Los archivos no se borran: se "retiran" (activo = false) y quedan para consulta histórica.
- La auditoría admite las acciones nuevas del panel.
- Política TOTP PARAMETROS_MODIFICAR: cambiar la regla APTO / NO APTO exige el código del
  autenticador, igual que el cargue masivo por Excel.
"""

from alembic import op

revision = "p0012_panel_parametros"
down_revision = "p0011_cursos_importacion"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"

# Mismo nombre de restricción que recrearon p0007 y p0009.
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
)
ACCIONES_NUEVAS = (
    "PARAMETROS_ACTUALIZADOS",
    "PLANTILLA_PUBLICADA",
    "PLANTILLA_DESCARGADA",
    "PLANTILLA_RETIRADA",
)


def _restriccion_acciones(acciones: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    op.execute(f"ALTER TABLE esart.auditoria_eventos DROP CONSTRAINT {NOMBRE_RESTRICCION}")
    op.execute(
        f"ALTER TABLE esart.auditoria_eventos ADD CONSTRAINT {NOMBRE_RESTRICCION} CHECK (accion IN ({lista}))"  # noqa: S608
    )


def upgrade():
    op.execute("""
        CREATE TABLE esart.plantillas_formatos (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            nombre_oficial VARCHAR(200) NOT NULL,
            nombre_archivo VARCHAR(255) NOT NULL,
            formato VARCHAR(10) NOT NULL,
            version VARCHAR(30) NOT NULL,
            descripcion TEXT NOT NULL DEFAULT '',
            tamano_bytes INTEGER NOT NULL,
            sha256 CHAR(64) NOT NULL,
            contenido BYTEA NOT NULL,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            subido_por_id BIGINT REFERENCES esart_ref.usuarios(id) ON DELETE SET NULL,
            subido_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            retirado_por_id BIGINT REFERENCES esart_ref.usuarios(id) ON DELETE SET NULL,
            retirado_en TIMESTAMPTZ,
            CONSTRAINT ck_plantillas_formatos_formato CHECK (formato IN ('XLSX', 'XLS', 'PDF', 'DOCX')),
            CONSTRAINT ck_plantillas_formatos_tamano CHECK (tamano_bytes > 0 AND tamano_bytes <= 26214400),
            CONSTRAINT ck_plantillas_formatos_retiro CHECK (activo OR retirado_en IS NOT NULL)
        )
    """)
    # Dos documentos activos con el mismo nombre y versión serían ambiguos al descargar.
    op.execute("""
        CREATE UNIQUE INDEX uq_plantillas_formatos_activa
        ON esart.plantillas_formatos (lower(nombre_oficial), version) WHERE activo
    """)
    _restriccion_acciones(ACCIONES_ANTERIORES + ACCIONES_NUEVAS)

    # Permisos mínimos de la API: publicar, leer y retirar (nunca borrar ni reescribir el archivo).
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT, INSERT ON esart.plantillas_formatos TO {CUENTA_APLICACION};
            GRANT UPDATE (activo, retirado_por_id, retirado_en)
              ON esart.plantillas_formatos TO {CUENTA_APLICACION};
            GRANT SELECT (id, codigo, nombre, activo) ON esart.tipos_curso TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608

    # Política TOTP de la regla de habilitación (solo si el módulo de seguridad está instalado).
    op.execute("""
        DO $$
        BEGIN
          IF to_regclass('seguridad.politicas_accion') IS NOT NULL THEN
            INSERT INTO seguridad.politicas_accion (codigo, nombre, modulo, requiere_totp)
            VALUES ('PARAMETROS_MODIFICAR', 'Modificar la regla de habilitación', 'PARAMETROS', true)
            ON CONFLICT (codigo) DO NOTHING;
          END IF;
        END $$;
    """)


def downgrade():
    op.execute("DROP TABLE esart.plantillas_formatos")
    # Solo funciona si no hay eventos con las acciones nuevas (la auditoría es inmutable).
    _restriccion_acciones(ACCIONES_ANTERIORES)
