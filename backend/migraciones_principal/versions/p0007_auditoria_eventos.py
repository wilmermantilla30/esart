"""Auditoría general e inmutable (HU-11): quién, qué, cuándo y desde dónde.

- Complementa a esart.auditoria_acceso (de HU-06/HU-07), que guarda el detalle técnico de los
  intentos de login y del captcha. Esta registra las acciones de negocio y de administración.
- INMUTABLE: un trigger impide UPDATE, DELETE y TRUNCATE para todos (también para el dueño),
  y la cuenta de la API solo tiene INSERT y SELECT.
- Nunca guarda contraseñas ni tokens (el servicio de auditoría lo valida antes de insertar).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p0007_auditoria_eventos"
down_revision = "p0006_parametros_habilitacion"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"

# Acciones admitidas. Agregar una nueva exige una revisión (así no se cuelan textos libres).
ACCIONES = (
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
)


def upgrade():
    acciones_sql = ", ".join(f"'{accion}'" for accion in ACCIONES)
    op.create_table(
        "auditoria_eventos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        # Copia del nombre por si el usuario se renombra o desactiva después.
        sa.Column("nombre_usuario", sa.String(80), nullable=True),
        sa.Column("accion", sa.String(40), nullable=False),
        sa.Column("numero_documento_consultado", sa.String(15), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=True),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("agente_usuario", sa.String(300), nullable=True),
        sa.Column("detalle", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="auditoria_eventos_pkey"),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["esart_ref.usuarios.id"], name="fk_auditoria_eventos_usuario_id"
        ),
        sa.CheckConstraint(f"accion IN ({acciones_sql})", name="ck_auditoria_eventos_accion"),
        schema="esart",
    )
    op.create_index("ix_auditoria_eventos_fecha", "auditoria_eventos", ["fecha"], schema="esart")
    op.create_index(
        "ix_auditoria_eventos_usuario_id_fecha", "auditoria_eventos", ["usuario_id", "fecha"], schema="esart"
    )
    op.create_index(
        "ix_auditoria_eventos_documento", "auditoria_eventos", ["numero_documento_consultado"], schema="esart"
    )

    # Inmutable: ninguna fila se modifica ni se borra, ni siquiera por el dueño de la tabla.
    op.execute("""
        CREATE OR REPLACE FUNCTION esart.impedir_modificacion_auditoria() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'La auditoría es inmutable: no se permite %', TG_OP;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER tr_auditoria_eventos_inmutable
        BEFORE UPDATE OR DELETE ON esart.auditoria_eventos
        FOR EACH ROW EXECUTE FUNCTION esart.impedir_modificacion_auditoria();
    """)
    op.execute("""
        CREATE TRIGGER tr_auditoria_eventos_sin_truncate
        BEFORE TRUNCATE ON esart.auditoria_eventos
        FOR EACH STATEMENT EXECUTE FUNCTION esart.impedir_modificacion_auditoria();
    """)

    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT, INSERT ON esart.auditoria_eventos TO {CUENTA_APLICACION};
            GRANT USAGE ON SEQUENCE esart.auditoria_eventos_id_seq TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608
    # Sin UPDATE, DELETE ni TRUNCATE para nadie más que el dueño (y el trigger lo frena igual).
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON esart.auditoria_eventos FROM PUBLIC")


def downgrade():
    # Bajar esta revisión borra la auditoría: solo tiene sentido en una base de desarrollo.
    op.execute("DROP TRIGGER IF EXISTS tr_auditoria_eventos_sin_truncate ON esart.auditoria_eventos")
    op.execute("DROP TRIGGER IF EXISTS tr_auditoria_eventos_inmutable ON esart.auditoria_eventos")
    op.drop_table("auditoria_eventos", schema="esart")
    op.execute("DROP FUNCTION IF EXISTS esart.impedir_modificacion_auditoria()")
