"""S2-11: permisos nuevos en la malla de permisos para la malla curricular y las notas.

No se crean roles: un usuario con rol USUARIO recibe estos permisos por excepción en la
pantalla "Malla de permisos" (por ejemplo, el instructor o el Inspector de Estudios).

Componentes nuevos, activos y sin ruta ("permiso especial" en la malla): el menú no los muestra
hasta que existan sus pantallas (S2-09, S2-12, S2-13 y S2-14), pero ya se pueden asignar.
- MALLAS_CURRICULARES: ver (leer), crear versiones (crear) y editar (actualizar) mallas.
- NOTAS_CARGA: el instructor descarga y sube las notas de SUS materias.
- NOTAS_REVISION: el Inspector de Estudios aprueba o devuelve las entregas de notas.
- CONSEJO_ACADEMICO: registrar la decisión del Consejo con quien pierde una habilitación.

ADMINISTRADOR los tiene todos (su política es fija); USUARIO ninguno por defecto.
"""

from alembic import op
from sqlalchemy import text

revision = "p0018_permisos_notas"
down_revision = "p0017_malla_curricular"
branch_labels = None
depends_on = None

# (codigo, nombre, orden): el orden los ubica junto a su módulo en la malla de permisos.
COMPONENTES = (
    ("NOTAS_CARGA", "Carga de notas (instructor)", 51),
    ("NOTAS_REVISION", "Revisión de notas (Inspector de Estudios)", 52),
    ("CONSEJO_ACADEMICO", "Consejo Académico", 53),
    ("MALLAS_CURRICULARES", "Mallas curriculares", 96),
)


def upgrade():
    conexion = op.get_bind()
    for codigo, nombre, orden in COMPONENTES:
        conexion.execute(
            text("""
                INSERT INTO esart.componentes
                  (codigo, nombre, ruta_angular, orden, componente_padre_id, activo)
                VALUES (:codigo, :nombre, NULL, :orden, NULL, true)
                ON CONFLICT (codigo) DO NOTHING
            """),
            {"codigo": codigo, "nombre": nombre, "orden": orden},
        )
    # Fila explícita del ADMINISTRADOR (su política ya es "todo"; así la malla queda coherente).
    conexion.execute(
        text("""
            INSERT INTO esart.rol_permisos
              (rol_id, componente_id, puede_acceder, puede_crear, puede_leer, puede_actualizar,
               puede_eliminar)
            SELECT r.id, c.id, true, true, true, true, true
            FROM esart.roles r CROSS JOIN esart.componentes c
            WHERE r.codigo = 'ADMINISTRADOR' AND c.codigo = ANY(:codigos)
            ON CONFLICT (rol_id, componente_id) DO NOTHING
        """),
        {"codigos": [codigo for codigo, _, _ in COMPONENTES]},
    )


def downgrade():
    conexion = op.get_bind()
    filtro = {"codigos": [codigo for codigo, _, _ in COMPONENTES]}
    for tabla in ("usuario_permisos", "rol_permisos"):
        conexion.execute(
            text(
                f"DELETE FROM esart.{tabla} WHERE componente_id IN "  # noqa: S608
                "(SELECT id FROM esart.componentes WHERE codigo = ANY(:codigos))"
            ),
            filtro,
        )
    conexion.execute(text("DELETE FROM esart.componentes WHERE codigo = ANY(:codigos)"), filtro)
