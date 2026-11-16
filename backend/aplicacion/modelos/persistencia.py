"""Mapeo de la estructura real auditada de esart_db; no ejecuta DDL ni reflexion al importar."""

import sqlalchemy as sa
from sqlalchemy.orm import relationship
from sqlalchemy.sql.elements import conv

from aplicacion.base_datos.base import BaseModelo


class AlertasAcademicas(BaseModelo):
    __table__ = sa.Table(
        "alertas_academicas",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("alumno_activo_id", sa.BigInteger(), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo_alerta", sa.String(40), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("resuelta", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("resuelta_por_id", sa.BigInteger(), nullable=True),
        sa.Column("resuelta_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("alertas_academicas_pkey")),
        sa.ForeignKeyConstraint(
            ["alumno_activo_id"],
            ["esart.alumnos_activos.id"],
            name=conv("fk_alertas_academicas_alumno_activo_id"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_alertas_academicas_personal_id")
        ),
        sa.ForeignKeyConstraint(
            ["resuelta_por_id"], ["esart_ref.usuarios.id"], name=conv("fk_alertas_academicas_resuelta_por_id")
        ),
        schema="esart",
    )


class AlertasCertificacion(BaseModelo):
    __table__ = sa.Table(
        "alertas_certificacion",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("certificado_id", sa.BigInteger(), nullable=False),
        sa.Column("sistema_en_op_id", sa.BigInteger(), nullable=True),
        sa.Column("tipo_alerta", sa.String(20), nullable=False),
        sa.Column("anios_sin_ejercer", sa.Numeric(5, 2), nullable=False),
        sa.Column("resuelta", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("generada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "((anios_sin_ejercer >= (0)::numeric))",
            name=conv("alertas_certificacion_anios_sin_ejercer_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("alertas_certificacion_pkey")),
        sa.ForeignKeyConstraint(
            ["certificado_id"],
            ["esart.certificados_reentrenamiento.id"],
            name=conv("fk_alertas_certificacion_certificado_id"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_alertas_certificacion_personal_id")
        ),
        sa.ForeignKeyConstraint(
            ["sistema_en_op_id"],
            ["esart_ref.sistemas_en_operacion.id"],
            name=conv("fk_alertas_certificacion_sistema_en_op_id"),
        ),
        schema="esart",
    )


class AlumnosActivos(BaseModelo):
    __table__ = sa.Table(
        "alumnos_activos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("curso_id", sa.BigInteger(), nullable=False),
        sa.Column("inscripcion_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha_ingreso_escuela", sa.Date(), nullable=False),
        sa.Column("fecha_fin_prevista", sa.Date(), nullable=False),
        sa.Column(
            "estado_alumno",
            sa.String(20),
            server_default=sa.text("'EN_CURSO'::character varying"),
            nullable=False,
        ),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("alumnos_activos_pkey")),
        sa.CheckConstraint(
            ("estado_alumno IN ('EN_CURSO', 'SUSPENDIDO', 'EN_HABILITACION')"),
            name=conv("ck_alumnos_estado"),
        ),
        sa.ForeignKeyConstraint(["curso_id"], ["esart.cursos.id"], name=conv("fk_alumnos_activos_curso_id")),
        sa.ForeignKeyConstraint(
            ["inscripcion_id"],
            ["esart.inscripciones_curso.id"],
            name=conv("fk_alumnos_activos_inscripcion_id"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_alumnos_activos_personal_id")
        ),
        schema="esart",
    )


class ArtilleroCargo(BaseModelo):
    __table__ = sa.Table(
        "artillero_cargos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("hoja_vida_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo_cargo_id", sa.BigInteger(), nullable=False),
        sa.Column("unidad_id", sa.BigInteger(), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("artillero_cargos_pkey")),
        sa.CheckConstraint(
            "(((fecha_fin IS NULL) OR (fecha_fin >= fecha_inicio)))", name=conv("ck_artillero_cargos_fechas")
        ),
        sa.ForeignKeyConstraint(
            ["hoja_vida_id"], ["esart.hoja_vida_artillero.id"], name=conv("fk_artillero_cargos_hoja_vida_id")
        ),
        sa.ForeignKeyConstraint(
            ["tipo_cargo_id"], ["esart.tipos_cargo.id"], name=conv("fk_artillero_cargos_tipo_cargo_id")
        ),
        sa.ForeignKeyConstraint(
            ["unidad_id"], ["esart_ref.unidades_militares.id"], name=conv("fk_artillero_cargos_unidad_id")
        ),
        schema="esart",
    )


class ArtilleroCertificacion(BaseModelo):
    __table__ = sa.Table(
        "artillero_certificaciones",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("hoja_vida_id", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("entidad", sa.String(200), nullable=False),
        sa.Column("fecha_emision", sa.Date(), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("archivo_url", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("fecha_baja", sa.Date(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("artillero_certificaciones_pkey")),
        sa.CheckConstraint(
            "((activo OR (fecha_baja IS NOT NULL)))", name=conv("ck_artillero_certificaciones_baja")
        ),
        sa.CheckConstraint(
            "(((fecha_vencimiento IS NULL) OR (fecha_vencimiento >= fecha_emision)))",
            name=conv("ck_artillero_certificaciones_vigencia"),
        ),
        sa.ForeignKeyConstraint(
            ["hoja_vida_id"],
            ["esart.hoja_vida_artillero.id"],
            name=conv("fk_artillero_certificaciones_hoja_vida_id"),
        ),
        schema="esart",
    )


class ArtilleroCurso(BaseModelo):
    __table__ = sa.Table(
        "artillero_cursos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("hoja_vida_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo_curso_id", sa.BigInteger(), nullable=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("institucion", sa.String(200), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("horas", sa.Integer(), nullable=True),
        sa.Column("aprobado", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("((horas >= 0))", name=conv("artillero_cursos_horas_check")),
        sa.PrimaryKeyConstraint("id", name=conv("artillero_cursos_pkey")),
        sa.CheckConstraint(
            "(((fecha_fin IS NULL) OR (fecha_fin >= fecha_inicio)))", name=conv("ck_artillero_cursos_fechas")
        ),
        sa.ForeignKeyConstraint(
            ["hoja_vida_id"], ["esart.hoja_vida_artillero.id"], name=conv("fk_artillero_cursos_hoja_vida_id")
        ),
        sa.ForeignKeyConstraint(
            ["tipo_curso_id"], ["esart.tipos_curso.id"], name=conv("fk_artillero_cursos_tipo_curso_id")
        ),
        schema="esart",
    )


class ArtilleroDisparos(BaseModelo):
    __table__ = sa.Table(
        "artillero_disparos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("hoja_vida_id", sa.BigInteger(), nullable=False),
        sa.Column("ejercicio", sa.String(200), nullable=False),
        sa.Column("sistema_nombre", sa.String(200), nullable=True),
        sa.Column("sistema_artilleria_id", sa.BigInteger(), nullable=True),
        sa.Column("unidad_id", sa.BigInteger(), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("cantidad_disparos", sa.Integer(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "((cantidad_disparos >= 0))", name=conv("artillero_disparos_cantidad_disparos_check")
        ),
        sa.PrimaryKeyConstraint("id", name=conv("artillero_disparos_pkey")),
        sa.ForeignKeyConstraint(
            ["hoja_vida_id"],
            ["esart.hoja_vida_artillero.id"],
            name=conv("fk_artillero_disparos_hoja_vida_id"),
        ),
        sa.ForeignKeyConstraint(
            ["sistema_artilleria_id"],
            ["esart_ref.sistemas_artilleria.id"],
            name=conv("fk_artillero_disparos_sistema_artilleria_id"),
        ),
        sa.ForeignKeyConstraint(
            ["unidad_id"], ["esart_ref.unidades_militares.id"], name=conv("fk_artillero_disparos_unidad_id")
        ),
        schema="esart",
    )


class CertificadosReentrenamiento(BaseModelo):
    __table__ = sa.Table(
        "certificados_reentrenamiento",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("participante_id", sa.BigInteger(), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("proposito", sa.String(30), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("movilidad", sa.String(20), nullable=False),
        sa.Column("calibre", sa.String(20), nullable=False),
        sa.Column("numero_certificado", sa.String(50), nullable=False),
        sa.Column("fecha_expedicion", sa.Date(), nullable=False),
        sa.Column("fecha_ultima_aplicacion", sa.Date(), nullable=True),
        sa.Column("apto_para_disparar", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("vigente", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("archivo_pdf_url", sa.Text(), nullable=True),
        sa.Column("expedido_por_id", sa.BigInteger(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "numero_certificado", name=conv("certificados_reentrenamiento_numero_certificado_key")
        ),
        sa.UniqueConstraint("participante_id", name=conv("certificados_reentrenamiento_participante_id_key")),
        sa.PrimaryKeyConstraint("id", name=conv("certificados_reentrenamiento_pkey")),
        sa.ForeignKeyConstraint(
            ["expedido_por_id"],
            ["esart_ref.usuarios.id"],
            name=conv("fk_certificados_reentrenamiento_expedido_por_id"),
        ),
        sa.ForeignKeyConstraint(
            ["participante_id"],
            ["esart.participantes_reentrenamiento.id"],
            name=conv("fk_certificados_reentrenamiento_participante_id"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"],
            ["esart.personal_militar.id"],
            name=conv("fk_certificados_reentrenamiento_personal_id"),
        ),
        schema="esart",
    )


class ComiteMovilInstructores(BaseModelo):
    __table__ = sa.Table(
        "comite_movil_instructores",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("comite_id", sa.BigInteger(), nullable=False),
        sa.Column("instructor_id", sa.BigInteger(), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("fecha_asignacion", sa.Date(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("comite_movil_instructores_pkey")),
        sa.ForeignKeyConstraint(
            ["comite_id"], ["esart.comites_moviles.id"], name=conv("fk_comite_movil_instructores_comite_id")
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["esart.instructores.id"],
            name=conv("fk_comite_movil_instructores_instructor_id"),
        ),
        schema="esart",
    )


class ComitesMoviles(BaseModelo):
    __table__ = sa.Table(
        "comites_moviles",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("director_autoriza_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha_constitucion", sa.Date(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("codigo", name=conv("comites_moviles_codigo_key")),
        sa.PrimaryKeyConstraint("id", name=conv("comites_moviles_pkey")),
        sa.ForeignKeyConstraint(
            ["director_autoriza_id"],
            ["esart_ref.usuarios.id"],
            name=conv("fk_comites_moviles_director_autoriza_id"),
        ),
        schema="esart",
    )


class Componente(BaseModelo):
    __table__ = sa.Table(
        "componentes",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(100), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("ruta_angular", sa.String(250), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("componente_padre_id", sa.BigInteger(), nullable=True),
        sa.Column("orden", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("codigo", name=conv("componentes_codigo_key")),
        sa.ForeignKeyConstraint(
            ["componente_padre_id"],
            ["esart.componentes.id"],
            name=conv("componentes_componente_padre_id_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=conv("componentes_pkey")),
        schema="esart",
    )


class ConsejosAcademicos(BaseModelo):
    __table__ = sa.Table(
        "consejos_academicos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("alumno_activo_id", sa.BigInteger(), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("alerta_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha_consejo", sa.Date(), nullable=True),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("acta_url", sa.Text(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("consejos_academicos_pkey")),
        sa.ForeignKeyConstraint(
            ["alerta_id"], ["esart.alertas_academicas.id"], name=conv("fk_consejos_academicos_alerta_id")
        ),
        sa.ForeignKeyConstraint(
            ["alumno_activo_id"],
            ["esart.alumnos_activos.id"],
            name=conv("fk_consejos_academicos_alumno_activo_id"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_consejos_academicos_personal_id")
        ),
        schema="esart",
    )


class Cursos(BaseModelo):
    __table__ = sa.Table(
        "cursos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("tipo_curso_id", sa.BigInteger(), nullable=False),
        sa.Column("semestre_id", sa.BigInteger(), nullable=False),
        sa.Column("comandante_id", sa.BigInteger(), nullable=False),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column(
            "estado", sa.String(20), server_default=sa.text("'PLANEADO'::character varying"), nullable=False
        ),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.BigInteger(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            ("estado IN ('PLANEADO', 'EN_EJECUCION', 'FINALIZADO', 'CANCELADO')"),
            name=conv("ck_cursos_estado"),
        ),
        sa.CheckConstraint(
            "(((fecha_fin IS NULL) OR (fecha_fin >= fecha_inicio)))", name=conv("ck_cursos_fechas")
        ),
        sa.UniqueConstraint("codigo", name=conv("cursos_codigo_key")),
        sa.PrimaryKeyConstraint("id", name=conv("cursos_pkey")),
        sa.ForeignKeyConstraint(
            ["comandante_id"], ["esart.instructores.id"], name=conv("fk_cursos_comandante_id")
        ),
        sa.ForeignKeyConstraint(
            ["creado_por_id"], ["esart_ref.usuarios.id"], name=conv("fk_cursos_creado_por_id")
        ),
        sa.ForeignKeyConstraint(
            ["semestre_id"], ["esart.semestres_academicos.id"], name=conv("fk_cursos_semestre_id")
        ),
        sa.ForeignKeyConstraint(
            ["tipo_curso_id"], ["esart.tipos_curso.id"], name=conv("fk_cursos_tipo_curso_id")
        ),
        schema="esart",
    )


class CursosInstructores(BaseModelo):
    __table__ = sa.Table(
        "cursos_instructores",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("curso_id", sa.BigInteger(), nullable=False),
        sa.Column("instructor_id", sa.BigInteger(), nullable=False),
        sa.Column("rol_en_curso", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("cursos_instructores_pkey")),
        sa.ForeignKeyConstraint(
            ["curso_id"], ["esart.cursos.id"], name=conv("fk_cursos_instructores_curso_id")
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"], ["esart.instructores.id"], name=conv("fk_cursos_instructores_instructor_id")
        ),
        schema="esart",
    )


class Diplomas(BaseModelo):
    __table__ = sa.Table(
        "diplomas",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("inscripcion_id", sa.BigInteger(), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("numero_diploma", sa.String(50), nullable=False),
        sa.Column("fecha_expedicion", sa.Date(), nullable=False),
        sa.Column("archivo_pdf_url", sa.Text(), nullable=True),
        sa.Column("expedido_por_id", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("inscripcion_id", name=conv("diplomas_inscripcion_id_key")),
        sa.UniqueConstraint("numero_diploma", name=conv("diplomas_numero_diploma_key")),
        sa.PrimaryKeyConstraint("id", name=conv("diplomas_pkey")),
        sa.ForeignKeyConstraint(
            ["expedido_por_id"], ["esart_ref.usuarios.id"], name=conv("fk_diplomas_expedido_por_id")
        ),
        sa.ForeignKeyConstraint(
            ["inscripcion_id"], ["esart.inscripciones_curso.id"], name=conv("fk_diplomas_inscripcion_id")
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_diplomas_personal_id")
        ),
        schema="esart",
    )


class DoctrinaDocumentos(BaseModelo):
    __table__ = sa.Table(
        "doctrina_documentos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("modulo", sa.String(50), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("ruta_archivo", sa.String(500), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("subido_por_id", sa.BigInteger(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=conv("doctrina_documentos_pkey")),
        sa.ForeignKeyConstraint(
            ["subido_por_id"], ["esart_ref.usuarios.id"], name=conv("fk_doctrina_documentos_subido_por_id")
        ),
        schema="esart",
    )


class EgresadosCurso(BaseModelo):
    __table__ = sa.Table(
        "egresados_curso",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("curso_id", sa.BigInteger(), nullable=False),
        sa.Column("inscripcion_id", sa.BigInteger(), nullable=False),
        sa.Column("comandante_curso_id", sa.BigInteger(), nullable=False),
        sa.Column("unidad_destino_id", sa.BigInteger(), nullable=True),
        sa.Column("fecha_ingreso", sa.Date(), nullable=False),
        sa.Column("fecha_egreso", sa.Date(), nullable=False),
        sa.Column("dias_en_curso", sa.Integer(), nullable=False),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("puesto_en_curso", sa.Integer(), nullable=True),
        sa.Column("distincion", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("nota_final", sa.Numeric(5, 2), nullable=True),
        sa.Column("conducta", sa.String(20), nullable=True),
        sa.Column("motivo_perdida", sa.Text(), nullable=True),
        sa.Column("folio_disciplinario", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_repetir", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("observaciones_comandante", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(((fecha_egreso IS NULL) OR (fecha_egreso >= fecha_ingreso)))",
            name=conv("ck_egresados_curso_fechas"),
        ),
        sa.CheckConstraint(
            ("resultado IN ('APROBADO', 'REPROBADO', 'RETIRADO')"),
            name=conv("ck_egresados_resultado"),
        ),
        sa.CheckConstraint("((dias_en_curso >= 0))", name=conv("egresados_curso_dias_en_curso_check")),
        sa.CheckConstraint(
            "(((nota_final >= (0)::numeric) AND (nota_final <= (100)::numeric)))",
            name=conv("egresados_curso_nota_final_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("egresados_curso_pkey")),
        sa.ForeignKeyConstraint(
            ["comandante_curso_id"],
            ["esart.instructores.id"],
            name=conv("fk_egresados_curso_comandante_curso_id"),
        ),
        sa.ForeignKeyConstraint(["curso_id"], ["esart.cursos.id"], name=conv("fk_egresados_curso_curso_id")),
        sa.ForeignKeyConstraint(
            ["inscripcion_id"],
            ["esart.inscripciones_curso.id"],
            name=conv("fk_egresados_curso_inscripcion_id"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_egresados_curso_personal_id")
        ),
        sa.ForeignKeyConstraint(
            ["unidad_destino_id"],
            ["esart_ref.unidades_militares.id"],
            name=conv("fk_egresados_curso_unidad_destino_id"),
        ),
        schema="esart",
    )


class EspecialidadesInstructor(BaseModelo):
    __table__ = sa.Table(
        "especialidades_instructor",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.UniqueConstraint("codigo", name=conv("especialidades_instructor_codigo_key")),
        sa.PrimaryKeyConstraint("id", name=conv("especialidades_instructor_pkey")),
        schema="esart",
    )


class Habilitaciones(BaseModelo):
    __table__ = sa.Table(
        "habilitaciones",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("alumno_activo_id", sa.BigInteger(), nullable=False),
        sa.Column("nota_materia_id", sa.BigInteger(), nullable=False),
        sa.Column("numero_habilitacion", sa.Integer(), nullable=False),
        sa.Column("fecha_habilitacion", sa.Date(), nullable=False),
        sa.Column("nota_obtenida", sa.Numeric(5, 2), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("registrado_por_id", sa.BigInteger(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            ("resultado IN ('APROBADA', 'REPROBADA')"),
            name=conv("ck_habilitaciones_resultado"),
        ),
        sa.ForeignKeyConstraint(
            ["alumno_activo_id"],
            ["esart.alumnos_activos.id"],
            name=conv("fk_habilitaciones_alumno_activo_id"),
        ),
        sa.ForeignKeyConstraint(
            ["nota_materia_id"], ["esart.notas_materia.id"], name=conv("fk_habilitaciones_nota_materia_id")
        ),
        sa.ForeignKeyConstraint(
            ["registrado_por_id"], ["esart_ref.usuarios.id"], name=conv("fk_habilitaciones_registrado_por_id")
        ),
        sa.CheckConstraint(
            "(((nota_obtenida >= (0)::numeric) AND (nota_obtenida <= (100)::numeric)))",
            name=conv("habilitaciones_nota_obtenida_check"),
        ),
        sa.CheckConstraint(
            "(((numero_habilitacion >= 1) AND (numero_habilitacion <= 2)))",
            name=conv("habilitaciones_numero_habilitacion_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("habilitaciones_pkey")),
        schema="esart",
    )


class HojaVidaArtillero(BaseModelo):
    __table__ = sa.Table(
        "hoja_vida_artillero",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("artillero_id", sa.BigInteger(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["artillero_id"], ["esart.personal_militar.id"], name=conv("fk_hoja_vida_artillero_artillero_id")
        ),
        sa.UniqueConstraint("artillero_id", name=conv("hoja_vida_artillero_artillero_id_key")),
        sa.PrimaryKeyConstraint("id", name=conv("hoja_vida_artillero_pkey")),
        schema="esart",
    )


class InscripcionesCurso(BaseModelo):
    __table__ = sa.Table(
        "inscripciones_curso",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("curso_id", sa.BigInteger(), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha_inscripcion", sa.Date(), nullable=False),
        sa.Column(
            "estado", sa.String(20), server_default=sa.text("'INSCRITO'::character varying"), nullable=False
        ),
        sa.Column("nota_final", sa.Numeric(5, 2), nullable=True),
        sa.Column("fecha_resultado", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.CheckConstraint(
            ("estado IN ('INSCRITO', 'SELECCIONADO', 'RETIRADO', 'GRADUADO', 'REPROBADO')"),
            name=conv("ck_inscripciones_estado"),
        ),
        sa.ForeignKeyConstraint(
            ["curso_id"], ["esart.cursos.id"], name=conv("fk_inscripciones_curso_curso_id")
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_inscripciones_curso_personal_id")
        ),
        sa.CheckConstraint(
            "(((nota_final >= (0)::numeric) AND (nota_final <= (100)::numeric)))",
            name=conv("inscripciones_curso_nota_final_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("inscripciones_curso_pkey")),
        schema="esart",
    )


class Instructores(BaseModelo):
    __table__ = sa.Table(
        "instructores",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha_ingreso_escuela", sa.Date(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["esart_ref.usuarios.id"], name=conv("fk_instructores_usuario_id")
        ),
        sa.PrimaryKeyConstraint("id", name=conv("instructores_pkey")),
        sa.UniqueConstraint("usuario_id", name=conv("instructores_usuario_id_key")),
        schema="esart",
    )


class InstructoresEspecialidades(BaseModelo):
    __table__ = sa.Table(
        "instructores_especialidades",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("instructor_id", sa.BigInteger(), nullable=False),
        sa.Column("especialidad_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha_asignacion", sa.Date(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["especialidad_id"],
            ["esart.especialidades_instructor.id"],
            name=conv("fk_instructores_especialidades_especialidad_id"),
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["esart.instructores.id"],
            name=conv("fk_instructores_especialidades_instructor_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("instructores_especialidades_pkey")),
        schema="esart",
    )


class MallaCurricular(BaseModelo):
    __table__ = sa.Table(
        "malla_curricular",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("tipo_curso_id", sa.BigInteger(), nullable=False),
        sa.Column("materia_id", sa.BigInteger(), nullable=False),
        sa.Column("nota_minima_aprobacion", sa.Numeric(4, 2), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["materia_id"], ["esart.materias.id"], name=conv("fk_malla_curricular_materia_id")
        ),
        sa.ForeignKeyConstraint(
            ["tipo_curso_id"], ["esart.tipos_curso.id"], name=conv("fk_malla_curricular_tipo_curso_id")
        ),
        sa.CheckConstraint(
            "(((nota_minima_aprobacion >= (0)::numeric) AND (nota_minima_aprobacion <= (100)::numeric)))",
            name=conv("malla_curricular_nota_minima_aprobacion_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("malla_curricular_pkey")),
        schema="esart",
    )


class Materias(BaseModelo):
    __table__ = sa.Table(
        "materias",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("codigo", name=conv("materias_codigo_key")),
        sa.PrimaryKeyConstraint("id", name=conv("materias_pkey")),
        schema="esart",
    )


class NotasFinalesEgresado(BaseModelo):
    __table__ = sa.Table(
        "notas_finales_egresado",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("egresado_id", sa.BigInteger(), nullable=False),
        sa.Column("materia_id", sa.BigInteger(), nullable=False),
        sa.Column("nota", sa.Numeric(5, 2), nullable=False),
        sa.Column("nota_habilitacion", sa.Numeric(5, 2), nullable=True),
        sa.Column("resultado_materia", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(
            ["egresado_id"], ["esart.egresados_curso.id"], name=conv("fk_notas_finales_egresado_egresado_id")
        ),
        sa.ForeignKeyConstraint(
            ["materia_id"], ["esart.materias.id"], name=conv("fk_notas_finales_egresado_materia_id")
        ),
        sa.CheckConstraint(
            "(((nota >= (0)::numeric) AND (nota <= (100)::numeric)))",
            name=conv("notas_finales_egresado_nota_check"),
        ),
        sa.CheckConstraint(
            "(((nota_habilitacion >= (0)::numeric) AND (nota_habilitacion <= (100)::numeric)))",
            name=conv("notas_finales_egresado_nota_habilitacion_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("notas_finales_egresado_pkey")),
        schema="esart",
    )


class NotasMateria(BaseModelo):
    __table__ = sa.Table(
        "notas_materia",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("alumno_activo_id", sa.BigInteger(), nullable=False),
        sa.Column("malla_id", sa.BigInteger(), nullable=False),
        sa.Column("nota", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "estado", sa.String(20), server_default=sa.text("'PENDIENTE'::character varying"), nullable=False
        ),
        sa.Column("nota_habilitacion", sa.Numeric(5, 2), nullable=True),
        sa.Column("fecha_evaluacion", sa.Date(), nullable=True),
        sa.Column("fecha_habilitacion", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["alumno_activo_id"], ["esart.alumnos_activos.id"], name=conv("fk_notas_materia_alumno_activo_id")
        ),
        sa.ForeignKeyConstraint(
            ["malla_id"], ["esart.malla_curricular.id"], name=conv("fk_notas_materia_malla_id")
        ),
        sa.CheckConstraint(
            "(((nota >= (0)::numeric) AND (nota <= (100)::numeric)))", name=conv("notas_materia_nota_check")
        ),
        sa.CheckConstraint(
            "(((nota_habilitacion >= (0)::numeric) AND (nota_habilitacion <= (100)::numeric)))",
            name=conv("notas_materia_nota_habilitacion_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("notas_materia_pkey")),
        schema="esart",
    )


class OperadoresSistema(BaseModelo):
    __table__ = sa.Table(
        "operadores_sistema",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("sistema_en_op_id", sa.BigInteger(), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("certificado_id", sa.BigInteger(), nullable=True),
        sa.Column("rol_en_sistema", sa.String(20), nullable=False),
        sa.Column("apto_para_disparar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fecha_certificacion", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["certificado_id"],
            ["esart.certificados_reentrenamiento.id"],
            name=conv("fk_operadores_sistema_certificado_id"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["esart.personal_militar.id"], name=conv("fk_operadores_sistema_personal_id")
        ),
        sa.ForeignKeyConstraint(
            ["sistema_en_op_id"],
            ["esart_ref.sistemas_en_operacion.id"],
            name=conv("fk_operadores_sistema_sistema_en_op_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("operadores_sistema_pkey")),
        schema="esart",
    )


class ParticipantesReentrenamiento(BaseModelo):
    __table__ = sa.Table(
        "participantes_reentrenamiento",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("reentrenamiento_id", sa.BigInteger(), nullable=False),
        sa.Column("personal_id", sa.BigInteger(), nullable=False),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("fecha_resultado", sa.Date(), nullable=True),
        sa.CheckConstraint(
            ("resultado IN ('CERTIFICADO', 'NO_CERTIFICADO', 'RETIRADO')"),
            name=conv("ck_participantes_resultado"),
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"],
            ["esart.personal_militar.id"],
            name=conv("fk_participantes_reentrenamiento_personal_id"),
        ),
        sa.ForeignKeyConstraint(
            ["reentrenamiento_id"],
            ["esart.reentrenamientos.id"],
            name=conv("fk_participantes_reentrenamiento_reentrenamiento_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("participantes_reentrenamiento_pkey")),
        schema="esart",
    )


class PersonalMilitar(BaseModelo):
    __table__ = sa.Table(
        "personal_militar",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("documento_identidad", sa.String(50), nullable=False),
        sa.Column("nombres", sa.String(150), nullable=False),
        sa.Column("apellidos", sa.String(150), nullable=False),
        sa.Column("grado", sa.String(20), nullable=False),
        sa.Column("genero", sa.String(1), nullable=False),
        sa.Column("categoria", sa.String(30), nullable=False),
        sa.Column("unidad_actual_id", sa.BigInteger(), nullable=True),
        sa.Column("especialidad_actual", sa.String(100), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["unidad_actual_id"],
            ["esart_ref.unidades_militares.id"],
            name=conv("fk_personal_militar_unidad_actual_id"),
        ),
        sa.UniqueConstraint("documento_identidad", name=conv("personal_militar_documento_identidad_key")),
        sa.PrimaryKeyConstraint("id", name=conv("personal_militar_pkey")),
        schema="esart",
    )


class Reentrenamientos(BaseModelo):
    __table__ = sa.Table(
        "reentrenamientos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("comite_id", sa.BigInteger(), nullable=False),
        sa.Column("unidad_id", sa.BigInteger(), nullable=False),
        sa.Column("bateria_designada_por", sa.BigInteger(), nullable=False),
        sa.Column("proposito", sa.String(30), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("movilidad", sa.String(20), nullable=False),
        sa.Column("calibre", sa.String(20), nullable=False),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column(
            "estado", sa.String(20), server_default=sa.text("'PLANEADO'::character varying"), nullable=False
        ),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("documento_certificacion", sa.String(500), nullable=True),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            ("estado IN ('PLANEADO', 'EN_EJECUCION', 'FINALIZADO', 'CANCELADO')"),
            name=conv("ck_reentrenamientos_estado"),
        ),
        sa.CheckConstraint(
            "(((fecha_fin IS NULL) OR (fecha_fin >= fecha_inicio)))", name=conv("ck_reentrenamientos_fechas")
        ),
        sa.ForeignKeyConstraint(
            ["bateria_designada_por"],
            ["esart_ref.usuarios.id"],
            name=conv("fk_reentrenamientos_bateria_designada_por"),
        ),
        sa.ForeignKeyConstraint(
            ["comite_id"], ["esart.comites_moviles.id"], name=conv("fk_reentrenamientos_comite_id")
        ),
        sa.ForeignKeyConstraint(
            ["unidad_id"], ["esart_ref.unidades_militares.id"], name=conv("fk_reentrenamientos_unidad_id")
        ),
        sa.UniqueConstraint("codigo", name=conv("reentrenamientos_codigo_key")),
        sa.PrimaryKeyConstraint("id", name=conv("reentrenamientos_pkey")),
        schema="esart",
    )


class RolPermiso(BaseModelo):
    __table__ = sa.Table(
        "rol_permisos",
        BaseModelo.metadata,
        sa.Column("rol_id", sa.BigInteger(), nullable=False),
        sa.Column("componente_id", sa.BigInteger(), nullable=False),
        sa.Column("puede_acceder", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_crear", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_leer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_actualizar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_eliminar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "((puede_acceder OR (NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar))))",
            name=conv("ck_esart_rol_crud_acceso"),
        ),
        sa.ForeignKeyConstraint(
            ["componente_id"],
            ["esart.componentes.id"],
            name=conv("rol_permisos_componente_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("rol_id", "componente_id", name=conv("rol_permisos_pkey")),
        sa.ForeignKeyConstraint(
            ["rol_id"], ["esart.roles.id"], name=conv("rol_permisos_rol_id_fkey"), ondelete="CASCADE"
        ),
        schema="esart",
    )


class Rol(BaseModelo):
    __table__ = sa.Table(
        "roles",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            ("codigo IN ('ADMINISTRADOR', 'USUARIO')"),
            name=conv("ck_esart_roles_codigo"),
        ),
        sa.UniqueConstraint("codigo", name=conv("roles_codigo_key")),
        sa.PrimaryKeyConstraint("id", name=conv("roles_pkey")),
        schema="esart",
    )


class SemestresAcademicos(BaseModelo):
    __table__ = sa.Table(
        "semestres_academicos",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "(((fecha_fin IS NULL) OR (fecha_fin >= fecha_inicio)))",
            name=conv("ck_semestres_academicos_fechas"),
        ),
        sa.CheckConstraint("((numero = ANY (ARRAY[1, 2])))", name=conv("semestres_academicos_numero_check")),
        sa.PrimaryKeyConstraint("id", name=conv("semestres_academicos_pkey")),
        schema="esart",
    )


class TipoCargo(BaseModelo):
    __table__ = sa.Table(
        "tipos_cargo",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("cuenta_para_coofu", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("nombre", name=conv("tipos_cargo_nombre_key")),
        sa.PrimaryKeyConstraint("id", name=conv("tipos_cargo_pkey")),
        schema="esart",
    )


class TipoCurso(BaseModelo):
    __table__ = sa.Table(
        "tipos_curso",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=True),
        sa.Column("modalidad", sa.String(30), nullable=False),
        sa.Column("duracion_semanas", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("codigo", name=conv("tipos_curso_codigo_key")),
        sa.CheckConstraint("((duracion_semanas >= 0))", name=conv("tipos_curso_duracion_semanas_check")),
        sa.PrimaryKeyConstraint("id", name=conv("tipos_curso_pkey")),
        schema="esart",
    )


class TipoUnidad(BaseModelo):
    __table__ = sa.Table(
        "tipos_unidad",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("codigo", name=conv("tipos_unidad_codigo_key")),
        sa.PrimaryKeyConstraint("id", name=conv("tipos_unidad_pkey")),
        schema="esart",
    )


class UsuarioPermiso(BaseModelo):
    __table__ = sa.Table(
        "usuario_permisos",
        BaseModelo.metadata,
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("componente_id", sa.BigInteger(), nullable=False),
        sa.Column("puede_acceder", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_crear", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_leer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_actualizar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("puede_eliminar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actualizado_por_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "((puede_acceder OR (NOT (puede_crear OR puede_leer OR puede_actualizar OR puede_eliminar))))",
            name=conv("ck_esart_usuario_crud_acceso"),
        ),
        sa.ForeignKeyConstraint(
            ["actualizado_por_id"],
            ["esart_ref.usuarios.id"],
            name=conv("usuario_permisos_actualizado_por_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["componente_id"],
            ["esart.componentes.id"],
            name=conv("usuario_permisos_componente_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("usuario_id", "componente_id", name=conv("usuario_permisos_pkey")),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["esart_ref.usuarios.id"],
            name=conv("usuario_permisos_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        schema="esart",
    )


class UsuarioRoles(BaseModelo):
    __table__ = sa.Table(
        "usuario_roles",
        BaseModelo.metadata,
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("rol_id", sa.BigInteger(), nullable=False),
        sa.Column("asignado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("asignado_por_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["asignado_por_id"],
            ["esart_ref.usuarios.id"],
            name=conv("usuario_roles_asignado_por_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("usuario_id", "rol_id", name=conv("usuario_roles_pkey")),
        sa.ForeignKeyConstraint(
            ["rol_id"], ["esart.roles.id"], name=conv("usuario_roles_rol_id_fkey"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["esart_ref.usuarios.id"],
            name=conv("usuario_roles_usuario_id_fkey"),
            ondelete="CASCADE",
        ),
        schema="esart",
    )


class SistemaArtilleria(BaseModelo):
    __table__ = sa.Table(
        "sistemas_artilleria",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("sistemas_artilleria_pkey")),
        schema="esart_ref",
    )


class SistemasEnOperacion(BaseModelo):
    __table__ = sa.Table(
        "sistemas_en_operacion",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("sistemas_en_operacion_pkey")),
        schema="esart_ref",
    )


class UnidadMilitar(BaseModelo):
    __table__ = sa.Table(
        "unidades_militares",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("codigo", sa.String(30), nullable=True),
        sa.Column("nombre", sa.String(200), nullable=True),
        sa.Column("tipo_unidad_id", sa.BigInteger(), nullable=True),
        sa.Column("unidad_padre_id", sa.BigInteger(), nullable=True),
        sa.Column("latitud", sa.Double(), nullable=True),
        sa.Column("longitud", sa.Double(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "fecha_actualizacion", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["unidad_padre_id"], ["esart_ref.unidades_militares.id"], name=conv("fk_esart_unidades_padre")
        ),
        sa.ForeignKeyConstraint(
            ["tipo_unidad_id"], ["esart.tipos_unidad.id"], name=conv("fk_esart_unidades_tipo")
        ),
        sa.PrimaryKeyConstraint("id", name=conv("unidades_militares_pkey")),
        schema="esart_ref",
    )


class Usuario(BaseModelo):
    __table__ = sa.Table(
        "usuarios",
        BaseModelo.metadata,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("usuario", sa.String(80), nullable=True),
        sa.Column("contrasena_hash", sa.Text(), nullable=True),
        sa.Column("documento_identidad", sa.String(50), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "requiere_cambio_contrasena", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ultimo_acceso_en", sa.DateTime(timezone=True), nullable=True),
        # Columnas de la revisión p0002_seguridad_sesiones (bloqueo por intentos, HU-06).
        sa.Column(
            "intentos_fallidos_consecutivos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "intentos_fallidos_consecutivos >= 0", name=conv("ck_esart_usuario_intentos_no_negativos")
        ),
        sa.CheckConstraint(
            "(((contrasena_hash IS NULL) OR (length(TRIM(BOTH FROM contrasena_hash)) > 0)))",
            name=conv("ck_esart_usuario_hash_no_vacio"),
        ),
        sa.PrimaryKeyConstraint("id", name=conv("usuarios_pkey")),
        schema="esart_ref",
    )


sa.Index(
    "ix_alertas_academicas_alumno_activo_id",
    sa.text("alumno_activo_id"),
    _table=BaseModelo.metadata.tables["esart.alertas_academicas"],
    unique=False,
)
sa.Index(
    "ix_alertas_academicas_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.alertas_academicas"],
    unique=False,
)
sa.Index(
    "ix_alertas_academicas_tipo_alerta",
    sa.text("tipo_alerta"),
    _table=BaseModelo.metadata.tables["esart.alertas_academicas"],
    unique=False,
)
sa.Index(
    "ix_alertas_certificacion_certificado_id",
    sa.text("certificado_id"),
    _table=BaseModelo.metadata.tables["esart.alertas_certificacion"],
    unique=False,
)
sa.Index(
    "ix_alertas_certificacion_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.alertas_certificacion"],
    unique=False,
)
sa.Index(
    "ix_alertas_certificacion_tipo_alerta",
    sa.text("tipo_alerta"),
    _table=BaseModelo.metadata.tables["esart.alertas_certificacion"],
    unique=False,
)
sa.Index(
    "ix_alumnos_activos_curso_id",
    sa.text("curso_id"),
    _table=BaseModelo.metadata.tables["esart.alumnos_activos"],
    unique=False,
)
sa.Index(
    "ix_alumnos_activos_inscripcion_id",
    sa.text("inscripcion_id"),
    _table=BaseModelo.metadata.tables["esart.alumnos_activos"],
    unique=False,
)
sa.Index(
    "ix_alumnos_activos_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.alumnos_activos"],
    unique=False,
)
sa.Index(
    "uq_alumno_personal_curso",
    sa.text("personal_id"),
    sa.text("curso_id"),
    _table=BaseModelo.metadata.tables["esart.alumnos_activos"],
    unique=True,
)
sa.Index(
    "ix_artillero_cargos_hoja_vida_id",
    sa.text("hoja_vida_id"),
    _table=BaseModelo.metadata.tables["esart.artillero_cargos"],
    unique=False,
)
sa.Index(
    "ix_artillero_cargos_tipo_cargo_id",
    sa.text("tipo_cargo_id"),
    _table=BaseModelo.metadata.tables["esart.artillero_cargos"],
    unique=False,
)
sa.Index(
    "ix_artillero_certificaciones_activo",
    sa.text("activo"),
    _table=BaseModelo.metadata.tables["esart.artillero_certificaciones"],
    unique=False,
)
sa.Index(
    "ix_artillero_certificaciones_fecha_vencimiento",
    sa.text("fecha_vencimiento"),
    _table=BaseModelo.metadata.tables["esart.artillero_certificaciones"],
    unique=False,
)
sa.Index(
    "ix_artillero_certificaciones_hoja_vida_id",
    sa.text("hoja_vida_id"),
    _table=BaseModelo.metadata.tables["esart.artillero_certificaciones"],
    unique=False,
)
sa.Index(
    "ix_artillero_cursos_hoja_vida_id",
    sa.text("hoja_vida_id"),
    _table=BaseModelo.metadata.tables["esart.artillero_cursos"],
    unique=False,
)
sa.Index(
    "ix_artillero_cursos_tipo_curso_id",
    sa.text("tipo_curso_id"),
    _table=BaseModelo.metadata.tables["esart.artillero_cursos"],
    unique=False,
)
sa.Index(
    "ix_artillero_disparos_hoja_vida_id",
    sa.text("hoja_vida_id"),
    _table=BaseModelo.metadata.tables["esart.artillero_disparos"],
    unique=False,
)
sa.Index(
    "ix_artillero_disparos_sistema_artilleria_id",
    sa.text("sistema_artilleria_id"),
    _table=BaseModelo.metadata.tables["esart.artillero_disparos"],
    unique=False,
)
sa.Index(
    "ix_certificados_reentrenamiento_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.certificados_reentrenamiento"],
    unique=False,
)
sa.Index(
    "ix_certificados_reentrenamiento_vigente",
    sa.text("vigente"),
    _table=BaseModelo.metadata.tables["esart.certificados_reentrenamiento"],
    unique=False,
)
sa.Index(
    "ix_comite_movil_instructores_comite_id",
    sa.text("comite_id"),
    _table=BaseModelo.metadata.tables["esart.comite_movil_instructores"],
    unique=False,
)
sa.Index(
    "ix_comite_movil_instructores_instructor_id",
    sa.text("instructor_id"),
    _table=BaseModelo.metadata.tables["esart.comite_movil_instructores"],
    unique=False,
)
sa.Index(
    "uq_comite_instructor",
    sa.text("comite_id"),
    sa.text("instructor_id"),
    _table=BaseModelo.metadata.tables["esart.comite_movil_instructores"],
    unique=True,
)
sa.Index(
    "ix_esart_componentes_padre",
    sa.text("componente_padre_id"),
    _table=BaseModelo.metadata.tables["esart.componentes"],
    unique=False,
)
sa.Index(
    "ix_consejos_academicos_alerta_id",
    sa.text("alerta_id"),
    _table=BaseModelo.metadata.tables["esart.consejos_academicos"],
    unique=False,
)
sa.Index(
    "ix_consejos_academicos_alumno_activo_id",
    sa.text("alumno_activo_id"),
    _table=BaseModelo.metadata.tables["esart.consejos_academicos"],
    unique=False,
)
sa.Index(
    "uq_curso_instructor",
    sa.text("curso_id"),
    sa.text("instructor_id"),
    _table=BaseModelo.metadata.tables["esart.cursos_instructores"],
    unique=True,
)
sa.Index(
    "ix_diplomas_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.diplomas"],
    unique=False,
)
sa.Index(
    "ix_doctrina_documentos_modulo",
    sa.text("modulo"),
    _table=BaseModelo.metadata.tables["esart.doctrina_documentos"],
    unique=False,
)
sa.Index(
    "ix_doctrina_modulo_activo",
    sa.text("modulo"),
    sa.text("activo"),
    _table=BaseModelo.metadata.tables["esart.doctrina_documentos"],
    unique=False,
)
sa.Index(
    "ix_egresados_curso_curso_id",
    sa.text("curso_id"),
    _table=BaseModelo.metadata.tables["esart.egresados_curso"],
    unique=False,
)
sa.Index(
    "ix_egresados_curso_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.egresados_curso"],
    unique=False,
)
sa.Index(
    "ix_egresados_curso_resultado",
    sa.text("resultado"),
    _table=BaseModelo.metadata.tables["esart.egresados_curso"],
    unique=False,
)
sa.Index(
    "uq_egresado_personal_curso",
    sa.text("personal_id"),
    sa.text("curso_id"),
    _table=BaseModelo.metadata.tables["esart.egresados_curso"],
    unique=True,
)
sa.Index(
    "ix_habilitaciones_alumno_activo_id",
    sa.text("alumno_activo_id"),
    _table=BaseModelo.metadata.tables["esart.habilitaciones"],
    unique=False,
)
sa.Index(
    "ix_habilitaciones_nota_materia_id",
    sa.text("nota_materia_id"),
    _table=BaseModelo.metadata.tables["esart.habilitaciones"],
    unique=False,
)
sa.Index(
    "uq_habilitacion_materia_intento",
    sa.text("nota_materia_id"),
    sa.text("numero_habilitacion"),
    _table=BaseModelo.metadata.tables["esart.habilitaciones"],
    unique=True,
)
sa.Index(
    "ix_inscripciones_curso_curso_id",
    sa.text("curso_id"),
    _table=BaseModelo.metadata.tables["esart.inscripciones_curso"],
    unique=False,
)
sa.Index(
    "ix_inscripciones_curso_estado",
    sa.text("estado"),
    _table=BaseModelo.metadata.tables["esart.inscripciones_curso"],
    unique=False,
)
sa.Index(
    "ix_inscripciones_curso_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.inscripciones_curso"],
    unique=False,
)
sa.Index(
    "uq_inscripcion_curso_personal",
    sa.text("curso_id"),
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.inscripciones_curso"],
    unique=True,
)
sa.Index(
    "uq_instructor_especialidad",
    sa.text("instructor_id"),
    sa.text("especialidad_id"),
    _table=BaseModelo.metadata.tables["esart.instructores_especialidades"],
    unique=True,
)
sa.Index(
    "uq_malla_tipo_materia",
    sa.text("tipo_curso_id"),
    sa.text("materia_id"),
    _table=BaseModelo.metadata.tables["esart.malla_curricular"],
    unique=True,
)
sa.Index(
    "ix_notas_finales_egresado_egresado_id",
    sa.text("egresado_id"),
    _table=BaseModelo.metadata.tables["esart.notas_finales_egresado"],
    unique=False,
)
sa.Index(
    "ix_notas_finales_egresado_materia_id",
    sa.text("materia_id"),
    _table=BaseModelo.metadata.tables["esart.notas_finales_egresado"],
    unique=False,
)
sa.Index(
    "uq_nota_final_egresado_materia",
    sa.text("egresado_id"),
    sa.text("materia_id"),
    _table=BaseModelo.metadata.tables["esart.notas_finales_egresado"],
    unique=True,
)
sa.Index(
    "ix_notas_materia_alumno_activo_id",
    sa.text("alumno_activo_id"),
    _table=BaseModelo.metadata.tables["esart.notas_materia"],
    unique=False,
)
sa.Index(
    "ix_notas_materia_malla_id",
    sa.text("malla_id"),
    _table=BaseModelo.metadata.tables["esart.notas_materia"],
    unique=False,
)
sa.Index(
    "uq_nota_alumno_malla",
    sa.text("alumno_activo_id"),
    sa.text("malla_id"),
    _table=BaseModelo.metadata.tables["esart.notas_materia"],
    unique=True,
)
sa.Index(
    "ix_operadores_sistema_certificado_id",
    sa.text("certificado_id"),
    _table=BaseModelo.metadata.tables["esart.operadores_sistema"],
    unique=False,
)
sa.Index(
    "ix_operadores_sistema_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.operadores_sistema"],
    unique=False,
)
sa.Index(
    "ix_operadores_sistema_sistema_en_op_id",
    sa.text("sistema_en_op_id"),
    _table=BaseModelo.metadata.tables["esart.operadores_sistema"],
    unique=False,
)
sa.Index(
    "uq_operador_sistema_personal",
    sa.text("sistema_en_op_id"),
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.operadores_sistema"],
    unique=True,
)
sa.Index(
    "ix_participantes_reentrenamiento_personal_id",
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.participantes_reentrenamiento"],
    unique=False,
)
sa.Index(
    "ix_participantes_reentrenamiento_reentrenamiento_id",
    sa.text("reentrenamiento_id"),
    _table=BaseModelo.metadata.tables["esart.participantes_reentrenamiento"],
    unique=False,
)
sa.Index(
    "ix_participantes_reentrenamiento_resultado",
    sa.text("resultado"),
    _table=BaseModelo.metadata.tables["esart.participantes_reentrenamiento"],
    unique=False,
)
sa.Index(
    "uq_participante_reentrenamiento",
    sa.text("reentrenamiento_id"),
    sa.text("personal_id"),
    _table=BaseModelo.metadata.tables["esart.participantes_reentrenamiento"],
    unique=True,
)
sa.Index(
    "ix_personal_activo_unidad",
    sa.text("activo"),
    sa.text("unidad_actual_id"),
    _table=BaseModelo.metadata.tables["esart.personal_militar"],
    unique=False,
)
sa.Index(
    "ix_personal_militar_grado",
    sa.text("grado"),
    _table=BaseModelo.metadata.tables["esart.personal_militar"],
    unique=False,
)
sa.Index(
    "ix_reentrenamientos_comite_id",
    sa.text("comite_id"),
    _table=BaseModelo.metadata.tables["esart.reentrenamientos"],
    unique=False,
)
sa.Index(
    "ix_reentrenamientos_estado",
    sa.text("estado"),
    _table=BaseModelo.metadata.tables["esart.reentrenamientos"],
    unique=False,
)
sa.Index(
    "ix_reentrenamientos_fecha_vencimiento",
    sa.text("fecha_vencimiento"),
    _table=BaseModelo.metadata.tables["esart.reentrenamientos"],
    unique=False,
)
sa.Index(
    "ix_reentrenamientos_unidad_id",
    sa.text("unidad_id"),
    _table=BaseModelo.metadata.tables["esart.reentrenamientos"],
    unique=False,
)
sa.Index(
    "ix_esart_rol_permisos_componente",
    sa.text("componente_id"),
    _table=BaseModelo.metadata.tables["esart.rol_permisos"],
    unique=False,
)
sa.Index(
    "uq_semestre_anio_numero",
    sa.text("anio"),
    sa.text("numero"),
    _table=BaseModelo.metadata.tables["esart.semestres_academicos"],
    unique=True,
)
sa.Index(
    "ix_tipos_curso_tipo",
    sa.text("tipo"),
    _table=BaseModelo.metadata.tables["esart.tipos_curso"],
    unique=False,
)
sa.Index(
    "ix_esart_usuario_permisos_componente",
    sa.text("componente_id"),
    _table=BaseModelo.metadata.tables["esart.usuario_permisos"],
    unique=False,
)
sa.Index(
    "ix_esart_usuario_roles_rol",
    sa.text("rol_id"),
    _table=BaseModelo.metadata.tables["esart.usuario_roles"],
    unique=False,
)
sa.Index(
    "ix_esart_ref_unidades_padre",
    sa.text("unidad_padre_id"),
    _table=BaseModelo.metadata.tables["esart_ref.unidades_militares"],
    unique=False,
)
sa.Index(
    "ix_esart_ref_unidades_tipo",
    sa.text("tipo_unidad_id"),
    _table=BaseModelo.metadata.tables["esart_ref.unidades_militares"],
    unique=False,
)
sa.Index(
    "uq_esart_ref_unidades_codigo",
    sa.text("codigo"),
    _table=BaseModelo.metadata.tables["esart_ref.unidades_militares"],
    unique=True,
)
sa.Index(
    "uq_esart_usuario_documento",
    sa.text("documento_identidad) WHERE (documento_identidad IS NOT NULL"),
    _table=BaseModelo.metadata.tables["esart_ref.usuarios"],
    unique=True,
)
sa.Index(
    "uq_esart_usuario_nombre_ci",
    sa.text("lower((usuario)::text)) WHERE (usuario IS NOT NULL"),
    _table=BaseModelo.metadata.tables["esart_ref.usuarios"],
    unique=True,
)

# Relaciones comprobadas: sin columnas virtuales ni FK a tablas inexistentes.
UnidadMilitar.unidad_padre = relationship(
    UnidadMilitar,
    remote_side=[UnidadMilitar.id],
    foreign_keys=[UnidadMilitar.unidad_padre_id],
    backref="subordinadas",
    lazy="raise",
)
UnidadMilitar.tipo_unidad = relationship(
    TipoUnidad, foreign_keys=[UnidadMilitar.tipo_unidad_id], lazy="raise"
)
PersonalMilitar.unidad_actual = relationship(
    UnidadMilitar, foreign_keys=[PersonalMilitar.unidad_actual_id], lazy="raise"
)
HojaVidaArtillero.personal_militar = relationship(
    PersonalMilitar, foreign_keys=[HojaVidaArtillero.artillero_id], lazy="raise"
)
ArtilleroCargo.hoja_vida = relationship(
    HojaVidaArtillero, foreign_keys=[ArtilleroCargo.hoja_vida_id], lazy="raise"
)
ArtilleroCargo.tipo_cargo = relationship(TipoCargo, foreign_keys=[ArtilleroCargo.tipo_cargo_id], lazy="raise")
ArtilleroCurso.tipo_curso = relationship(TipoCurso, foreign_keys=[ArtilleroCurso.tipo_curso_id], lazy="raise")
UsuarioRoles.usuario = relationship(Usuario, foreign_keys=[UsuarioRoles.usuario_id], lazy="raise")
UsuarioRoles.rol = relationship(Rol, foreign_keys=[UsuarioRoles.rol_id], lazy="raise")
