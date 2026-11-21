"""
Firma electrónica desde el celular (rúbrica dibujada + TOTP de ESART) para certificaciones y oficios.

Flujo (docs/ESART_FIRMA_MOVIL.md):
1. En el PC, quien genera el documento elige un firmante autorizado y pide la firma
   (solicitar_firma): se guarda el PDF BORRADOR (versión 1), el documento queda PENDIENTE_FIRMA y se
   crea una solicitud con un token de un solo uso (vence en 15 minutos) que viaja en el QR.
2. El firmante escanea el QR con su celular (abrir_solicitud), revisa el borrador, dibuja su rúbrica
   y escribe el código de su autenticador de ESART.
3. firmar(): valida el token, el TOTP del firmante (con el límite de intentos de ESART), la rúbrica
   (PNG re-codificado, sin metadatos) y el hash del borrador; registra desafío FIRMAR, consentimiento,
   firma y evidencias; genera el PDF FINAL con la rúbrica en la línea de firma (versión 2) y deja el
   documento FIRMADO. Todo en una transacción (el llamador confirma).

Sobre el esquema conciliado de p0018 (esart_firma): la solicitud apunta a documentos/versiones de
ESART; firmante y autorizaciones son identidades enlazadas 1:1 al usuario ESART; consentimiento,
firma y auditoría usan las tablas heredadas. Nunca se guarda el token en claro (solo su sha256).
"""

# Las sentencias SQL y los mensajes al usuario se dejan en una línea para leerlos completos.
# ruff: noqa: E501

import base64
import binascii
import hashlib
import io
import json
import logging
import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.reportes.comun import DatosDocumento, FirmaDocumento, datos_a_json, datos_desde_json
from aplicacion.reportes.maestro import generar_documento
from aplicacion.seguridad.sesion_http import obtener_ip_cliente
from aplicacion.servicios.almacenamiento_documental import (
    guardar_archivo_privado,
    guardar_pdf_temporalmente,
    identidad_firma,
    registrar_documento,
    registrar_evento_firma,
    resolver_archivo_privado,
)

registrador = logging.getLogger(__name__)

TIPOS_FIRMABLES = ("CERTIFICACION", "OFICIO_REMISORIO")
DURACION_SOLICITUD = timedelta(minutes=15)
VERSION_CONSENTIMIENTO = "v1"
TEXTO_CONSENTIMIENTO = (
    "Declaro que revisé el documento mostrado y lo firmo electrónicamente con mi rúbrica, "
    "confirmando mi identidad con el código del autenticador de ESART."
)
# Rúbrica: PNG del lienzo del celular.
MAX_RUBRICA_BYTES = 400_000
MIN_LADO_RUBRICA, MAX_LADO_RUBRICA = 100, 2400
ESTADOS_ABIERTOS = ("PENDIENTE", "ABIERTA")

# Firmantes con autorización vigente para un tipo de documento (nombre desde personal_militar si el
# usuario tiene cédula registrada; si no, el nombre mostrado de la identidad).
SQL_FIRMANTES = """
    SELECT a.id AS autorizacion_id, a.identidad_id, a.tipo_certificado AS tipo, a.cargo, a.grado,
           a.vigente_hasta, i.usuario_id,
           coalesce(nullif(trim(concat_ws(' ', coalesce(a.grado, p.grado), p.nombres, p.apellidos)), ''),
                    i.nombre_mostrado) AS nombre
    FROM esart_firma.autorizaciones_firmantes a
    JOIN esart_firma.identidades i ON i.id = a.identidad_id AND i.activo
    LEFT JOIN esart_ref.usuarios u ON u.id = i.usuario_id
    LEFT JOIN esart.personal_militar p ON p.documento_identidad = u.documento_identidad
    WHERE a.revocado_en IS NULL AND a.vigente_desde <= now()
      AND (a.vigente_hasta IS NULL OR a.vigente_hasta > now())
      AND i.usuario_id IS NOT NULL
"""


# Estructura y permisos que exige la firma (p0018 + p0019). Se consulta por pasos: PostgreSQL resuelve
# los nombres constantes al planificar (aunque estén en un CASE), y sin USAGE sobre esart_firma eso ya
# sería "permission denied" en vez de un "no disponible".
SQL_ESQUEMA_FIRMA = (
    "SELECT to_regnamespace('esart_firma') IS NOT NULL "
    "AND has_schema_privilege(to_regnamespace('esart_firma'), 'USAGE')"
)
SQL_ESTRUCTURA_FIRMA = """
    SELECT CASE
      WHEN to_regclass('esart_firma.documentos') IS NULL THEN 'SIN_P0018'
      WHEN NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('esart_firma.identidades')
                       AND attname = 'usuario_id' AND NOT attisdropped) THEN 'SIN_P0018'
      ELSE 'TABLAS_OK'
    END
"""
SQL_PERMISOS_FIRMA = """
    SELECT has_table_privilege('esart_firma.documentos', 'INSERT')
       AND has_table_privilege('esart_firma.autorizaciones_firmantes', 'SELECT')
       AND has_table_privilege('esart_firma.solicitudes_firma', 'INSERT')
       AND has_table_privilege('esart_firma.consentimientos_firma', 'INSERT')
       AND has_table_privilege('esart_firma.desafios_autenticacion', 'INSERT')
       AND has_table_privilege('esart_firma.firmas_certificado', 'INSERT')
"""
MENSAJE_FIRMA_NO_DISPONIBLE = (
    "La firma desde el celular aún no está habilitada en la base de datos "
    "(faltan las migraciones p0018 y p0019). Contacte al administrador."
)


async def verificar_estructura_firma(sesion: AsyncSession) -> None:
    """503 claro (en vez de un error interno) si la base no tiene la estructura o los permisos de firma."""
    if not await sesion.scalar(text(SQL_ESQUEMA_FIRMA)):
        estado = "SIN_ESQUEMA_O_USAGE"
    else:
        estado = await sesion.scalar(text(SQL_ESTRUCTURA_FIRMA))
        if estado == "TABLAS_OK":
            estado = "OK" if await sesion.scalar(text(SQL_PERMISOS_FIRMA)) else "SIN_P0019"
    if estado != "OK":
        registrador.error("FIRMA_NO_DISPONIBLE causa=%s", estado)
        raise ErrorAplicacion(503, "FIRMA_NO_DISPONIBLE", MENSAJE_FIRMA_NO_DISPONIBLE)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validar_rubrica(datos_png: str) -> bytes:
    """
    Decodifica el PNG del lienzo (data URL o base64), comprueba tamaño, formato y que tenga trazo,
    y lo re-codifica como PNG RGBA sin metadatos. Devuelve los bytes listos para el PDF.
    """
    contenido = datos_png.split(",", 1)[1] if datos_png.startswith("data:") else datos_png
    try:
        crudo = base64.b64decode(contenido, validate=True)
    except (binascii.Error, ValueError):
        raise ErrorAplicacion(422, "RUBRICA_INVALIDA", "La rúbrica no llegó en un formato válido.") from None
    if not crudo or len(crudo) > MAX_RUBRICA_BYTES:
        raise ErrorAplicacion(422, "RUBRICA_INVALIDA", "La rúbrica está vacía o es demasiado grande.")
    try:
        with Image.open(io.BytesIO(crudo)) as imagen:
            if imagen.format != "PNG":
                raise ErrorAplicacion(422, "RUBRICA_INVALIDA", "La rúbrica debe ser una imagen PNG.")
            ancho, alto = imagen.size
            if not (MIN_LADO_RUBRICA <= ancho <= MAX_LADO_RUBRICA and 50 <= alto <= MAX_LADO_RUBRICA):
                raise ErrorAplicacion(422, "RUBRICA_INVALIDA", "La rúbrica tiene un tamaño no admitido.")
            limpia = imagen.convert("RGBA")
    except (UnidentifiedImageError, OSError):
        raise ErrorAplicacion(422, "RUBRICA_INVALIDA", "La rúbrica no es una imagen válida.") from None
    # Debe haber trazo: algún píxel visible y oscuro (el lienzo vacío es transparente o blanco).
    gris = Image.new("RGBA", limpia.size, (255, 255, 255, 255))
    gris.alpha_composite(limpia)
    if gris.convert("L").point(lambda v: 255 if v < 200 else 0).getbbox() is None:
        raise ErrorAplicacion(422, "RUBRICA_VACIA", "Dibuje su firma antes de continuar.")
    salida = io.BytesIO()
    limpia.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


async def listar_candidatos(sesion: AsyncSession) -> list[dict]:
    """Usuarios activos que se pueden autorizar como firmantes (con su nombre y si tienen autenticador)."""
    filas = await sesion.execute(
        text("""
            SELECT u.id AS usuario_id, u.usuario,
                   coalesce(nullif(trim(concat_ws(' ', p.grado, p.nombres, p.apellidos)), ''), u.usuario) AS nombre,
                   EXISTS (SELECT 1 FROM seguridad.usuario_totp t WHERE t.usuario_id = u.id AND t.estado = 'ACTIVO')
                     AS totp_activo
            FROM esart_ref.usuarios u
            LEFT JOIN esart.personal_militar p ON p.documento_identidad = u.documento_identidad
            WHERE u.activo
            ORDER BY nombre
        """)
    )
    return [dict(f) for f in filas.mappings()]


async def listar_firmantes(sesion: AsyncSession, tipo: str) -> list[dict]:
    if tipo not in TIPOS_FIRMABLES:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Ese documento no se firma desde el celular.")
    filas = await sesion.execute(
        text(SQL_FIRMANTES + " AND a.tipo_certificado = :tipo ORDER BY nombre"), {"tipo": tipo}
    )
    return [dict(f) for f in filas.mappings()]


async def autorizar_firmante(
    sesion: AsyncSession,
    *,
    usuario_id: int,
    tipo: str,
    cargo: str,
    grado: str | None,
    concedido_por: int,
    request,
) -> dict:
    """El administrador (FIRMA_DOCUMENTOS) autoriza a un usuario ESART a firmar un tipo de documento."""
    if tipo not in TIPOS_FIRMABLES:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Tipo de documento no firmable.")
    cargo = " ".join((cargo or "").split())
    if not cargo:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Indique el cargo con el que firma.")
    if not await sesion.scalar(
        text("SELECT 1 FROM esart_ref.usuarios WHERE id=:u AND activo"), {"u": usuario_id}
    ):
        raise ErrorAplicacion(404, "USUARIO_NO_ENCONTRADO", "El usuario no existe o está inactivo.")
    identidad = await identidad_firma(sesion, usuario_id)
    concedente = await identidad_firma(sesion, concedido_por)
    if await sesion.scalar(
        text(SQL_FIRMANTES + " AND a.tipo_certificado = :tipo AND a.identidad_id = :i LIMIT 1"),
        {"tipo": tipo, "i": identidad},
    ):
        raise ErrorAplicacion(
            409, "AUTORIZACION_EXISTENTE", "Ese usuario ya está autorizado para ese documento."
        )
    autorizacion = await sesion.scalar(
        text("""
            INSERT INTO esart_firma.autorizaciones_firmantes
              (identidad_id, tipo_certificado, cargo, grado, vigente_desde, concedido_por)
            VALUES (:i, :tipo, :cargo, :grado, now(), :c) RETURNING id
        """),
        {
            "i": identidad,
            "tipo": tipo,
            "cargo": cargo,
            "grado": (grado or "").strip() or None,
            "c": concedente,
        },
    )
    await registrar_evento_firma(
        sesion, usuario_id=concedido_por, correlacion_id=uuid.uuid4(), accion="FIRMANTE_AUTORIZADO",
        recurso_tipo="AUTORIZACION", recurso_id=str(autorizacion), resultado="EXITO",
        detalle={"tipo": tipo, "usuario_autorizado": usuario_id}, request=request,
    )  # fmt: skip
    return {"autorizacion_id": autorizacion, "usuario_id": usuario_id, "tipo": tipo, "cargo": cargo}


async def _firmante_con_totp(sesion: AsyncSession, autorizacion_id, tipo: str) -> dict:
    firmante = (
        (
            await sesion.execute(
                text(SQL_FIRMANTES + " AND a.id = :a AND a.tipo_certificado = :tipo"),
                {"a": autorizacion_id, "tipo": tipo},
            )
        )
        .mappings()
        .one_or_none()
    )
    if firmante is None:
        raise ErrorAplicacion(
            422, "FIRMANTE_NO_AUTORIZADO", "El firmante no tiene autorización vigente para ese documento."
        )
    if not await sesion.scalar(
        text("SELECT 1 FROM seguridad.usuario_totp WHERE usuario_id = :u AND estado = 'ACTIVO'"),
        {"u": firmante["usuario_id"]},
    ):
        raise ErrorAplicacion(
            409,
            "FIRMANTE_SIN_AUTENTICADOR",
            "El firmante debe tener activo el autenticador de ESART para firmar.",
        )
    return dict(firmante)


async def solicitar_firma(
    sesion: AsyncSession, *, datos: DatosDocumento, tipo: str, personal_id: int, autorizacion_id,
    usuario_id: int, directorio: Path, request,
) -> tuple[dict, Path]:  # fmt: skip
    """Guarda el borrador y crea la solicitud. Devuelve (respuesta, archivo) — el llamador confirma
    y, si falla, borra el archivo."""
    if tipo not in TIPOS_FIRMABLES:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Ese documento no se firma desde el celular.")
    firmante = await _firmante_con_totp(sesion, autorizacion_id, tipo)
    pdf, _ = generar_documento(tipo, datos)
    documento_id, destino, sha, correlacion = await registrar_documento(
        sesion, directorio=directorio, pdf=pdf, numero=datos.numero, tipo=tipo, personal_id=personal_id,
        usuario_id=usuario_id, datos_emitidos=datos_a_json(datos), request=request,
    )  # fmt: skip
    try:
        await sesion.execute(
            text("UPDATE esart_firma.documentos SET estado='PENDIENTE_FIRMA' WHERE id=:d"),
            {"d": documento_id},
        )
        version_id = await sesion.scalar(
            text("SELECT id FROM esart_firma.versiones_documento WHERE documento_id=:d AND numero_version=1"),
            {"d": documento_id},
        )
        token = secrets.token_urlsafe(32)
        solicitud = (
            await sesion.execute(
                text("""
                    INSERT INTO esart_firma.solicitudes_firma
                      (id, documento_id, documento_version_id, firmante_id, autorizacion_id, token_qr_hash,
                       creada_por, expira_en)
                    VALUES (:id, :d, :v, :f, :a, :h, :c, now() + make_interval(mins => :m))
                    RETURNING id, expira_en
                """),
                {
                    "id": uuid.uuid4(),
                    "d": documento_id,
                    "v": version_id,
                    "f": firmante["identidad_id"],
                    "a": autorizacion_id,
                    "h": hash_token(token),
                    "c": await identidad_firma(sesion, usuario_id),
                    "m": int(DURACION_SOLICITUD.total_seconds() // 60),
                },  # fmt: skip
            )
        ).one()
        await registrar_evento_firma(
            sesion, usuario_id=usuario_id, correlacion_id=correlacion, accion="FIRMA_SOLICITADA",
            recurso_tipo="SOLICITUD_FIRMA", recurso_id=str(solicitud.id), resultado="EXITO",
            detalle={"documento_id": str(documento_id), "tipo": tipo, "borrador_sha256": sha,
                     "firmante_identidad": firmante["identidad_id"]},
            request=request,
        )  # fmt: skip
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    return (
        {
            "solicitud_id": solicitud.id,
            "documento_id": documento_id,
            "token": token,
            "expira_en": solicitud.expira_en,
            "firmante": firmante["nombre"],
            "cargo": firmante["cargo"],
        },
        destino,
    )


SQL_SOLICITUD = """
    SELECT s.id, s.estado, s.expira_en, s.expira_en <= now() AS vencida, s.firmante_id, s.creada_por,
           s.documento_id, s.documento_version_id, s.autorizacion_id,
           d.tipo, d.numero, d.datos_emitidos, d.estado AS estado_documento,
           v.sha256 AS borrador_sha256, v.ubicacion_privada AS borrador_ruta,
           a.cargo, i.usuario_id AS firmante_usuario_id,
           coalesce(nullif(trim(concat_ws(' ', coalesce(a.grado, p.grado), p.nombres, p.apellidos)), ''),
                    i.nombre_mostrado) AS firmante
    FROM esart_firma.solicitudes_firma s
    JOIN esart_firma.documentos d ON d.id = s.documento_id
    JOIN esart_firma.versiones_documento v ON v.id = s.documento_version_id
    JOIN esart_firma.autorizaciones_firmantes a ON a.id = s.autorizacion_id
    JOIN esart_firma.identidades i ON i.id = s.firmante_id
    LEFT JOIN esart_ref.usuarios u ON u.id = i.usuario_id
    LEFT JOIN esart.personal_militar p ON p.documento_identidad = u.documento_identidad
"""


async def _solicitud_por_token(sesion: AsyncSession, token: str, *, bloquear: bool = False):
    if not token or len(token) > 100:
        raise ErrorAplicacion(404, "SOLICITUD_NO_ENCONTRADA", "El enlace de firma no es válido.")
    fila = (
        (
            await sesion.execute(
                text(
                    SQL_SOLICITUD + " WHERE s.token_qr_hash = :h" + (" FOR UPDATE OF s" if bloquear else "")
                ),
                {"h": hash_token(token)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if fila is None:
        raise ErrorAplicacion(404, "SOLICITUD_NO_ENCONTRADA", "El enlace de firma no es válido.")
    return fila


def _resumen(fila) -> dict:
    datos = (
        fila["datos_emitidos"]
        if isinstance(fila["datos_emitidos"], dict)
        else json.loads(fila["datos_emitidos"])
    )
    return {
        "estado": "EXPIRADA" if fila["vencida"] and fila["estado"] in ESTADOS_ABIERTOS else fila["estado"],
        "tipo": fila["tipo"],
        "numero": fila["numero"],
        "artillero": f"{datos.get('grado', '')} {datos.get('nombres', '')} {datos.get('apellidos', '')}".strip(),
        "firmante": fila["firmante"],
        "cargo": fila["cargo"],
        "expira_en": fila["expira_en"],
        "texto_consentimiento": TEXTO_CONSENTIMIENTO,
    }


async def abrir_solicitud(sesion: AsyncSession, token: str) -> dict:
    """Lo que ve el celular al escanear el QR. La primera apertura deja la solicitud ABIERTA."""
    fila = await _solicitud_por_token(sesion, token, bloquear=True)
    if fila["vencida"] and fila["estado"] in ESTADOS_ABIERTOS:
        await sesion.execute(
            text("UPDATE esart_firma.solicitudes_firma SET estado='EXPIRADA' WHERE id=:s"), {"s": fila["id"]}
        )
    elif fila["estado"] == "PENDIENTE":
        await sesion.execute(
            text("UPDATE esart_firma.solicitudes_firma SET estado='ABIERTA', abierta_en=now() WHERE id=:s"),
            {"s": fila["id"]},
        )
    return _resumen(fila) | (
        {"estado": "ABIERTA"} if fila["estado"] == "PENDIENTE" and not fila["vencida"] else {}
    )


async def pdf_borrador(sesion: AsyncSession, token: str, directorio: Path) -> tuple[bytes, str]:
    """PDF que se va a firmar (verificado contra su sha256). Solo mientras la solicitud está abierta."""
    fila = await _solicitud_por_token(sesion, token)
    if fila["vencida"] or fila["estado"] not in ESTADOS_ABIERTOS:
        raise ErrorAplicacion(409, "SOLICITUD_CERRADA", "La solicitud de firma ya no está disponible.")
    return _leer_verificado(directorio, fila["borrador_ruta"], fila["borrador_sha256"]), fila["numero"]


def _leer_verificado(directorio: Path, ruta: str, sha: str) -> bytes:
    try:
        contenido = resolver_archivo_privado(directorio, ruta).read_bytes()
    except (FileNotFoundError, OSError, ValueError):
        raise ErrorAplicacion(503, "DOCUMENTO_NO_DISPONIBLE", "El borrador no está disponible.") from None
    if hashlib.sha256(contenido).hexdigest() != (sha or "").strip():
        raise ErrorAplicacion(
            503, "DOCUMENTO_INTEGRO_NO_VERIFICADO", "El borrador no pasó la verificación de integridad."
        )
    return contenido


async def _verificar_totp_firmante(sesion: AsyncSession, usuario_id: int, codigo: str, request) -> None:
    """Mismo TOTP, límite de intentos y protección contra reutilización que el resto de ESART."""
    from aplicacion.servicios.totp import TotpService

    servicio = TotpService(sesion)
    ip = obtener_ip_cliente(request)
    await servicio.limitar(ip, f"firma:{usuario_id}")
    try:
        await servicio.usuario(usuario_id)
    except ErrorAplicacion:
        # La página del celular no tiene sesión: nunca responder 401 (no hay a dónde redirigir).
        raise ErrorAplicacion(
            409, "FIRMANTE_NO_DISPONIBLE", "El firmante está inactivo o bloqueado."
        ) from None
    registro = await servicio.registro(usuario_id)
    if not registro or registro.estado != "ACTIVO":
        raise ErrorAplicacion(
            409, "FIRMANTE_SIN_AUTENTICADOR", "El firmante no tiene el autenticador activo."
        )
    if not await servicio.verificar(registro, (codigo or "").strip()):
        try:
            # Audita el intento y lo confirma (cuenta para el límite); su propio 401 no aplica aquí.
            await servicio.rechazar(usuario_id, ip)
        except ErrorAplicacion:
            pass
        raise ErrorAplicacion(422, "TOTP_INVALIDO", "Código del autenticador inválido o ya utilizado.")


async def firmar(
    sesion: AsyncSession, *, token: str, rubrica_png: str, codigo_totp: str, acepto: bool,
    directorio: Path, request,
) -> tuple[dict, list[Path]]:  # fmt: skip
    """Firma la solicitud. Devuelve (resumen, archivos creados) — el llamador confirma y, si falla,
    borra los archivos."""
    if not acepto:
        raise ErrorAplicacion(422, "CONSENTIMIENTO_REQUERIDO", "Debe aceptar la declaración de firma.")
    rubrica = validar_rubrica(rubrica_png)
    previa = await _solicitud_por_token(sesion, token)
    if previa["vencida"] or previa["estado"] not in ESTADOS_ABIERTOS:
        raise ErrorAplicacion(409, "SOLICITUD_CERRADA", "La solicitud de firma ya no está disponible.")
    # TOTP antes de bloquear: un código inválido confirma su auditoría y el límite de intentos.
    await _verificar_totp_firmante(sesion, previa["firmante_usuario_id"], codigo_totp, request)

    fila = await _solicitud_por_token(sesion, token, bloquear=True)
    if fila["vencida"] or fila["estado"] not in ESTADOS_ABIERTOS:
        raise ErrorAplicacion(409, "SOLICITUD_CERRADA", "La solicitud de firma ya no está disponible.")
    borrador = _leer_verificado(directorio, fila["borrador_ruta"], fila["borrador_sha256"])
    ip = obtener_ip_cliente(request)
    agente = (request.headers.get("user-agent", "")[:300] or None) if request is not None else None
    ahora = await sesion.scalar(text("SELECT now()"))
    ahora_local = await sesion.scalar(text("SELECT (now() AT TIME ZONE 'America/Bogota')"))
    firma_id = uuid.uuid4()
    archivos: list[Path] = []
    try:
        desafio = await sesion.scalar(
            text("""
                INSERT INTO esart_firma.desafios_autenticacion
                  (identidad_id, proposito, recurso_id, expira_en, validado_en, consumido_en)
                VALUES (:i, 'FIRMAR', :s, now() + interval '5 minutes', now(), now()) RETURNING id
            """),
            {"i": fila["firmante_id"], "s": fila["id"]},
        )
        consentimiento = await sesion.scalar(
            text("""
                INSERT INTO esart_firma.consentimientos_firma
                  (solicitud_id, texto_aceptado, version_texto, documento_sha256, ip, agente_usuario, desafio_id)
                VALUES (:s, :t, :v, :h, CAST(:ip AS inet), :a, :d) RETURNING id
            """),
            {"s": fila["id"], "t": TEXTO_CONSENTIMIENTO, "v": VERSION_CONSENTIMIENTO,
             "h": hashlib.sha256(borrador).hexdigest(), "ip": ip, "a": agente, "d": desafio},
        )  # fmt: skip
        ruta_rubrica, destino_rubrica, sha_rubrica = guardar_archivo_privado(
            directorio, Path(str(fila["documento_id"])) / "rubricas" / f"{uuid.uuid4().hex}.png", rubrica
        )
        archivos.append(destino_rubrica)
        datos = (
            fila["datos_emitidos"]
            if isinstance(fila["datos_emitidos"], dict)
            else json.loads(fila["datos_emitidos"])
        )
        firmado = datos_desde_json(
            datos,
            FirmaDocumento(
                rubrica_png=rubrica, firmante=fila["firmante"], cargo=fila["cargo"], firmado_en=ahora_local,
                codigo_verificacion=f"F-{firma_id.hex[:8].upper()}",
            ),
        )  # fmt: skip
        pdf_final, _ = generar_documento(fila["tipo"], firmado)
        ruta_pdf, destino_pdf, sha_pdf = guardar_pdf_temporalmente(
            directorio, fila["documento_id"], pdf_final, version=2
        )
        archivos.append(destino_pdf)
        await sesion.execute(
            text("""
                INSERT INTO esart_firma.versiones_documento
                  (id, documento_id, numero_version, sha256, ubicacion_privada, tamano_bytes, creado_por)
                VALUES (:id, :d, 2, :h, :r, :t, :u)
            """),
            {"id": uuid.uuid4(), "d": fila["documento_id"], "h": sha_pdf, "r": ruta_pdf, "t": len(pdf_final),
             "u": fila["firmante_usuario_id"]},
        )  # fmt: skip
        await sesion.execute(
            text("""
                INSERT INTO esart_firma.firmas_certificado
                  (id, solicitud_id, consentimiento_id, metodo, rubrica_archivo_sha256, rubrica_ubicacion_segura,
                   pdf_resultante_sha256, pdf_resultante_ubicacion_segura)
                VALUES (:id, :s, :c, 'RUBRICA_ELECTRONICA', :hr, :rr, :hp, :rp)
            """),
            {"id": firma_id, "s": fila["id"], "c": consentimiento, "hr": sha_rubrica, "rr": ruta_rubrica,
             "hp": sha_pdf, "rp": ruta_pdf},
        )  # fmt: skip
        await sesion.execute(
            text("UPDATE esart_firma.solicitudes_firma SET estado='APROBADA', decidida_en=now() WHERE id=:s"),
            {"s": fila["id"]},
        )
        await sesion.execute(
            text("""
                UPDATE esart_firma.documentos SET estado='FIRMADO', version_actual=2, emitido_en=:a WHERE id=:d
            """),
            {"a": ahora, "d": fila["documento_id"]},
        )
        evento = await registrar_evento_firma(
            sesion, usuario_id=fila["firmante_usuario_id"], correlacion_id=uuid.uuid4(), accion="DOCUMENTO_FIRMADO",
            recurso_tipo="DOCUMENTO", recurso_id=str(fila["documento_id"]), resultado="EXITO",
            detalle={"solicitud_id": str(fila["id"]), "firma_id": str(firma_id), "pdf_sha256": sha_pdf,
                     "borrador_sha256": fila["borrador_sha256"].strip(), "metodo": "RUBRICA_ELECTRONICA"},
            request=request,
        )  # fmt: skip
        for clase, sha, ruta in (("RUBRICA", sha_rubrica, ruta_rubrica), ("PDF_FIRMADO", sha_pdf, ruta_pdf)):
            await sesion.execute(
                text("""
                    INSERT INTO esart_firma.evidencias (id, documento_id, evento_id, clase, archivo_sha256, ubicacion_segura)
                    VALUES (:id, :d, :e, :c, :h, :r)
                """),
                {"id": uuid.uuid4(), "d": fila["documento_id"], "e": evento, "c": clase, "h": sha, "r": ruta},
            )
    except BaseException:
        for archivo in archivos:
            archivo.unlink(missing_ok=True)
        raise
    return (
        {
            "estado": "APROBADA",
            "documento_id": fila["documento_id"],
            "codigo_verificacion": f"F-{firma_id.hex[:8].upper()}",
            "pdf_sha256": sha_pdf,
        },
        archivos,
    )


async def estado_solicitud(sesion: AsyncSession, solicitud_id, usuario_id: int, ver_todas: bool) -> dict:
    """Estado para el PC que muestra el QR (solo quien la creó o quien administra la firma)."""
    fila = (
        (await sesion.execute(text(SQL_SOLICITUD + " WHERE s.id = :s"), {"s": solicitud_id}))
        .mappings()
        .one_or_none()
    )
    if fila is None or (
        not ver_todas
        and not await sesion.scalar(
            text("SELECT 1 FROM esart_firma.identidades WHERE id=:i AND usuario_id=:u"),
            {"i": fila["creada_por"], "u": usuario_id},
        )
    ):
        raise ErrorAplicacion(404, "SOLICITUD_NO_ENCONTRADA", "La solicitud no existe.")
    resumen = _resumen(fila)
    return {
        "solicitud_id": fila["id"],
        "documento_id": fila["documento_id"],
        "estado": resumen["estado"],
        "estado_documento": fila["estado_documento"],
        "expira_en": fila["expira_en"],
        "firmante": fila["firmante"],
        "cargo": fila["cargo"],
    }
