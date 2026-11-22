"""
Menú del usuario para el front (sidebar y pestañas), a partir de sus permisos efectivos.

- Primer nivel: componentes padre con ruta a los que el usuario puede acceder (sidebar).
- Segundo nivel: sus hijos accesibles (pestañas dentro del módulo).
- Los componentes sin ruta (por ejemplo VER_DOCUMENTO_COMPLETO) no son menú: van solo
  en la lista de permisos.
- Excepción (S2-09): un permiso especial (sin ruta) que es hijo de un módulo da entrada a ese
  módulo aunque el usuario no tenga el padre. Ejemplo: MALLAS_CURRICULARES abre Parámetros y
  allí el usuario ve solo la pestaña de mallas.

El menú es comodidad de navegación: cada endpoint vuelve a verificar su permiso en el servidor.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.seguridad.permisos import PermisoEfectivo, obtener_permisos_efectivos

# Nombre de cada operación tal como la ve el front.
OPERACIONES = (
    ("crear", "puede_crear"),
    ("leer", "puede_leer"),
    ("actualizar", "puede_actualizar"),
    ("eliminar", "puede_eliminar"),
)


@dataclass
class ElementoMenu:
    """Una opción del menú, con lo que el usuario puede hacer en ella."""

    codigo: str
    nombre: str
    ruta: str
    operaciones: list[str]
    hijos: list["ElementoMenu"] = field(default_factory=list)


@dataclass(frozen=True)
class MenuYPermisos:
    menu: list[ElementoMenu]
    # Códigos de todos los componentes a los que puede acceder (incluidos los que no son menú).
    permisos: list[str]
    # Operaciones de cada componente accesible, también de los que no son menú (S2-09): el front
    # decide con esto qué botones mostrar, por ejemplo en la pestaña de mallas curriculares.
    operaciones: dict[str, list[str]] = field(default_factory=dict)


def _a_elemento(permiso: PermisoEfectivo) -> ElementoMenu:
    return ElementoMenu(
        codigo=permiso.codigo,
        nombre=permiso.nombre,
        ruta=permiso.ruta_angular or "",
        operaciones=[nombre for nombre, atributo in OPERACIONES if getattr(permiso, atributo)],
    )


def construir_menu(permisos_efectivos: list[PermisoEfectivo]) -> MenuYPermisos:
    """Arma el árbol de menú (ya viene ordenado por 'orden' desde la consulta)."""
    accesibles = [p for p in permisos_efectivos if p.puede_acceder]
    # Módulos a los que se entra por un permiso especial hijo (sin ruta).
    por_permiso_especial = {p.codigo_padre for p in accesibles if p.codigo_padre and not p.ruta_angular}
    padres = {
        p.codigo: _a_elemento(p)
        for p in permisos_efectivos
        if p.codigo_padre is None and p.ruta_angular and (p.puede_acceder or p.codigo in por_permiso_especial)
    }
    for permiso in accesibles:
        # Un hijo solo aparece si también puede entrar al módulo padre.
        if permiso.codigo_padre in padres and permiso.ruta_angular:
            padres[permiso.codigo_padre].hijos.append(_a_elemento(permiso))
    return MenuYPermisos(
        menu=list(padres.values()),
        permisos=[p.codigo for p in accesibles],
        operaciones={p.codigo: _a_elemento(p).operaciones for p in accesibles},
    )


async def obtener_menu_y_permisos(sesion: AsyncSession, usuario_id: int) -> MenuYPermisos:
    """Menú y permisos del usuario, listos para /api/auth/yo."""
    return construir_menu(await obtener_permisos_efectivos(sesion, usuario_id))
