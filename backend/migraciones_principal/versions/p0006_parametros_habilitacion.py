"""Parámetros de la regla de habilitación (APTO / NO APTO), editables desde el panel.

Regla vigente (acordada el 2026-11-16):
    APTO = militar ACTIVO y (curso habilitante APROBADO o reentrenamiento VIGENTE)
- Cursos habilitantes: SACLI y SACME. No vencen.
- Reentrenamiento vigente: certificado marcado vigente, apto para disparar y expedido hace
  menos de MESES_VIGENCIA_REENTRENAMIENTO meses (vence el mismo día, un año después).
- Alerta "por vencer": faltan DIAS_ALERTA_VENCIMIENTO días o menos.

También da a la cuenta de la API la lectura de las tablas que la verificación consulta.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "p0006_parametros_habilitacion"
down_revision = "p0005_componentes_y_malla"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"

# (codigo, valor JSON, descripción)
PARAMETROS_INICIALES = [
    (
        "CURSOS_HABILITANTES",
        '["SACLI", "SACME"]',
        "Códigos de tipos_curso que, aprobados, hacen APTO al militar. No vencen.",
    ),
    (
        "MESES_VIGENCIA_REENTRENAMIENTO",
        "12",
        "Meses que dura vigente un certificado de reentrenamiento desde su fecha de expedición.",
    ),
    (
        "DIAS_ALERTA_VENCIMIENTO",
        "60",
        "Días antes del vencimiento del reentrenamiento en que se muestra la alerta 'por vencer'.",
    ),
    (
        "EXIGE_APTO_PARA_DISPARAR",
        "true",
        "Si es verdadero, el certificado de reentrenamiento solo cuenta si está marcado apto para disparar.",
    ),
]

SQL_PARAMETRO = text("""
    INSERT INTO esart.parametros_habilitacion (codigo, valor, descripcion)
    VALUES (:codigo, CAST(:valor AS jsonb), :descripcion)
    ON CONFLICT (codigo) DO NOTHING
""")


def upgrade():
    op.create_table(
        "parametros_habilitacion",
        sa.Column("codigo", sa.String(60), nullable=False),
        sa.Column("valor", postgresql.JSONB(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actualizado_por_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("codigo", name="parametros_habilitacion_pkey"),
        sa.ForeignKeyConstraint(
            ["actualizado_por_id"],
            ["esart_ref.usuarios.id"],
            name="fk_parametros_habilitacion_actualizado_por_id",
            ondelete="SET NULL",
        ),
        schema="esart",
    )
    conexion = op.get_bind()
    for codigo, valor, descripcion in PARAMETROS_INICIALES:
        conexion.execute(SQL_PARAMETRO, {"codigo": codigo, "valor": valor, "descripcion": descripcion})

    # Permisos de la cuenta de la API: leer lo que la verificación necesita y editar
    # solo el valor de los parámetros (no crearlos ni borrarlos).
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT ON esart.parametros_habilitacion TO {CUENTA_APLICACION};
            GRANT UPDATE (valor, actualizado_en, actualizado_por_id)
              ON esart.parametros_habilitacion TO {CUENTA_APLICACION};
            GRANT SELECT ON esart.personal_militar, esart.hoja_vida_artillero, esart.artillero_cursos,
              esart.tipos_curso, esart.certificados_reentrenamiento, esart_ref.unidades_militares
              TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    op.drop_table("parametros_habilitacion", schema="esart")
