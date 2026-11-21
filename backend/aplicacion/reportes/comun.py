"""
Piezas comunes de los documentos PDF: datos de entrada, estilos, membrete y pie de página.

Los scripts de cada documento (diploma.py, oficio_remisorio.py, certificacion.py) solo reciben un
DatosDocumento: no consultan la base de datos. Así se pueden probar y generar sin PostgreSQL, y la
consulta (con sus permisos y su auditoría) queda en el servicio servicios/documentos_artillero.py.

Textos institucionales (nombre de la escuela, firmante, ciudad) están en las constantes de este
archivo para cambiarlos en un solo lugar.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --- Textos institucionales ---------------------------------------------------------------
INSTITUCION = "EJÉRCITO NACIONAL DE COLOMBIA"
ESCUELA = "ESCUELA DE ARTILLERÍA"
ESCUELA_TEXTO = "Escuela de Artillería"  # dentro de los párrafos
LEMA = "Patria, Honor, Lealtad"
CIUDAD = "Bogotá D.C."
FIRMANTE_NOMBRE = "Director de la Escuela de Artillería"
FIRMANTE_CARGO = "Escuela de Artillería — ESART"
SISTEMA = "ESART — Sistema de gestión del personal artillero"

# --- Colores institucionales --------------------------------------------------------------
AZUL = colors.HexColor("#0B5D7A")
AZUL_CLARO = colors.HexColor("#E6F4FA")
GRIS = colors.HexColor("#4B6577")
VERDE = colors.HexColor("#15803D")
ROJO = colors.HexColor("#B91C1C")
DORADO = colors.HexColor("#B08D2E")

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


# --- Datos de entrada ---------------------------------------------------------------------
@dataclass(frozen=True)
class CursoDocumento:
    nombre: str
    codigo: str | None
    institucion: str | None
    fecha_inicio: date | None
    fecha_fin: date | None
    aprobado: bool


@dataclass(frozen=True)
class ReentrenamientoDocumento:
    numero_certificado: str
    tipo: str | None
    calibre: str | None
    fecha_expedicion: date
    fecha_vencimiento: date
    estado: str


@dataclass(frozen=True)
class CriterioDocumento:
    descripcion: str
    tipo: str  # OBLIGATORIO | ALTERNATIVO
    cumple: bool
    detalle: str | None


@dataclass(frozen=True)
class FirmaDocumento:
    """Rúbrica electrónica que se estampa en la línea de firma (firma desde el celular)."""

    rubrica_png: bytes  # PNG ya validado y sin metadatos (servicios/firma_movil.py)
    firmante: str  # grado y nombre del firmante autorizado
    cargo: str
    firmado_en: datetime
    codigo_verificacion: str  # referencia corta de la firma (aparece bajo la rúbrica)


@dataclass(frozen=True)
class DatosDocumento:
    """Todo lo que un documento necesita del artillero; lo arma el servicio a partir de la verificación."""

    cedula: str  # completa o enmascarada, según el permiso VER_DOCUMENTO_COMPLETO de quien la pide
    grado: str
    nombres: str
    apellidos: str
    categoria: str
    unidad: str | None
    activo: bool
    resultado: str  # APTO | NO_APTO
    fecha_expedicion: date
    numero: str  # consecutivo del documento (trazabilidad)
    expedido_por: str  # usuario de ESART que lo generó
    motivos: list[str] = field(default_factory=list)
    criterios: list[CriterioDocumento] = field(default_factory=list)
    cursos: list[CursoDocumento] = field(default_factory=list)
    reentrenamientos: list[ReentrenamientoDocumento] = field(default_factory=list)
    # Sin firma: línea en blanco para el Director. Con firma: la rúbrica, el firmante y la fecha.
    firma: FirmaDocumento | None = None

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def grado_y_nombre(self) -> str:
        return f"{self.grado} {self.nombre_completo}".strip()


# --- Utilidades de formato ----------------------------------------------------------------
def fecha_larga(valor: date | None) -> str:
    """18 de noviembre de 2026."""
    if valor is None:
        return "—"
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


def fecha_corta(valor: date | None) -> str:
    """18/11/2026."""
    return valor.strftime("%d/%m/%Y") if valor else "—"


def escapar(texto: str | None) -> str:
    """Los Paragraph de ReportLab interpretan XML: los datos del usuario se escapan siempre."""
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def estilos() -> dict[str, ParagraphStyle]:
    """Estilos de párrafo compartidos por los tres documentos."""
    base = getSampleStyleSheet()
    normal = ParagraphStyle("Normal", parent=base["Normal"], fontName="Helvetica", fontSize=10.5, leading=15)
    return {
        "normal": normal,
        "justificado": ParagraphStyle("Justificado", parent=normal, alignment=TA_JUSTIFY),
        "centro": ParagraphStyle("Centro", parent=normal, alignment=TA_CENTER),
        "izquierda": ParagraphStyle("Izquierda", parent=normal, alignment=TA_LEFT),
        "pequeno": ParagraphStyle("Pequeno", parent=normal, fontSize=8.5, leading=11, textColor=GRIS),
        "pequeno_centro": ParagraphStyle(
            "PequenoCentro", parent=normal, fontSize=7.5, leading=10, textColor=GRIS, alignment=TA_CENTER
        ),
        "titulo": ParagraphStyle(
            "Titulo", parent=normal, fontName="Helvetica-Bold", fontSize=16, leading=20,
            alignment=TA_CENTER, textColor=AZUL, spaceAfter=6,
        ),
        "subtitulo": ParagraphStyle(
            "Subtitulo", parent=normal, fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=AZUL, spaceBefore=8, spaceAfter=4,
        ),
        "celda": ParagraphStyle("Celda", parent=normal, fontSize=9, leading=11.5),
        "celda_titulo": ParagraphStyle(
            "CeldaTitulo", parent=normal, fontName="Helvetica-Bold", fontSize=9, leading=11.5,
            textColor=colors.white,
        ),
    }  # fmt: skip


def tabla(filas: list[list], anchos: list[float], estilos_parrafo: dict[str, ParagraphStyle]) -> Table:
    """Tabla con encabezado azul y filas alternadas; las celdas de texto se envuelven en Paragraph."""
    datos = [
        [
            Paragraph(escapar(str(c)), estilos_parrafo["celda_titulo" if i == 0 else "celda"])
            if not isinstance(c, Flowable)
            else c
            for c in fila
        ]
        for i, fila in enumerate(filas)
    ]
    resultado = Table(datos, colWidths=anchos, repeatRows=1)
    resultado.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, AZUL_CLARO]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBDDE5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return resultado


def bloque_firma(
    estilos_parrafo: dict[str, ParagraphStyle], firma: FirmaDocumento | None = None
) -> list[Flowable]:
    """
    Línea de firma (centrada). Sin firma: espacio en blanco y el cargo del Director.
    Con firma (rúbrica dibujada en el celular): la rúbrica sobre la línea, el nombre y cargo del
    firmante autorizado, la fecha y hora y el código de verificación de la firma.
    KeepTogether evita que la rúbrica quede en una página y el nombre en la siguiente.
    """
    if firma is None:
        encima = [Spacer(1, 1.3 * cm)]
        nombre, cargo, pie = FIRMANTE_NOMBRE, FIRMANTE_CARGO, []
    else:
        rubrica = Image(BytesIO(firma.rubrica_png), width=6 * cm, height=2.2 * cm, kind="proportional")
        rubrica.hAlign = "CENTER"
        encima = [Spacer(1, 0.2 * cm), rubrica]
        nombre, cargo = escapar(firma.firmante), escapar(firma.cargo)
        pie = [
            Paragraph(
                f"Firmado electrónicamente el {firma.firmado_en:%d/%m/%Y %H:%M} · "
                f"Código {escapar(firma.codigo_verificacion)}",
                estilos_parrafo["pequeno_centro"],
            )
        ]
    return [
        KeepTogether(
            [
                *encima,
                Paragraph("_______________________________________", estilos_parrafo["centro"]),
                Paragraph(f"<b>{nombre}</b>", estilos_parrafo["centro"]),
                Paragraph(cargo, estilos_parrafo["centro"]),
                *pie,
            ]
        )
    ]


def datos_a_json(datos: DatosDocumento) -> dict:
    """DatosDocumento → dict JSON (sin la firma). Se guarda en documentos.datos_emitidos para poder
    regenerar exactamente el mismo documento al firmarlo."""
    salida = asdict(datos)
    salida.pop("firma", None)

    def convertir(valor):
        if isinstance(valor, dict):
            return {k: convertir(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [convertir(v) for v in valor]
        if isinstance(valor, date):
            return valor.isoformat()
        return valor

    return convertir(salida)


def datos_desde_json(datos: dict, firma: FirmaDocumento | None = None) -> DatosDocumento:
    """Inverso de datos_a_json; agrega la firma si se indica."""

    def fecha(valor):
        return date.fromisoformat(valor) if valor else None

    return DatosDocumento(
        **{
            k: v
            for k, v in datos.items()
            if k not in ("fecha_expedicion", "criterios", "cursos", "reentrenamientos")
        },
        fecha_expedicion=fecha(datos["fecha_expedicion"]),
        criterios=[CriterioDocumento(**c) for c in datos.get("criterios", [])],
        cursos=[
            CursoDocumento(
                **{**c, "fecha_inicio": fecha(c["fecha_inicio"]), "fecha_fin": fecha(c["fecha_fin"])}
            )
            for c in datos.get("cursos", [])
        ],
        reentrenamientos=[
            ReentrenamientoDocumento(
                **{
                    **r,
                    "fecha_expedicion": fecha(r["fecha_expedicion"]),
                    "fecha_vencimiento": fecha(r["fecha_vencimiento"]),
                }
            )
            for r in datos.get("reentrenamientos", [])
        ],
        firma=firma,
    )


class DocumentoNoDisponible(ValueError):
    """El documento no aplica a este artillero (por ejemplo, diploma sin curso aprobado)."""


def _membrete_y_pie(
    datos: DatosDocumento, titulo: str, marco: bool
) -> Callable[[Canvas, SimpleDocTemplate], None]:
    """Dibuja en cada página: franja institucional arriba, pie con número, fecha y paginación y,
    si se pide, un marco dorado doble (diploma)."""

    def dibujar(lienzo: Canvas, documento: SimpleDocTemplate) -> None:
        ancho, alto = documento.pagesize
        lienzo.saveState()
        if marco:
            lienzo.setStrokeColor(DORADO)
            lienzo.setLineWidth(3)
            lienzo.rect(0.8 * cm, 0.8 * cm, ancho - 1.6 * cm, alto - 1.6 * cm)
            lienzo.setLineWidth(0.8)
            lienzo.rect(1.05 * cm, 1.05 * cm, ancho - 2.1 * cm, alto - 2.1 * cm)
            lienzo.restoreState()
            lienzo.saveState()
        lienzo.setFillColor(AZUL)
        lienzo.rect(0, alto - 2.1 * cm, ancho, 2.1 * cm, stroke=0, fill=1)
        lienzo.setFillColor(colors.white)
        lienzo.setFont("Helvetica-Bold", 12)
        lienzo.drawString(2 * cm, alto - 1.05 * cm, INSTITUCION)
        lienzo.setFont("Helvetica", 9.5)
        lienzo.drawString(2 * cm, alto - 1.55 * cm, f"{ESCUELA} · {LEMA}")
        lienzo.drawRightString(ancho - 2 * cm, alto - 1.3 * cm, titulo.upper())
        lienzo.setFillColor(GRIS)
        lienzo.setFont("Helvetica", 7.5)
        lienzo.drawString(
            2 * cm, 1.2 * cm,
            f"{SISTEMA} · Documento No. {datos.numero} · Generado por {datos.expedido_por} "
            f"el {fecha_corta(datos.fecha_expedicion)}",
        )  # fmt: skip
        lienzo.drawRightString(ancho - 2 * cm, 1.2 * cm, f"Página {documento.page}")
        lienzo.restoreState()

    return dibujar


def construir_pdf(
    datos: DatosDocumento,
    titulo: str,
    contenido: list[Flowable],
    *,
    pagina=LETTER,
    margen_superior: float = 3.0 * cm,
    marco: bool = False,
) -> bytes:
    """Arma el PDF con membrete y pie en cada página y devuelve sus bytes."""
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=pagina,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=margen_superior,
        bottomMargin=2.0 * cm,
        title=f"{titulo} — {datos.grado_y_nombre}",
        author=ESCUELA,
        subject=titulo,
        creator=SISTEMA,
    )
    pie = _membrete_y_pie(datos, titulo, marco)
    documento.build(contenido, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
