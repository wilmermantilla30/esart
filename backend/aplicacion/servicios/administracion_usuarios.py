"""
Administración de usuarios (HU-10): crear, activar/desactivar, restablecer y cambiar contraseña,
desbloquear cuenta e IP, y listar.

Lo usan el panel web "Gestión de usuarios" y el comando de consola herramientas/administrar_usuarios.py.

Reglas:
- Todo usuario corresponde a un militar de esart.personal_militar (la cédula es obligatoria).
  La única excepción es el administrador inicial que se crea desde el .env.
- La contraseña que pone el administrador es TEMPORAL: el usuario debe cambiarla al entrar
  (requiere_cambio_contrasena). Nunca se guarda ni se audita en claro; solo su hash bcrypt.
- Cada acción queda en la auditoría (HU-11), con quién la hizo: el usuario web o "consola".
"""

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

import pyotp
from fastapi import Request
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.configuracion import obtener_configuracion
from aplicacion.modelos import PersonalMilitar, Rol, SesionUsuario, UnidadMilitar, Usuario, UsuarioRoles
from aplicacion.modelos.seguridad import LimiteInicioIP
from aplicacion.modelos.totp import (
    CambioSeguridad,
    DesafioTotp,
    RecuperacionTotp,
    UsuarioTotp,
)
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.contrasenas import generar_hash_contrasena, verificar_contrasena
from aplicacion.servicios import auditoria
from aplicacion.servicios.autenticacion import (
    UsuarioAutenticado,
    buscar_usuario_por_nombre,
    obtener_codigo_rol,
    obtener_nombre_completo,
)
from aplicacion.servicios.malla_permisos import exigir_administrador_de_malla
from aplicacion.servicios.seguridad_login import seudonimo

# Quien actúa desde la consola no tiene sesión web: así se identifica en la auditoría.
NOMBRE_ACTOR_CONSOLA = "consola"

PATRON_CEDULA = re.compile(r"^\d{5,15}$")
LONGITUD_MINIMA_CONTRASENA = 10
LONGITUD_MAXIMA_NOMBRE_USUARIO = 80

# Los nombres de usuario sugeridos terminan así (por ejemplo jperez.esart).
SUFIJO_NOMBRE_USUARIO = ".esart"


@dataclass(frozen=True)
class EstadoUsuario:
    id: int
    usuario: str
    rol: str | None
    activo: bool
    intentos_fallidos: int
    bloqueado_hasta: datetime | None
    bloqueado: bool
    documento_identidad: str | None = None
    nombre_completo: str | None = None
    requiere_cambio_contrasena: bool = False
    ultimo_acceso_en: datetime | None = None


@dataclass(frozen=True)
class MilitarParaUsuario:
    """Lo que el formulario "Nuevo usuario" muestra al buscar una cédula."""

    documento_identidad: str
    grado: str
    nombres: str
    apellidos: str
    unidad: str | None
    activo: bool
    # Si ese militar ya tiene usuario, su nombre (no se le puede crear otro).
    usuario_existente: str | None
    nombre_usuario_sugerido: str


@dataclass(frozen=True)
class Actor:
    """
    Quién hace la acción, para la auditoría.

    - Web: el usuario en sesión (su id y nombre) y la petición (IP y navegador).
    - Consola: sin id, nombre "consola" y el usuario del sistema operativo en 'operador'.
    """

    usuario_id: int | None
    nombre_usuario: str
    operador: str
    request: Request | None = None

    @classmethod
    def consola(cls, operador: str) -> "Actor":
        return cls(usuario_id=None, nombre_usuario=NOMBRE_ACTOR_CONSOLA, operador=operador)

    @classmethod
    def web(cls, usuario: UsuarioAutenticado, request: Request) -> "Actor":
        return cls(
            usuario_id=usuario.id,
            nombre_usuario=usuario.nombre_usuario,
            operador=usuario.nombre_usuario,
            request=request,
        )


async def _auditar(
    sesion: AsyncSession, accion: str, actor: Actor, detalle: dict, documento=None, confirmar=True
) -> None:
    """Registra la acción con el actor y confirma (registrar_evento hace commit)."""
    await auditoria.registrar_evento(
        sesion,
        accion,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        documento=documento,
        resultado="EXITOSO",
        detalle={**detalle, "operador": actor.operador},
        confirmar=confirmar,
    )


# --- Validaciones -----------------------------------------------------------------------


def validar_contrasena_nueva(contrasena: str) -> None:
    """Mínimo 10 caracteres, con letras y números; máximo 72 bytes (límite de bcrypt)."""
    if len(contrasena) < LONGITUD_MINIMA_CONTRASENA:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La contraseña debe tener al menos 10 caracteres.")
    if not (re.search(r"[A-Za-z]", contrasena) and re.search(r"\d", contrasena)):
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La contraseña debe combinar letras y números.")
    if len(contrasena.encode("utf-8")) > 72:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La contraseña no puede superar 72 bytes.")


def validar_cedula(documento_identidad: str | None) -> str:
    """La cédula es obligatoria y solo lleva números. Devuelve la cédula sin espacios."""
    cedula = (documento_identidad or "").strip()
    if not PATRON_CEDULA.match(cedula):
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La cédula debe tener solo números (5 a 15 dígitos).")
    return cedula


def _solo_letras_ascii(texto: str) -> str:
    """'Pérez Muñoz' -> 'perezmunoz': sin tildes, sin eñes, sin espacios, en minúscula."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", sin_tildes.lower())


async def sugerir_nombre_usuario(sesion: AsyncSession, nombres: str, apellidos: str) -> str:
    """
    Inicial del primer nombre + primer apellido + ".esart" (Juan Pérez Gómez -> jperez.esart).
    Si ya existe, agrega un número: jperez2.esart, jperez3.esart...
    """
    inicial = _solo_letras_ascii(nombres.split()[0])[:1] if nombres.split() else ""
    apellido = _solo_letras_ascii(apellidos.split()[0]) if apellidos.split() else ""
    base = f"{inicial}{apellido}" or "usuario"
    candidato = f"{base}{SUFIJO_NOMBRE_USUARIO}"
    numero = 2
    while await buscar_usuario_por_nombre(sesion, candidato) is not None:
        candidato = f"{base}{numero}{SUFIJO_NOMBRE_USUARIO}"
        numero += 1
    return candidato


# --- Consultas --------------------------------------------------------------------------


async def buscar_militar_para_usuario(sesion: AsyncSession, documento_identidad: str) -> MilitarParaUsuario:
    """Datos del militar con esa cédula, si ya tiene usuario y el nombre sugerido. 404 si no existe."""
    cedula = validar_cedula(documento_identidad)
    fila = (
        await sesion.execute(
            select(PersonalMilitar, UnidadMilitar.nombre)
            .outerjoin(UnidadMilitar, UnidadMilitar.id == PersonalMilitar.unidad_actual_id)
            .where(PersonalMilitar.documento_identidad == cedula)
        )
    ).first()
    if fila is None:
        raise ErrorAplicacion(
            404,
            "RECURSO_NO_ENCONTRADO",
            "No hay ningún militar registrado con esa cédula en Personal militar.",
        )
    militar, nombre_unidad = fila
    usuario_existente = await sesion.scalar(
        select(Usuario.usuario).where(Usuario.documento_identidad == cedula)
    )
    return MilitarParaUsuario(
        documento_identidad=cedula,
        grado=militar.grado,
        nombres=militar.nombres,
        apellidos=militar.apellidos,
        unidad=nombre_unidad,
        activo=militar.activo,
        usuario_existente=usuario_existente,
        nombre_usuario_sugerido=await sugerir_nombre_usuario(sesion, militar.nombres, militar.apellidos),
    )


async def listar_usuarios(sesion: AsyncSession, texto: str | None = None) -> list[EstadoUsuario]:
    """Usuarios con su rol, militar y estado de bloqueo (hora del servidor de base de datos)."""
    ahora = await sesion.scalar(text("SELECT now()"))
    # populate_existing: relee los valores aunque el usuario ya esté en memoria (tras un cambio).
    consulta = (
        select(Usuario)
        .where(Usuario.usuario.is_not(None))
        .order_by(Usuario.usuario)
        .execution_options(populate_existing=True)
    )
    if texto:
        patron = texto.strip().lower()
        consulta = consulta.where(
            func.lower(Usuario.usuario).contains(patron) | Usuario.documento_identidad.contains(patron)
        )
    resultado = []
    for usuario in await sesion.scalars(consulta):
        nombre_completo = await obtener_nombre_completo(sesion, usuario.documento_identidad, usuario.usuario)
        resultado.append(
            EstadoUsuario(
                id=usuario.id,
                usuario=usuario.usuario,
                rol=await obtener_codigo_rol(sesion, usuario.id),
                activo=usuario.activo,
                intentos_fallidos=usuario.intentos_fallidos_consecutivos,
                bloqueado_hasta=usuario.bloqueado_hasta,
                bloqueado=bool(usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora),
                documento_identidad=usuario.documento_identidad,
                # Si no tiene militar asociado, obtener_nombre_completo devuelve el usuario: no se repite.
                nombre_completo=None if nombre_completo == usuario.usuario else nombre_completo,
                requiere_cambio_contrasena=usuario.requiere_cambio_contrasena,
                ultimo_acceso_en=usuario.ultimo_acceso_en,
            )
        )
    return resultado


async def obtener_estado_usuario(sesion: AsyncSession, usuario_id: int) -> EstadoUsuario:
    usuario = await _obtener_usuario(sesion, usuario_id)
    return next(
        estado for estado in await listar_usuarios(sesion, usuario.usuario) if estado.id == usuario_id
    )


async def _obtener_usuario(sesion: AsyncSession, usuario_id: int) -> Usuario:
    usuario = await sesion.get(Usuario, usuario_id, populate_existing=True)
    if usuario is None or usuario.usuario is None:
        raise ErrorAplicacion(404, "RECURSO_NO_ENCONTRADO", "No existe ese usuario.")
    return usuario


async def _revocar_sesiones(sesion: AsyncSession, usuario_id: int, excepto=None) -> None:
    """Cierra en el servidor todas las sesiones abiertas del usuario (menos 'excepto', si se indica)."""
    condiciones = [SesionUsuario.usuario_id == usuario_id, SesionUsuario.revocada.is_(False)]
    if excepto is not None:
        condiciones.append(SesionUsuario.id != excepto)
    await sesion.execute(
        update(SesionUsuario).where(*condiciones).values(revocada=True, fecha_revocacion=datetime.now(UTC))
    )


# --- Acciones ---------------------------------------------------------------------------


async def crear_usuario(
    sesion: AsyncSession,
    *,
    nombre_usuario: str,
    codigo_rol: str,
    contrasena: str,
    documento_identidad: str,
    actor: Actor,
) -> int:
    """
    Crea el usuario de un militar con un rol y una contraseña temporal (debe cambiarla al entrar).
    Devuelve su id. Queda auditado como USUARIO_CREADO (sin la contraseña).
    """
    nombre_usuario = nombre_usuario.strip()
    if (
        not 3 <= len(nombre_usuario) <= LONGITUD_MAXIMA_NOMBRE_USUARIO
        or not nombre_usuario.isprintable()
        or " " in nombre_usuario
    ):
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "El usuario debe tener de 3 a 80 caracteres, sin espacios."
        )
    cedula = validar_cedula(documento_identidad)
    validar_contrasena_nueva(contrasena)

    rol = await sesion.scalar(select(Rol).where(Rol.codigo == codigo_rol, Rol.activo.is_(True)))
    if rol is None:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", f"El rol {codigo_rol} no existe o está inactivo.")
    militar = await sesion.scalar(
        select(PersonalMilitar).where(PersonalMilitar.documento_identidad == cedula)
    )
    if militar is None:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "No hay ningún militar registrado con esa cédula en Personal militar."
        )
    if not militar.activo:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "El militar está inactivo: no se le puede crear usuario."
        )
    if await buscar_usuario_por_nombre(sesion, nombre_usuario) is not None:
        raise ErrorAplicacion(409, "USUARIO_EXISTENTE", f"Ya existe el usuario {nombre_usuario}.")
    if await sesion.scalar(select(Usuario.id).where(Usuario.documento_identidad == cedula)):
        raise ErrorAplicacion(409, "USUARIO_EXISTENTE", "Ese militar ya tiene un usuario.")

    usuario = Usuario(
        usuario=nombre_usuario,
        contrasena_hash=await asyncio.to_thread(generar_hash_contrasena, contrasena),
        documento_identidad=cedula,
        activo=True,
        requiere_cambio_contrasena=True,
    )
    sesion.add(usuario)
    await sesion.flush()
    sesion.add(UsuarioRoles(usuario_id=usuario.id, rol_id=rol.id))
    await _auditar(
        sesion,
        auditoria.USUARIO_CREADO,
        actor,
        {"usuario_creado": nombre_usuario, "rol": codigo_rol},
        documento=cedula,
    )
    return usuario.id


async def cambiar_estado_activo(
    sesion: AsyncSession, *, usuario_id: int, activo: bool, actor: Actor
) -> EstadoUsuario:
    """
    Activa o desactiva un usuario. Al desactivar se cierran sus sesiones abiertas.
    Nadie se desactiva a sí mismo y siempre queda alguien que administre los permisos.
    """
    usuario = await _obtener_usuario(sesion, usuario_id)
    if not activo and actor.usuario_id == usuario_id:
        raise ErrorAplicacion(409, "AUTOBLOQUEO", "No puede desactivar su propio usuario.")
    if usuario.activo == activo:
        return await obtener_estado_usuario(sesion, usuario_id)
    await sesion.execute(
        update(Usuario).where(Usuario.id == usuario_id).values(activo=activo, actualizado_en=func.now())
    )
    if not activo:
        await _revocar_sesiones(sesion, usuario_id)
        # Si era el último que podía editar la malla, deshace el cambio y responde 409.
        await exigir_administrador_de_malla(sesion)
    await _auditar(
        sesion,
        auditoria.USUARIO_ACTIVADO if activo else auditoria.USUARIO_DESACTIVADO,
        actor,
        {"usuario_afectado": usuario.usuario},
    )
    return await obtener_estado_usuario(sesion, usuario_id)


async def restablecer_contrasena(
    sesion: AsyncSession, *, usuario_id: int, contrasena_temporal: str, actor: Actor
) -> EstadoUsuario:
    """
    Pone una contraseña temporal (el usuario deberá cambiarla al entrar), quita el bloqueo por
    intentos y cierra sus sesiones abiertas. Para la propia contraseña está "Cambiar contraseña".
    """
    usuario = await _obtener_usuario(sesion, usuario_id)
    if actor.usuario_id == usuario_id:
        raise ErrorAplicacion(409, "AUTOBLOQUEO", "Para su propia contraseña use «Cambiar contraseña».")
    validar_contrasena_nueva(contrasena_temporal)
    nuevo_hash = await asyncio.to_thread(generar_hash_contrasena, contrasena_temporal)
    await sesion.execute(
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(
            contrasena_hash=nuevo_hash,
            requiere_cambio_contrasena=True,
            intentos_fallidos_consecutivos=0,
            bloqueado_hasta=None,
            actualizado_en=func.now(),
        )
    )
    await _revocar_sesiones(sesion, usuario_id)
    await _auditar(sesion, auditoria.CONTRASENA_RESTABLECIDA, actor, {"usuario_afectado": usuario.usuario})
    return await obtener_estado_usuario(sesion, usuario_id)


async def restablecer_totp(
    sesion: AsyncSession,
    *,
    usuario_id: int,
    contrasena_administrador: str,
    codigo_totp: str,
    justificacion: str,
    actor: UsuarioAutenticado,
    request: Request,
    ip_cliente: str | None,
) -> None:
    """Revoca el factor del usuario sin borrar su historial y exige enrolamiento al próximo login."""
    from aplicacion.servicios.totp import TotpService

    if actor.id == usuario_id:
        raise ErrorAplicacion(
            409,
            "AUTORESTABLECIMIENTO_TOTP",
            "Use el cambio de autenticador de su propia cuenta.",
        )

    ip = ip_cliente
    servicio = TotpService(sesion)
    await servicio.preparar()
    politica = await servicio.politica("USUARIO_RESTABLECER_TOTP")
    if politica.permiso_requerido != "usuarios:restablecer_totp":
        raise ErrorAplicacion(503, "POLITICA_NO_DISPONIBLE", "Política de restablecimiento no disponible.")

    # Bloqueo y verificación del administrador: sesión válida, contraseña y un TOTP vigente
    # que aún no se haya utilizado. El endpoint está además protegido por el permiso admin.
    await servicio.limitar(ip, actor.id)
    administrador = await servicio.usuario(actor.id)
    if not administrador.contrasena_hash or not await asyncio.to_thread(
        verificar_contrasena, contrasena_administrador, administrador.contrasena_hash
    ):
        await servicio.rechazar(actor.id, ip, "TOTP_ADMIN_RESET_REAUTENTICACION_INVALIDA")
    factor_admin = await servicio.registro(actor.id)
    if not factor_admin or factor_admin.estado != "ACTIVO" or not await servicio.verificar(
        factor_admin, codigo_totp
    ):
        await servicio.rechazar(actor.id, ip, "TOTP_ADMIN_RESET_TOTP_INVALIDO")

    objetivo = await sesion.scalar(
        select(Usuario)
        .where(Usuario.id == usuario_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not objetivo or not objetivo.activo:
        raise ErrorAplicacion(404, "USUARIO_NO_ENCONTRADO", "No se encontró un usuario activo para restablecer.")
    factor = await sesion.scalar(
        select(UsuarioTotp)
        .where(UsuarioTotp.usuario_id == usuario_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not factor or factor.estado != "ACTIVO":
        raise ErrorAplicacion(
            409,
            "TOTP_NO_ACTIVO",
            "El usuario no tiene un autenticador activo para restablecer.",
        )

    ahora = await reloj_servidor(sesion)
    estado_anterior = factor.estado
    # Sobrescribe el secreto cifrado anterior con uno nuevo, aleatorio e inaccesible al operador.
    # Sin vencimiento de configuración, el login del usuario generará una clave/QR nuevo.
    factor.secreto_cifrado = servicio.cifrar(usuario_id, pyotp.random_base32())
    factor.estado = "PENDIENTE"
    factor.activado_en = None
    factor.expira_configuracion_en = None
    factor.revocado_en = ahora
    factor.ultimo_intervalo_aceptado = None
    factor.actualizado_en = ahora
    await sesion.execute(
        update(RecuperacionTotp)
        .where(RecuperacionTotp.usuario_id == usuario_id, RecuperacionTotp.revocado_en.is_(None))
        .values(revocado_en=ahora)
    )
    await sesion.execute(
        update(DesafioTotp)
        .where(DesafioTotp.usuario_id == usuario_id, DesafioTotp.estado.in_(["PENDIENTE", "VERIFICADO"]))
        .values(estado="CANCELADO")
    )
    await sesion.execute(
        update(SesionUsuario)
        .where(SesionUsuario.usuario_id == usuario_id, SesionUsuario.revocada.is_(False))
        .values(revocada=True, fecha_revocacion=ahora)
    )

    evento = await servicio.auditar(usuario_id, "TOTP_RESTABLECIDO_POR_ADMIN", "CORRECTO", ip)
    await sesion.flush()
    sesion.add(
        CambioSeguridad(
            auditoria_id=evento.id,
            campo="estado_totp",
            valor_anterior=estado_anterior,
            valor_nuevo="PENDIENTE",
        )
    )
    await auditoria.registrar_evento(
        sesion,
        auditoria.TOTP_RESTABLECIDO,
        request,
        usuario_id=actor.id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "usuario_afectado": objetivo.usuario,
            "estado_anterior": estado_anterior,
            "estado_nuevo": "PENDIENTE",
            "justificacion": justificacion,
            "sesion_id": str(actor.sesion_id),
        },
        confirmar=False,
    )
    await sesion.commit()


async def cambiar_contrasena_propia(
    sesion: AsyncSession,
    *,
    usuario: UsuarioAutenticado,
    contrasena_actual: str,
    contrasena_nueva: str,
    request: Request | None = None,
) -> None:
    """
    El usuario en sesión cambia su contraseña (obligatorio si era temporal).
    Exige la actual, valida la nueva, quita la marca de cambio obligatorio y cierra sus otras sesiones.
    """
    await cambiar_contrasena_comprobada(
        sesion,
        usuario_id=usuario.id,
        nombre_usuario=usuario.nombre_usuario,
        sesion_a_conservar=usuario.sesion_id,
        contrasena_actual=contrasena_actual,
        contrasena_nueva=contrasena_nueva,
        request=request,
    )


async def cambiar_contrasena_comprobada(
    sesion: AsyncSession,
    *,
    usuario_id: int,
    nombre_usuario: str,
    contrasena_actual: str,
    contrasena_nueva: str,
    request: Request | None = None,
    sesion_a_conservar=None,
    confirmar=True,
) -> None:
    """Reglas HU-10 compartidas por la sesión y el desafío restringido de primer acceso."""
    fila = await _obtener_usuario(sesion, usuario_id)
    actor = Actor(usuario_id, nombre_usuario, nombre_usuario, request)
    if not fila.contrasena_hash or not await asyncio.to_thread(
        verificar_contrasena, contrasena_actual, fila.contrasena_hash
    ):
        await auditoria.registrar_evento(
            sesion,
            auditoria.CONTRASENA_CAMBIADA,
            request,
            usuario_id=usuario_id,
            nombre_usuario=nombre_usuario,
            resultado="RECHAZADO",
            detalle={"codigo": "CONTRASENA_ACTUAL_INCORRECTA"},
        )
        raise ErrorAplicacion(422, "CONTRASENA_ACTUAL_INCORRECTA", "La contraseña actual no es correcta.")
    validar_contrasena_nueva(contrasena_nueva)
    if contrasena_nueva == contrasena_actual:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La contraseña nueva debe ser distinta de la actual.")
    nuevo_hash = await asyncio.to_thread(generar_hash_contrasena, contrasena_nueva)
    await sesion.execute(
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(contrasena_hash=nuevo_hash, requiere_cambio_contrasena=False, actualizado_en=func.now())
    )
    # Si alguien más conocía la contraseña anterior y tenía una sesión abierta, se le cierra.
    await _revocar_sesiones(sesion, usuario_id, excepto=sesion_a_conservar)
    if obtener_configuracion().totp_habilitado:
        from aplicacion.modelos.totp import DesafioTotp

        await sesion.execute(
            update(DesafioTotp)
            .where(
                DesafioTotp.usuario_id == usuario_id,
                DesafioTotp.estado == "PENDIENTE",
            )
            .values(estado="CANCELADO")
        )
    await _auditar(
        sesion,
        auditoria.CONTRASENA_CAMBIADA,
        actor,
        {"usuario_afectado": nombre_usuario},
        confirmar=confirmar,
    )


async def desbloquear_usuario(sesion: AsyncSession, *, nombre_usuario: str, actor: Actor) -> EstadoUsuario:
    """Pone en cero los intentos fallidos y quita el bloqueo. Queda auditado (USUARIO_DESBLOQUEADO)."""
    usuario = await buscar_usuario_por_nombre(sesion, nombre_usuario)
    if usuario is None:
        raise ErrorAplicacion(404, "RECURSO_NO_ENCONTRADO", f"No existe el usuario {nombre_usuario}.")
    antes = {
        "intentos_fallidos": usuario.intentos_fallidos_consecutivos,
        "bloqueado_hasta": usuario.bloqueado_hasta.isoformat() if usuario.bloqueado_hasta else None,
    }
    await sesion.execute(
        update(Usuario)
        .where(Usuario.id == usuario.id)
        .values(intentos_fallidos_consecutivos=0, bloqueado_hasta=None)
    )
    await _auditar(
        sesion,
        auditoria.USUARIO_DESBLOQUEADO,
        actor,
        {"tipo": "CUENTA", "usuario_desbloqueado": usuario.usuario, "antes": antes},
    )
    return await obtener_estado_usuario(sesion, usuario.id)


async def desbloquear_ip(sesion: AsyncSession, *, ip: str, actor: Actor) -> int:
    """
    Pone en cero el contador de intentos de una IP (bloqueo por IP de HU-06).
    La IP se guarda como seudónimo (HMAC), igual que la calcula el login. Devuelve los intentos que tenía.
    """
    canonica = ip_canonica(ip)
    if canonica is None:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La dirección IP no es válida.")
    clave = seudonimo("ip", canonica)
    limite = await sesion.get(LimiteInicioIP, clave)
    intentos_anteriores = limite.intentos if limite else 0
    if limite is not None:
        await sesion.execute(update(LimiteInicioIP).where(LimiteInicioIP.clave == clave).values(intentos=0))
    await _auditar(
        sesion,
        auditoria.USUARIO_DESBLOQUEADO,
        actor,
        {"tipo": "IP", "ip": canonica, "intentos_anteriores": intentos_anteriores},
    )
    return intentos_anteriores
