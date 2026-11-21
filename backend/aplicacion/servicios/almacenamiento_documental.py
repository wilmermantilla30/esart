"""
Persistencia privada e inmutable de los PDF emitidos por ESART (esquema esart_firma, p0018).

Usa el esquema heredado conciliado (docs/ESART_P0018_CONCILIACION_DEFINITIVA.md):
- documentos / versiones_documento: tablas nuevas de p0018 (usuarios y personal reales de ESART).
- auditoria_eventos: la auditoría encadenada heredada (hash_anterior → hash_evento), no una nueva.
- evidencias: tabla heredada (archivo_sha256, ubicacion_segura) con la columna documento_id de p0018.
- identidades: el actor de la auditoría es la identidad de firma enlazada 1:1 al usuario ESART
  (identidades.usuario_id). No es otra cuenta: no tiene contraseña, TOTP ni sesión.
"""

import hashlib
import json
import os
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.seguridad.sesion_http import obtener_ip_cliente

# Serializa la cadena de hashes de auditoria_eventos entre transacciones concurrentes.
CANDADO_AUDITORIA_FIRMA = "esart_firma.auditoria_eventos"


def hash_evento_firma(anterior: str | None, campos: dict) -> str:
    """Eslabón de la cadena: sha256 del hash anterior + campos del evento en JSON canónico."""
    cuerpo = json.dumps(campos, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{anterior or ''}|{cuerpo}".encode()).hexdigest()


async def identidad_firma(sesion: AsyncSession, usuario_id: int) -> int:
    """Identidad de firma del usuario ESART (la crea enlazada si aún no existe)."""
    await sesion.execute(
        text("""
            INSERT INTO esart_firma.identidades (usuario_externo_id, nombre_mostrado, usuario_id)
            SELECT 'esart:' || u.id, coalesce(u.usuario, 'usuario ' || u.id), u.id
            FROM esart_ref.usuarios u
            WHERE u.id = :usuario
              AND NOT EXISTS (SELECT 1 FROM esart_firma.identidades i WHERE i.usuario_id = u.id)
            ON CONFLICT (usuario_externo_id) DO NOTHING
        """),
        {"usuario": usuario_id},
    )
    identidad = await sesion.scalar(
        text("SELECT id FROM esart_firma.identidades WHERE usuario_id = :usuario"), {"usuario": usuario_id}
    )
    if identidad is None:
        raise ValueError("El usuario no tiene identidad de firma enlazada.")
    return int(identidad)


async def registrar_evento_firma(
    sesion: AsyncSession,
    *,
    usuario_id: int,
    correlacion_id: uuid.UUID,
    accion: str,
    recurso_tipo: str,
    recurso_id: str,
    resultado: str,
    detalle: dict,
    request,
) -> uuid.UUID:
    """Agrega un eslabón a la auditoría encadenada heredada y devuelve su evento_id."""
    actor = await identidad_firma(sesion, usuario_id)
    await sesion.execute(text("SELECT pg_advisory_xact_lock(hashtext(:c))"), {"c": CANDADO_AUDITORIA_FIRMA})
    anterior = await sesion.scalar(
        text("SELECT hash_evento FROM esart_firma.auditoria_eventos ORDER BY id DESC LIMIT 1")
    )
    evento_id = uuid.uuid4()
    campos = {
        "evento_id": str(evento_id),
        "actor_id": actor,
        "correlacion_id": str(correlacion_id),
        "accion": accion,
        "recurso_tipo": recurso_tipo,
        "recurso_id": recurso_id,
        "resultado": resultado,
        "detalle": detalle,
    }
    await sesion.execute(
        text("""
            INSERT INTO esart_firma.auditoria_eventos
                (evento_id, actor_id, correlacion_id, accion, recurso_tipo, recurso_id, resultado,
                 ip, agente_usuario, detalle_filtrado, hash_anterior, hash_evento)
            VALUES (:evento, :actor, :correlacion, :accion, :tipo, :recurso, :resultado,
                    CAST(:ip AS inet), :agente, CAST(:detalle AS jsonb), :anterior, :hash)
        """),
        {
            "evento": evento_id,
            "actor": actor,
            "correlacion": correlacion_id,
            "accion": accion,
            "tipo": recurso_tipo,
            "recurso": recurso_id,
            "resultado": resultado,
            "ip": obtener_ip_cliente(request) if request is not None else None,
            "agente": (
                (request.headers.get("user-agent", "")[:300] or None) if request is not None else None
            ),
            "detalle": json.dumps(detalle, ensure_ascii=False),
            "anterior": anterior.strip() if anterior else None,
            "hash": hash_evento_firma(anterior.strip() if anterior else None, campos),
        },
    )
    return evento_id


def guardar_archivo_privado(raiz: Path, ruta_relativa: Path, contenido: bytes) -> tuple[str, Path, str]:
    """Escribe un archivo nuevo en la raíz privada (nunca sobrescribe); devuelve ruta, destino y sha256."""
    raiz = raiz.resolve()
    destino = (raiz / ruta_relativa).resolve()
    if not destino.is_relative_to(raiz):
        raise ValueError("La ruta documental sale del almacenamiento privado.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    descriptor = os.open(temporal, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        destino.unlink(missing_ok=True)
        raise
    return ruta_relativa.as_posix(), destino, hashlib.sha256(contenido).hexdigest()


def guardar_pdf_temporalmente(
    raiz: Path, documento_id: uuid.UUID, pdf: bytes, version: int = 1
) -> tuple[str, Path, str]:
    """Escribe un PDF con nombre aleatorio en <documento>/v<version>/, sin sobrescribir archivos previos."""
    if not pdf.startswith(b"%PDF-") or not pdf:
        raise ValueError("El archivo generado no tiene una cabecera PDF valida.")
    return guardar_archivo_privado(
        raiz, Path(str(documento_id)) / f"v{version}" / f"{uuid.uuid4().hex}.pdf", pdf
    )


async def registrar_documento(
    sesion: AsyncSession,
    *,
    directorio: Path,
    pdf: bytes,
    numero: str,
    tipo: str,
    personal_id: int,
    usuario_id: int,
    datos_emitidos: dict,
    request,
) -> tuple[uuid.UUID, Path, str, uuid.UUID]:
    """Guarda el original y encola documento + primera version en la transaccion actual.

    El llamador debe confirmar junto con el evento de auditoria. Si falla el commit,
    debe eliminar el archivo devuelto para no dejar PDF huerfanos.
    """
    documento_id = uuid.uuid4()
    version_id = uuid.uuid4()
    correlacion_id = uuid.uuid4()
    ruta, destino, sha256 = guardar_pdf_temporalmente(directorio, documento_id, pdf)
    try:
        await sesion.execute(
            text("""
                INSERT INTO esart_firma.documentos
                    (id,tipo,numero,personal_id,datos_emitidos,estado,version_actual,creado_por)
                VALUES (:id,:tipo,:numero,:personal,:datos,'BORRADOR',1,:usuario)
            """),
            {
                "id": documento_id,
                "tipo": tipo,
                "numero": numero,
                "personal": personal_id,
                "datos": json.dumps(datos_emitidos, ensure_ascii=False),
                "usuario": usuario_id,
            },
        )
        await sesion.execute(
            text("""
                INSERT INTO esart_firma.versiones_documento
                    (id,documento_id,numero_version,sha256,ubicacion_privada,tamano_bytes,creado_por)
                VALUES (:version,:documento,1,:sha,:ruta,:tamano,:usuario)
            """),
            {
                "version": version_id,
                "documento": documento_id,
                "sha": sha256,
                "ruta": ruta,
                "tamano": len(pdf),
                "usuario": usuario_id,
            },
        )
        evento_id = await registrar_evento_firma(
            sesion,
            usuario_id=usuario_id,
            correlacion_id=correlacion_id,
            accion="DOCUMENTO_GENERADO",
            recurso_tipo="DOCUMENTO",
            recurso_id=str(documento_id),
            resultado="EXITO",
            detalle={"tipo_documento": tipo, "version": 1},
            request=request,
        )
        await sesion.execute(
            text("""
                INSERT INTO esart_firma.evidencias
                    (id,documento_id,evento_id,clase,archivo_sha256,ubicacion_segura)
                VALUES (:id,:documento,:evento,'PDF_ORIGINAL',:sha,:ruta)
            """),
            {
                "id": uuid.uuid4(),
                "documento": documento_id,
                "evento": evento_id,
                "sha": sha256,
                "ruta": ruta,
            },
        )
        return documento_id, destino, sha256, correlacion_id
    except BaseException:
        destino.unlink(missing_ok=True)
        raise


def resolver_archivo_privado(raiz: Path, ruta_relativa: str) -> Path:
    """Resuelve una ruta guardada sin aceptar traversal ni enlaces fuera de la raiz."""
    base = raiz.resolve()
    ruta = (base / ruta_relativa).resolve(strict=True)
    if not ruta.is_relative_to(base) or not ruta.is_file():
        raise FileNotFoundError("Documento privado no disponible.")
    return ruta
