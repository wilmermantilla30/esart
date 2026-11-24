"""
S2-12: carga de notas por el instructor (componente NOTAS_CARGA).

Flujo:
1. "Mis materias": el usuario ve las materias que dicta como titular (S2-02), reconocido como
   instructor por su cédula (instructor_del_usuario, S2-11). Tener el permiso no basta: solo
   ve y carga SUS materias.
2. Descarga la plantilla Excel de una materia: los alumnos del curso (hoja_vida_artillero) y una
   columna "Nota". Una hoja oculta lleva una FIRMA (HMAC con la clave del servidor) del curso, la
   materia y la lista de alumnos: así se detecta un archivo alterado o de otra materia.
3. Sube la plantilla con las notas. Se valida todo antes de guardar nada:
   - archivo seguro (misma validación del repositorio de plantillas) y firma correcta;
   - la lista de alumnos del curso no cambió desde la descarga;
   - cada fila: alumno del curso, sin repetir, nota de 0 a 5 con máximo 2 decimales;
   - no falta la nota de ningún alumno (decisión de la Escuela: si falta una, se rechaza todo).
4. La entrega queda EN_REVISION y no cuenta para nada hasta que el Inspector la apruebe (S2-13).
   Mientras esté en revisión o devuelta, volver a subir la reemplaza; aprobada, ya no.
"""

import base64
import hashlib
import hmac
import io
import json
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.instructores import NOMBRE_VISIBLE_INSTRUCTOR, instructor_del_usuario
from aplicacion.servicios.plantillas import limpiar_nombre_archivo, validar_archivo

ESTADO_EN_REVISION = "EN_REVISION"
ESTADO_APROBADA = "APROBADA"
ESTADO_DEVUELTA = "DEVUELTA"
TIPO_MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Disposición de la plantilla (la lectura usa las mismas posiciones).
HOJA_NOTAS = "Notas"
HOJA_CONTROL = "control"
FILA_ENCABEZADO = 8
PRIMERA_FILA_ALUMNOS = FILA_ENCABEZADO + 1
COLUMNA_CEDULA = 2
COLUMNA_NOTA = 5
ENCABEZADOS = ("N.º", "Cédula", "Grado", "Apellidos y nombres", "Nota (0 a 5)")
VERSION_FIRMA = "v1"
# Límite al descomprimir el libro subido (evita archivos "bomba").
TAMANO_MAXIMO_DESCOMPRIMIDO = 50 * 1024 * 1024
MAXIMO_ERRORES = 50
NOTA_MAXIMA = Decimal("5")
DOS_DECIMALES = Decimal("0.01")


@dataclass(frozen=True)
class MateriaAsignada:
    """Curso y materia que el instructor dicta (lo que se valida antes de descargar o subir)."""

    instructor_id: int
    curso_id: int
    codigo_curso: str
    nombre_curso: str
    tipo_curso: str
    estado_curso: str
    malla_id: int
    codigo_materia: str
    materia: str
    nota_minima: Decimal | None
    instructor: str


# --- Quién es el instructor y qué materias dicta ------------------------------------------------


async def _instructor(sesion: AsyncSession, usuario: UsuarioAutenticado) -> int:
    instructor_id = await instructor_del_usuario(sesion, usuario.documento_identidad)
    if instructor_id is None:
        raise ErrorAplicacion(
            403, "NO_ES_INSTRUCTOR", "Su usuario no corresponde a un instructor activo de la Escuela."
        )
    return instructor_id


CONSULTA_MATERIAS = f"""
    SELECT a.instructor_id, c.id AS curso_id, c.codigo AS codigo_curso, c.nombre AS nombre_curso,
           tc.codigo AS tipo_curso, c.estado AS estado_curso, c.fecha_inicio, c.fecha_fin,
           m.id AS malla_id, m.orden, mt.codigo AS codigo_materia, mt.nombre AS materia,
           c.nota_minima_aprobacion AS nota_minima,
           {NOMBRE_VISIBLE_INSTRUCTOR} AS instructor,
           (SELECT count(DISTINCT hv.artillero_id) FROM esart.hoja_vida_artillero hv
            WHERE hv.curso_id = c.id) AS alumnos,
           e.id AS entrega_id, e.estado AS estado_entrega, e.subido_en, e.revisado_en,
           e.observacion_revision,
           (SELECT count(*) FROM esart.notas_entrega n WHERE n.entrega_id = e.id) AS notas_entregadas
    FROM esart.cursos_materias_instructor a
    JOIN esart.cursos c ON c.id = a.curso_id
    JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    JOIN esart.malla_curricular m ON m.id = a.malla_id
    JOIN esart.materias mt ON mt.id = m.materia_id
    JOIN esart.instructores i ON i.id = a.instructor_id
    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
    LEFT JOIN esart.entregas_notas e ON e.curso_id = c.id AND e.malla_id = m.id
    WHERE a.instructor_id = :instructor
"""  # noqa: S608 (NOMBRE_VISIBLE_INSTRUCTOR es una constante; los valores van como parámetros)


async def mis_materias(sesion: AsyncSession, usuario: UsuarioAutenticado) -> dict:
    """Materias que dicta el usuario, con el estado de su entrega de notas en cada curso."""
    instructor_id = await instructor_del_usuario(sesion, usuario.documento_identidad)
    if instructor_id is None:
        return {"es_instructor": False, "materias": []}
    filas = await sesion.execute(
        text(CONSULTA_MATERIAS + " ORDER BY c.fecha_inicio DESC, c.id DESC, m.orden"),
        {"instructor": instructor_id},
    )
    materias = []
    for fila in filas:
        datos = dict(fila._mapping)
        datos["nota_minima"] = float(datos["nota_minima"]) if datos["nota_minima"] is not None else None
        datos["puede_subir"] = (
            datos["estado_curso"] != "CANCELADO" and datos["estado_entrega"] != ESTADO_APROBADA
        )
        materias.append(datos)
    return {"es_instructor": True, "materias": materias}


async def materia_asignada(
    sesion: AsyncSession, usuario: UsuarioAutenticado, curso_id: int, malla_id: int
) -> MateriaAsignada:
    """La materia del curso, solo si el usuario es su instructor titular."""
    instructor_id = await _instructor(sesion, usuario)
    fila = (
        await sesion.execute(
            text(CONSULTA_MATERIAS + " AND a.curso_id = :curso AND a.malla_id = :malla"),
            {"instructor": instructor_id, "curso": curso_id, "malla": malla_id},
        )
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(
            403, "MATERIA_NO_ASIGNADA", "Usted no es el instructor de esa materia en ese curso."
        )
    if fila.estado_curso == "CANCELADO":
        raise ErrorAplicacion(409, "CURSO_NO_EDITABLE", "El curso está cancelado: no recibe notas.")
    return MateriaAsignada(
        instructor_id=instructor_id,
        curso_id=fila.curso_id,
        codigo_curso=fila.codigo_curso,
        nombre_curso=fila.nombre_curso,
        tipo_curso=fila.tipo_curso,
        estado_curso=fila.estado_curso,
        malla_id=fila.malla_id,
        codigo_materia=fila.codigo_materia,
        materia=fila.materia,
        nota_minima=fila.nota_minima,
        instructor=fila.instructor,
    )


async def alumnos_del_curso(sesion: AsyncSession, curso_id: int) -> list[dict]:
    """Alumnos del curso (una vez cada uno), ordenados por apellidos y nombres."""
    filas = await sesion.execute(
        text("""
            SELECT DISTINCT p.id, p.documento_identidad AS cedula, p.grado, p.apellidos, p.nombres
            FROM esart.hoja_vida_artillero hv
            JOIN esart.personal_militar p ON p.id = hv.artillero_id
            WHERE hv.curso_id = :curso
            ORDER BY p.apellidos, p.nombres, p.id
        """),
        {"curso": curso_id},
    )
    return [dict(fila._mapping) for fila in filas]


# --- Firma de la plantilla -----------------------------------------------------------------------


def _clave_firma() -> bytes:
    """Clave propia de las plantillas, derivada de la clave del servidor (nunca sale de él)."""
    secreto = obtener_configuracion().jwt_clave_secreta.get_secret_value().encode()
    return hmac.new(secreto, b"esart-plantilla-notas", hashlib.sha256).digest()


def firmar(curso_id: int, malla_id: int, alumnos: list[int]) -> str:
    """'v1.<datos en base64>.<firma>' con el curso, la materia y los ids de los alumnos."""
    datos = json.dumps({"c": curso_id, "m": malla_id, "a": sorted(alumnos)}, separators=(",", ":"))
    datos_b64 = base64.urlsafe_b64encode(datos.encode()).decode()
    firma = hmac.new(_clave_firma(), datos_b64.encode(), hashlib.sha256).hexdigest()
    return f"{VERSION_FIRMA}.{datos_b64}.{firma}"


def leer_firma(token: object) -> dict | None:
    """Los datos firmados, o None si falta la firma o no coincide (archivo alterado)."""
    if not isinstance(token, str) or token.count(".") != 2:
        return None
    version, datos_b64, firma = token.split(".")
    esperada = hmac.new(_clave_firma(), datos_b64.encode(), hashlib.sha256).hexdigest()
    if version != VERSION_FIRMA or not hmac.compare_digest(firma, esperada):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(datos_b64.encode()))
    except ValueError:
        return None


# --- Plantilla -----------------------------------------------------------------------------------


async def generar_plantilla(
    sesion: AsyncSession, usuario: UsuarioAutenticado, curso_id: int, malla_id: int
) -> tuple[str, bytes]:
    """Nombre del archivo y contenido de la plantilla de la materia, con los alumnos del curso."""
    materia = await materia_asignada(sesion, usuario, curso_id, malla_id)
    alumnos = await alumnos_del_curso(sesion, curso_id)
    if not alumnos:
        raise ErrorAplicacion(409, "CURSO_SIN_ALUMNOS", "El curso no tiene alumnos registrados.")

    libro = Workbook()
    hoja = libro.active
    hoja.title = HOJA_NOTAS
    negrita = Font(bold=True)
    hoja["A1"] = "ESART — Planilla de notas"
    hoja["A1"].font = Font(bold=True, size=14)
    datos = (
        ("Curso", f"{materia.tipo_curso} · {materia.codigo_curso} — {materia.nombre_curso}"),
        ("Materia", f"{materia.materia} ({materia.codigo_materia})"),
        ("Instructor", materia.instructor),
        ("Nota mínima", f"{materia.nota_minima:.2f}" if materia.nota_minima is not None else "—"),
        (
            "Instrucciones",
            "Escriba la nota de cada alumno de 0 a 5 con máximo 2 decimales. No cambie las demás celdas.",
        ),
    )
    for numero, (etiqueta, valor) in enumerate(datos, start=2):
        hoja.cell(numero, 1, etiqueta).font = negrita
        hoja.cell(numero, 2, valor)

    relleno = PatternFill("solid", start_color="1F3A5F")
    borde = Border(*(Side(style="thin", color="BFC7D5"),) * 4)
    for columna, titulo in enumerate(ENCABEZADOS, start=1):
        celda = hoja.cell(FILA_ENCABEZADO, columna, titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = relleno
        celda.alignment = Alignment(horizontal="center")
    editable = PatternFill("solid", start_color="FFF6D5")
    for posicion, alumno in enumerate(alumnos):
        fila = PRIMERA_FILA_ALUMNOS + posicion
        valores = (
            posicion + 1,
            alumno["cedula"],
            alumno["grado"],
            f"{alumno['apellidos']} {alumno['nombres']}",
        )
        for columna, valor in enumerate(valores, start=1):
            hoja.cell(fila, columna, valor).border = borde
        nota = hoja.cell(fila, COLUMNA_NOTA)
        nota.number_format = "0.00"
        nota.fill = editable
        nota.border = borde
        nota.protection = Protection(locked=False)
    ultima = PRIMERA_FILA_ALUMNOS + len(alumnos) - 1
    validacion = DataValidation(
        type="decimal",
        operator="between",
        formula1="0",
        formula2="5",
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Nota no válida",
        error="La nota debe estar entre 0 y 5.",
    )
    hoja.add_data_validation(validacion)
    validacion.add(f"E{PRIMERA_FILA_ALUMNOS}:E{ultima}")
    for columna, ancho in zip("ABCDE", (6, 16, 10, 42, 14), strict=True):
        hoja.column_dimensions[columna].width = ancho
    hoja.freeze_panes = hoja.cell(PRIMERA_FILA_ALUMNOS, 1)
    # Protección sin contraseña: evita cambios accidentales (la firma detecta los demás).
    hoja.protection.sheet = True

    control = libro.create_sheet(HOJA_CONTROL)
    control["A1"] = firmar(curso_id, malla_id, [alumno["id"] for alumno in alumnos])
    control.sheet_state = "veryHidden"

    salida = io.BytesIO()
    libro.save(salida)
    nombre = limpiar_nombre_archivo(f"Notas_{materia.codigo_curso}_{materia.codigo_materia}.xlsx")
    return nombre, salida.getvalue()


# --- Carga ---------------------------------------------------------------------------------------


def _texto(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def leer_nota(valor: object) -> Decimal:
    """Convierte la celda a nota. Acepta número o texto con coma o punto. ValueError con el motivo."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ValueError("Falta la nota.")
    if isinstance(valor, bool):
        raise ValueError("La nota debe ser un número.")
    try:
        nota = (
            Decimal(str(valor).strip().replace(",", ".")) if isinstance(valor, str) else Decimal(repr(valor))
        )
    except InvalidOperation:
        raise ValueError("La nota debe ser un número.") from None
    if not nota.is_finite():
        raise ValueError("La nota debe ser un número.")
    # Excel guarda 3,45 como 3.4500000000000002: se tolera el ruido de coma flotante.
    redondeada = nota.quantize(DOS_DECIMALES)
    if abs(nota - redondeada) > Decimal("0.000001"):
        raise ValueError("La nota admite como máximo 2 decimales.")
    if not Decimal(0) <= redondeada <= NOTA_MAXIMA:
        raise ValueError("La nota debe estar entre 0 y 5.")
    return redondeada


def _abrir_libro(contenido: bytes):
    """Abre el XLSX ya validado, con un límite al descomprimir."""
    with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
        if sum(parte.file_size for parte in archivo.infolist()) > TAMANO_MAXIMO_DESCOMPRIMIDO:
            raise ErrorAplicacion(
                422, "ARCHIVO_INVALIDO", "El archivo es demasiado grande al descomprimirlo."
            )
    try:
        return load_workbook(io.BytesIO(contenido), read_only=True, data_only=True, keep_links=False)
    except Exception:
        raise ErrorAplicacion(422, "ARCHIVO_INVALIDO", "No fue posible leer el Excel.") from None


def leer_planilla(contenido: bytes, curso_id: int, malla_id: int, alumnos: list[dict]) -> dict[int, Decimal]:
    """
    Lee y valida la plantilla subida. Devuelve {personal_id: nota} con TODOS los alumnos.
    Si algo falla, 422 con la lista de filas a corregir (no se guarda nada).
    """
    libro = _abrir_libro(contenido)
    try:
        if HOJA_CONTROL not in libro.sheetnames or HOJA_NOTAS not in libro.sheetnames:
            raise _alterada()
        firmado = leer_firma(
            next(libro[HOJA_CONTROL].iter_rows(min_row=1, max_row=1, values_only=True), (None,))[0]
        )
        if firmado is None:
            raise _alterada()
        if (firmado.get("c"), firmado.get("m")) != (curso_id, malla_id):
            raise ErrorAplicacion(
                422, "PLANTILLA_DE_OTRA_MATERIA", "Esta plantilla es de otro curso o de otra materia."
            )
        if firmado.get("a") != sorted(alumno["id"] for alumno in alumnos):
            raise ErrorAplicacion(
                409,
                "PLANTILLA_DESACTUALIZADA",
                "La lista de alumnos del curso cambió desde que descargó la plantilla: descárguela de nuevo.",
            )
        por_cedula = {re.sub(r"\D", "", alumno["cedula"]): alumno for alumno in alumnos}
        hoja = libro[HOJA_NOTAS]
        errores: list[dict] = []
        notas: dict[int, Decimal] = {}
        maxima = PRIMERA_FILA_ALUMNOS + len(alumnos) + 200  # filas extra: se revisan por si traen datos
        for numero, fila in enumerate(
            hoja.iter_rows(
                min_row=PRIMERA_FILA_ALUMNOS, max_row=maxima, max_col=COLUMNA_NOTA, values_only=True
            ),
            start=PRIMERA_FILA_ALUMNOS,
        ):
            fila = tuple(fila) + (None,) * (COLUMNA_NOTA - len(fila))
            cedula = re.sub(r"\D", "", _texto(fila[COLUMNA_CEDULA - 1]))
            valor_nota = fila[COLUMNA_NOTA - 1]
            if not cedula and (valor_nota is None or _texto(valor_nota) == ""):
                continue
            alumno = por_cedula.get(cedula)
            if alumno is None:
                errores.append({"fila": numero, "mensaje": "La cédula no corresponde a un alumno del curso."})
                continue
            if alumno["id"] in notas:
                errores.append({"fila": numero, "mensaje": "El alumno aparece dos veces."})
                continue
            try:
                notas[alumno["id"]] = leer_nota(valor_nota)
            except ValueError as motivo:
                errores.append({"fila": numero, "mensaje": str(motivo)})
                notas[alumno["id"]] = None  # visto, aunque con error
        faltantes = [a for a in alumnos if a["id"] not in notas]
        for alumno in faltantes:
            errores.append(
                {"fila": None, "mensaje": f"Falta el alumno {alumno['cedula']} ({alumno['apellidos']})."}
            )
        if errores:
            raise ErrorAplicacion(
                422,
                "NOTAS_INVALIDAS",
                f"La planilla tiene {len(errores)} error(es). Corríjalos y súbala de nuevo: "
                "no se guardó nada.",
                {"errores": errores[:MAXIMO_ERRORES]},
            )
        return notas
    finally:
        libro.close()


def _alterada() -> ErrorAplicacion:
    return ErrorAplicacion(
        422,
        "PLANTILLA_ALTERADA",
        "El archivo no es la plantilla descargada de la plataforma o fue modificado. Descárguela de nuevo.",
    )


async def subir_planilla(
    sesion: AsyncSession,
    usuario: UsuarioAutenticado,
    curso_id: int,
    malla_id: int,
    nombre_archivo: str | None,
    contenido: bytes,
    *,
    actor: Actor,
) -> dict:
    """Valida la planilla y la guarda como entrega EN_REVISION (reemplaza la anterior si se puede)."""
    materia = await materia_asignada(sesion, usuario, curso_id, malla_id)
    anterior = (
        await sesion.execute(
            text(
                "SELECT id, estado FROM esart.entregas_notas WHERE curso_id = :c AND malla_id = :m FOR UPDATE"
            ),
            {"c": curso_id, "m": malla_id},
        )
    ).one_or_none()
    if anterior is not None and anterior.estado == ESTADO_APROBADA:
        raise ErrorAplicacion(
            409,
            "ENTREGA_APROBADA",
            "El Inspector ya aprobó estas notas. Para corregirlas, pídale que devuelva la entrega.",
        )
    archivo = validar_archivo(nombre_archivo, contenido)
    if archivo.formato != "XLSX":
        raise ErrorAplicacion(
            422, "ARCHIVO_INVALIDO", "Suba la plantilla descargada de la plataforma (.xlsx)."
        )
    alumnos = await alumnos_del_curso(sesion, curso_id)
    notas = leer_planilla(archivo.contenido, curso_id, malla_id, alumnos)

    parametros = {
        "c": curso_id,
        "m": malla_id,
        "instructor": materia.instructor_id,
        "nombre": archivo.nombre_archivo,
        "sha": archivo.sha256,
        "usuario": actor.usuario_id,
    }
    if anterior is None:
        entrega_id = await sesion.scalar(
            text("""
                INSERT INTO esart.entregas_notas
                  (curso_id, malla_id, instructor_id, nombre_archivo, sha256, subido_por_id)
                VALUES (:c, :m, :instructor, :nombre, :sha, :usuario)
                RETURNING id
            """),
            parametros,
        )
    else:
        entrega_id = anterior.id
        # Una nueva carga vuelve a revisión y borra la revisión anterior (la auditoría la conserva).
        await sesion.execute(
            text("""
                UPDATE esart.entregas_notas
                SET instructor_id = :instructor, estado = 'EN_REVISION', nombre_archivo = :nombre,
                    sha256 = :sha, subido_por_id = :usuario, subido_en = now(),
                    revisado_por_id = NULL, revisado_en = NULL, observacion_revision = NULL
                WHERE id = :id
            """),
            {**parametros, "id": entrega_id},
        )
        await sesion.execute(
            text("DELETE FROM esart.notas_entrega WHERE entrega_id = :id"), {"id": entrega_id}
        )
    await sesion.execute(
        text("INSERT INTO esart.notas_entrega (entrega_id, personal_id, nota) VALUES (:e, :p, :n)"),
        [{"e": entrega_id, "p": personal_id, "n": nota} for personal_id, nota in notas.items()],
    )
    promedio = sum(notas.values()) / len(notas)
    minima = materia.nota_minima
    # registrar_evento confirma: la entrega y su auditoría quedan juntas o no quedan.
    await auditoria.registrar_evento(
        sesion,
        auditoria.NOTAS_ENTREGADAS,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "curso": materia.codigo_curso,
            "materia": materia.materia,
            "alumnos": len(notas),
            "promedio": str(promedio.quantize(DOS_DECIMALES)),
            "por_debajo_de_la_minima": sum(
                1 for nota in notas.values() if minima is not None and nota < minima
            ),
            "reemplaza": anterior.estado if anterior else None,
            "sha256": archivo.sha256,
        },
    )
    return await entrega(sesion, usuario, curso_id, malla_id)


async def entrega(sesion: AsyncSession, usuario: UsuarioAutenticado, curso_id: int, malla_id: int) -> dict:
    """La entrega del instructor para esa materia, con la nota de cada alumno (o None si no ha subido)."""
    materia = await materia_asignada(sesion, usuario, curso_id, malla_id)
    fila = (
        await sesion.execute(
            text("""
                SELECT e.id, e.estado, e.nombre_archivo, e.subido_en, u.usuario AS subido_por,
                       e.revisado_en, e.observacion_revision
                FROM esart.entregas_notas e
                LEFT JOIN esart_ref.usuarios u ON u.id = e.subido_por_id
                WHERE e.curso_id = :c AND e.malla_id = :m
            """),
            {"c": curso_id, "m": malla_id},
        )
    ).one_or_none()
    notas = []
    if fila is not None:
        notas = [
            {**dict(n._mapping), "nota": float(n.nota)}
            for n in await sesion.execute(
                text("""
                    SELECT p.documento_identidad AS cedula, p.grado, p.apellidos, p.nombres, n.nota
                    FROM esart.notas_entrega n
                    JOIN esart.personal_militar p ON p.id = n.personal_id
                    WHERE n.entrega_id = :e
                    ORDER BY p.apellidos, p.nombres
                """),
                {"e": fila.id},
            )
        ]
    return {
        "curso_id": materia.curso_id,
        "codigo_curso": materia.codigo_curso,
        "materia": materia.materia,
        "nota_minima": float(materia.nota_minima) if materia.nota_minima is not None else None,
        "entrega": (
            {
                "estado": fila.estado,
                "nombre_archivo": fila.nombre_archivo,
                "subido_en": fila.subido_en,
                "subido_por": fila.subido_por,
                "revisado_en": fila.revisado_en,
                "observacion_revision": fila.observacion_revision,
                "notas": notas,
            }
            if fila is not None
            else None
        ),
    }
