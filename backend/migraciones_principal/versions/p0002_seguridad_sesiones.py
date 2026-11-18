"""Seguridad del inicio de sesión (HU-05 a HU-08).

- esart_ref.usuarios: intentos_fallidos_consecutivos y bloqueado_hasta (bloqueo 3/7/3 h, HU-06).
- esart.sesiones_usuario: una fila por sesión; su id es el 'jti' del JWT. Permite revocar
  sesiones y cerrar por 30 minutos de inactividad (HU-08).
- esart.intentos_inicio_sesion: registro de cada intento, también con usuarios inexistentes,
  para limitar por IP (HU-06). Nunca guarda la contraseña intentada.

El índice único de usuario (uq_esart_usuario_nombre_ci, lower(usuario)) ya existe desde HU-04.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p0002_seguridad_sesiones"
down_revision = "p0001_real"
branch_labels = None
depends_on = None

# Cuenta con la que corre FastAPI. Si existe (producción y equipos de desarrollo), recibe
# solo los permisos que el login necesita sobre las tablas nuevas.
CUENTA_APLICACION = "esart_aplicacion"


def upgrade():
    # --- Bloqueo por intentos en usuarios ---
    op.add_column(
        "usuarios",
        sa.Column(
            "intentos_fallidos_consecutivos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        schema="esart_ref",
    )
    op.add_column(
        "usuarios",
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        schema="esart_ref",
    )
    op.create_check_constraint(
        "ck_esart_usuario_intentos_no_negativos",
        "usuarios",
        "intentos_fallidos_consecutivos >= 0",
        schema="esart_ref",
    )

    # --- Sesiones ---
    op.create_table(
        "sesiones_usuario",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "fecha_inicio", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_ultima_actividad",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("agente_usuario", sa.String(300), nullable=True),
        sa.Column("revocada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fecha_revocacion", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="sesiones_usuario_pkey"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["esart_ref.usuarios.id"],
            name="fk_sesiones_usuario_usuario_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(revocada AND fecha_revocacion IS NOT NULL) OR (NOT revocada AND fecha_revocacion IS NULL)",
            name="ck_sesiones_usuario_revocacion",
        ),
        schema="esart",
    )
    op.create_index("ix_sesiones_usuario_usuario_id", "sesiones_usuario", ["usuario_id"], schema="esart")

    # --- Intentos de inicio de sesión ---
    op.create_table(
        "intentos_inicio_sesion",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("nombre_usuario_intentado", sa.String(80), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("exitoso", sa.Boolean(), nullable=False),
        sa.Column("motivo_fallo", sa.String(40), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="intentos_inicio_sesion_pkey"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["esart_ref.usuarios.id"],
            name="fk_intentos_inicio_sesion_usuario_id",
            ondelete="SET NULL",
        ),
        schema="esart",
    )
    op.create_index(
        "ix_intentos_inicio_sesion_usuario_id_fecha",
        "intentos_inicio_sesion",
        ["usuario_id", "fecha"],
        schema="esart",
    )
    op.create_index(
        "ix_intentos_inicio_sesion_direccion_ip_fecha",
        "intentos_inicio_sesion",
        ["direccion_ip", "fecha"],
        schema="esart",
    )

    # --- Permisos mínimos para la cuenta de la API ---
    # La cuenta es una constante de este archivo, nunca un dato externo.
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            -- Sesiones e intentos (tablas nuevas).
            GRANT SELECT, INSERT, UPDATE ON esart.sesiones_usuario TO {CUENTA_APLICACION};
            GRANT SELECT, INSERT ON esart.intentos_inicio_sesion TO {CUENTA_APLICACION};
            GRANT USAGE ON SEQUENCE esart.intentos_inicio_sesion_id_seq TO {CUENTA_APLICACION};
            -- Login: leer usuarios y sus roles; actualizar solo contadores y último acceso.
            GRANT SELECT ON esart_ref.usuarios, esart.roles, esart.usuario_roles TO {CUENTA_APLICACION};
            GRANT UPDATE (intentos_fallidos_consecutivos, bloqueado_hasta, ultimo_acceso_en)
              ON esart_ref.usuarios TO {CUENTA_APLICACION};
            -- Administrador inicial desde el .env: crear el usuario, el rol y su asignación.
            GRANT INSERT ON esart_ref.usuarios, esart.roles, esart.usuario_roles TO {CUENTA_APLICACION};
            GRANT USAGE ON SEQUENCE esart_ref.usuarios_id_seq, esart.roles_id_seq TO {CUENTA_APLICACION};
            -- Nombre visible del usuario: solo estas columnas del militar, no toda la ficha.
            GRANT SELECT (documento_identidad, grado, nombres, apellidos)
              ON esart.personal_militar TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    op.drop_index("ix_intentos_inicio_sesion_direccion_ip_fecha", "intentos_inicio_sesion", schema="esart")
    op.drop_index("ix_intentos_inicio_sesion_usuario_id_fecha", "intentos_inicio_sesion", schema="esart")
    op.drop_table("intentos_inicio_sesion", schema="esart")
    op.drop_index("ix_sesiones_usuario_usuario_id", "sesiones_usuario", schema="esart")
    op.drop_table("sesiones_usuario", schema="esart")
    op.drop_constraint(
        "ck_esart_usuario_intentos_no_negativos", "usuarios", schema="esart_ref", type_="check"
    )
    op.drop_column("usuarios", "bloqueado_hasta", schema="esart_ref")
    op.drop_column("usuarios", "intentos_fallidos_consecutivos", schema="esart_ref")
