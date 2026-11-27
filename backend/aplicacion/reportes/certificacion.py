"""
Certificación de habilitación (opción CERTIFICACION).

"El Director de la Escuela de Artillería CERTIFICA que <grado nombre> ... se encuentra APTO /
NO APTO" con el soporte de la verificación:
- Datos del artillero (cédula, categoría, unidad, estado del servicio).
- Resultado destacado (verde APTO / rojo NO APTO) y, si es NO APTO, sus motivos.
- Tabla de criterios evaluados (obligatorios y alternativos) con Cumple / No cumple.
- Tabla de cursos registrados y tabla de reentrenamientos con su estado.
- S2-17: historial académico de los cursos con notas en la plataforma (materias, nota, si fue
  habilitada, instructor, nota final y puesto); el curso en curso aparece como parcial.
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
    if datos.historial:
        contenido += historial_academico(datos, e)
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


ESTADOS_MATERIA = {
    "HABILITADA": "Habilitada",
    "APROBADA_POR_CONSEJO": "Aprobada por el Consejo",
    "HABILITACION_PERDIDA": "Habilitación perdida",
}


def _nota(valor: float | None) -> str:
    return f"{valor:.2f}".replace(".", ",") if valor is not None else "—"


def historial_academico(datos: DatosDocumento, e: dict) -> list:
    """S2-17: un bloque por curso con sus materias, la nota final y el puesto."""
    contenido = [Paragraph("Historial académico", e["subtitulo"])]
    for curso in datos.historial:
        if curso.cerrado:
            puesto = (
                f"puesto {curso.puesto} de {curso.aprobados_del_curso}"
                if curso.puesto is not None
                else "sin puesto"
            )
            resumen = (
                f"Nota final <b>{_nota(curso.nota_final)}</b> · "
                f"{'Aprobado' if curso.resultado == 'APROBADO' else 'Reprobado'} · {puesto}"
            )
        else:
            resumen = "<b>En curso:</b> notas parciales aprobadas hasta la fecha de expedición"
        contenido += [
            Paragraph(
                f"<b>{escapar(curso.nombre)} ({escapar(curso.codigo)})</b> · "
                f"{fecha_corta(curso.fecha_inicio)} – {fecha_corta(curso.fecha_fin)} · {resumen}",
                e["normal"],
            ),
            Spacer(1, 0.15 * cm),
            tabla(
                [["Materia", "Nota", "Observación", "Instructor"]]
                + [
                    [
                        m.materia,
                        _nota(m.nota),
                        ESTADOS_MATERIA.get(m.estado or "", "—"),
                        m.instructor or "—",
                    ]
                    for m in curso.materias
                ],
                [7 * cm, 1.6 * cm, 3.6 * cm, 4.4 * cm],
                e,
            ),
            Spacer(1, 0.3 * cm),
        ]
    return contenido
