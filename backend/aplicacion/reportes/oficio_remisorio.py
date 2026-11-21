"""
Oficio remisorio (opción OFICIO_REMISORIO).

Carta formal de la Escuela de Artillería al Comandante de la unidad del artillero que remite el
resultado de la verificación de habilitación. Contenido:
- Número de oficio, ciudad y fecha.
- Destinatario: "Señor Comandante <unidad>" (o "Señor Comandante de la unidad" si no tiene unidad).
- Asunto: "Remisión de resultado de verificación de habilitación — <grado nombre>".
- Cuerpo: identificación del artillero, resultado APTO / NO APTO y, si es NO APTO, sus motivos.
- Relación de anexos (certificación de habilitación y, si aplica, diploma).
- Firma del Director.

Siempre se puede generar (no exige curso aprobado ni resultado APTO).
"""

from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, Spacer

from aplicacion.reportes.comun import (
    CIUDAD,
    ESCUELA_TEXTO,
    DatosDocumento,
    bloque_firma,
    construir_pdf,
    escapar,
    estilos,
    fecha_larga,
)

TITULO = "Oficio remisorio"


def generar(datos: DatosDocumento) -> bytes:
    """Devuelve el PDF del oficio remisorio."""
    e = estilos()
    unidad = escapar(datos.unidad) if datos.unidad else "de la unidad"
    resultado = "APTO" if datos.resultado == "APTO" else "NO APTO"
    anexos = ["Certificación de habilitación del artillero."]
    if any(curso.aprobado for curso in datos.cursos):
        anexos.append("Diploma del último curso aprobado.")

    contenido = [
        Paragraph(f"<b>Oficio No. {escapar(datos.numero)}</b>", e["izquierda"]),
        Paragraph(f"{CIUDAD}, {fecha_larga(datos.fecha_expedicion)}", e["izquierda"]),
        Spacer(1, 0.7 * cm),
        Paragraph("Señor", e["izquierda"]),
        Paragraph(f"<b>Comandante {unidad}</b>", e["izquierda"]),
        Paragraph("Ejército Nacional de Colombia", e["izquierda"]),
        Spacer(1, 0.6 * cm),
        Paragraph(
            f"<b>Asunto:</b> Remisión de resultado de verificación de habilitación — "
            f"{escapar(datos.grado_y_nombre)}.",
            e["izquierda"],
        ),
        Spacer(1, 0.5 * cm),
        Paragraph(
            "Respetuosamente me permito remitir a ese Comando el resultado de la verificación "
            "de habilitación del siguiente personal artillero:",
            e["justificado"],
        ),  # fmt: skip
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"<b>{escapar(datos.grado_y_nombre)}</b>, cédula No. {escapar(datos.cedula)}, categoría "
            f"{escapar(datos.categoria)}, en servicio {'activo' if datos.activo else 'inactivo'}.",
            e["justificado"],
        ),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"Una vez verificados los requisitos vigentes en la {ESCUELA_TEXTO}, el resultado es: "
            f"<b>{resultado}</b>.",
            e["justificado"],
        ),
    ]
    if datos.resultado != "APTO" and datos.motivos:
        contenido += [
            Spacer(1, 0.2 * cm),
            Paragraph("Motivos:", e["izquierda"]),
            ListFlowable(
                [ListItem(Paragraph(escapar(motivo), e["normal"])) for motivo in datos.motivos],
                bulletType="bullet",
                leftIndent=14,
            ),
        ]
    contenido += [
        Spacer(1, 0.4 * cm),
        Paragraph("Lo anterior para su conocimiento y fines pertinentes.", e["justificado"]),
        Spacer(1, 0.4 * cm),
        Paragraph("<b>Anexos:</b>", e["izquierda"]),
        ListFlowable(
            [ListItem(Paragraph(anexo, e["normal"])) for anexo in anexos],
            bulletType="1",
            bulletFormat="%s.",
            leftIndent=14,
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Atentamente,", e["izquierda"]),
        *bloque_firma(e, datos.firma),
    ]
    return construir_pdf(datos, TITULO, contenido)
