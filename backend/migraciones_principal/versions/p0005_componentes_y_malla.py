"""Componentes del sistema (menú) y malla de permisos inicial por rol (HU-09).

- Personal militar es el módulo padre; sus pestañas son componentes hijos
  (componente_padre_id). El sidebar muestra los padres; las pestañas, los hijos.
- Los módulos de la segunda entrega se crean INACTIVOS: no aparecen hasta que existan.
- VER_DOCUMENTO_COMPLETO no es un menú (sin ruta): es el permiso de ver la cédula completa.
- La malla es el punto de partida acordado: se puede modificar y ampliar después
  (pantalla Malla de permisos o nuevas revisiones). Por eso los permisos existentes
  NO se sobrescriben (ON CONFLICT DO NOTHING).
"""

from alembic import op
from sqlalchemy import text

revision = "p0005_componentes_y_malla"
down_revision = "p0004_captcha_local"
branch_labels = None
depends_on = None

CUENTA_APLICACION = "esart_aplicacion"

# (codigo, nombre, ruta_angular, orden, codigo_padre, activo)
COMPONENTES = [
    ("DASHBOARD", "Panel principal", "/dashboard", 10, None, True),
    ("PERSONAL_MILITAR", "Personal militar", "/personal", 20, None, True),
    ("PERSONAL_VERIFICAR", "Verificar artillero", "/personal/verificar", 21, "PERSONAL_MILITAR", True),
    ("PERSONAL_HABILITADOS", "Habilitados", "/personal/habilitados", 22, "PERSONAL_MILITAR", True),
    (
        "PERSONAL_CARGUE_EXCEL",
        "Cargue masivo por Excel",
        "/personal/cargue-excel",
        23,
        "PERSONAL_MILITAR",
        True,
    ),
    (
        "PERSONAL_CARGUE_MANUAL",
        "Registro manual de personal",
        "/personal/cargue-manual",
        24,
        "PERSONAL_MILITAR",
        True,
    ),
    # Segunda entrega: se crean inactivos.
    ("HOJAS_VIDA", "Hojas de vida", "/hojas-vida", 30, None, False),
    ("CURSOS", "Cursos académicos", "/cursos", 40, None, False),
    ("NOTAS", "Notas académicas", "/notas", 50, None, False),
    ("REENTRENAMIENTOS", "Reentrenamientos", "/reentrenamientos", 60, None, False),
    ("CERTIFICACIONES", "Certificaciones", "/certificaciones", 70, None, False),
    ("DOCTRINA", "Documentos de doctrina", "/doctrina", 80, None, False),
    # Administración.
    ("USUARIOS", "Gestión de usuarios", "/administracion/usuarios", 90, None, True),
    ("PARAMETROS_HABILITACION", "Parámetros de habilitación", "/administracion/parametros", 95, None, True),
    ("PERMISOS", "Malla de permisos", "/administracion/permisos", 100, None, True),
    ("AUDITORIA", "Auditoría", "/administracion/auditoria", 110, None, True),
    # Permiso sin menú.
    ("VER_DOCUMENTO_COMPLETO", "Ver cédula completa", None, 1000, None, True),
]

# Operaciones: A=acceder, C=crear, L=leer, U=actualizar, D=eliminar.
MALLA = {
    "ADMINISTRADOR": {
        "DASHBOARD": "AL",
        "PERSONAL_MILITAR": "AL",
        "PERSONAL_VERIFICAR": "AL",
        "PERSONAL_HABILITADOS": "AL",
        "PERSONAL_CARGUE_EXCEL": "ACL",
        "PERSONAL_CARGUE_MANUAL": "ACLU",
        "USUARIOS": "ACLUD",
        "PARAMETROS_HABILITACION": "ALU",
        "PERMISOS": "ALU",
        "AUDITORIA": "AL",  # Inmutable: nadie la edita ni la borra (HU-11).
        "VER_DOCUMENTO_COMPLETO": "AL",
    },
    "USUARIO": {
        "DASHBOARD": "AL",
        "PERSONAL_MILITAR": "AL",
        "PERSONAL_VERIFICAR": "AL",
        "PERSONAL_HABILITADOS": "AL",
        # El Comandante es USUARIO y ve la cédula completa (decisión del 2026-11-16).
        "VER_DOCUMENTO_COMPLETO": "AL",
    },
}

NOMBRES_ROL = {"ADMINISTRADOR": "Administrador", "USUARIO": "Usuario"}


SQL_ROL = text(
    "INSERT INTO esart.roles (codigo, nombre, activo) VALUES (:codigo, :nombre, true) "
    "ON CONFLICT (codigo) DO NOTHING"
)

SQL_COMPONENTE = text("""
    INSERT INTO esart.componentes (codigo, nombre, ruta_angular, orden, componente_padre_id, activo)
    VALUES (
      :codigo, :nombre, :ruta, :orden,
      (SELECT id FROM esart.componentes WHERE codigo = :padre), :activo
    )
    ON CONFLICT (codigo) DO UPDATE SET
      nombre = EXCLUDED.nombre, ruta_angular = EXCLUDED.ruta_angular, orden = EXCLUDED.orden,
      componente_padre_id = EXCLUDED.componente_padre_id, activo = EXCLUDED.activo
""")

SQL_PERMISO = text("""
    INSERT INTO esart.rol_permisos
      (rol_id, componente_id, puede_acceder, puede_crear, puede_leer, puede_actualizar, puede_eliminar)
    SELECT r.id, c.id, :acceder, :crear, :leer, :actualizar, :eliminar
    FROM esart.roles r, esart.componentes c
    WHERE r.codigo = :rol AND c.codigo = :componente
    ON CONFLICT (rol_id, componente_id) DO NOTHING
""")


def upgrade():
    conexion = op.get_bind()

    # 1. Roles: existen desde el administrador inicial, pero una base nueva puede no tenerlos.
    for codigo, nombre in NOMBRES_ROL.items():
        conexion.execute(SQL_ROL, {"codigo": codigo, "nombre": nombre})

    # 2. Componentes: primero los padres y luego los hijos (necesitan el id del padre).
    #    Si ya existían (por ejemplo, cargados a mano), se alinean con esta definición.
    for incluir_hijos in (False, True):
        for codigo, nombre, ruta, orden, padre, activo in COMPONENTES:
            if (padre is not None) == incluir_hijos:
                conexion.execute(
                    SQL_COMPONENTE,
                    {
                        "codigo": codigo,
                        "nombre": nombre,
                        "ruta": ruta,
                        "orden": orden,
                        "padre": padre,
                        "activo": activo,
                    },
                )

    # 3. Malla inicial. Si un permiso ya existe (alguien lo ajustó), se respeta.
    for codigo_rol, permisos in MALLA.items():
        for codigo_componente, letras in permisos.items():
            conexion.execute(
                SQL_PERMISO,
                {
                    "rol": codigo_rol,
                    "componente": codigo_componente,
                    "acceder": "A" in letras,
                    "crear": "C" in letras,
                    "leer": "L" in letras,
                    "actualizar": "U" in letras,
                    "eliminar": "D" in letras,
                },
            )

    # 4. La API lee la malla para armar el menú y verificar permisos. GRANT no admite
    #    parámetros: la cuenta es la constante CUENTA_APLICACION de este archivo.
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{CUENTA_APLICACION}') THEN
            GRANT SELECT ON esart.componentes, esart.rol_permisos, esart.usuario_permisos
              TO {CUENTA_APLICACION};
          END IF;
        END $$;
    """)  # noqa: S608


def downgrade():
    conexion = op.get_bind()
    codigos = [c[0] for c in COMPONENTES]
    filtro = {"codigos": codigos}
    conexion.execute(
        text(
            "DELETE FROM esart.rol_permisos WHERE componente_id IN "
            "(SELECT id FROM esart.componentes WHERE codigo = ANY(:codigos))"
        ),
        filtro,
    )
    conexion.execute(
        text(
            "DELETE FROM esart.usuario_permisos WHERE componente_id IN "
            "(SELECT id FROM esart.componentes WHERE codigo = ANY(:codigos))"
        ),
        filtro,
    )
    # Primero los hijos (tienen FK al padre con ON DELETE RESTRICT).
    conexion.execute(
        text(
            "DELETE FROM esart.componentes WHERE componente_padre_id IS NOT NULL AND codigo = ANY(:codigos)"
        ),
        {"codigos": codigos},
    )
    conexion.execute(text("DELETE FROM esart.componentes WHERE codigo = ANY(:codigos)"), {"codigos": codigos})
