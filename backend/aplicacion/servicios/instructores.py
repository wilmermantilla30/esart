"""
Instructores de la Escuela de Artillería: directorio con foto y especialidades.

- MILITAR: se busca por cédula en Personal militar; nombre, grado y unidad salen de allí.
- CIVIL: se registran su documento, nombres, apellidos y profesión.
- Las especialidades vienen del catálogo esart.especialidades_instructor. Quitar una
  especialidad la desactiva (queda el historial con su fecha de asignación).
- Los instructores no se borran: se desactivan.

La foto es un dato personal (Ley 1581): solo se entrega a quien tiene el componente
INSTRUCTORES. Al subirla se comprueba que sea una imagen real y se vuelve a guardar como
JPEG reducido: así se eliminan metadatos ocultos (ubicación GPS, cámara) y cualquier
contenido que no sea la imagen.
"""

import io
import warnings
from dataclasses import dataclass
from datetime import date

from fastapi import Request
from PIL import Image, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.habilitacion import enmascarar_cedula, normalizar_cedula

TIPO_MILITAR = "MILITAR"
TIPO_CIVIL = "CIVIL"

# Foto: lo que se acepta al subir y cómo se guarda.
TAMANO_MAXIMO_FOTO_SUBIDA = 5 * 1024 * 1024
TAMANO_MAXIMO_FOTO_GUARDADA = 2 * 1024 * 1024  # mismo límite que el CHECK de la base (p0011)
LADO_MAXIMO_FOTO = 800
CALIDAD_JPEG = 85
FORMATOS_IMAGEN_ADMITIDOS = {"JPEG", "PNG", "WEBP"}
# Protección contra imágenes "bomba" (pocas KB que se expanden a gigapíxeles en memoria).
PIXELES_MAXIMOS = 40_000_000

# Columnas del listado: nombre y grado del militar o datos propios del civil.
CONSULTA_INSTRUCTORES = """
    SELECT i.id, i.tipo, i.activo, i.fecha_ingreso_escuela, i.profesion, i.actualizado_en,
           i.foto IS NOT NULL AS tiene_foto,
           COALESCE(p.documento_identidad, i.documento_identidad) AS documento,
           p.grado,
           COALESCE(p.nombres, i.nombres) AS nombres,
           COALESCE(p.apellidos, i.apellidos) AS apellidos,
           um.codigo AS unidad,
           u.usuario AS nombre_usuario,
           COALESCE(
             (SELECT json_agg(json_build_object('codigo', e.codigo, 'nombre', e.nombre) ORDER BY e.nombre)
              FROM esart.instructores_especialidades ie
              JOIN esart.especialidades_instructor e ON e.id = ie.especialidad_id
              WHERE ie.instructor_id = i.id AND ie.activo),
             '[]'::json
           ) AS especialidades
    FROM esart.instructores i
    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
    LEFT JOIN esart_ref.unidades_militares um ON um.id = p.unidad_actual_id
    -- El usuario del instructor: el enlazado (usuario_id) o, desde S2-11, el que tiene su cédula.
    LEFT JOIN esart_ref.usuarios u ON u.id = i.usuario_id OR (
      i.usuario_id IS NULL AND u.documento_identidad = COALESCE(p.documento_identidad, i.documento_identidad)
    )
"""


@dataclass(frozen=True)
class DatosInstructor:
    """Lo que se puede registrar o editar de un instructor."""

    fecha_ingreso_escuela: date
    especialidades: list[str]
    profesion: str | None = None
    nombres: str | None = None
    apellidos: str | None = None


def _instructor(fila, ver_documento_completo: bool) -> dict:
    """Fila de la consulta -> respuesta para el front (documento enmascarado según permiso)."""
    nombre = f"{fila.nombres or ''} {fila.apellidos or ''}".strip()
    return {
        "id": fila.id,
        "tipo": fila.tipo,
        "documento": enmascarar_cedula(fila.documento or "", ver_documento_completo),
        "grado": fila.grado,
        "nombres": fila.nombres,
        "apellidos": fila.apellidos,
        "nombre_completo": f"{fila.grado} {nombre}" if fila.grado else nombre,
        "unidad": fila.unidad,
        "profesion": fila.profesion,
        "fecha_ingreso_escuela": fila.fecha_ingreso_escuela,
        "activo": fila.activo,
        "tiene_foto": fila.tiene_foto,
        "version": fila.actualizado_en,
        "nombre_usuario": fila.nombre_usuario,
        "especialidades": fila.especialidades,
    }


async def especialidades(sesion: AsyncSession) -> list[dict]:
    filas = await sesion.execute(
        text("SELECT codigo, nombre FROM esart.especialidades_instructor ORDER BY nombre")
    )
    return [dict(fila._mapping) for fila in filas]


async def listar(
    sesion: AsyncSession,
    *,
    texto: str | None,
    especialidad: str | None,
    estado: str,
    ver_documento_completo: bool,
) -> list[dict]:
    """Instructores filtrados por texto (nombre, documento, profesión), especialidad y estado."""
    condiciones = []
    valores: dict = {}
    if estado == "ACTIVOS":
        condiciones.append("i.activo")
    elif estado == "INACTIVOS":
        condiciones.append("NOT i.activo")
    if texto:
        condiciones.append("""(
            concat_ws(' ', p.grado, p.nombres, p.apellidos, i.nombres, i.apellidos, i.profesion)
              ILIKE :texto
            OR COALESCE(p.documento_identidad, i.documento_identidad) LIKE :texto
        )""")
        valores["texto"] = f"%{texto.strip()}%"
    if especialidad:
        condiciones.append("""EXISTS (
            SELECT 1 FROM esart.instructores_especialidades ie
            JOIN esart.especialidades_instructor e ON e.id = ie.especialidad_id
            WHERE ie.instructor_id = i.id AND ie.activo AND e.codigo = :especialidad
        )""")
        valores["especialidad"] = especialidad
    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = await sesion.execute(
        # Las condiciones son constantes de este archivo; los valores van como parámetros.
        text(f"{CONSULTA_INSTRUCTORES} {donde} ORDER BY i.activo DESC, apellidos, nombres"),  # noqa: S608
        valores,
    )
    return [_instructor(fila, ver_documento_completo) for fila in filas]


async def obtener(sesion: AsyncSession, instructor_id: int, ver_documento_completo: bool) -> dict:
    fila = (
        await sesion.execute(text(f"{CONSULTA_INSTRUCTORES} WHERE i.id = :id"), {"id": instructor_id})  # noqa: S608
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(404, "INSTRUCTOR_NO_ENCONTRADO", "El instructor no existe.")
    return _instructor(fila, ver_documento_completo)


async def buscar_militar(sesion: AsyncSession, cedula: str, ver_documento_completo: bool) -> dict:
    """Militar de Personal militar para registrarlo como instructor (y si ya lo es)."""
    cedula = normalizar_cedula(cedula)
    fila = (
        await sesion.execute(
            text("""
                SELECT p.id, p.documento_identidad, p.grado, p.nombres, p.apellidos, p.activo,
                       um.codigo AS unidad,
                       EXISTS (SELECT 1 FROM esart.instructores i WHERE i.personal_id = p.id)
                         AS ya_es_instructor
                FROM esart.personal_militar p
                LEFT JOIN esart_ref.unidades_militares um ON um.id = p.unidad_actual_id
                WHERE p.documento_identidad = :cedula
            """),
            {"cedula": cedula},
        )
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(
            404, "MILITAR_NO_ENCONTRADO", "No hay un militar con esa cédula en Personal militar."
        )
    return {
        "documento": enmascarar_cedula(fila.documento_identidad, ver_documento_completo),
        "nombre_completo": f"{fila.grado} {fila.nombres} {fila.apellidos}",
        "unidad": fila.unidad,
        "activo": fila.activo,
        "ya_es_instructor": fila.ya_es_instructor,
    }


async def _ids_especialidades(sesion: AsyncSession, codigos: list[str]) -> dict[str, int]:
    """Código -> id de las especialidades pedidas; 422 si alguna no existe."""
    pedidas = sorted({codigo.strip().upper() for codigo in codigos if codigo.strip()})
    filas = await sesion.execute(
        text("SELECT codigo, id FROM esart.especialidades_instructor WHERE codigo = ANY(:codigos)"),
        {"codigos": pedidas},
    )
    encontradas = {fila.codigo: fila.id for fila in filas}
    faltantes = [codigo for codigo in pedidas if codigo not in encontradas]
    if faltantes:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", f"Especialidades que no existen: {', '.join(faltantes)}."
        )
    return encontradas


async def _asignar_especialidades(sesion: AsyncSession, instructor_id: int, codigos: list[str]) -> None:
    """Deja activas exactamente las especialidades pedidas (las demás se desactivan, no se borran)."""
    ids = list((await _ids_especialidades(sesion, codigos)).values())
    await sesion.execute(
        text("""
            UPDATE esart.instructores_especialidades SET activo = (especialidad_id = ANY(:ids))
            WHERE instructor_id = :instructor
        """),
        {"ids": ids, "instructor": instructor_id},
    )
    await sesion.execute(
        text("""
            INSERT INTO esart.instructores_especialidades
              (instructor_id, especialidad_id, fecha_asignacion, activo)
            SELECT :instructor, especialidad, CURRENT_DATE, true
            FROM unnest(CAST(:ids AS bigint[])) AS especialidad
            WHERE NOT EXISTS (
                SELECT 1 FROM esart.instructores_especialidades ie
                WHERE ie.instructor_id = :instructor AND ie.especialidad_id = especialidad
            )
        """),
        {"ids": ids, "instructor": instructor_id},
    )


def _texto_obligatorio(valor: str | None, campo: str) -> str:
    limpio = (valor or "").strip()
    if len(limpio) < 2:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", f"Escriba {campo}.")
    return limpio


def _validar_fecha(fecha: date, hoy: date) -> None:
    if fecha > hoy:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La fecha de ingreso a la Escuela no puede ser futura.")


async def registrar(
    sesion: AsyncSession,
    *,
    tipo: str,
    documento: str,
    datos: DatosInstructor,
    usuario_id: int,
    nombre_usuario: str,
    request: Request,
) -> int:
    """Registra un instructor militar (por cédula) o civil y sus especialidades. Devuelve el id."""
    hoy = await sesion.scalar(text("SELECT (now() AT TIME ZONE 'America/Bogota')::date"))
    _validar_fecha(datos.fecha_ingreso_escuela, hoy)
    documento = normalizar_cedula(documento)
    # Todo se valida antes de escribir: un error no deja un instructor a medias.
    await _ids_especialidades(sesion, datos.especialidades)
    if tipo == TIPO_MILITAR:
        personal = (
            await sesion.execute(
                text("SELECT id, activo FROM esart.personal_militar WHERE documento_identidad = :cedula"),
                {"cedula": documento},
            )
        ).one_or_none()
        if personal is None:
            raise ErrorAplicacion(
                404, "MILITAR_NO_ENCONTRADO", "No hay un militar con esa cédula en Personal militar."
            )
        if not personal.activo:
            raise ErrorAplicacion(409, "MILITAR_INACTIVO", "El militar figura como inactivo.")
        if await sesion.scalar(
            text("SELECT 1 FROM esart.instructores WHERE personal_id = :id"), {"id": personal.id}
        ):
            raise ErrorAplicacion(
                409, "INSTRUCTOR_EXISTENTE", "Ese militar ya está registrado como instructor."
            )
        valores = {
            "tipo": tipo,
            "personal_id": personal.id,
            "documento": None,
            "nombres": None,
            "apellidos": None,
        }
    else:
        nombres = _texto_obligatorio(datos.nombres, "los nombres")
        apellidos = _texto_obligatorio(datos.apellidos, "los apellidos")
        if await sesion.scalar(
            text("SELECT 1 FROM esart.personal_militar WHERE documento_identidad = :doc"), {"doc": documento}
        ):
            raise ErrorAplicacion(
                409, "ES_MILITAR", "Ese documento pertenece a un militar: regístrelo como instructor militar."
            )
        if await sesion.scalar(
            text("SELECT 1 FROM esart.instructores WHERE tipo = 'CIVIL' AND documento_identidad = :doc"),
            {"doc": documento},
        ):
            raise ErrorAplicacion(
                409, "INSTRUCTOR_EXISTENTE", "Ya hay un instructor civil con ese documento."
            )
        valores = {
            "tipo": tipo,
            "personal_id": None,
            "documento": documento,
            "nombres": nombres,
            "apellidos": apellidos,
        }

    instructor_id = await sesion.scalar(
        text("""
            INSERT INTO esart.instructores
              (tipo, personal_id, documento_identidad, nombres, apellidos, profesion,
               fecha_ingreso_escuela, activo)
            VALUES (:tipo, :personal_id, :documento, :nombres, :apellidos, :profesion, :fecha, true)
            RETURNING id
        """),
        {
            **valores,
            "profesion": (datos.profesion or "").strip() or None,
            "fecha": datos.fecha_ingreso_escuela,
        },
    )
    await _asignar_especialidades(sesion, instructor_id, datos.especialidades)
    await auditoria.registrar_evento(
        sesion,
        auditoria.INSTRUCTOR_REGISTRADO,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        documento=documento,
        resultado="EXITOSO",
        detalle={
            "instructor_id": instructor_id,
            "tipo": tipo,
            "especialidades": sorted(datos.especialidades),
        },
    )
    return instructor_id


async def actualizar(
    sesion: AsyncSession,
    instructor_id: int,
    datos: DatosInstructor,
    *,
    usuario_id: int,
    nombre_usuario: str,
    request: Request,
) -> None:
    """Edita fecha de ingreso, profesión, especialidades y (si es civil) nombres y apellidos."""
    actual = (
        await sesion.execute(
            text("SELECT tipo FROM esart.instructores WHERE id = :id"), {"id": instructor_id}
        )
    ).one_or_none()
    if actual is None:
        raise ErrorAplicacion(404, "INSTRUCTOR_NO_ENCONTRADO", "El instructor no existe.")
    hoy = await sesion.scalar(text("SELECT (now() AT TIME ZONE 'America/Bogota')::date"))
    _validar_fecha(datos.fecha_ingreso_escuela, hoy)
    await _ids_especialidades(sesion, datos.especialidades)
    cambios = {
        "fecha": datos.fecha_ingreso_escuela,
        "profesion": (datos.profesion or "").strip() or None,
        "id": instructor_id,
    }
    if actual.tipo == TIPO_CIVIL:
        cambios["nombres"] = _texto_obligatorio(datos.nombres, "los nombres")
        cambios["apellidos"] = _texto_obligatorio(datos.apellidos, "los apellidos")
        datos_civiles = ", nombres = :nombres, apellidos = :apellidos"
    else:
        datos_civiles = ""
    await sesion.execute(
        text(f"""
            UPDATE esart.instructores
            SET fecha_ingreso_escuela = :fecha, profesion = :profesion,
                actualizado_en = clock_timestamp() {datos_civiles}
            WHERE id = :id
        """),  # noqa: S608 (datos_civiles es una constante de este archivo)
        cambios,
    )
    await _asignar_especialidades(sesion, instructor_id, datos.especialidades)
    await auditoria.registrar_evento(
        sesion,
        auditoria.INSTRUCTOR_ACTUALIZADO,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={"instructor_id": instructor_id, "especialidades": sorted(datos.especialidades)},
    )


def preparar_foto(contenido: bytes) -> bytes:
    """
    Comprueba que el archivo sea una foto JPEG, PNG o WebP real y la devuelve como JPEG
    de máximo 800 px por lado, sin metadatos. Cualquier otra cosa: 422 FOTO_INVALIDA.
    """
    if not contenido:
        raise ErrorAplicacion(422, "FOTO_INVALIDA", "El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_FOTO_SUBIDA:
        raise ErrorAplicacion(422, "FOTO_INVALIDA", "La foto supera el tamaño máximo de 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contenido)) as imagen:
                if imagen.format not in FORMATOS_IMAGEN_ADMITIDOS:
                    raise ErrorAplicacion(422, "FOTO_INVALIDA", "La foto debe ser JPG, PNG o WebP.")
                if imagen.width * imagen.height > PIXELES_MAXIMOS:
                    raise ErrorAplicacion(
                        422, "FOTO_INVALIDA", "La foto tiene una resolución demasiado grande."
                    )
                imagen.load()  # decodifica de verdad: un archivo dañado o disfrazado falla aquí
                if imagen.mode in ("RGBA", "LA", "P"):
                    # Transparencias sobre fondo blanco (JPEG no tiene canal alfa).
                    fondo = Image.new("RGB", imagen.size, (255, 255, 255))
                    fondo.paste(imagen.convert("RGBA"), mask=imagen.convert("RGBA").split()[-1])
                    imagen_rgb = fondo
                else:
                    imagen_rgb = imagen.convert("RGB")
                imagen_rgb.thumbnail((LADO_MAXIMO_FOTO, LADO_MAXIMO_FOTO))
                salida = io.BytesIO()
                # Sin exif ni otros metadatos: solo los píxeles.
                imagen_rgb.save(salida, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
    except ErrorAplicacion:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Warning):
        raise ErrorAplicacion(422, "FOTO_INVALIDA", "El archivo no es una imagen válida.") from None
    foto = salida.getvalue()
    if len(foto) > TAMANO_MAXIMO_FOTO_GUARDADA:
        raise ErrorAplicacion(422, "FOTO_INVALIDA", "La foto no se pudo reducir a menos de 2 MB.")
    return foto


async def cambiar_foto(
    sesion: AsyncSession,
    instructor_id: int,
    foto: bytes | None,
    *,
    usuario_id: int,
    nombre_usuario: str,
    request: Request,
) -> None:
    """Guarda (o quita, si foto es None) la foto del instructor."""
    resultado = await sesion.execute(
        text("""
            UPDATE esart.instructores
            SET foto = :foto, foto_tipo = CASE WHEN :hay_foto THEN 'image/jpeg' END,
                actualizado_en = clock_timestamp()
            WHERE id = :id
        """),
        {"foto": foto, "hay_foto": foto is not None, "id": instructor_id},
    )
    if resultado.rowcount == 0:
        raise ErrorAplicacion(404, "INSTRUCTOR_NO_ENCONTRADO", "El instructor no existe.")
    await auditoria.registrar_evento(
        sesion,
        auditoria.INSTRUCTOR_ACTUALIZADO,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={"instructor_id": instructor_id, "foto": "actualizada" if foto else "retirada"},
    )


async def leer_foto(sesion: AsyncSession, instructor_id: int) -> bytes:
    foto = await sesion.scalar(
        text("SELECT foto FROM esart.instructores WHERE id = :id"), {"id": instructor_id}
    )
    if foto is None:
        raise ErrorAplicacion(404, "FOTO_NO_ENCONTRADA", "El instructor no tiene foto.")
    return bytes(foto)


async def cambiar_estado(
    sesion: AsyncSession,
    instructor_id: int,
    activo: bool,
    *,
    usuario_id: int,
    nombre_usuario: str,
    request: Request,
) -> None:
    """Activa o desactiva (nunca borra) al instructor."""
    resultado = await sesion.execute(
        text(
            "UPDATE esart.instructores SET activo = :activo, actualizado_en = clock_timestamp() "
            "WHERE id = :id"
        ),
        {"activo": activo, "id": instructor_id},
    )
    if resultado.rowcount == 0:
        raise ErrorAplicacion(404, "INSTRUCTOR_NO_ENCONTRADO", "El instructor no existe.")
    await auditoria.registrar_evento(
        sesion,
        auditoria.INSTRUCTOR_ACTIVADO if activo else auditoria.INSTRUCTOR_DESACTIVADO,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={"instructor_id": instructor_id},
    )


# --- Cursos del instructor (solo lectura) ---------------------------------------------------

# Columnas comunes de un curso para el detalle del instructor.
COLUMNAS_CURSO = """
    c.id, c.codigo, c.nombre, tc.codigo AS tipo_curso, c.fecha_inicio, c.fecha_fin, c.estado,
    (SELECT count(*) FROM esart.hoja_vida_artillero hv WHERE hv.curso_id = c.id) AS alumnos
"""


async def cursos_del_instructor(sesion: AsyncSession, instructor_id: int) -> dict:
    """
    Cursos donde el instructor es comandante (cursos.comandante_id, lo llena el cargue por
    Excel) y cursos donde participa con otro rol (cursos_instructores). Los más recientes primero.
    """
    if not await sesion.scalar(
        text("SELECT 1 FROM esart.instructores WHERE id = :id"), {"id": instructor_id}
    ):
        raise ErrorAplicacion(404, "INSTRUCTOR_NO_ENCONTRADO", "El instructor no existe.")
    comandante = await sesion.execute(
        text(f"""
            SELECT {COLUMNAS_CURSO}
            FROM esart.cursos c
            JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
            WHERE c.comandante_id = :id
            ORDER BY c.fecha_inicio DESC, c.id DESC
        """),  # noqa: S608 (COLUMNAS_CURSO es una constante de este archivo)
        {"id": instructor_id},
    )
    participa = await sesion.execute(
        text(f"""
            SELECT {COLUMNAS_CURSO}, ci.rol_en_curso
            FROM esart.cursos_instructores ci
            JOIN esart.cursos c ON c.id = ci.curso_id
            JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
            WHERE ci.instructor_id = :id
            ORDER BY c.fecha_inicio DESC, c.id DESC
        """),  # noqa: S608
        {"id": instructor_id},
    )
    return {
        "comandante": [dict(fila._mapping) for fila in comandante],
        "participa": [dict(fila._mapping) for fila in participa],
    }


async def instructor_del_usuario(sesion: AsyncSession, documento_usuario: str | None) -> int | None:
    """
    S2-11: instructor ACTIVO que corresponde a un usuario, por su cédula (el militar a través de
    Personal militar; el civil por su propia cédula). None si el usuario no es instructor.

    Con el permiso NOTAS_CARGA, el usuario solo verá los cursos y materias asignados a este
    instructor (S2-02 y S2-12): tener el permiso no basta para ver las notas de otros.
    """
    if not documento_usuario:
        return None
    return await sesion.scalar(
        text("""
            SELECT i.id
            FROM esart.instructores i
            LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
            WHERE i.activo AND COALESCE(p.documento_identidad, i.documento_identidad) = :cedula
            ORDER BY i.id
            LIMIT 1
        """),
        {"cedula": documento_usuario},
    )
