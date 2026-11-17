"""
Lógica de inicio de sesión, sesión actual y administrador inicial, sobre el modelo de HU-04:

- esart_ref.usuarios: 'usuario' (único sin distinguir mayúsculas) y 'contrasena_hash' (bcrypt).
- Roles en esart.usuario_roles (un usuario puede tener varios). Se informa uno solo:
  ADMINISTRADOR si lo tiene; si no, USUARIO. Sin ningún rol activo no puede entrar.
- Nombre visible: el del militar en esart.personal_militar (por documento_identidad).

Las rutas no verifican contraseñas ni consultan usuarios: llaman a este servicio.
El control persistente 3/7/3h se delega a seguridad_login; el generador CAPTCHA corresponde a HU siguiente.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import PersonalMilitar, Rol, SesionUsuario, Usuario, UsuarioRoles
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.captcha import VerificadorCaptcha
from aplicacion.seguridad.contrasenas import gastar_tiempo_de_verificacion, verificar_contrasena
from aplicacion.seguridad.tokens import crear_token_sesion
from aplicacion.servicios import seguridad_login
from aplicacion.servicios.totp import DesafioLoginTotp

registrador = logging.getLogger(__name__)

# Códigos de rol que admite la base (CHECK ck_esart_roles_codigo).
CODIGO_ROL_ADMINISTRADOR = "ADMINISTRADOR"
CODIGO_ROL_USUARIO = "USUARIO"
NOMBRE_ROL_ADMINISTRADOR = "Administrador"

# Largo máximo de la columna sesiones_usuario.agente_usuario.
LONGITUD_MAXIMA_AGENTE_USUARIO = 300

# Mismo mensaje para usuario inexistente, contraseña errada, usuario inactivo o sin rol:
# así nadie puede averiguar qué usuarios existen.
MENSAJE_CREDENCIALES_INVALIDAS = "Usuario o contraseña incorrectos."


@dataclass(frozen=True)
class UsuarioAutenticado:
    """Identidad confirmada por el servidor (cookie firmada + fila de sesión vigente)."""

    id: int
    nombre_usuario: str
    rol: str
    documento_identidad: str | None
    sesion_id: uuid.UUID
    # La contraseña es temporal (la puso un administrador): debe cambiarla antes de usar el sistema.
    requiere_cambio_contrasena: bool = False


@dataclass(frozen=True)
class ResultadoInicioSesion:
    """Lo que la ruta necesita para responder a un login exitoso."""

    usuario_id: int
    nombre_usuario: str
    nombre_completo: str
    rol: str
    token_sesion: str
    requiere_cambio_contrasena: bool = False


def _error_credenciales_invalidas() -> ErrorAplicacion:
    """Construye el error genérico de login (siempre el mismo)."""
    return ErrorAplicacion(401, "CREDENCIALES_INVALIDAS", MENSAJE_CREDENCIALES_INVALIDAS)


async def buscar_usuario_por_nombre(sesion: AsyncSession, nombre_usuario: str) -> Usuario | None:
    """
    Busca un usuario por nombre, sin distinguir mayúsculas.

    Compara con lower() porque así está definido el índice único uq_esart_usuario_nombre_ci:
    la consulta usa ese índice.
    """
    return await sesion.scalar(
        select(Usuario).where(func.lower(Usuario.usuario) == nombre_usuario.strip().lower())
    )


async def obtener_codigo_rol(sesion: AsyncSession, usuario_id: int) -> str | None:
    """
    Devuelve el rol que se informa del usuario: ADMINISTRADOR si lo tiene entre sus roles
    activos; si no, USUARIO; None si no tiene ningún rol activo.
    """
    codigos = set(
        await sesion.scalars(
            select(Rol.codigo)
            .join(UsuarioRoles, UsuarioRoles.rol_id == Rol.id)
            .where(UsuarioRoles.usuario_id == usuario_id, Rol.activo.is_(True))
        )
    )
    if CODIGO_ROL_ADMINISTRADOR in codigos:
        return CODIGO_ROL_ADMINISTRADOR
    if CODIGO_ROL_USUARIO in codigos:
        return CODIGO_ROL_USUARIO
    return None


async def obtener_nombre_completo(
    sesion: AsyncSession, documento_identidad: str | None, nombre_usuario: str
) -> str:
    """
    Nombre visible: 'grado nombres apellidos' del militar con esa cédula.
    Si el usuario no tiene cédula o no hay militar con ella, se usa el nombre de usuario.
    """
    if documento_identidad:
        militar = (
            await sesion.execute(
                select(PersonalMilitar.grado, PersonalMilitar.nombres, PersonalMilitar.apellidos).where(
                    PersonalMilitar.documento_identidad == documento_identidad
                )
            )
        ).first()
        if militar is not None:
            return " ".join(parte.strip() for parte in militar if parte and parte.strip())
    return nombre_usuario


async def iniciar_sesion(
    sesion: AsyncSession,
    nombre_usuario: str,
    contrasena: str,
    direccion_ip: str | None,
    agente_usuario: str | None,
    captcha_id: str | None = None,
    captcha_respuesta: str | None = None,
    verificador_captcha: VerificadorCaptcha | None = None,
) -> DesafioLoginTotp:
    """
    Verifica contraseña, CAPTCHA y bloqueo; entrega un desafío sin sesión completa.

    El propósito es VINCULACION si falta factor activo, o LOGIN si ya existe.
    Solo finalizar_login, después del TOTP, puede emitir la sesión y su JWT.
    """
    # Contraseña, CAPTCHA y bloqueo persisten incluso si TOTP no está disponible.
    # Su disponibilidad se exige después de validar credenciales, antes de emitir JWT.
    contexto = await seguridad_login.preparar(
        sesion, nombre_usuario, direccion_ip, captcha_id, captcha_respuesta, verificador_captcha
    )
    usuario = contexto.usuario

    if usuario is None or not usuario.contrasena_hash:
        # Se gasta el mismo tiempo que una verificación real (ver contrasenas.py).
        await asyncio.to_thread(gastar_tiempo_de_verificacion)
        await seguridad_login.rechazar(sesion, contexto, "CREDENCIALES_INVALIDAS")

    # La contraseña se verifica SIEMPRE antes de mirar si el usuario está activo o tiene
    # rol: si se revisara antes, la diferencia de tiempo revelaría esas cuentas.
    contrasena_correcta = await asyncio.to_thread(verificar_contrasena, contrasena, usuario.contrasena_hash)
    rol = await obtener_codigo_rol(sesion, usuario.id) if contrasena_correcta else None
    if not contrasena_correcta or not usuario.activo or rol is None:
        await seguridad_login.rechazar(sesion, contexto, "CREDENCIALES_INVALIDAS")

    from aplicacion.servicios.totp import TotpService

    totp = TotpService(sesion)
    await totp.preparar()
    registro = await totp.registro(usuario.id)
    proposito = (
        "CAMBIO_CONTRASENA"
        if usuario.requiere_cambio_contrasena
        else "LOGIN"
        if registro and registro.estado == "ACTIVO"
        else "VINCULACION"
    )
    desafio = await totp.crear_desafio(usuario.id, proposito, direccion_ip)
    await seguridad_login.registrar(
        sesion, contexto, exito=False, motivo="TOTP_PENDIENTE", evento="TOTP_REQUERIDO"
    )
    await sesion.commit()
    return desafio


async def finalizar_login(sesion, usuario, direccion_ip, agente_usuario, contexto, request=None):
    rol = await obtener_codigo_rol(sesion, usuario.id)
    if not usuario.activo or rol is None:
        raise ErrorAplicacion(401, "CREDENCIALES_INVALIDAS", "No fue posible iniciar sesi?n.")
    if usuario.requiere_cambio_contrasena:
        raise ErrorAplicacion(403, "CAMBIO_CONTRASENA_REQUERIDO", "Debe cambiar su contraseña temporal.")
    ahora = await seguridad_login.reloj_servidor(sesion)
    sesion_usuario = SesionUsuario(
        id=uuid.uuid4(),
        usuario_id=usuario.id,
        fecha_inicio=ahora,
        fecha_ultima_actividad=ahora,
        direccion_ip=direccion_ip,
        agente_usuario=(agente_usuario or "")[:LONGITUD_MAXIMA_AGENTE_USUARIO] or None,
        revocada=False,
    )
    sesion.add(sesion_usuario)
    usuario.ultimo_acceso_en = ahora
    usuario.intentos_fallidos_consecutivos = 0
    usuario.bloqueado_hasta = None
    nombre_completo = await obtener_nombre_completo(sesion, usuario.documento_identidad, usuario.usuario)
    await seguridad_login.registrar(sesion, contexto, exito=True, motivo=None, evento="LOGIN_EXITOSO")
    if obtener_configuracion().totp_habilitado:
        from aplicacion.servicios.totp import TotpService

        await TotpService(sesion).auditar(usuario.id, "LOGIN_EXITOSO", "CORRECTO", direccion_ip)
    token = crear_token_sesion(usuario.id, sesion_usuario.id)
    from aplicacion.servicios import auditoria

    await auditoria.registrar_evento(
        sesion,
        auditoria.LOGIN_EXITOSO,
        request,
        usuario_id=usuario.id,
        nombre_usuario=usuario.usuario,
        resultado="EXITOSO",
        confirmar=False,
    )
    await sesion.commit()

    registrador.info("Inicio de sesión exitoso del usuario_id=%s", usuario.id)
    return ResultadoInicioSesion(
        usuario_id=usuario.id,
        nombre_usuario=usuario.usuario,
        nombre_completo=nombre_completo,
        rol=rol,
        token_sesion=token,
        requiere_cambio_contrasena=usuario.requiere_cambio_contrasena,
    )


async def validar_sesion(sesion: AsyncSession, usuario_id: int, sesion_id: uuid.UUID) -> UsuarioAutenticado:
    """
    Comprueba que la sesión del token siga vigente y registra la actividad.

    - Revocada, de otro usuario, usuario inactivo o sin rol: 401 NO_AUTENTICADO.
    - Más de MINUTOS_INACTIVIDAD_SESION sin actividad: se revoca y 401 SESION_EXPIRADA.
    - Vigente: se actualiza fecha_ultima_actividad (la ventana de 30 minutos se reinicia).
    """
    sesion_usuario = await sesion.get(SesionUsuario, sesion_id)
    usuario = await sesion.get(Usuario, usuario_id) if sesion_usuario else None
    if (
        sesion_usuario is None
        or usuario is None
        or sesion_usuario.revocada
        or sesion_usuario.usuario_id != usuario_id
        or not usuario.activo
    ):
        raise ErrorAplicacion(401, "NO_AUTENTICADO", "Debe iniciar sesión.")

    ahora = datetime.now(UTC)
    limite_inactividad = timedelta(minutes=obtener_configuracion().minutos_inactividad_sesion)
    if usuario.bloqueado_hasta is not None and ahora < usuario.bloqueado_hasta:
        raise ErrorAplicacion(401, "NO_AUTENTICADO", "Debe iniciar sesión.")
    from aplicacion.servicios.totp import TotpService

    totp = TotpService(sesion)
    await totp.preparar()
    factor = await totp.registro(usuario_id)
    if (
        not factor
        or factor.estado != "ACTIVO"
        or factor.activado_en is None
        or sesion_usuario.fecha_inicio < factor.activado_en
    ):
        raise ErrorAplicacion(401, "NO_AUTENTICADO", "Complete la vinculación del autenticador.")
    if ahora - sesion_usuario.fecha_ultima_actividad > limite_inactividad:
        sesion_usuario.revocada = True
        sesion_usuario.fecha_revocacion = ahora
        await sesion.commit()
        raise ErrorAplicacion(401, "SESION_EXPIRADA", "Su sesión expiró por inactividad.")

    rol = await obtener_codigo_rol(sesion, usuario.id)
    if rol is None:
        raise ErrorAplicacion(401, "NO_AUTENTICADO", "Debe iniciar sesión.")

    sesion_usuario.fecha_ultima_actividad = ahora
    await sesion.commit()
    return UsuarioAutenticado(
        id=usuario.id,
        nombre_usuario=usuario.usuario,
        rol=rol,
        documento_identidad=usuario.documento_identidad,
        sesion_id=sesion_usuario.id,
        requiere_cambio_contrasena=usuario.requiere_cambio_contrasena,
    )


async def cerrar_sesion(sesion: AsyncSession, sesion_id: uuid.UUID) -> None:
    """Revoca la sesión: el mismo token ya no sirve aunque alguien lo haya copiado."""
    sesion_usuario = await sesion.get(SesionUsuario, sesion_id)
    if sesion_usuario is not None and not sesion_usuario.revocada:
        sesion_usuario.revocada = True
        sesion_usuario.fecha_revocacion = datetime.now(UTC)
        await sesion.commit()


async def asegurar_administrador_inicial(sesion: AsyncSession) -> bool:
    """
    Crea el administrador inicial desde el .env si todavía no existe.

    - Usa ADMIN_USUARIO y ADMIN_HASH_CONTRASENA: la contraseña nunca está en texto plano.
    - Si el usuario ya existe NO lo modifica: cambiar el hash en el .env no reescribe la
      contraseña de un administrador que ya la cambió.
    - Crea el rol ADMINISTRADOR si falta y lo asigna en usuario_roles.

    Devuelve True si creó el usuario y False si ya existía.
    """
    configuracion = obtener_configuracion()

    if await buscar_usuario_por_nombre(sesion, configuracion.admin_usuario) is not None:
        return False

    rol_administrador = await sesion.scalar(select(Rol).where(Rol.codigo == CODIGO_ROL_ADMINISTRADOR))
    if rol_administrador is None:
        rol_administrador = Rol(codigo=CODIGO_ROL_ADMINISTRADOR, nombre=NOMBRE_ROL_ADMINISTRADOR, activo=True)
        sesion.add(rol_administrador)

    administrador = Usuario(
        usuario=configuracion.admin_usuario.strip(),
        contrasena_hash=configuracion.admin_hash_contrasena.get_secret_value(),
        activo=True,
    )
    sesion.add(administrador)
    try:
        # flush asigna los id (identity) del rol y del usuario antes de relacionarlos.
        await sesion.flush()
        sesion.add(UsuarioRoles(usuario_id=administrador.id, rol_id=rol_administrador.id))
        await sesion.commit()
    except IntegrityError:
        # Otro proceso (otro worker de uvicorn) lo creó al mismo tiempo: no es un error.
        await sesion.rollback()
        return False

    registrador.info("Administrador inicial creado desde las variables de entorno")
    return True
