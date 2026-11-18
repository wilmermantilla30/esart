"""
Diploma del artillero (opción DIPLOMA).

Contenido:
- Hoja carta horizontal con marco dorado y membrete institucional.
- "La Escuela de Artillería otorga el presente DIPLOMA a <grado nombre>, identificado con
  cédula <cédula>, por haber aprobado el curso <curso>", con fechas e institución del curso.
- Firma del Director, ciudad y fecha de expedición.

Regla: se usa el curso aprobado más reciente (por fecha de finalización). Si el artillero no tiene
ningún curso aprobado se lanza DocumentoNoDisponible (el endpoint responde 409): no se emite un
diploma sin curso que lo respalde.
"""

from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

from aplicacion.reportes.comun import (
    AZUL,
    CIUDAD,
    DORADO,
    ESCUELA_TEXTO,
    CursoDocumento,
    DatosDocumento,
    DocumentoNoDisponible,
    bloque_firma,
    construir_pdf,
    escapar,
    estilos,
    fecha_larga,
)

TITULO = "Diploma"


def curso_del_diploma(datos: DatosDocumento) -> CursoDocumento:
    """Curso aprobado más reciente; DocumentoNoDisponible si no hay ninguno."""
    aprobados = [curso for curso in datos.cursos if curso.aprobado]
    if not aprobados:
        raise DocumentoNoDisponible("El artillero no tiene cursos aprobados: no se puede expedir un diploma.")
    return max(aprobados, key=lambda curso: curso.fecha_fin or curso.fecha_inicio or datos.fecha_expedicion)


def generar(datos: DatosDocumento) -> bytes:
    """Devuelve el PDF del diploma."""
    curso = curso_del_diploma(datos)
    e = estilos()
    grande = ParagraphStyle("Diploma", parent=e["centro"], fontName="Helvetica-Bold", fontSize=34,
                            leading=40, textColor=DORADO, spaceAfter=4)  # fmt: skip
    nombre = ParagraphStyle("Nombre", parent=e["centro"], fontName="Helvetica-Bold", fontSize=22,
                            leading=28, textColor=AZUL)  # fmt: skip
    texto = ParagraphStyle("Texto", parent=e["centro"], fontSize=12.5, leading=19)

    periodo = ""
    if curso.fecha_inicio and curso.fecha_fin:
        periodo = (
            f", realizado entre el {fecha_larga(curso.fecha_inicio)} y el {fecha_larga(curso.fecha_fin)}"
        )
    institucion = f" en {escapar(curso.institucion)}" if curso.institucion else ""
    codigo = f" ({escapar(curso.codigo)})" if curso.codigo else ""

    contenido = [
        Spacer(1, 0.4 * cm),
        Paragraph(f"La {ESCUELA_TEXTO} otorga el presente", texto),
        Paragraph("DIPLOMA", grande),
        Paragraph("a", texto),
        Spacer(1, 0.2 * cm),
        Paragraph(escapar(datos.grado_y_nombre), nombre),
        Paragraph(f"identificado(a) con cédula de ciudadanía No. {escapar(datos.cedula)}", texto),
        Spacer(1, 0.4 * cm),
        Paragraph(
            f"por haber cursado y aprobado satisfactoriamente el curso <b>{escapar(curso.nombre)}</b>"
            f"{codigo}{institucion}{periodo}.",
            texto,
        ),
        Spacer(1, 0.3 * cm),
        Paragraph(f"Dado en {CIUDAD}, el {fecha_larga(datos.fecha_expedicion)}.", texto),
        *bloque_firma(e),
    ]
    return construir_pdf(
        datos, TITULO, contenido, pagina=landscape(LETTER), margen_superior=2.8 * cm, marco=True
    )
