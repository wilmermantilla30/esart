"""
Repositorio de plantillas y formatos institucionales (panel de Parámetros).

Los archivos se guardan en esart.plantillas_formatos (BYTEA): entran en los respaldos de la base
y se publican en la misma transacción que su auditoría. Nunca se borran: se retiran.

Seguridad de lo que se sube (un documento puede ser un vector de ataque):
- Solo Excel (.xlsx, .xls), PDF y Word (.docx), hasta 25 MB.
- Se comprueba el contenido REAL, no solo la extensión: firma del archivo y estructura interna.
- Se rechazan documentos con macros (vbaProject / _VBA_PROJECT) y PDF con JavaScript o
  acciones de ejecución. Los formatos con macros (.xlsm, .docm) no se admiten.
- El nombre del archivo se limpia: nunca se usa como ruta y no puede inyectar cabeceras.
"""

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria

TAMANO_MAXIMO_BYTES = 25 * 1024 * 1024

# Extensión -> formato guardado y tipo MIME con el que se entrega.
FORMATOS = {
    ".xlsx": ("XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".xls": ("XLS", "application/vnd.ms-excel"),
    ".pdf": ("PDF", "application/pdf"),
    ".docx": ("DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}
TIPO_MIME_POR_FORMATO = {formato: mime for formato, mime in FORMATOS.values()}

FIRMA_ZIP = b"PK\x03\x04"
FIRMA_OLE = bytes.fromhex("D0CF11E0A1B11AE1")
FIRMA_PDF = b"%PDF-"
# Parte obligatoria dentro del ZIP de cada formato Office abierto.
PARTE_PRINCIPAL = {"XLSX": "xl/workbook.xml", "DOCX": "word/document.xml"}
# Marcas de contenido activo que no se aceptan.
MARCA_MACRO_OLE = "_VBA_PROJECT".encode("utf-16-le")
# Nombres PDF completos (no prefijos de otros nombres): JavaScript, lanzar programas o
# archivos incrustados. /OpenAction no se rechaza solo: muchos PDF lo usan para el zoom inicial.
PATRON_PDF_ACTIVO = re.compile(rb"/(?:JavaScript|JS|Launch|EmbeddedFile)(?![A-Za-z])")

COLUMNAS_LISTADO = """
    p.id, p.nombre_oficial, p.nombre_archivo, p.formato, p.version, p.descripcion,
    p.tamano_bytes, p.sha256, p.subido_en, u.usuario AS subido_por
"""


@dataclass(frozen=True)
class ArchivoValidado:
    nombre_archivo: str
    formato: str
    contenido: bytes
    sha256: str


def limpiar_nombre_archivo(nombre: str | None) -> str:
    """Solo el nombre (sin carpetas), con caracteres seguros para guardar y para la descarga."""
    base = re.split(r"[\\/]", nombre or "")[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return base[:200] or "documento"


def _rechazar(mensaje: str) -> ErrorAplicacion:
    return ErrorAplicacion(422, "ARCHIVO_INVALIDO", mensaje)


def _validar_office_abierto(contenido: bytes, formato: str) -> None:
    """XLSX y DOCX son ZIP: deben tener su parte principal y ningún proyecto de macros."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as libro:
            # Solo se leen los nombres de las partes: nunca se descomprime nada.
            partes = {parte.lower() for parte in libro.namelist()}
    except zipfile.BadZipFile:
        raise _rechazar("El archivo está dañado o no es un documento de Office.") from None
    if PARTE_PRINCIPAL[formato] not in partes or "[content_types].xml" not in partes:
        raise _rechazar("El contenido no corresponde a la extensión del archivo.")
    if any(parte.endswith("vbaproject.bin") for parte in partes):
        raise _rechazar("No se admiten documentos con macros.")


def validar_archivo(nombre: str | None, contenido: bytes) -> ArchivoValidado:
    """Comprueba tamaño, extensión y contenido real. Devuelve el archivo listo para guardar."""
    nombre_limpio = limpiar_nombre_archivo(nombre)
    extension = next((ext for ext in FORMATOS if nombre_limpio.lower().endswith(ext)), None)
    if extension is None:
        raise _rechazar("Solo se admiten archivos Excel (.xlsx, .xls), PDF (.pdf) y Word (.docx).")
    if not contenido:
        raise _rechazar("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise _rechazar("El archivo supera el tamaño máximo de 25 MB.")
    formato = FORMATOS[extension][0]

    if formato in PARTE_PRINCIPAL:
        if not contenido.startswith(FIRMA_ZIP):
            raise _rechazar("El contenido no corresponde a la extensión del archivo.")
        _validar_office_abierto(contenido, formato)
    elif formato == "XLS":
        if not contenido.startswith(FIRMA_OLE):
            raise _rechazar("El contenido no corresponde a la extensión del archivo.")
        if MARCA_MACRO_OLE in contenido:
            raise _rechazar("No se admiten documentos con macros.")
    elif formato == "PDF":
        if not contenido.startswith(FIRMA_PDF):
            raise _rechazar("El contenido no corresponde a la extensión del archivo.")
        if PATRON_PDF_ACTIVO.search(contenido):
            raise _rechazar("No se admiten PDF con contenido ejecutable o archivos incrustados.")

    return ArchivoValidado(nombre_limpio, formato, contenido, hashlib.sha256(contenido).hexdigest())


async def listar(sesion: AsyncSession, formato: str | None = None) -> list:
    """Plantillas vigentes (sin el contenido), las más recientes primero."""
    condicion = "AND p.formato = :formato" if formato else ""
    filas = await sesion.execute(
        text(f"""
            SELECT {COLUMNAS_LISTADO}
            FROM esart.plantillas_formatos p
            LEFT JOIN esart_ref.usuarios u ON u.id = p.subido_por_id
            WHERE p.activo {condicion}
            ORDER BY p.subido_en DESC, p.id DESC
        """),  # noqa: S608 (condicion es una constante; el valor va como parámetro)
        {"formato": formato} if formato else {},
    )
    return filas.all()


async def _obtener_activa(sesion: AsyncSession, plantilla_id: int):
    fila = (
        await sesion.execute(
            text(f"""
                SELECT {COLUMNAS_LISTADO}
                FROM esart.plantillas_formatos p
                LEFT JOIN esart_ref.usuarios u ON u.id = p.subido_por_id
                WHERE p.id = :id AND p.activo
            """),  # noqa: S608
            {"id": plantilla_id},
        )
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(404, "PLANTILLA_NO_ENCONTRADA", "La plantilla no existe o fue retirada.")
    return fila


async def publicar(
    sesion: AsyncSession,
    archivo: ArchivoValidado,
    *,
    nombre_oficial: str,
    version: str,
    descripcion: str,
    usuario_id: int,
    nombre_usuario: str,
    request: Request,
):
    """Guarda una plantilla nueva y la audita (misma transacción)."""
    repetida = await sesion.scalar(
        text("""
            SELECT 1 FROM esart.plantillas_formatos
            WHERE activo AND lower(nombre_oficial) = lower(:nombre) AND version = :version
        """),
        {"nombre": nombre_oficial, "version": version},
    )
    if repetida:
        raise ErrorAplicacion(
            409,
            "PLANTILLA_DUPLICADA",
            "Ya hay una plantilla vigente con ese nombre y versión. Use otra versión o retire la anterior.",
        )
    plantilla_id = await sesion.scalar(
        text("""
            INSERT INTO esart.plantillas_formatos
              (nombre_oficial, nombre_archivo, formato, version, descripcion,
               tamano_bytes, sha256, contenido, subido_por_id)
            VALUES (:nombre_oficial, :nombre_archivo, :formato, :version, :descripcion,
                    :tamano, :sha256, :contenido, :usuario)
            RETURNING id
        """),
        {
            "nombre_oficial": nombre_oficial,
            "nombre_archivo": archivo.nombre_archivo,
            "formato": archivo.formato,
            "version": version,
            "descripcion": descripcion,
            "tamano": len(archivo.contenido),
            "sha256": archivo.sha256,
            "contenido": archivo.contenido,
            "usuario": usuario_id,
        },
    )
    await auditoria.registrar_evento(
        sesion,
        auditoria.PLANTILLA_PUBLICADA,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "plantilla_id": plantilla_id,
            "nombre_oficial": nombre_oficial,
            "version": version,
            "formato": archivo.formato,
            "sha256": archivo.sha256,
        },
    )
    return await _obtener_activa(sesion, plantilla_id)


async def descargar(
    sesion: AsyncSession, plantilla_id: int, *, usuario_id: int, nombre_usuario: str, request: Request
) -> tuple[str, str, bytes]:
    """Devuelve (nombre de archivo, tipo MIME, contenido) y deja la descarga auditada."""
    fila = (
        await sesion.execute(
            text("""
                SELECT nombre_archivo, formato, contenido, nombre_oficial, version
                FROM esart.plantillas_formatos WHERE id = :id AND activo
            """),
            {"id": plantilla_id},
        )
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(404, "PLANTILLA_NO_ENCONTRADA", "La plantilla no existe o fue retirada.")
    await auditoria.registrar_evento(
        sesion,
        auditoria.PLANTILLA_DESCARGADA,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "plantilla_id": plantilla_id,
            "nombre_oficial": fila.nombre_oficial,
            "version": fila.version,
        },
    )
    return fila.nombre_archivo, TIPO_MIME_POR_FORMATO[fila.formato], bytes(fila.contenido)


async def retirar(
    sesion: AsyncSession, plantilla_id: int, *, usuario_id: int, nombre_usuario: str, request: Request
) -> None:
    """Deja de ofrecer la plantilla (no se borra: queda para consulta histórica y auditoría)."""
    fila = await _obtener_activa(sesion, plantilla_id)
    await sesion.execute(
        text("""
            UPDATE esart.plantillas_formatos
            SET activo = false, retirado_en = now(), retirado_por_id = :usuario
            WHERE id = :id
        """),
        {"id": plantilla_id, "usuario": usuario_id},
    )
    await auditoria.registrar_evento(
        sesion,
        auditoria.PLANTILLA_RETIRADA,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "plantilla_id": plantilla_id,
            "nombre_oficial": fila.nombre_oficial,
            "version": fila.version,
        },
    )
