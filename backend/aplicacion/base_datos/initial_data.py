"""
Script de datos iniciales (seed) para Vulcano 3.0.

Carga los catalogos base que el sistema necesita para funcionar:
    - 2 roles del sistema: ADMINISTRADOR y USUARIO
    - Catalogo de permisos granulares (33 permisos en 10 modulos)
    - Estados operacionales de sistemas de artilleria
    - Estados logisticos de sistemas de artilleria
    - Tipos de unidad militar
    - Usuario administrador de prueba

Uso:
    python seeds/initial_data.py

IMPORTANTE: Ejecutar DESPUES de alembic upgrade head.
"""

import asyncio
import sys
from pathlib import Path

# Agregar la raíz del proyecto al path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent))

import bcrypt
from app.configuracion import configuracion
from app.db.models.permisos import Permiso
from app.db.models.roles import Rol
from app.db.models.sistemas import EstadoLogistico, EstadoOperacional
from app.db.models.unidades import TipoUnidad, UnidadMilitar
from app.db.models.usuarios import Usuario
from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select


def hashear_password(password: str) -> str:
    """Genera un hash bcrypt de la contraseña.

    Args:
        password: Contraseña en texto plano.

    Returns:
        str: Hash bcrypt listo para almacenar en la BD.
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# =============================================================================
# Datos a sembrar
# =============================================================================

ROLES = [
    {
        "codigo": "ADMINISTRADOR",
        "nombre": "Administrador del Sistema",
        "descripcion": (
            "Acceso total a la plataforma sin restricciones. "
            "Gestiona usuarios, asigna permisos, configura el sistema y accede a todos los modulos."
        ),
    },
    {
        "codigo": "USUARIO",
        "nombre": "Usuario del Sistema",
        "descripcion": (
            "Acceso controlado por los permisos que el administrador asigne individualmente. "
            "Sin permisos asignados, el usuario solo puede autenticarse."
        ),
    },
]

PERMISOS = [
    # ── Sistemas ──────────────────────────────────────────────────────────────
    {
        "codigo": "gestionar_sistemas",
        "nombre": "Gestionar sistemas de artilleria",
        "modulo": "sistemas",
        "descripcion": "Crear, editar y dar de baja sistemas de artilleria.",
    },
    {
        "codigo": "ver_sistemas",
        "nombre": "Ver sistemas de artilleria",
        "modulo": "sistemas",
        "descripcion": "Consultar la ficha tecnica de cada sistema.",
    },
    {
        "codigo": "estado_ubicacion",
        "nombre": "Estado y ubicacion de sistemas",
        "modulo": "sistemas",
        "descripcion": "Ver el estado operacional y la posicion geografica de cada sistema en el mapa.",
    },
    {
        "codigo": "gestionar_operadores",
        "nombre": "Gestionar operadores de sistemas",
        "modulo": "sistemas",
        "descripcion": "Asignar y cambiar los soldados operadores de cada sistema de artilleria.",
    },
    # ── Graficacion ───────────────────────────────────────────────────────────
    {
        "codigo": "graficar_blancos",
        "nombre": "Graficacion de blancos y sistemas",
        "modulo": "graficacion",
        "descripcion": "Graficar blancos, rangos efectivos de fuego y zonas de impacto sobre el mapa.",
    },
    {
        "codigo": "graficar_rutas",
        "nombre": "Graficacion de rutas de movimiento",
        "modulo": "graficacion",
        "descripcion": "Dibujar y consultar rutas de desplazamiento de sistemas de artilleria.",
    },
    {
        "codigo": "graficar_plan_operacion",
        "nombre": "Graficacion de planes de operacion",
        "modulo": "graficacion",
        "descripcion": "Dibujar planes de operacion sobre el mapa con sistemas asignados.",
    },
    # ── Balistica ─────────────────────────────────────────────────────────────
    {
        "codigo": "calculos_balisticos",
        "nombre": "Calculos balisticos",
        "modulo": "balistica",
        "descripcion": "Ejecutar calculos de tiro: elevacion, deriva, carga y correcciones.",
    },
    {
        "codigo": "configurar_tablas_balisticas",
        "nombre": "Configurar tablas balisticas",
        "modulo": "balistica",
        "descripcion": "Gestionar tablas balisticas y parametros de municion por tipo de sistema.",
    },
    # ── Misiones ──────────────────────────────────────────────────────────────
    {
        "codigo": "misiones_fuego",
        "nombre": "Misiones de fuego",
        "modulo": "misiones",
        "descripcion": "Crear, ejecutar y consultar misiones de fuego de artilleria.",
    },
    {
        "codigo": "aprobar_mision",
        "nombre": "Aprobar ordenes de fuego",
        "modulo": "misiones",
        "descripcion": "Aprobar o rechazar ordenes de fuego (nivel comando).",
    },
    {
        "codigo": "cancelar_mision",
        "nombre": "Cancelar mision en ejecucion",
        "modulo": "misiones",
        "descripcion": "Cancelar una mision de fuego que ya se encuentra en ejecucion.",
    },
    # ── Municion ──────────────────────────────────────────────────────────────
    {
        "codigo": "gestionar_municion",
        "nombre": "Gestionar municion",
        "modulo": "municion",
        "descripcion": "Registrar consumo, altas y bajas de municion. Gestionar stock.",
    },
    {
        "codigo": "ver_municion",
        "nombre": "Ver stock de municion",
        "modulo": "municion",
        "descripcion": "Consultar existencias de municion y alertas de minimos.",
    },
    # ── Inventario ────────────────────────────────────────────────────────────
    {
        "codigo": "gestionar_inventario",
        "nombre": "Gestionar inventario",
        "modulo": "inventario",
        "descripcion": "Administrar repuestos, insumos y partes de los sistemas.",
    },
    {
        "codigo": "ver_inventario",
        "nombre": "Ver inventario",
        "modulo": "inventario",
        "descripcion": "Consultar el inventario de repuestos e insumos.",
    },
    # ── Mantenimiento ─────────────────────────────────────────────────────────
    {
        "codigo": "ver_mantenimiento",
        "nombre": "Ver mantenimiento",
        "modulo": "mantenimiento",
        "descripcion": "Consultar historial de mantenimientos realizados y proximas fechas programadas.",
    },
    {
        "codigo": "registrar_mantenimiento",
        "nombre": "Registrar mantenimiento",
        "modulo": "mantenimiento",
        "descripcion": "Cargar la ejecucion de un mantenimiento: fecha, tipo y nivel realizado.",
    },
    {
        "codigo": "programar_mantenimiento",
        "nombre": "Programar mantenimiento",
        "modulo": "mantenimiento",
        "descripcion": "Agendar fechas de proximos mantenimientos preventivos.",
    },
    # ── Infografia ────────────────────────────────────────────────────────────
    {
        "codigo": "infografia_sistema",
        "nombre": "Infografia completa del sistema desplegado",
        "modulo": "infografia",
        "descripcion": (
            "Ver la tarjeta completa del sistema al hacer clic en el mapa: comandante, "
            "operadores, municion, disparos, mantenimiento y certificaciones."
        ),
    },
    {
        "codigo": "ver_infografia_personal",
        "nombre": "Ver personal en infografia (ESART)",
        "modulo": "infografia",
        "descripcion": (
            "Ver unicamente la seccion de personal y certificaciones en la inf" "ografia del sistema."
        ),
    },
    # ── Historial ─────────────────────────────────────────────────────────────
    {
        "codigo": "historial_sistemas",
        "nombre": "Historial de sistemas",
        "modulo": "historial",
        "descripcion": "Consultar historial de movimientos, mantenimientos y disparos realizados.",
    },
    {
        "codigo": "exportar_historial",
        "nombre": "Exportar historial",
        "modulo": "historial",
        "descripcion": "Descargar el historial de sistemas en formato Excel o PDF.",
    },
    # ── Unidades ──────────────────────────────────────────────────────────────
    {
        "codigo": "gestionar_unidades",
        "nombre": "Gestionar unidades militares",
        "modulo": "unidades",
        "descripcion": (
            "Registrar nuevas unidades militares en el sistema (batallones, baterias, etc.). "
            "Util para agregar unidades a las que se asignan sistemas de artilleria."
        ),
    },
    # ── ESART ─────────────────────────────────────────────────────────────────
    {
        "codigo": "modulo_esart",
        "nombre": "Modulo ESART completo",
        "modulo": "esart",
        "descripcion": (
            "Acceso total al modulo de la Escuela de Artilleria: cursos, instructores, "
            "alumnos, malla curricular y reentrenamientos."
        ),
    },
    {
        "codigo": "ver_personal_esart",
        "nombre": "Ver personal ESART",
        "modulo": "esart",
        "descripcion": "Consultar personal y certificaciones de la ESART sin poder modificar.",
    },
    {
        "codigo": "gestionar_doctrina",
        "nombre": "Gestionar documentos de doctrina",
        "modulo": "esart",
        "descripcion": (
            "Subir, editar y desactivar documentos PDF de doctrina artillera "
            "(balistica, protocolos, manuales ejercito, doctrina ejercito, manuales sistemas)."
        ),
    },
    {
        "codigo": "ver_doctrina",
        "nombre": "Ver y descargar documentos de doctrina",
        "modulo": "esart",
        "descripcion": "Consultar y descargar los documentos PDF de doctrina artillera disponibles.",
    },
    # ── Reportes ──────────────────────────────────────────────────────────────
    {
        "codigo": "reportes_enviar_ver",
        "nombre": "Reportes: enviar, recibir y ver",
        "modulo": "reportes",
        "descripcion": "Acceso completo al modulo de reportes: enviar, recibir y consultar informes.",
    },
    {
        "codigo": "reportes_solo_enviar",
        "nombre": "Reportes: solo enviar",
        "modulo": "reportes",
        "descripcion": "Enviar informes unicamente, sin acceso a los recibidos.",
    },
    {
        "codigo": "reportes_solo_ver",
        "nombre": "Reportes: solo ver",
        "modulo": "reportes",
        "descripcion": "Consultar informes recibidos sin poder enviar.",
    },
    {
        "codigo": "reportes_exportar",
        "nombre": "Exportar reportes",
        "modulo": "reportes",
        "descripcion": "Generar y descargar reportes en PDF o Excel.",
    },
    # ── Auditoria ─────────────────────────────────────────────────────────────
    {
        "codigo": "ver_auditoria",
        "nombre": "Ver auditoria del sistema",
        "modulo": "auditoria",
        "descripcion": "Consultar el log de actividad: quien hizo que accion y cuando.",
    },
    # ── Dashboard ─────────────────────────────────────────────────────────────
    {
        "codigo": "ver_dashboard",
        "nombre": "Ver panel principal de metricas",
        "modulo": "dashboard",
        "descripcion": "Acceder al panel general con indicadores del teatro de operaciones.",
    },
    # ── Alertas ───────────────────────────────────────────────────────────────
    {
        "codigo": "configurar_alertas",
        "nombre": "Configurar alertas del sistema",
        "modulo": "alertas",
        "descripcion": (
            "Definir umbrales de alerta: dias sin mantenimiento, stock minimo," " disparos acumulados."
        ),
    },
    {
        "codigo": "recibir_alertas",
        "nombre": "Recibir notificaciones y alertas",
        "modulo": "alertas",
        "descripcion": "Recibir notificaciones automaticas cuando se superen los umbrales configurados.",
    },
]

ESTADOS_OPERACIONALES = [
    {"codigo": "EN_OPERACION", "nombre": "En Operacion"},
    {"codigo": "EN_BATALLON", "nombre": "En Batallon"},
    {"codigo": "PENDIENTE_BAJA", "nombre": "Pendiente de Baja"},
    {"codigo": "DADO_BAJA", "nombre": "Dado de Baja"},
]

ESTADOS_LOGISTICOS = [
    {"codigo": "SMI", "nombre": "Sistema en Mantenimiento Imprevisto"},
    {"codigo": "SMP", "nombre": "Sistema en Mantenimiento Programado"},
    {"codigo": "SNLA", "nombre": "Sistema No Listo por Abastecimiento"},
    {"codigo": "SCL", "nombre": "Sistema Completamente Listo"},
    {"codigo": "SFS", "nombre": "Sistema Fuera de Servicio"},
    {"codigo": "SPB", "nombre": "Sistema en Proceso de Baja"},
    {"codigo": "SDB", "nombre": "Sistema Dado de Baja"},
    {"codigo": "SID", "nombre": "Sistema con Duplicidad de Informacion"},
]

TIPOS_UNIDAD = [
    {"codigo": "DIV", "nombre": "División"},
    {"codigo": "BR", "nombre": "Brigada"},
    {"codigo": "BAACA", "nombre": "Batallón de Artillería"},
    {"codigo": "BATAR", "nombre": "Batería de Artillería"},
    {"codigo": "CECFU", "nombre": "Centro de Coordinación de Fuegos"},
    {"codigo": "CEDOC", "nombre": "Centro de Educación y Doctrina"},
    {"codigo": "CEM", "nombre": "Centro de Educación Militar"},
    {"codigo": "BAADA", "nombre": "Batallón de Artillería de Defensa Aérea"},
    {"codigo": "ESART", "nombre": "Escuela de Artillería"},
]

# lon, lat en WGS84 (EPSG:4326) — coordenadas aproximadas de la sede de cada unidad.
# Actualizar con coordenadas exactas cuando se disponga de ellas.
DIVISIONES = [
    {
        "codigo": "DIV01",
        "nombre": "Primera División",
        "tipo": "DIV",
        "lon": -74.2110,
        "lat": 11.2408,
    },  # Santa Marta
    {
        "codigo": "DIV02",
        "nombre": "Segunda División",
        "tipo": "DIV",
        "lon": -73.1198,
        "lat": 7.1254,
    },  # Bucaramanga
    {
        "codigo": "DIV03",
        "nombre": "Tercera División",
        "tipo": "DIV",
        "lon": -76.6147,
        "lat": 2.4448,
    },  # Popayán
    {
        "codigo": "DIV04",
        "nombre": "Cuarta División",
        "tipo": "DIV",
        "lon": -73.6366,
        "lat": 4.1420,
    },  # Villavicencio
    {"codigo": "DIV05", "nombre": "Quinta División", "tipo": "DIV", "lon": -75.2322, "lat": 4.4389},  # Ibagué
    {
        "codigo": "DIV06",
        "nombre": "Sexta División",
        "tipo": "DIV",
        "lon": -75.6063,
        "lat": 1.6144,
    },  # Florencia
    {
        "codigo": "DIV07",
        "nombre": "Séptima División",
        "tipo": "DIV",
        "lon": -75.5812,
        "lat": 6.2442,
    },  # Medellín
    {"codigo": "DIV08", "nombre": "Octava División", "tipo": "DIV", "lon": -72.3959, "lat": 5.3378},  # Yopal
    {
        "codigo": "DIVFE",
        "nombre": "División de Fuerzas Especiales",
        "tipo": "DIV",
        "lon": -74.0721,
        "lat": 4.7110,
    },  # Bogotá
    {
        "codigo": "DAAVA",
        "nombre": "División de Aviación y Asalto Aéreo",
        "tipo": "DIV",
        "lon": -74.0721,
        "lat": 4.7110,
    },  # Bogotá
    {
        "codigo": "FUTOM",
        "nombre": "Fuerza de Tarea Omega",
        "tipo": "DIV",
        "lon": -75.4353,
        "lat": 1.4836,
    },  # La Montañita
    {
        "codigo": "CEDOC",
        "nombre": "Centro de Educación y Doctrina",
        "tipo": "CEDOC",
        "lon": -74.0721,
        "lat": 4.7110,
    },  # Bogotá
]

BRIGADAS = [
    {
        "codigo": "BR01",
        "nombre": "Primera Brigada",
        "tipo": "BR",
        "padre": "DIV05",
        "lon": -73.3578,
        "lat": 5.5446,
    },  # Tunja
    {
        "codigo": "BR03",
        "nombre": "Tercera Brigada",
        "tipo": "BR",
        "padre": "DIV03",
        "lon": -76.5319,
        "lat": 3.4516,
    },  # Cali
    {
        "codigo": "BR04",
        "nombre": "Cuarta Brigada",
        "tipo": "BR",
        "padre": "DIV07",
        "lon": -75.5812,
        "lat": 6.2442,
    },  # Medellín
    {
        "codigo": "BR05",
        "nombre": "Quinta Brigada",
        "tipo": "BR",
        "padre": "DIV02",
        "lon": -73.1198,
        "lat": 7.1254,
    },  # Bucaramanga
    {
        "codigo": "BR08",
        "nombre": "Octava Brigada",
        "tipo": "BR",
        "padre": "DIV05",
        "lon": -75.6811,
        "lat": 4.5339,
    },  # Armenia
    {
        "codigo": "BR09",
        "nombre": "Novena Brigada",
        "tipo": "BR",
        "padre": "DIV05",
        "lon": -75.2819,
        "lat": 2.9273,
    },  # Neiva
    {
        "codigo": "BR10",
        "nombre": "Décima Brigada",
        "tipo": "BR",
        "padre": "DIV01",
        "lon": -73.2532,
        "lat": 10.4631,
    },  # Valledupar
    {
        "codigo": "BR13",
        "nombre": "Décimo Tercera Brigada",
        "tipo": "BR",
        "padre": "DIV05",
        "lon": -74.0721,
        "lat": 4.7110,
    },  # Bogotá
    {
        "codigo": "BR18",
        "nombre": "Décimo Octava Brigada",
        "tipo": "BR",
        "padre": "DIV08",
        "lon": -70.7587,
        "lat": 7.0832,
    },  # Arauca
    {
        "codigo": "BR27",
        "nombre": "Vigésimo Séptima Brigada",
        "tipo": "BR",
        "padre": "DIV06",
        "lon": -76.6472,
        "lat": 1.1521,
    },  # Mocoa
    {
        "codigo": "BR30",
        "nombre": "Trigésima Brigada",
        "tipo": "BR",
        "padre": "DIV02",
        "lon": -72.5078,
        "lat": 7.8939,
    },  # Cúcuta
    {
        "codigo": "CEMIL",
        "nombre": "Centro de Educación Militar",
        "tipo": "CEM",
        "padre": "CEDOC",
        "lon": -74.0721,
        "lat": 4.7110,
    },  # Bogotá
]

# Coordenadas en WGS84: POINT(lon lat). Las fuente son lat,lon — se invierten al construir el WKT.
BATALLONES_ARTILLERIA = [
    {
        "codigo": "BAACA1",
        "nombre": "Batallón de Artillería de Campaña N°1",
        "tipo": "BAACA",
        "padre": "BR01",
        "lon": -72.95869722,
        "lat": 5.676441667,
    },
    {
        "codigo": "BAACA2",
        "nombre": "Batallón de Artillería de Campaña N°2",
        "tipo": "BAACA",
        "padre": "BR10",
        "lon": -73.27576389,
        "lat": 10.46263333,
    },
    {
        "codigo": "BAACA3",
        "nombre": "Batallón de Artillería de Campaña N°3",
        "tipo": "BAACA",
        "padre": "BR03",
        "lon": -76.28934722,
        "lat": 3.892013889,
    },
    {
        "codigo": "BAACA4",
        "nombre": "Batallón de Artillería de Campaña N°4",
        "tipo": "BAACA",
        "padre": "BR04",
        "lon": -75.54786389,
        "lat": 6.234122222,
    },
    {
        "codigo": "BAACA5",
        "nombre": "Batallón de Artillería de Campaña N°5",
        "tipo": "BAACA",
        "padre": "BR05",
        "lon": -73.26530000,
        "lat": 6.46515000,
    },
    {
        "codigo": "BAACA6",
        "nombre": "Batallón de Artillería de Campaña N°6",
        "tipo": "BAACA",
        "padre": "BR05",
        "lon": -73.85130000,
        "lat": 7.06250000,
    },
    {
        "codigo": "BAACA8",
        "nombre": "Batallón de Artillería de Campaña N°8",
        "tipo": "BAACA",
        "padre": "BR08",
        "lon": -75.72368889,
        "lat": 4.815508333,
    },
    {
        "codigo": "BAACA9",
        "nombre": "Batallón de Artillería de Campaña N°9",
        "tipo": "BAACA",
        "padre": "BR09",
        "lon": -75.28198333,
        "lat": 2.943336111,
    },
    {
        "codigo": "BAACA10",
        "nombre": "Batallón de Artillería de Campaña N°10",
        "tipo": "BAACA",
        "padre": "BR10",
        "lon": -72.89158611,
        "lat": 10.88464167,
    },
    {
        "codigo": "BAACA13",
        "nombre": "Batallón de Artillería de Campaña N°13",
        "tipo": "BAACA",
        "padre": "BR13",
        "lon": -74.12137500,
        "lat": 4.548575000,
    },
    {
        "codigo": "BAACA18",
        "nombre": "Batallón de Artillería de Campaña N°18",
        "tipo": "BAACA",
        "padre": "BR18",
        "lon": -71.35258611,
        "lat": 6.685847222,
    },
    {
        "codigo": "BAACA27",
        "nombre": "Batallón de Artillería de Campaña N°27",
        "tipo": "BAACA",
        "padre": "BR27",
        "lon": -76.56973611,
        "lat": 0.598483333,
    },
    {
        "codigo": "BAACA30",
        "nombre": "Batallón de Artillería de Campaña N°30",
        "tipo": "BAACA",
        "padre": "BR30",
        "lon": -72.50741944,
        "lat": 7.862433333,
    },
    {
        "codigo": "BAADA1",
        "nombre": "Batallón de Artillería de Defensa Aérea N°1",
        "tipo": "BAADA",
        "padre": "BR10",
        "lon": -72.59993889,
        "lat": 11.15399444,
    },
    {
        "codigo": "BAADA2",
        "nombre": "Batallón de Artillería de Defensa Aérea N°2",
        "tipo": "BAADA",
        "padre": "BR05",
        "lon": -73.86629444,
        "lat": 7.06250000,
    },
    {
        "codigo": "ESART",
        "nombre": "Escuela de Artillería",
        "tipo": "ESART",
        "padre": "CEMIL",
        "lon": -74.12169444,
        "lat": 4.548711111,
    },
]


# =============================================================================
# Funciones de seed
# =============================================================================


async def sembrar_roles(sesion: AsyncSession) -> dict[str, int]:
    """Inserta los roles del sistema si no existen.

    Returns:
        dict: Mapa {codigo: id} de los roles insertados/encontrados.
    """
    mapa_roles = {}
    for datos in ROLES:
        resultado = await sesion.execute(select(Rol).where(Rol.codigo == datos["codigo"]))
        rol = resultado.scalar_one_or_none()
        if rol is None:
            rol = Rol(**datos)
            sesion.add(rol)
            await sesion.flush()
            print(f"  [+] Rol creado: {datos['codigo']}")
        else:
            print(f"  [=] Rol ya existe: {datos['codigo']}")
        mapa_roles[datos["codigo"]] = rol.id
    return mapa_roles


async def sembrar_permisos(sesion: AsyncSession) -> None:
    """Inserta el catalogo de permisos si no existen.

    Es idempotente: si el permiso ya existe no lo duplica.
    Permite agregar nuevos permisos al catalogo en futuras versiones
    sin afectar los permisos ya asignados a usuarios.
    """
    nuevos = 0
    for datos in PERMISOS:
        resultado = await sesion.execute(select(Permiso).where(Permiso.codigo == datos["codigo"]))
        if resultado.scalar_one_or_none() is None:
            sesion.add(Permiso(**datos))
            nuevos += 1
            print(f"  [+] Permiso creado: {datos['codigo']} ({datos['modulo']})")
        else:
            print(f"  [=] Permiso ya existe: {datos['codigo']}")
    if nuevos:
        await sesion.flush()
        print(f"  → {nuevos} permiso(s) nuevos agregados al catalogo.")


async def sembrar_estados_operacionales(sesion: AsyncSession) -> None:
    """Inserta los estados operacionales base si no existen."""
    for datos in ESTADOS_OPERACIONALES:
        resultado = await sesion.execute(
            select(EstadoOperacional).where(EstadoOperacional.codigo == datos["codigo"])
        )
        if resultado.scalar_one_or_none() is None:
            sesion.add(EstadoOperacional(**datos))
            print(f"  [+] Estado operacional: {datos['codigo']}")
        else:
            print(f"  [=] Ya existe: {datos['codigo']}")


async def sembrar_estados_logisticos(sesion: AsyncSession) -> None:
    """Inserta los estados logísticos base si no existen."""
    for datos in ESTADOS_LOGISTICOS:
        resultado = await sesion.execute(
            select(EstadoLogistico).where(EstadoLogistico.codigo == datos["codigo"])
        )
        if resultado.scalar_one_or_none() is None:
            sesion.add(EstadoLogistico(**datos))
            print(f"  [+] Estado logístico: {datos['codigo']}")
        else:
            print(f"  [=] Ya existe: {datos['codigo']}")


async def sembrar_tipos_unidad(sesion: AsyncSession) -> None:
    """Inserta los tipos de unidad militar base si no existen."""
    for datos in TIPOS_UNIDAD:
        resultado = await sesion.execute(select(TipoUnidad).where(TipoUnidad.codigo == datos["codigo"]))
        if resultado.scalar_one_or_none() is None:
            sesion.add(TipoUnidad(**datos))
            print(f"  [+] Tipo de unidad: {datos['codigo']}")
        else:
            print(f"  [=] Ya existe: {datos['codigo']}")


async def sembrar_divisiones(sesion: AsyncSession) -> None:
    """Inserta las divisiones del Ejercito Nacional si no existen."""
    res_tipos = await sesion.execute(select(TipoUnidad))
    mapa_tipos = {t.codigo: t.id for t in res_tipos.scalars().all()}

    for datos in DIVISIONES:
        resultado = await sesion.execute(select(UnidadMilitar).where(UnidadMilitar.codigo == datos["codigo"]))
        if resultado.scalar_one_or_none() is None:
            unidad = UnidadMilitar(
                tipo_unidad_id=mapa_tipos[datos["tipo"]],
                unidad_padre_id=None,
                codigo=datos["codigo"],
                nombre=datos["nombre"],
                ubicacion=WKTElement(f"POINT({datos['lon']} {datos['lat']})", srid=4326),
                activo=True,
            )
            sesion.add(unidad)
            print(f"  [+] {datos['codigo']}: {datos['nombre']}")
        else:
            print(f"  [=] Ya existe: {datos['codigo']}")


async def sembrar_brigadas_y_cedoc(sesion: AsyncSession) -> None:
    """Inserta brigadas y unidades CEDOC/CEMIL si no existen.

    Requiere que las divisiones ya hayan sido insertadas y flusheadas
    para poder resolver los unidad_padre_id por codigo.
    """
    res_tipos = await sesion.execute(select(TipoUnidad))
    mapa_tipos = {t.codigo: t.id for t in res_tipos.scalars().all()}

    res_unidades = await sesion.execute(select(UnidadMilitar.codigo, UnidadMilitar.id))
    mapa_unidades = {codigo: id_ for codigo, id_ in res_unidades.all()}

    for datos in BRIGADAS:
        resultado = await sesion.execute(select(UnidadMilitar).where(UnidadMilitar.codigo == datos["codigo"]))
        if resultado.scalar_one_or_none() is None:
            padre_id = mapa_unidades.get(datos["padre"]) if datos["padre"] else None
            unidad = UnidadMilitar(
                tipo_unidad_id=mapa_tipos[datos["tipo"]],
                unidad_padre_id=padre_id,
                codigo=datos["codigo"],
                nombre=datos["nombre"],
                ubicacion=WKTElement(f"POINT({datos['lon']} {datos['lat']})", srid=4326),
                activo=True,
            )
            sesion.add(unidad)
            print(f"  [+] {datos['codigo']}: {datos['nombre']}")
        else:
            print(f"  [=] Ya existe: {datos['codigo']}")


async def sembrar_batallones_artilleria(sesion: AsyncSession) -> None:
    """Inserta los batallones de artilleria si no existen.

    Requiere que las brigadas ya hayan sido insertadas y flusheadas.
    """
    res_tipos = await sesion.execute(select(TipoUnidad))
    mapa_tipos = {t.codigo: t.id for t in res_tipos.scalars().all()}

    res_unidades = await sesion.execute(select(UnidadMilitar.codigo, UnidadMilitar.id))
    mapa_unidades = {codigo: id_ for codigo, id_ in res_unidades.all()}

    for datos in BATALLONES_ARTILLERIA:
        resultado = await sesion.execute(select(UnidadMilitar).where(UnidadMilitar.codigo == datos["codigo"]))
        if resultado.scalar_one_or_none() is None:
            padre_id = mapa_unidades.get(datos["padre"]) if datos["padre"] else None
            unidad = UnidadMilitar(
                tipo_unidad_id=mapa_tipos[datos["tipo"]],
                unidad_padre_id=padre_id,
                codigo=datos["codigo"],
                nombre=datos["nombre"],
                ubicacion=WKTElement(f"POINT({datos['lon']} {datos['lat']})", srid=4326),
                activo=True,
            )
            sesion.add(unidad)
            print(f"  [+] {datos['codigo']}: {datos['nombre']}")
        else:
            print(f"  [=] Ya existe: {datos['codigo']}")


async def sembrar_usuario_admin(sesion: AsyncSession, rol_admin_id: int) -> None:
    """Crea el usuario administrador de prueba si no existe.

    Args:
        sesion: Sesion de base de datos activa.
        rol_admin_id: ID del rol ADMINISTRADOR.
    """
    resultado = await sesion.execute(select(Usuario).where(Usuario.documentos_identidad == "1000000001"))
    if resultado.scalar_one_or_none() is not None:
        print("  [=] Usuario admin ya existe")
        return

    password_hash = hashear_password("Vulcano2026*")
    admin = Usuario(
        rol_id=rol_admin_id,
        grado="CR",
        nombres="Administrador",
        apellidos="Sistema Vulcano",
        documentos_identidad="1000000001",
        email_institucional="admin@ejercito.mil.co",
        password_hash=password_hash,
        activo=True,
    )
    sesion.add(admin)
    print("  [+] Usuario admin creado: doc=1000000001 / pass=Vulcano2026*")
    print("      ⚠️  CAMBIAR LA CONTRASEÑA EN PRODUCCIÓN")


async def ejecutar_seeds() -> None:
    """Punto de entrada principal — ejecuta todos los seeds en orden."""
    motor = create_async_engine(configuracion.DATABASE_URL, echo=False)
    FabricaSesion = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)

    print("\n" + "=" * 60)
    print("  Vulcano 3.0 — Cargando datos iniciales")
    print("=" * 60)

    async with FabricaSesion() as sesion:
        async with sesion.begin():
            print("\n[1/7] Roles del sistema...")
            mapa_roles = await sembrar_roles(sesion)

            print("\n[2/7] Catalogo de permisos...")
            await sembrar_permisos(sesion)

            print("\n[3/7] Estados operacionales...")
            await sembrar_estados_operacionales(sesion)

            print("\n[4/7] Estados logisticos...")
            await sembrar_estados_logisticos(sesion)

            print("\n[5/7] Tipos de unidad...")
            await sembrar_tipos_unidad(sesion)

            print("\n[6/8] Divisiones del Ejercito Nacional...")
            await sembrar_divisiones(sesion)
            await sesion.flush()  # necesario para que los IDs de divisiones estén disponibles

            print("\n[7/9] Brigadas y unidades CEDOC...")
            await sembrar_brigadas_y_cedoc(sesion)
            await sesion.flush()  # necesario para que los IDs de brigadas estén disponibles

            print("\n[8/9] Batallones de artilleria...")
            await sembrar_batallones_artilleria(sesion)

            print("\n[9/9] Usuario administrador...")
            await sembrar_usuario_admin(sesion, mapa_roles["ADMINISTRADOR"])

    await motor.dispose()

    print("\n" + "=" * 60)
    print("  ✅ Seeds completados exitosamente")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(ejecutar_seeds())
