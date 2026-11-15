"""Integridad del mapeo contractual sin PostgreSQL ni .env real."""

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import configure_mappers

from aplicacion.modelos.historico import PersonalMilitar, Rol, Usuario
from aplicacion.modelos.historico.base import BaseModelo

TABLAS_ESPERADAS = {
    "unidades_militares",
    "personal_militar",
    "hoja_vida_artillero",
    "tipos_curso",
    "artillero_cursos",
    "tipos_certificacion",
    "artillero_certificaciones",
    "sistemas_artilleria",
    "requisitos_habilitacion",
    "tipos_cargo",
    "artillero_cargos",
    "roles",
    "permisos",
    "roles_permisos",
    "usuarios",
    "intentos_inicio_sesion",
    "sesiones_usuario",
    "auditoria_eventos",
    "importaciones_excel",
    "componentes",
    "rol_permisos",
    "usuario_permisos",
}


def test_inventario_y_relaciones_sin_ciclos():
    configure_mappers()
    # HU-03 conserva 22 tablas; la propuesta 0002 añade solo tipos_unidad.
    assert set(BaseModelo.metadata.tables) == TABLAS_ESPERADAS | {"tipos_unidad"}
    assert Usuario.rol.property.mapper.class_ is Rol
    assert PersonalMilitar.unidad_militar.property.mapper.local_table.name == "unidades_militares"


def test_cada_fk_tiene_indice_individual():
    for tabla in BaseModelo.metadata.tables.values():
        for fk in tabla.foreign_keys:
            assert any(list(indice.columns) == [fk.parent] for indice in tabla.indexes), str(fk)


def test_roles_y_malla_tienen_checks_y_auditoria():
    for nombre in ("roles", "rol_permisos", "usuario_permisos"):
        tabla = BaseModelo.metadata.tables[nombre]
        assert any(isinstance(c, CheckConstraint) for c in tabla.constraints)
        assert not tabla.c.fecha_actualizacion.nullable
    assert set(BaseModelo.metadata.tables["rol_permisos"].primary_key.columns.keys()) == {
        "rol_id",
        "componente_id",
    }


def test_tipos_contractuales():
    assert BaseModelo.metadata.tables["personal_militar"].c.id.type.python_type.__name__ == "UUID"
    assert BaseModelo.metadata.tables["artillero_cursos"].c.nota_final.type.scale == 2
    assert BaseModelo.metadata.tables["sesiones_usuario"].c.id.server_default is None
    hash_archivo = BaseModelo.metadata.tables["importaciones_excel"].c.hash_sha256_archivo
    assert hash_archivo.unique
