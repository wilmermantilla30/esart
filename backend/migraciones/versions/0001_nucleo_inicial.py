"""Núcleo ESART y malla CRUD aprobada. Sin semillas ni tablas Vulcano.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLAS_AUDITORIA = (
    "componentes",
    "permisos",
    "roles",
    "sistemas_artilleria",
    "tipos_cargo",
    "tipos_certificacion",
    "tipos_curso",
    "unidades_militares",
    "personal_militar",
    "requisitos_habilitacion",
    "rol_permisos",
    "roles_permisos",
    "usuarios",
    "hoja_vida_artillero",
    "importaciones_excel",
    "usuario_permisos",
    "artillero_cargos",
    "artillero_certificaciones",
    "artillero_cursos",
)


def comprobar_destino(*, reversion=False):
    if context.is_offline_mode():
        if reversion:
            op.execute("""
                DO $$ BEGIN
                    IF current_database() <> 'esart_hu03_pruebas' THEN
                        RAISE EXCEPTION 'Downgrade solo autorizado en esart_hu03_pruebas';
                    END IF;
                END $$
            """)
        return
    conexion = op.get_bind()
    identidad = conexion.execute(
        sa.text(
            "SELECT current_database(), current_user, current_schema(), "
            "(SELECT rolsuper FROM pg_roles WHERE rolname=current_user)"
        )
    ).one()
    if identidad[3] or identidad[1] == "postgres":
        raise RuntimeError("Las migraciones no pueden usar un superusuario.")
    if identidad[2] != "public":
        raise RuntimeError("La revisión 0001 requiere el esquema activo public.")
    if reversion:
        if identidad[0] != "esart_hu03_pruebas":
            raise RuntimeError("Downgrade solo autorizado en esart_hu03_pruebas.")
        return
    existentes = conexion.execute(
        sa.text(
            "SELECT 1 FROM pg_catalog.pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog','information_schema') "
            "AND schemaname NOT LIKE 'pg_toast%' "
            "AND NOT (schemaname='public' AND tablename='alembic_version') LIMIT 1"
        )
    ).first()
    if existentes:
        raise RuntimeError("La base contiene tablas; concilie su esquema antes de instalar 0001.")


def upgrade():
    comprobar_destino()
    op.create_table(
        "componentes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=100), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("ruta_angular", sa.String(length=250), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("componente_padre_id", sa.Uuid(), nullable=True),
        sa.Column("orden", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["componente_padre_id"],
            ["componentes.id"],
            name=op.f("fk_componentes_componente_padre_id_componentes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_componentes")),
        sa.UniqueConstraint("codigo", name=op.f("uq_componentes_codigo")),
    )
    op.create_index(
        op.f("ix_componentes_componente_padre_id"), "componentes", ["componente_padre_id"], unique=False
    )
    op.create_table(
        "permisos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("descripcion", sa.String(length=200), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permisos")),
        sa.UniqueConstraint("codigo", name=op.f("uq_permisos_codigo")),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("codigo IN ('ADMINISTRADOR', 'USUARIO')", name=op.f("ck_roles_codigo")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("codigo", name=op.f("uq_roles_codigo")),
    )
    op.create_table(
        "sistemas_artilleria",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("tipo_sistema", sa.String(length=50), nullable=False),
        sa.Column("calibre_milimetros", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("verificacion_habilitada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sistemas_artilleria")),
        sa.UniqueConstraint("codigo", name=op.f("uq_sistemas_artilleria_codigo")),
    )
    op.create_table(
        "tipos_cargo",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipos_cargo")),
        sa.UniqueConstraint("codigo", name=op.f("uq_tipos_cargo_codigo")),
    )
    op.create_table(
        "tipos_certificacion",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("entidad_emisora", sa.String(length=200), nullable=True),
        sa.Column("tipo_sistema", sa.String(length=50), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipos_certificacion")),
        sa.UniqueConstraint("codigo", name=op.f("uq_tipos_certificacion_codigo")),
    )
    op.create_table(
        "tipos_curso",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("tipo_sistema", sa.String(length=50), nullable=True),
        sa.Column("vigencia_meses", sa.Integer(), nullable=True),
        sa.Column("nota_minima_aprobacion", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "nota_minima_aprobacion BETWEEN 0 AND 5", name=op.f("ck_tipos_curso_nota_minima_aprobacion")
        ),
        sa.CheckConstraint("vigencia_meses > 0", name=op.f("ck_tipos_curso_vigencia_meses")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipos_curso")),
        sa.UniqueConstraint("codigo", name=op.f("uq_tipos_curso_codigo")),
    )
    op.create_table(
        "unidades_militares",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("sigla", sa.String(length=30), nullable=True),
        sa.Column("unidad_superior_id", sa.Uuid(), nullable=True),
        sa.Column("activa", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["unidad_superior_id"],
            ["unidades_militares.id"],
            name=op.f("fk_unidades_militares_unidad_superior_id_unidades_militares"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unidades_militares")),
        sa.UniqueConstraint("codigo", name=op.f("uq_unidades_militares_codigo")),
    )
    op.create_index(
        op.f("ix_unidades_militares_unidad_superior_id"),
        "unidades_militares",
        ["unidad_superior_id"],
        unique=False,
    )
    op.create_table(
        "personal_militar",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("numero_documento", sa.String(length=10), nullable=False),
        sa.Column("primer_nombre", sa.String(length=60), nullable=False),
        sa.Column("segundo_nombre", sa.String(length=60), nullable=True),
        sa.Column("primer_apellido", sa.String(length=60), nullable=False),
        sa.Column("segundo_apellido", sa.String(length=60), nullable=True),
        sa.Column("grado", sa.String(length=40), nullable=False),
        sa.Column("categoria", sa.String(length=20), nullable=False),
        sa.Column("arma", sa.String(length=40), nullable=True),
        sa.Column("unidad_militar_id", sa.Uuid(), nullable=True),
        sa.Column("estado_servicio", sa.String(length=20), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "categoria IN ('OFICIAL','SUBOFICIAL','SOLDADO_PROFESIONAL','CIVIL')",
            name=op.f("ck_personal_militar_categoria"),
        ),
        sa.CheckConstraint(
            "estado_servicio IN ('ACTIVO','RETIRADO','SUSPENDIDO','COMISION','LICENCIA')",
            name=op.f("ck_personal_militar_estado_servicio"),
        ),
        sa.CheckConstraint(
            "numero_documento ~ '^[0-9]{6,10}$'", name=op.f("ck_personal_militar_numero_documento")
        ),
        sa.ForeignKeyConstraint(
            ["unidad_militar_id"],
            ["unidades_militares.id"],
            name=op.f("fk_personal_militar_unidad_militar_id_unidades_militares"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_personal_militar")),
        sa.UniqueConstraint("numero_documento", name=op.f("uq_personal_militar_numero_documento")),
    )
    op.create_index(
        "ix_personal_militar_estado_servicio", "personal_militar", ["estado_servicio"], unique=False
    )
    op.create_index(
        op.f("ix_personal_militar_unidad_militar_id"), "personal_militar", ["unidad_militar_id"], unique=False
    )
    op.create_table(
        "requisitos_habilitacion",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sistema_artilleria_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_requisito", sa.String(length=20), nullable=False),
        sa.Column("tipo_curso_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_certificacion_id", sa.Uuid(), nullable=True),
        sa.Column("descripcion", sa.String(length=300), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "(tipo_requisito = 'CURSO' AND tipo_curso_id IS NOT NULL AND tipo_certificacion_id IS NULL) "
            "OR (tipo_requisito = 'CERTIFICACION' AND tipo_certificacion_id IS NOT NULL "
            "AND tipo_curso_id IS NULL)",
            name=op.f("ck_requisitos_habilitacion_coherencia"),
        ),
        sa.CheckConstraint(
            "tipo_requisito IN ('CURSO','CERTIFICACION')",
            name=op.f("ck_requisitos_habilitacion_tipo_requisito"),
        ),
        sa.ForeignKeyConstraint(
            ["sistema_artilleria_id"],
            ["sistemas_artilleria.id"],
            name=op.f("fk_requisitos_habilitacion_sistema_artilleria_id_sistemas_artilleria"),
        ),
        sa.ForeignKeyConstraint(
            ["tipo_certificacion_id"],
            ["tipos_certificacion.id"],
            name=op.f("fk_requisitos_habilitacion_tipo_certificacion_id_tipos_certificacion"),
        ),
        sa.ForeignKeyConstraint(
            ["tipo_curso_id"],
            ["tipos_curso.id"],
            name=op.f("fk_requisitos_habilitacion_tipo_curso_id_tipos_curso"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requisitos_habilitacion")),
    )
    op.create_index(
        op.f("ix_requisitos_habilitacion_sistema_artilleria_id"),
        "requisitos_habilitacion",
        ["sistema_artilleria_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_requisitos_habilitacion_tipo_certificacion_id"),
        "requisitos_habilitacion",
        ["tipo_certificacion_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_requisitos_habilitacion_tipo_curso_id"),
        "requisitos_habilitacion",
        ["tipo_curso_id"],
        unique=False,
    )
    op.create_table(
        "rol_permisos",
        sa.Column("rol_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        sa.Column("puede_acceder", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_crear", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_leer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_actualizar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_eliminar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "puede_acceder OR NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar)",
            name=op.f("ck_rol_permisos_coherencia"),
        ),
        sa.ForeignKeyConstraint(
            ["componente_id"],
            ["componentes.id"],
            name=op.f("fk_rol_permisos_componente_id_componentes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rol_id"], ["roles.id"], name=op.f("fk_rol_permisos_rol_id_roles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("rol_id", "componente_id", name=op.f("pk_rol_permisos")),
    )
    op.create_index(op.f("ix_rol_permisos_componente_id"), "rol_permisos", ["componente_id"], unique=False)
    op.create_index(op.f("ix_rol_permisos_rol_id"), "rol_permisos", ["rol_id"], unique=False)
    op.create_table(
        "roles_permisos",
        sa.Column("rol_id", sa.Uuid(), nullable=False),
        sa.Column("permiso_id", sa.Uuid(), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["permiso_id"], ["permisos.id"], name=op.f("fk_roles_permisos_permiso_id_permisos")
        ),
        sa.ForeignKeyConstraint(["rol_id"], ["roles.id"], name=op.f("fk_roles_permisos_rol_id_roles")),
        sa.PrimaryKeyConstraint("rol_id", "permiso_id", name=op.f("pk_roles_permisos")),
    )
    op.create_index(op.f("ix_roles_permisos_permiso_id"), "roles_permisos", ["permiso_id"], unique=False)
    op.create_index(op.f("ix_roles_permisos_rol_id"), "roles_permisos", ["rol_id"], unique=False)
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("nombre_usuario", sa.String(length=60), nullable=False),
        sa.Column("nombre_completo", sa.String(length=200), nullable=False),
        sa.Column("hash_contrasena", sa.String(length=100), nullable=False),
        sa.Column("rol_id", sa.Uuid(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "intentos_fallidos_consecutivos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fecha_ultimo_acceso", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["rol_id"], ["roles.id"], name=op.f("fk_usuarios_rol_id_roles")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
    )
    op.create_index(op.f("ix_usuarios_rol_id"), "usuarios", ["rol_id"], unique=False)
    op.create_index("ux_usuarios_nombre_usuario", "usuarios", [sa.text("lower(nombre_usuario)")], unique=True)
    op.create_table(
        "auditoria_eventos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("nombre_usuario", sa.String(length=60), nullable=True),
        sa.Column("accion", sa.String(length=40), nullable=False),
        sa.Column("numero_documento_consultado", sa.String(length=10), nullable=True),
        sa.Column("resultado", sa.String(length=20), nullable=True),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("agente_usuario", sa.String(length=300), nullable=True),
        sa.Column("detalle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "accion IN ('LOGIN_EXITOSO','LOGIN_FALLIDO','USUARIO_BLOQUEADO',"
            "'USUARIO_DESBLOQUEADO','CONSULTA_ARTILLERO','CONSULTA_HABILITADOS',"
            "'CONSULTA_NO_HABILITADOS','IMPORTACION_EXCEL','CIERRE_SESION')",
            name=op.f("ck_auditoria_eventos_accion"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_auditoria_eventos_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditoria_eventos")),
    )
    op.create_index("ix_auditoria_eventos_fecha", "auditoria_eventos", ["fecha"], unique=False)
    op.create_index(
        "ix_auditoria_eventos_numero_documento_consultado",
        "auditoria_eventos",
        ["numero_documento_consultado"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auditoria_eventos_usuario_id"), "auditoria_eventos", ["usuario_id"], unique=False
    )
    op.create_index(
        "ix_auditoria_eventos_usuario_id_fecha", "auditoria_eventos", ["usuario_id", "fecha"], unique=False
    )
    op.create_table(
        "hoja_vida_artillero",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("personal_militar_id", sa.Uuid(), nullable=False),
        sa.Column("especialidad", sa.String(length=100), nullable=True),
        sa.Column("fecha_ingreso_arma", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["personal_militar_id"],
            ["personal_militar.id"],
            name=op.f("fk_hoja_vida_artillero_personal_militar_id_personal_militar"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoja_vida_artillero")),
    )
    op.create_index(
        op.f("ix_hoja_vida_artillero_personal_militar_id"),
        "hoja_vida_artillero",
        ["personal_militar_id"],
        unique=True,
    )
    op.create_table(
        "importaciones_excel",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=False),
        sa.Column("hash_sha256_archivo", sa.CHAR(length=64), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("filas_totales", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("filas_validas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("filas_rechazadas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("errores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "estado IN ('PROCESANDO','APLICADA','RECHAZADA')", name=op.f("ck_importaciones_excel_estado")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_importaciones_excel_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_importaciones_excel")),
        sa.UniqueConstraint("hash_sha256_archivo", name=op.f("uq_importaciones_excel_hash_sha256_archivo")),
    )
    op.create_index(
        op.f("ix_importaciones_excel_usuario_id"), "importaciones_excel", ["usuario_id"], unique=False
    )
    op.create_table(
        "intentos_inicio_sesion",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("nombre_usuario_intentado", sa.String(length=60), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("direccion_ip", postgresql.INET(), nullable=True),
        sa.Column("exitoso", sa.Boolean(), nullable=False),
        sa.Column("motivo_fallo", sa.String(length=40), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_intentos_inicio_sesion_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intentos_inicio_sesion")),
    )
    op.create_index(
        "ix_intentos_inicio_sesion_direccion_ip_fecha",
        "intentos_inicio_sesion",
        ["direccion_ip", "fecha"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intentos_inicio_sesion_usuario_id"), "intentos_inicio_sesion", ["usuario_id"], unique=False
    )
    op.create_index(
        "ix_intentos_inicio_sesion_usuario_id_fecha",
        "intentos_inicio_sesion",
        ["usuario_id", "fecha"],
        unique=False,
    )
    op.create_table(
        "sesiones_usuario",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
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
        sa.Column("agente_usuario", sa.String(length=300), nullable=True),
        sa.Column("revocada", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fecha_revocacion", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_sesiones_usuario_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sesiones_usuario")),
    )
    op.create_index(op.f("ix_sesiones_usuario_usuario_id"), "sesiones_usuario", ["usuario_id"], unique=False)
    op.create_table(
        "usuario_permisos",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("componente_id", sa.Uuid(), nullable=False),
        sa.Column("puede_acceder", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_crear", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_leer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_actualizar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_eliminar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "puede_acceder OR NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar)",
            name=op.f("ck_usuario_permisos_coherencia"),
        ),
        sa.ForeignKeyConstraint(
            ["actualizado_por_id"],
            ["usuarios.id"],
            name=op.f("fk_usuario_permisos_actualizado_por_id_usuarios"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["componente_id"],
            ["componentes.id"],
            name=op.f("fk_usuario_permisos_componente_id_componentes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_usuario_permisos_usuario_id_usuarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("usuario_id", "componente_id", name=op.f("pk_usuario_permisos")),
    )
    op.create_index(
        op.f("ix_usuario_permisos_actualizado_por_id"),
        "usuario_permisos",
        ["actualizado_por_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usuario_permisos_componente_id"), "usuario_permisos", ["componente_id"], unique=False
    )
    op.create_index(op.f("ix_usuario_permisos_usuario_id"), "usuario_permisos", ["usuario_id"], unique=False)
    op.create_table(
        "artillero_cargos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hoja_vida_artillero_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_cargo_id", sa.Uuid(), nullable=False),
        sa.Column("unidad_militar_id", sa.Uuid(), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("numero_resolucion", sa.String(length=50), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "fecha_fin IS NULL OR fecha_fin >= fecha_inicio", name=op.f("ck_artillero_cargos_coherencia")
        ),
        sa.ForeignKeyConstraint(
            ["hoja_vida_artillero_id"],
            ["hoja_vida_artillero.id"],
            name=op.f("fk_artillero_cargos_hoja_vida_artillero_id_hoja_vida_artillero"),
        ),
        sa.ForeignKeyConstraint(
            ["tipo_cargo_id"], ["tipos_cargo.id"], name=op.f("fk_artillero_cargos_tipo_cargo_id_tipos_cargo")
        ),
        sa.ForeignKeyConstraint(
            ["unidad_militar_id"],
            ["unidades_militares.id"],
            name=op.f("fk_artillero_cargos_unidad_militar_id_unidades_militares"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artillero_cargos")),
    )
    op.create_index(
        op.f("ix_artillero_cargos_hoja_vida_artillero_id"),
        "artillero_cargos",
        ["hoja_vida_artillero_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artillero_cargos_tipo_cargo_id"), "artillero_cargos", ["tipo_cargo_id"], unique=False
    )
    op.create_index(
        op.f("ix_artillero_cargos_unidad_militar_id"), "artillero_cargos", ["unidad_militar_id"], unique=False
    )
    op.create_table(
        "artillero_certificaciones",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hoja_vida_artillero_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_certificacion_id", sa.Uuid(), nullable=False),
        sa.Column("numero_certificado", sa.String(length=50), nullable=True),
        sa.Column("fecha_expedicion", sa.Date(), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("importacion_excel_id", sa.Uuid(), nullable=True),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "estado IN ('ACTIVA','SUSPENDIDA','REVOCADA')", name=op.f("ck_artillero_certificaciones_estado")
        ),
        sa.CheckConstraint(
            "fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_expedicion",
            name=op.f("ck_artillero_certificaciones_coherencia"),
        ),
        sa.ForeignKeyConstraint(
            ["hoja_vida_artillero_id"],
            ["hoja_vida_artillero.id"],
            name=op.f("fk_artillero_certificaciones_hoja_vida_artillero_id_hoja_vida_artillero"),
        ),
        sa.ForeignKeyConstraint(
            ["importacion_excel_id"],
            ["importaciones_excel.id"],
            name=op.f("fk_artillero_certificaciones_importacion_excel_id_importaciones_excel"),
        ),
        sa.ForeignKeyConstraint(
            ["tipo_certificacion_id"],
            ["tipos_certificacion.id"],
            name=op.f("fk_artillero_certificaciones_tipo_certificacion_id_tipos_certificacion"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artillero_certificaciones")),
    )
    op.create_index(
        "ix_artillero_certificaciones_evaluacion",
        "artillero_certificaciones",
        ["hoja_vida_artillero_id", "tipo_certificacion_id", "estado", "fecha_vencimiento"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artillero_certificaciones_hoja_vida_artillero_id"),
        "artillero_certificaciones",
        ["hoja_vida_artillero_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artillero_certificaciones_importacion_excel_id"),
        "artillero_certificaciones",
        ["importacion_excel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artillero_certificaciones_tipo_certificacion_id"),
        "artillero_certificaciones",
        ["tipo_certificacion_id"],
        unique=False,
    )
    op.create_table(
        "artillero_cursos",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hoja_vida_artillero_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_curso_id", sa.Uuid(), nullable=False),
        sa.Column("numero_cohorte", sa.String(length=30), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("nota_final", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("numero_acta", sa.String(length=50), nullable=True),
        sa.Column("institucion", sa.String(length=200), nullable=True),
        sa.Column("importacion_excel_id", sa.Uuid(), nullable=True),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "estado IN ('EN_CURSO','APROBADO','REPROBADO','RETIRADO','ANULADO')",
            name=op.f("ck_artillero_cursos_estado"),
        ),
        sa.CheckConstraint(
            "fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio",
            name=op.f("ck_artillero_cursos_coherencia"),
        ),
        sa.CheckConstraint("nota_final BETWEEN 0 AND 5", name=op.f("ck_artillero_cursos_nota_final")),
        sa.ForeignKeyConstraint(
            ["hoja_vida_artillero_id"],
            ["hoja_vida_artillero.id"],
            name=op.f("fk_artillero_cursos_hoja_vida_artillero_id_hoja_vida_artillero"),
        ),
        sa.ForeignKeyConstraint(
            ["importacion_excel_id"],
            ["importaciones_excel.id"],
            name=op.f("fk_artillero_cursos_importacion_excel_id_importaciones_excel"),
        ),
        sa.ForeignKeyConstraint(
            ["tipo_curso_id"], ["tipos_curso.id"], name=op.f("fk_artillero_cursos_tipo_curso_id_tipos_curso")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artillero_cursos")),
        sa.UniqueConstraint(
            "hoja_vida_artillero_id",
            "tipo_curso_id",
            "numero_cohorte",
            name=op.f("uq_artillero_cursos_hoja_vida_artillero_id_tipo_curso_id_numero_cohorte"),
        ),
    )
    op.create_index(
        "ix_artillero_cursos_evaluacion",
        "artillero_cursos",
        ["hoja_vida_artillero_id", "tipo_curso_id", "estado"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artillero_cursos_hoja_vida_artillero_id"),
        "artillero_cursos",
        ["hoja_vida_artillero_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artillero_cursos_importacion_excel_id"),
        "artillero_cursos",
        ["importacion_excel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artillero_cursos_tipo_curso_id"), "artillero_cursos", ["tipo_curso_id"], unique=False
    )
    # ### end Alembic commands ###

    op.execute("""
        CREATE FUNCTION public.actualizar_fecha_actualizacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.fecha_actualizacion = now();
            RETURN NEW;
        END;
        $$
    """)
    for tabla in TABLAS_AUDITORIA:
        op.execute(
            sa.text(
                f"CREATE TRIGGER tr_{tabla}_fecha BEFORE UPDATE ON public.{tabla} "
                "FOR EACH ROW EXECUTE FUNCTION public.actualizar_fecha_actualizacion()"
            )
        )
    op.execute("""
        CREATE FUNCTION public.impedir_modificacion_auditoria() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla auditoria_eventos es inmutable: no se permite %', TG_OP;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER tr_auditoria_eventos_inmutable
        BEFORE UPDATE OR DELETE ON public.auditoria_eventos
        FOR EACH ROW EXECUTE FUNCTION public.impedir_modificacion_auditoria()
    """)
    op.execute("""
        CREATE TRIGGER tr_auditoria_eventos_no_truncar
        BEFORE TRUNCATE ON public.auditoria_eventos
        FOR EACH STATEMENT EXECUTE FUNCTION public.impedir_modificacion_auditoria()
    """)
    op.execute("REVOKE ALL ON public.auditoria_eventos FROM PUBLIC")
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
        "ON public.auditoria_eventos FROM CURRENT_USER"
    )
    op.execute("GRANT INSERT, SELECT ON public.auditoria_eventos TO CURRENT_USER")


def downgrade():
    comprobar_destino(reversion=True)
    op.execute("DROP TRIGGER tr_auditoria_eventos_no_truncar ON public.auditoria_eventos")
    op.execute("DROP TRIGGER tr_auditoria_eventos_inmutable ON public.auditoria_eventos")
    for tabla in reversed(TABLAS_AUDITORIA):
        op.execute(sa.text(f"DROP TRIGGER tr_{tabla}_fecha ON public.{tabla}"))
    op.execute("DROP FUNCTION public.impedir_modificacion_auditoria()")
    op.execute("DROP FUNCTION public.actualizar_fecha_actualizacion()")
    op.drop_index(op.f("ix_artillero_cursos_tipo_curso_id"), table_name="artillero_cursos")
    op.drop_index(op.f("ix_artillero_cursos_importacion_excel_id"), table_name="artillero_cursos")
    op.drop_index(op.f("ix_artillero_cursos_hoja_vida_artillero_id"), table_name="artillero_cursos")
    op.drop_index("ix_artillero_cursos_evaluacion", table_name="artillero_cursos")
    op.drop_table("artillero_cursos")
    op.drop_index(
        op.f("ix_artillero_certificaciones_tipo_certificacion_id"), table_name="artillero_certificaciones"
    )
    op.drop_index(
        op.f("ix_artillero_certificaciones_importacion_excel_id"), table_name="artillero_certificaciones"
    )
    op.drop_index(
        op.f("ix_artillero_certificaciones_hoja_vida_artillero_id"), table_name="artillero_certificaciones"
    )
    op.drop_index("ix_artillero_certificaciones_evaluacion", table_name="artillero_certificaciones")
    op.drop_table("artillero_certificaciones")
    op.drop_index(op.f("ix_artillero_cargos_unidad_militar_id"), table_name="artillero_cargos")
    op.drop_index(op.f("ix_artillero_cargos_tipo_cargo_id"), table_name="artillero_cargos")
    op.drop_index(op.f("ix_artillero_cargos_hoja_vida_artillero_id"), table_name="artillero_cargos")
    op.drop_table("artillero_cargos")
    op.drop_index(op.f("ix_usuario_permisos_usuario_id"), table_name="usuario_permisos")
    op.drop_index(op.f("ix_usuario_permisos_componente_id"), table_name="usuario_permisos")
    op.drop_index(op.f("ix_usuario_permisos_actualizado_por_id"), table_name="usuario_permisos")
    op.drop_table("usuario_permisos")
    op.drop_index(op.f("ix_sesiones_usuario_usuario_id"), table_name="sesiones_usuario")
    op.drop_table("sesiones_usuario")
    op.drop_index("ix_intentos_inicio_sesion_usuario_id_fecha", table_name="intentos_inicio_sesion")
    op.drop_index(op.f("ix_intentos_inicio_sesion_usuario_id"), table_name="intentos_inicio_sesion")
    op.drop_index("ix_intentos_inicio_sesion_direccion_ip_fecha", table_name="intentos_inicio_sesion")
    op.drop_table("intentos_inicio_sesion")
    op.drop_index(op.f("ix_importaciones_excel_usuario_id"), table_name="importaciones_excel")
    op.drop_table("importaciones_excel")
    op.drop_index(op.f("ix_hoja_vida_artillero_personal_militar_id"), table_name="hoja_vida_artillero")
    op.drop_table("hoja_vida_artillero")
    op.drop_index("ix_auditoria_eventos_usuario_id_fecha", table_name="auditoria_eventos")
    op.drop_index(op.f("ix_auditoria_eventos_usuario_id"), table_name="auditoria_eventos")
    op.drop_index("ix_auditoria_eventos_numero_documento_consultado", table_name="auditoria_eventos")
    op.drop_index("ix_auditoria_eventos_fecha", table_name="auditoria_eventos")
    op.drop_table("auditoria_eventos")
    op.drop_index("ux_usuarios_nombre_usuario", table_name="usuarios")
    op.drop_index(op.f("ix_usuarios_rol_id"), table_name="usuarios")
    op.drop_table("usuarios")
    op.drop_index(op.f("ix_roles_permisos_rol_id"), table_name="roles_permisos")
    op.drop_index(op.f("ix_roles_permisos_permiso_id"), table_name="roles_permisos")
    op.drop_table("roles_permisos")
    op.drop_index(op.f("ix_rol_permisos_rol_id"), table_name="rol_permisos")
    op.drop_index(op.f("ix_rol_permisos_componente_id"), table_name="rol_permisos")
    op.drop_table("rol_permisos")
    op.drop_index(op.f("ix_requisitos_habilitacion_tipo_curso_id"), table_name="requisitos_habilitacion")
    op.drop_index(
        op.f("ix_requisitos_habilitacion_tipo_certificacion_id"), table_name="requisitos_habilitacion"
    )
    op.drop_index(
        op.f("ix_requisitos_habilitacion_sistema_artilleria_id"), table_name="requisitos_habilitacion"
    )
    op.drop_table("requisitos_habilitacion")
    op.drop_index(op.f("ix_personal_militar_unidad_militar_id"), table_name="personal_militar")
    op.drop_index("ix_personal_militar_estado_servicio", table_name="personal_militar")
    op.drop_table("personal_militar")
    op.drop_index(op.f("ix_unidades_militares_unidad_superior_id"), table_name="unidades_militares")
    op.drop_table("unidades_militares")
    op.drop_table("tipos_curso")
    op.drop_table("tipos_certificacion")
    op.drop_table("tipos_cargo")
    op.drop_table("sistemas_artilleria")
    op.drop_table("roles")
    op.drop_table("permisos")
    op.drop_index(op.f("ix_componentes_componente_padre_id"), table_name="componentes")
    op.drop_table("componentes")
    # ### end Alembic commands ###
