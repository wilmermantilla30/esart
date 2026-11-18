"""
Estadísticas del panel principal (componente DASHBOARD): cursos, alumnos y egresados.

Período: los cursos se ubican por su FECHA DE INICIO. Semestre 1 = enero a junio,
semestre 2 = julio a diciembre (los cursos del cargue por Excel no traen semestre académico).

Definiciones (acordadas con SS.Mantilla el 2026-11-18):
- Alumno de un curso: cada fila de hoja_vida_artillero con ese curso (la deja el cargue por Excel),
  con el grado que tenía al entrar al curso.
- Egresado: alumno de un curso CULMINADO. Cuando se registren aprobados y reprobados
  (egresados_curso, segunda entrega) esta definición se refina.
- "En curso" es el estado de HOY, sin importar el filtro de período.
Solo cifras agregadas: no se devuelven nombres ni cédulas de alumnos.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.servicios.habilitacion import resumir_habilitacion
from aplicacion.servicios.registro_personal import GRADOS_POR_CATEGORIA

ESTADO_EN_CURSO = "EN_CURSO"
ESTADO_CULMINADO = "CULMINADO"
MES_INICIO_SEGUNDO_SEMESTRE = 7

# Nombre del comandante: militar (Personal militar), civil (datos propios) o su usuario.
NOMBRE_COMANDANTE = """
    COALESCE(NULLIF(TRIM(CONCAT_WS(' ', p.grado, p.nombres, p.apellidos)), ''),
             NULLIF(TRIM(CONCAT_WS(' ', i.nombres, i.apellidos)), ''),
             u.usuario, 'Instructor ' || i.id)
"""

# Un curso con su tipo, comandante y número de alumnos. :anio y :semestre filtran (NULL = todos).
# Constantes de este archivo, sin datos del usuario (los filtros van como parámetros).
CONSULTA_CURSOS = f"""
    SELECT c.id, c.codigo, c.nombre, tc.codigo AS tipo_curso, c.estado, c.fecha_inicio, c.fecha_fin,
           {NOMBRE_COMANDANTE} AS comandante,
           (SELECT count(*) FROM esart.hoja_vida_artillero hv WHERE hv.curso_id = c.id) AS alumnos
    FROM esart.cursos c
    JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    JOIN esart.instructores i ON i.id = c.comandante_id
    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
    LEFT JOIN esart_ref.usuarios u ON u.id = i.usuario_id
"""  # noqa: S608
FILTRO_PERIODO = """
    (CAST(:anio AS integer) IS NULL OR EXTRACT(YEAR FROM c.fecha_inicio) = :anio)
    AND (CAST(:semestre AS integer) IS NULL
         OR (CASE WHEN EXTRACT(MONTH FROM c.fecha_inicio) < 7 THEN 1 ELSE 2 END) = :semestre)
"""


def catalogo_grados() -> list[dict]:
    """Grados en orden jerárquico (oficiales, suboficiales, soldados), del catálogo del registro manual."""
    return [
        {"sigla": sigla, "nombre": nombre, "categoria": categoria}
        for categoria, (_, grados) in GRADOS_POR_CATEGORIA.items()
        for sigla, nombre in grados
    ]


def avance_del_curso(inicio: date, fin: date, hoy: date) -> dict:
    """Días transcurridos, porcentaje (0-100), días restantes y si ya pasó la fecha de fin."""
    dias_totales = max((fin - inicio).days, 1)
    transcurridos = min(max((hoy - inicio).days, 0), dias_totales)
    return {
        "dias_totales": dias_totales,
        "dias_transcurridos": transcurridos,
        "porcentaje": round(transcurridos * 100 / dias_totales),
        "dias_restantes": max((fin - hoy).days, 0),
        "vencido": hoy > fin,
    }


async def panel(sesion: AsyncSession, anio: int | None, semestre: int | None) -> dict:
    """Todo lo que muestra el panel principal para el período pedido."""
    filtros = {"anio": anio, "semestre": semestre}
    hoy: date = await sesion.scalar(text("SELECT (now() AT TIME ZONE 'America/Bogota')::date"))

    cursos = [
        dict(fila._mapping)
        for fila in await sesion.execute(
            text(f"{CONSULTA_CURSOS} WHERE {FILTRO_PERIODO} ORDER BY c.fecha_inicio DESC, c.id DESC"),  # noqa: S608
            filtros,
        )
    ]
    # Grado (al entrar al curso) y género de los alumnos de cada curso del período, en una consulta.
    composicion = await sesion.execute(
        text(f"""
            SELECT hv.curso_id, COALESCE(NULLIF(hv.grado, ''), p.grado) AS grado, p.genero,
                   count(*) AS cantidad
            FROM esart.hoja_vida_artillero hv
            JOIN esart.personal_militar p ON p.id = hv.artillero_id
            JOIN esart.cursos c ON c.id = hv.curso_id
            WHERE {FILTRO_PERIODO}
            GROUP BY hv.curso_id, 2, p.genero
        """),  # noqa: S608
        filtros,
    )
    por_curso = {curso["id"]: curso for curso in cursos}
    for curso in cursos:
        curso["grados"] = {}
        curso["genero"] = {"M": 0, "F": 0}
    for fila in composicion:
        curso = por_curso.get(fila.curso_id)
        if curso is None:
            continue
        grado = (fila.grado or "SIN GRADO").strip().upper()
        curso["grados"][grado] = curso["grados"].get(grado, 0) + fila.cantidad
        genero = "F" if (fila.genero or "").upper().startswith("F") else "M"
        curso["genero"][genero] += fila.cantidad

    # Cursos en curso HOY (sin filtro de período): el seguimiento siempre es del presente.
    en_curso = [
        {**dict(fila._mapping), **avance_del_curso(fila.fecha_inicio, fila.fecha_fin, hoy)}
        for fila in await sesion.execute(
            text(f"{CONSULTA_CURSOS} WHERE c.estado = :estado ORDER BY c.fecha_fin, c.id"),  # noqa: S608
            {"estado": ESTADO_EN_CURSO},
        )
    ]

    por_anio = [
        dict(fila._mapping)
        for fila in await sesion.execute(
            text("""
                SELECT EXTRACT(YEAR FROM fecha_inicio)::int AS anio,
                       count(*) FILTER (WHERE EXTRACT(MONTH FROM fecha_inicio) < 7) AS semestre_1,
                       count(*) FILTER (WHERE EXTRACT(MONTH FROM fecha_inicio) >= 7) AS semestre_2
                FROM esart.cursos GROUP BY 1 ORDER BY 1
            """)
        )
    ]

    # Grados presentes en el período, en orden jerárquico; los desconocidos van al final.
    presentes = {grado for curso in cursos for grado in curso["grados"]}
    catalogo = catalogo_grados()
    conocidos = {grado["sigla"] for grado in catalogo}
    grados = [grado for grado in catalogo if grado["sigla"] in presentes] + [
        {"sigla": sigla, "nombre": sigla.title(), "categoria": "OTRO"}
        for sigla in sorted(presentes - conocidos)
    ]

    habilitacion = await resumir_habilitacion(sesion)
    culminados = [curso for curso in cursos if curso["estado"] == ESTADO_CULMINADO]
    return {
        "periodo": {"anio": anio, "semestre": semestre},
        "hoy": hoy,
        "anios_disponibles": [fila["anio"] for fila in por_anio],
        "indicadores": {
            "cursos_periodo": len(cursos),
            "alumnos_periodo": sum(curso["alumnos"] for curso in cursos),
            "egresados": sum(curso["alumnos"] for curso in culminados),
            "cursos_culminados": len(culminados),
            "cursos_en_curso": len(en_curso),
            "alumnos_en_curso": sum(curso["alumnos"] for curso in en_curso),
        },
        "habilitacion": {
            "total": habilitacion["total"],
            "aptos": habilitacion["aptos"],
            "no_aptos": habilitacion["no_aptos"],
            "reentrenamiento_por_vencer": habilitacion["reentrenamiento_por_vencer"],
        },
        "cursos_por_anio": por_anio,
        "grados": grados,
        "cursos": cursos,
        "en_curso": en_curso,
    }
