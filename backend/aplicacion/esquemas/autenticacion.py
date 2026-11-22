"""Esquemas de entrada y salida de /api/auth (contrato de API, §2)."""

from pydantic import BaseModel, ConfigDict, Field

from aplicacion.seguridad.contrasenas import LONGITUD_MAXIMA_CONTRASENA_BYTES

LONGITUD_MAXIMA_NOMBRE_USUARIO = 80


class SolicitudInicioSesion(BaseModel):
    """Cuerpo de POST /api/auth/login."""

    # extra="forbid": un campo desconocido se rechaza en vez de ignorarse en silencio.
    model_config = ConfigDict(extra="forbid")

    # Mismo largo que esart_ref.usuarios.usuario (VARCHAR(80)).
    nombre_usuario: str = Field(min_length=3, max_length=LONGITUD_MAXIMA_NOMBRE_USUARIO)
    # El límite real de bcrypt es en bytes y lo controla verificar_contrasena;
    # aquí solo se corta lo absurdamente largo antes de procesarlo.
    contrasena: str = Field(min_length=1, max_length=LONGITUD_MAXIMA_CONTRASENA_BYTES)
    # El captcha se exige a partir del 3.er fallo (HU-07); por ahora es opcional.
    captcha_id: str | None = Field(default=None, max_length=64)
    captcha_respuesta: str | None = Field(default=None, max_length=20)


class UsuarioEnSesion(BaseModel):
    """Datos públicos del usuario. Nunca incluye el hash ni el token."""

    nombre_usuario: str
    nombre_completo: str
    rol: str
    # True: la contraseña es temporal y el front lleva a "Cambiar contraseña" antes que a nada.
    requiere_cambio_contrasena: bool = False


class RespuestaInicioSesion(BaseModel):
    """Cuerpo de la respuesta 200 del login. El JWT va en la cookie, no aquí."""

    usuario: UsuarioEnSesion
    expira_por_inactividad_segundos: int


class SolicitudCambioContrasena(BaseModel):
    """Cuerpo de POST /api/auth/cambiar-contrasena. Las reglas de la nueva las valida el servicio."""

    model_config = ConfigDict(extra="forbid")

    contrasena_actual: str = Field(min_length=1, max_length=LONGITUD_MAXIMA_CONTRASENA_BYTES)
    contrasena_nueva: str = Field(min_length=1, max_length=LONGITUD_MAXIMA_CONTRASENA_BYTES)


class ElementoMenu(BaseModel):
    """Opción del menú: módulo del sidebar (con sus pestañas en 'hijos')."""

    codigo: str
    nombre: str
    ruta: str
    # Lo que el usuario puede hacer ahí: "crear", "leer", "actualizar", "eliminar".
    operaciones: list[str]
    hijos: list["ElementoMenu"] = []


class RespuestaUsuarioActual(UsuarioEnSesion):
    """Cuerpo de GET /api/auth/yo (contrato §2)."""

    # Códigos de los componentes a los que puede acceder (malla de permisos, HU-09).
    permisos: list[str]
    # Menú ya filtrado por permisos: el front lo dibuja tal cual.
    menu: list[ElementoMenu]
    # Operaciones de cada componente accesible, incluidos los permisos sin menú (S2-09).
    operaciones: dict[str, list[str]] = {}
    expira_por_inactividad_segundos: int
