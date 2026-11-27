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
   S2-16: la fase de campaña (materia calificada por ítems) la registra el COMANDANTE del curso
   con una columna por ítem donde marca "X" en los aprobados; la nota es la suma de los puntajes.
4. La entrega queda EN_REVISION y no cuenta para nada hasta que el Inspector la apruebe (S2-13).
   Mientras esté en revisión o devuelta, volver a subir la reemplaza; aprobada, solo si el
   Inspector la reabre (las notas oficiales siguen vigentes hasta la nueva aprobación).
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
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria, campana
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.instructores import NOMBRE_VISIBLE_INSTRUCTOR, instructor_del_usuario
from aplicacion.servicios.plantillas import limpiar_nombre_archivo, validar_archivo

ESTADO_EN_REVISION = "EN_REVISION"
ESTADO_APROBADA = "APROBADA"
ESTADO_DEVUELTA = "DEVUELTA"
# Tipos de entrega (p0024): la planilla de S2-12 y la habilitación de S2-14.
TIPO_ORDINARIA = "ORDINARIA"
TIPO_HABILITACION = "HABILITACION"
TIPO_MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Disposición de la plantilla (la lectura usa las mismas posiciones).
HOJA_NOTAS = "Notas"
HOJA_CONTROL = "control"
FILA_ENCABEZADO = 8
PRIMERA_FILA_ALUMNOS = FILA_ENCABEZADO + 1
COLUMNA_CEDULA = 2
COLUMNA_NOTA = 5
# Fase de campaña (S2-16): los ítems van desde la columna de la nota en adelante.
COLUMNA_PRIMER_ITEM = COLUMNA_NOTA
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
    # S2-16: la registra el comandante marcando ítems (fase de campaña).
    por_items: bool = False


# --- Quién es el instructor y qué materias dicta ------------------------------------------------


async def _instructor(sesion: AsyncSession, usuario: UsuarioAutenticado) -> int:
    instructor_id = await instructor_del_usuario(sesion, usuario.documento_identidad)
    if instructor_id is None:
        raise ErrorAplicacion(
            403, "NO_ES_INSTRUCTOR", "Su usuario no corresponde a un instructor activo de la Escuela."
        )
    return instructor_id


# Quién registra cada materia: su instructor titular (S2-02) o, si se califica por ítems (fase de
# campaña, S2-16), el comandante del curso.
ASIGNACIONES = f"""
    SELECT cmi.curso_id, cmi.malla_id, cmi.instructor_id
    FROM esart.cursos_materias_instructor cmi
    JOIN esart.malla_curricular mm ON mm.id = cmi.malla_id
    WHERE NOT {campana.condicion_por_items("mm.materia_id")}
    UNION ALL
    SELECT cc.id, mm.id, cc.comandante_id
    FROM esart.cursos cc
    JOIN esart.malla_curricular mm ON mm.version_id = cc.malla_version_id
    WHERE mm.evaluable AND {campana.condicion_por_items("mm.materia_id")}
"""  # noqa: S608 (texto fijo)

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
           (SELECT count(*) FROM esart.notas_entrega n WHERE n.entrega_id = e.id) AS notas_entregadas,
           EXISTS (SELECT 1 FROM esart.notas_oficiales o
                   WHERE o.curso_id = c.id AND o.malla_id = m.id) AS tiene_notas_oficiales,
           (SELECT count(*) FROM esart.notas_oficiales o
            WHERE o.curso_id = c.id AND o.malla_id = m.id
              AND o.nota_ordinaria < c.nota_minima_aprobacion) AS alumnos_a_habilitar,
           h.estado AS estado_habilitacion, h.observacion_revision AS observacion_habilitacion,
           {campana.condicion_por_items("m.materia_id")} AS por_items
    FROM ({ASIGNACIONES}) a
    JOIN esart.cursos c ON c.id = a.curso_id
    JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    JOIN esart.malla_curricular m ON m.id = a.malla_id
    JOIN esart.materias mt ON mt.id = m.materia_id
    JOIN esart.instructores i ON i.id = a.instructor_id
    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
    LEFT JOIN esart.entregas_notas e ON e.curso_id = c.id AND e.malla_id = m.id AND e.tipo = 'ORDINARIA'
    LEFT JOIN esart.entregas_notas h ON h.curso_id = c.id AND h.malla_id = m.id AND h.tipo = 'HABILITACION'
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
            403,
            "MATERIA_NO_ASIGNADA",
            "Usted no es el instructor de esa materia en ese curso "
            "(la fase de campaña la registra el comandante).",
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
        por_items=fila.por_items,
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


def firmar(curso_id: int, malla_id: int, alumnos: list[int], items: list | None = None) -> str:
    """'v1.<datos en base64>.<firma>' con el curso, la materia, los ids de los alumnos y (fase de
    campaña) los ítems con su puntaje."""
    contenido = {"c": curso_id, "m": malla_id, "a": sorted(alumnos)}
    if items:
        contenido["i"] = items
    datos = json.dumps(contenido, separators=(",", ":"))
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
    items = await campana.items_de_malla(sesion, malla_id) if materia.por_items else []

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
            (
                f"Marque {campana.MARCA_APROBADO} en cada ítem aprobado y deje vacío el no aprobado. "
                "La nota es la suma de los puntajes aprobados. No cambie las demás celdas."
            )
            if items
            else "Escriba la nota de cada alumno de 0 a 5 con máximo 2 decimales. No cambie las demás "
            "celdas.",
        ),
    )
    for numero, (etiqueta, valor) in enumerate(datos, start=2):
        hoja.cell(numero, 1, etiqueta).font = negrita
        hoja.cell(numero, 2, valor)

    relleno = PatternFill("solid", start_color="1F3A5F")
    borde = Border(*(Side(style="thin", color="BFC7D5"),) * 4)
    if items:
        _hoja_de_items(hoja, alumnos, items, relleno, borde)
        control = libro.create_sheet(HOJA_CONTROL)
        control["A1"] = firmar(
            curso_id, malla_id, [alumno["id"] for alumno in alumnos], campana.firma_de_items(items)
        )
        control.sheet_state = "veryHidden"
        salida = io.BytesIO()
        libro.save(salida)
        nombre = limpiar_nombre_archivo(f"Campana_{materia.codigo_curso}_{materia.codigo_materia}.xlsx")
        return nombre, salida.getvalue()
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


def _hoja_de_items(hoja, alumnos: list[dict], items: list[dict], relleno, borde) -> None:
    """Fase de campaña: un alumno por fila y una columna por ítem (marca X), más la nota calculada."""
    titulos = [
        *ENCABEZADOS[:4],
        *(f"{item['orden']}. {item['nombre']} ({Decimal(item['puntaje']):.4f})" for item in items),
        "Nota (calculada)",
    ]
    for columna, titulo in enumerate(titulos, start=1):
        celda = hoja.cell(FILA_ENCABEZADO, columna, titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = relleno
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    hoja.row_dimensions[FILA_ENCABEZADO].height = 90
    # Fila oculta con el puntaje de cada ítem: la usa la fórmula de la nota.
    fila_puntajes = FILA_ENCABEZADO - 1
    for posicion, item in enumerate(items):
        hoja.cell(fila_puntajes, COLUMNA_PRIMER_ITEM + posicion, float(item["puntaje"]))
    hoja.row_dimensions[fila_puntajes].hidden = True
    editable = PatternFill("solid", start_color="FFF6D5")
    primera = get_column_letter(COLUMNA_PRIMER_ITEM)
    ultima_item = get_column_letter(COLUMNA_PRIMER_ITEM + len(items) - 1)
    columna_nota = COLUMNA_PRIMER_ITEM + len(items)
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
        for desplazamiento in range(len(items)):
            celda = hoja.cell(fila, COLUMNA_PRIMER_ITEM + desplazamiento)
            celda.fill = editable
            celda.border = borde
            celda.alignment = Alignment(horizontal="center")
            celda.protection = Protection(locked=False)
        # Solo para ver la nota mientras se marca; la plataforma la vuelve a calcular al subir.
        nota = hoja.cell(
            fila,
            columna_nota,
            f'=MIN(5,ROUND(SUMPRODUCT((UPPER(TRIM({primera}{fila}:{ultima_item}{fila}))="X")'
            f"*{primera}${fila_puntajes}:{ultima_item}${fila_puntajes}),2))",
        )
        nota.number_format = "0.00"
        nota.border = borde
    ultima_fila = PRIMERA_FILA_ALUMNOS + len(alumnos) - 1
    validacion = DataValidation(
        type="list",
        formula1=f'"{campana.MARCA_APROBADO}"',
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Marca no válida",
        error=f"Escriba {campana.MARCA_APROBADO} si aprobó o deje la celda vacía.",
    )
    hoja.add_data_validation(validacion)
    validacion.add(f"{primera}{PRIMERA_FILA_ALUMNOS}:{ultima_item}{ultima_fila}")
    for columna, ancho in zip("ABCD", (6, 16, 10, 38), strict=True):
        hoja.column_dimensions[columna].width = ancho
    for desplazamiento in range(len(items) + 1):
        hoja.column_dimensions[get_column_letter(COLUMNA_PRIMER_ITEM + desplazamiento)].width = 14
    hoja.freeze_panes = hoja.cell(PRIMERA_FILA_ALUMNOS, COLUMNA_PRIMER_ITEM)
    hoja.protection.sheet = True


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


def leer_planilla(
    contenido: bytes, curso_id: int, malla_id: int, alumnos: list[dict], items: list[dict] | None = None
) -> tuple[dict[int, Decimal], dict[int, set[int]]]:
    """
    Lee y valida la plantilla subida. Devuelve ({personal_id: nota}, {personal_id: ítems aprobados})
    con TODOS los alumnos (el segundo vacío si la materia no se califica por ítems).
    Si algo falla, 422 con la lista de filas a corregir (no se guarda nada).
    """
    items = items or []
    aprobados: dict[int, set[int]] = {}
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
        if (firmado.get("i") or []) != campana.firma_de_items(items):
            raise ErrorAplicacion(
                409,
                "PLANTILLA_DESACTUALIZADA",
                "Los ítems o puntajes de la fase de campaña cambiaron desde que descargó la plantilla: "
                "descárguela de nuevo.",
            )
        ultima_columna = COLUMNA_PRIMER_ITEM + len(items) - 1 if items else COLUMNA_NOTA
        por_cedula = {re.sub(r"\D", "", alumno["cedula"]): alumno for alumno in alumnos}
        hoja = libro[HOJA_NOTAS]
        errores: list[dict] = []
        notas: dict[int, Decimal] = {}
        maxima = PRIMERA_FILA_ALUMNOS + len(alumnos) + 200  # filas extra: se revisan por si traen datos
        for numero, fila in enumerate(
            hoja.iter_rows(
                min_row=PRIMERA_FILA_ALUMNOS, max_row=maxima, max_col=ultima_columna, values_only=True
            ),
            start=PRIMERA_FILA_ALUMNOS,
        ):
            fila = tuple(fila) + (None,) * (ultima_columna - len(fila))
            cedula = re.sub(r"\D", "", _texto(fila[COLUMNA_CEDULA - 1]))
            valores = fila[COLUMNA_NOTA - 1 :] if items else (fila[COLUMNA_NOTA - 1],)
            if not cedula and all(valor is None or _texto(valor) == "" for valor in valores):
                continue
            alumno = por_cedula.get(cedula)
            if alumno is None:
                errores.append({"fila": numero, "mensaje": "La cédula no corresponde a un alumno del curso."})
                continue
            if alumno["id"] in notas:
                errores.append({"fila": numero, "mensaje": "El alumno aparece dos veces."})
                continue
            if items:
                notas[alumno["id"]] = _nota_por_items(fila, items, numero, errores, aprobados, alumno["id"])
                continue
            try:
                notas[alumno["id"]] = leer_nota(fila[COLUMNA_NOTA - 1])
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
        return notas, aprobados
    finally:
        libro.close()


def _nota_por_items(
    fila: tuple, items: list[dict], numero: int, errores: list[dict], aprobados: dict, personal_id: int
) -> Decimal | None:
    """Nota de la fase de campaña de una fila: suma de los puntajes de los ítems marcados con X."""
    marcados: set[int] = set()
    valida = True
    for posicion, item in enumerate(items):
        try:
            if campana.leer_marca(fila[COLUMNA_PRIMER_ITEM - 1 + posicion]):
                marcados.add(item["id"])
        except ValueError as motivo:
            errores.append({"fila": numero, "mensaje": f"Ítem {item['orden']}: {motivo}"})
            valida = False
    aprobados[personal_id] = marcados
    if not valida:
        return None
    return campana.nota_de_items([Decimal(item["puntaje"]) for item in items if item["id"] in marcados])


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
    anterior = await entrega_reemplazable(sesion, materia, TIPO_ORDINARIA)
    archivo = validar_archivo(nombre_archivo, contenido)
    if archivo.formato != "XLSX":
        raise ErrorAplicacion(
            422, "ARCHIVO_INVALIDO", "Suba la plantilla descargada de la plataforma (.xlsx)."
        )
    alumnos = await alumnos_del_curso(sesion, curso_id)
    items = await campana.items_de_malla(sesion, malla_id) if materia.por_items else []
    notas, aprobados = leer_planilla(archivo.contenido, curso_id, malla_id, alumnos, items)
    await guardar_entrega(
        sesion,
        materia,
        TIPO_ORDINARIA,
        anterior,
        archivo.nombre_archivo,
        archivo.sha256,
        notas,
        actor=actor,
        items=items,
        aprobados=aprobados,
    )
    return await entrega(sesion, usuario, curso_id, malla_id)


async def entrega_reemplazable(sesion: AsyncSession, materia: MateriaAsignada, tipo: str):
    """La entrega anterior de ese tipo, reservada hasta el commit (None si no hay); 409 si está aprobada."""
    anterior = (
        await sesion.execute(
            text("""
                SELECT id, estado FROM esart.entregas_notas
                WHERE curso_id = :c AND malla_id = :m AND tipo = :tipo
                FOR UPDATE
            """),
            {"c": materia.curso_id, "m": materia.malla_id, "tipo": tipo},
        )
    ).one_or_none()
    if anterior is not None and anterior.estado == ESTADO_APROBADA:
        raise ErrorAplicacion(
            409,
            "ENTREGA_APROBADA",
            "El Inspector ya aprobó estas notas. Para corregirlas, pídale que reabra la entrega.",
        )
    return anterior


async def guardar_entrega(
    sesion: AsyncSession,
    materia: MateriaAsignada,
    tipo: str,
    anterior,
    nombre_archivo: str,
    sha256: str,
    notas: dict[int, Decimal],
    *,
    actor: Actor,
    items: list[dict] | None = None,
    aprobados: dict[int, set[int]] | None = None,
) -> None:
    """Guarda la entrega (nueva o reemplazo) EN_REVISION con sus notas y la audita. Común a la planilla
    ordinaria (S2-12) y a la habilitación (S2-14)."""
    parametros = {
        "c": materia.curso_id,
        "m": materia.malla_id,
        "tipo": tipo,
        "instructor": materia.instructor_id,
        "nombre": nombre_archivo,
        "sha": sha256,
        "usuario": actor.usuario_id,
    }
    if anterior is None:
        entrega_id = await sesion.scalar(
            text("""
                INSERT INTO esart.entregas_notas
                  (curso_id, malla_id, tipo, instructor_id, nombre_archivo, sha256, subido_por_id)
                VALUES (:c, :m, :tipo, :instructor, :nombre, :sha, :usuario)
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
    if items:
        # Fase de campaña: qué ítem aprobó cada alumno y con qué puntaje se calificó.
        await sesion.execute(
            text("DELETE FROM esart.items_entrega WHERE entrega_id = :id"), {"id": entrega_id}
        )
        await sesion.execute(
            text("""
                INSERT INTO esart.items_entrega (entrega_id, personal_id, item_id, aprobado, puntaje)
                VALUES (:e, :p, :i, :a, :puntaje)
            """),
            [
                {
                    "e": entrega_id,
                    "p": personal_id,
                    "i": item["id"],
                    "a": item["id"] in (aprobados or {}).get(personal_id, set()),
                    "puntaje": item["puntaje"],
                }
                for personal_id in notas
                for item in items
            ],
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
            "tipo": tipo,
            "curso": materia.codigo_curso,
            "materia": materia.materia,
            "alumnos": len(notas),
            "promedio": str(promedio.quantize(DOS_DECIMALES)),
            "por_debajo_de_la_minima": sum(
                1 for nota in notas.values() if minima is not None and nota < minima
            ),
            "reemplaza": anterior.estado if anterior else None,
            "sha256": sha256,
            "por_items": bool(items),
        },
    )


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
                WHERE e.curso_id = :c AND e.malla_id = :m AND e.tipo = 'ORDINARIA'
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
