"""Catálogo organizacional HU-04 fase 3, autorizado en dos bases de pruebas.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def comprobar_destino(*, reversion=False):
    """La guardia se incluye también en SQL offline antes del primer DDL."""
    op.execute("""
        DO $$ BEGIN
            IF current_database() NOT IN ('esart_hu03_pruebas', 'esart_hu04_fase3_temporal') THEN
                RAISE EXCEPTION '0002 solo autorizada en las dos bases de pruebas';
            END IF;
            IF current_schema() <> 'public' OR
               (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
                RAISE EXCEPTION '0002 requiere public y cuenta sin superusuario';
            END IF;
            IF current_setting('server_version_num')::integer / 10000 <> 18 THEN
                RAISE EXCEPTION '0002 requiere PostgreSQL 18';
            END IF;
        END $$;
    """)
    if reversion:
        op.execute("""
            DO $$ BEGIN
                IF current_database() <> 'esart_hu04_fase3_temporal' THEN
                    RAISE EXCEPTION 'Reversion 0002 solo autorizada en esart_hu04_fase3_temporal';
                END IF;
            END $$;
        """)


def upgrade():
    comprobar_destino()
    # Operaciones congeladas: no importar modelos mutables en una revisión.
    op.create_table(
        "tipos_unidad",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipos_unidad")),
        sa.UniqueConstraint("codigo", name=op.f("uq_tipos_unidad_codigo")),
        sa.CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{0,19}$'", name=op.f("ck_tipos_unidad_codigo")),
        sa.CheckConstraint("length(btrim(nombre)) > 0", name=op.f("ck_tipos_unidad_nombre")),
    )
    op.add_column("unidades_militares", sa.Column("tipo_unidad_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_unidades_militares_tipo_unidad_id_tipos_unidad"),
        "unidades_militares",
        "tipos_unidad",
        ["tipo_unidad_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_unidades_militares_tipo_unidad_id"), "unidades_militares", ["tipo_unidad_id"])
    op.execute("""
        CREATE TRIGGER tr_tipos_unidad_fecha BEFORE UPDATE ON public.tipos_unidad
        FOR EACH ROW EXECUTE FUNCTION public.actualizar_fecha_actualizacion()
    """)


def downgrade():
    comprobar_destino(reversion=True)
    # No destruir datos de negocio ni semillas, incluso si alguien pide downgrade.
    op.execute("LOCK TABLE public.tipos_unidad, public.unidades_militares IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM public.tipos_unidad) OR EXISTS (
                SELECT 1 FROM public.unidades_militares WHERE tipo_unidad_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Reversion rechazada: catalogo o clasificaciones con datos';
            END IF;
        END $$;
    """)
    op.drop_index(op.f("ix_unidades_militares_tipo_unidad_id"), table_name="unidades_militares")
    op.drop_constraint(
        op.f("fk_unidades_militares_tipo_unidad_id_tipos_unidad"), "unidades_militares", type_="foreignkey"
    )
    op.drop_column("unidades_militares", "tipo_unidad_id")
    op.execute("DROP TRIGGER tr_tipos_unidad_fecha ON public.tipos_unidad")
    op.drop_table("tipos_unidad")
