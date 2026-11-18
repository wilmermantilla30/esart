"""
Certificación de habilitación (opción CERTIFICACION).

"El Director de la Escuela de Artillería CERTIFICA que <grado nombre> ... se encuentra APTO /
NO APTO" con el soporte de la verificación:
- Datos del artillero (cédula, categoría, unidad, estado del servicio).
- Resultado destacado (verde APTO / rojo NO APTO) y, si es NO APTO, sus motivos.
- Tabla de criterios evaluados (obligatorios y alternativos) con Cumple / No cumple.
- Tabla de cursos registrados y tabla de reentrenamientos con su estado.
- Leyenda de validez: el resultado corresponde a la fecha de expedición.

Siempre se puede generar.
"""

from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, Spacer, Table, TableStyle

from aplicacion.reportes.comun import (
    AZUL_CLARO,
    CIUDAD,
    ESCUELA_TEXTO,
    ROJO,
    VERDE,
    DatosDocumento,
    bloque_firma,
    construir_pdf,
    escapar,
    estilos,
    fecha_corta,
    fecha_larga,
    tabla,
)

TITULO = "Certificación de habilitación"


def generar(datos: DatosDocumento) -> bytes:
    """Devuelve el PDF de la certificación."""
    e = estilos()
    apto = datos.resultado == "APTO"
    color = VERDE if apto else ROJO
    texto_resultado = "APTO" if apto else "NO APTO"

    ficha = Table(
        [
            ["Cédula", datos.cedula],
            ["Grado y nombre", datos.grado_y_nombre],
            ["Categoría", datos.categoria],
            ["Unidad", datos.unidad or "Sin unidad asignada"],
            ["Servicio", "Activo" if datos.activo else "Inactivo"],
        ],
        colWidths=[4 * cm, 12.6 * cm],
    )
    ficha.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("BACKGROUND", (0, 0), (0, -1), AZUL_CLARO),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    sello = Table([[texto_resultado]], colWidths=[16.6 * cm], rowHeights=[1.1 * cm])
    sello.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("TEXTCOLOR", (0, 0), (-1, -1), "white"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 18),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    contenido = [
        Paragraph("CERTIFICACIÓN DE HABILITACIÓN", e["titulo"]),
        Paragraph(f"No. {escapar(datos.numero)}", e["centro"]),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"El Director de la {ESCUELA_TEXTO} <b>CERTIFICA</b> que, según los registros del sistema "
            f"ESART verificados el {fecha_larga(datos.fecha_expedicion)}, el siguiente personal artillero "
            f"se encuentra:",
            e["justificado"],
        ),
        Spacer(1, 0.3 * cm),
        sello,
        Spacer(1, 0.4 * cm),
        ficha,
    ]
    if not apto and datos.motivos:
        contenido += [
            Paragraph("Motivos del resultado", e["subtitulo"]),
            ListFlowable(
                [ListItem(Paragraph(escapar(m), e["normal"])) for m in datos.motivos],
                bulletType="bullet",
                leftIndent=14,
            ),
        ]
    if datos.criterios:
        contenido += [
            Paragraph("Criterios evaluados", e["subtitulo"]),
            tabla(
                [["Criterio", "Tipo", "Resultado", "Detalle"]]
                + [
                    [
                        c.descripcion,
                        c.tipo.capitalize(),
                        "Cumple" if c.cumple else "No cumple",
                        c.detalle or "—",
                    ]
                    for c in datos.criterios
                ],
                [6 * cm, 2.4 * cm, 2.2 * cm, 6 * cm],
                e,
            ),
        ]
    contenido.append(Paragraph("Cursos registrados", e["subtitulo"]))
    if datos.cursos:
        contenido.append(
            tabla(
                [["Curso", "Institución", "Inicio", "Fin", "Estado"]]
                + [
                    [
                        f"{c.nombre} ({c.codigo})" if c.codigo else c.nombre,
                        c.institucion or "—",
                        fecha_corta(c.fecha_inicio),
                        fecha_corta(c.fecha_fin),
                        "Aprobado" if c.aprobado else "En curso / no aprobado",
                    ]
                    for c in datos.cursos
                ],
                [5.6 * cm, 3.6 * cm, 2.2 * cm, 2.2 * cm, 3 * cm],
                e,
            )
        )
    else:
        contenido.append(Paragraph("No registra cursos.", e["normal"]))
    contenido.append(Paragraph("Reentrenamientos", e["subtitulo"]))
    if datos.reentrenamientos:
        contenido.append(
            tabla(
                [["Certificado", "Tipo / calibre", "Expedición", "Vencimiento", "Estado"]]
                + [
                    [
                        r.numero_certificado,
                        " · ".join(filter(None, [r.tipo, r.calibre])) or "—",
                        fecha_corta(r.fecha_expedicion),
                        fecha_corta(r.fecha_vencimiento),
                        r.estado.replace("_", " ").capitalize(),
                    ]
                    for r in datos.reentrenamientos
                ],
                [3.6 * cm, 4.2 * cm, 2.6 * cm, 2.6 * cm, 3.6 * cm],
                e,
            )
        )
    else:
        contenido.append(Paragraph("No registra reentrenamientos.", e["normal"]))
    contenido += [
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"La presente se expide en {CIUDAD}, el {fecha_larga(datos.fecha_expedicion)}, a solicitud del "
            "interesado. El resultado corresponde a la fecha de expedición y puede cambiar si se "
            "actualizan los cursos o reentrenamientos del artillero.",
            e["pequeno"],
        ),
        *bloque_firma(e),
    ]
    return construir_pdf(datos, TITULO, contenido)
