"""Contrato real auditado y protección HTTP. No crea registros ni abre otra base."""

import json
import runpy
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

from aplicacion.base_datos.base import BaseModelo
from aplicacion.base_datos.configuracion import opciones_tls_local
from aplicacion.modelos import MODELOS_PENDIENTES, TipoUnidad, UnidadMilitar, Usuario

RAIZ = Path(__file__).parents[1]


# Tablas creadas por revisiones posteriores a la fotografía p0001 (p0002 en adelante).
TABLAS_POSTERIORES_A_P0001 = {
    "esart.sesiones_usuario",
    "esart.intentos_inicio_sesion",
    "esart.limites_inicio_ip",
    "esart.estados_acceso_anonimos",
    "esart.auditoria_acceso",
    "esart.desafios_captcha",
    "esart.parametros_habilitacion",
    "esart.auditoria_eventos",
}
COLUMNAS_P0002 = {("esart_ref", "usuarios"): {"intentos_fallidos_consecutivos", "bloqueado_hasta"}}
# p0011: curso de la importación masiva e historial de grados.
COLUMNAS_P0011 = {
    # p0013 agrega los datos del instructor militar o civil.
    ("esart", "instructores"): {
        "foto",
        "foto_tipo",
        "tipo",
        "personal_id",
        "documento_identidad",
        "nombres",
        "apellidos",
        "profesion",
        "actualizado_en",
    },
    ("esart", "hoja_vida_artillero"): {"grado", "curso_id", "unidad_id"},
}
# Columnas que una revisión posterior dejó opcionales (p0011: semestre; p0013: usuario del instructor).
OPCIONALES_P0011 = {("esart", "cursos", "semestre_id"), ("esart", "instructores", "usuario_id")}


def test_todos_los_modelos_corresponden_a_tablas_y_columnas_reales():
    referencia = json.loads((RAIZ / "migraciones_principal/estructura_p0001.json").read_text())
    assert set(BaseModelo.metadata.tables) - TABLAS_POSTERIORES_A_P0001 == {
        t["esquema"] + "." + t["tabla"] for t in referencia["tablas"]
    }
    for tabla in BaseModelo.metadata.tables.values():
        if tabla.fullname in TABLAS_POSTERIORES_A_P0001:
            continue
        columnas = [
            c for c in referencia["columnas"] if c["esquema"] == tabla.schema and c["tabla"] == tabla.name
        ]
        agregadas = COLUMNAS_P0002.get((tabla.schema, tabla.name), set()) | COLUMNAS_P0011.get(
            (tabla.schema, tabla.name), set()
        )
        assert set(tabla.c.keys()) - agregadas == {c["columna"] for c in columnas}
        for c in columnas:
            mapped = tabla.c[c["columna"]]
            if (tabla.schema, tabla.name, c["columna"]) in OPCIONALES_P0011:
                assert mapped.nullable
            else:
                assert mapped.nullable == c["permite_null"]
            if c["tipo"] == "bigint":
                assert isinstance(mapped.type, BigInteger)
            assert (mapped.server_default is None) == (
                c["defecto"] is None and not c["identidad"].endswith("d'")
            )
    assert len(MODELOS_PENDIENTES) == 5
    assert "esart.permisos" not in BaseModelo.metadata.tables


def test_relaciones_bigint_y_usuarios_sin_rol_id_inventado():
    configure_mappers()
    assert UnidadMilitar.__table__.fullname == "esart_ref.unidades_militares"
    assert TipoUnidad.__table__.fullname == "esart.tipos_unidad"
    assert "rol_id" not in Usuario.__table__.c
    assert UnidadMilitar.unidad_padre.property.mapper.class_ is UnidadMilitar
    assert UnidadMilitar.tipo_unidad.property.mapper.class_ is TipoUnidad
    assert "esart_ref.unidades_militares.id" in {
        fk.target_fullname for fk in UnidadMilitar.__table__.c.unidad_padre_id.foreign_keys
    }
    sql = str(UnidadMilitar.__table__.select().compile(dialect=postgresql.dialect()))
    assert "esart_ref.unidades_militares" in sql
    assert "uuid" not in sql.lower()


def test_historial_operativo_unico_y_sin_stamp():
    script = ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini")))
    assert script.get_heads() == ["p0019_firma_movil"]
    assert script.get_revision("p0019_firma_movil").down_revision == "p0018_firma_documental"
    assert script.get_revision("p0018_firma_documental").down_revision == "p0017_restablecer_totp_admin"
    assert script.get_revision("p0017_restablecer_totp_admin").down_revision == "p0016_cursos_artilleros"
    assert script.get_revision("p0016_cursos_artilleros").down_revision == "p0015_registro_manual_personal"
    assert (
        script.get_revision("p0015_registro_manual_personal").down_revision == "p0014_cursos_del_instructor"
    )
    assert script.get_revision("p0014_cursos_del_instructor").down_revision == "p0013_panel_instructores"
    assert script.get_revision("p0013_panel_instructores").down_revision == "p0012_panel_parametros"
    assert script.get_revision("p0012_panel_parametros").down_revision == "p0011_cursos_importacion"
    assert script.get_revision("p0011_cursos_importacion").down_revision == "p0010_merge_hu10_totp"
    assert set(script.get_revision("p0010_merge_hu10_totp").down_revision) == {
        "p0009_gestion_usuarios",
        "p0005_integracion_totp",
    }
    assert script.get_revision("p0005_integracion_totp").down_revision == "p0004_captcha_local"
    assert script.get_revision("p0009_gestion_usuarios").down_revision == "p0008_malla_editable"
    assert script.get_revision("p0008_malla_editable").down_revision == "p0007_auditoria_eventos"
    assert script.get_revision("p0007_auditoria_eventos").down_revision == "p0006_parametros_habilitacion"
    assert script.get_revision("p0006_parametros_habilitacion").down_revision == "p0005_componentes_y_malla"
    assert script.get_revision("p0005_componentes_y_malla").down_revision == "p0004_captcha_local"
    assert script.get_revision("p0002_seguridad_sesiones").down_revision == "p0001_real"
    assert script.get_revision("p0001_real").down_revision == "p0000_instalacion_inicial"
    assert script.get_revision("p0000_instalacion_inicial").down_revision is None
    historico = ScriptDirectory.from_config(Config(str(RAIZ / "alembic_historico.ini")))
    assert historico.get_heads() == ["0002"]


def test_p0017_conserva_todas_las_acciones_de_auditoria_de_p0015():
    directorio = RAIZ / "migraciones_principal" / "versions"
    p0015 = runpy.run_path(str(directorio / "p0015_registro_manual_personal.py"))
    p0017 = runpy.run_path(str(directorio / "p0017_restablecer_totp_admin.py"))
    acciones_p0015 = set(p0015["ACCIONES_ANTERIORES"] + p0015["ACCIONES_NUEVAS"])
    assert set(p0017["ACCIONES"]) == acciones_p0015 | {"TOTP_RESTABLECIDO"}


def test_tls_no_se_degrada_para_servidores_remotos():
    assert opciones_tls_local("postgresql+asyncpg://127.0.0.1/esart_db") == {"ssl": False}
    assert opciones_tls_local("postgresql+asyncpg://servidor/esart_db") == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "ruta",
    [
        "unidades",
        "unidades/jerarquia",
        "unidades/1",
        "unidades/1/subordinadas",
        "tipos-unidad",
        "cargos",
        "cursos",
    ],
)
async def test_catalogos_no_omiten_autenticacion(cliente_api, ruta):
    respuesta = await cliente_api.get("/api/catalogos/" + ruta)
    assert respuesta.status_code == 401


def test_identificadores_de_revision_caben_en_alembic_version():
    """alembic_version.version_num es varchar(32): un id más largo falla al final del upgrade."""
    script = ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini")))
    largos = [r.revision for r in script.walk_revisions() if len(r.revision) > 32]
    assert largos == []
