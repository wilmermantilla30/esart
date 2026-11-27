"""
S2-17: historial académico del artillero (notas por materia, nota final y puesto).

- Cursos CERRADOS en la plataforma (resultados_curso, S2-15): cada materia evaluable con su nota,
  si fue habilitada o aprobada por el Consejo, su instructor, y la nota final, el resultado y el
  puesto ("3 de 25") guardados al cerrar.
- Curso EN CURSO (o aplazado) con alguna nota oficial: las notas aprobadas hasta hoy, marcado como
  parcial y sin nota final ni puesto.
- Los cursos anteriores o cargados por Excel no tienen notas en la plataforma: siguen mostrándose
  solo como aprobado / no aprobado en la lista de cursos de la verificación.
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.servicios import campana
from aplicacion.servicios.instructores import NOMBRE_VISIBLE_INSTRUCTOR

# Cómo terminó una materia que pasó por habilitación (null si no la necesitó).
HABILITADA = "HABILITADA"
APROBADA_POR_CONSEJO = "APROBADA_POR_CONSEJO"
HABILITACION_PERDIDA = "HABILITACION_PERDIDA"

CONSULTA_CURSOS = """
    SELECT DISTINCT c.id, c.codigo, c.nombre, tc.codigo AS tipo_curso, c.fecha_inicio, c.fecha_fin, c.estado,
           c.nota_minima_aprobacion AS nota_minima, c.malla_version_id, c.comandante_id,
           r.nota_final, r.resultado, r.motivo, r.puesto, r.materias_habilitadas,
           (r.id IS NOT NULL) AS cerrado,
           (SELECT count(*) FROM esart.resultados_curso a
            WHERE a.curso_id = c.id AND a.resultado = 'APROBADO') AS aprobados_del_curso
    FROM esart.hoja_vida_artillero hv
    JOIN esart.cursos c ON c.id = hv.curso_id
    JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    LEFT JOIN esart.resultados_curso r ON r.curso_id = c.id AND r.personal_id = hv.artillero_id
    WHERE hv.artillero_id = :persona
      AND c.malla_version_id IS NOT NULL
      AND (r.id IS NOT NULL
           OR (c.estado IN ('EN_CURSO', 'APLAZADO')
               AND EXISTS (SELECT 1 FROM esart.notas_oficiales o
                           WHERE o.curso_id = c.id AND o.personal_id = hv.artillero_id)))
    ORDER BY c.fecha_inicio DESC, c.id DESC
"""

CONSULTA_MATERIAS = f"""
    SELECT m.orden, mt.nombre AS materia, o.nota, o.nota_ordinaria, o.origen,
           hm.nota AS nota_habilitacion, hm.resultado AS resultado_habilitacion,
           {campana.condicion_por_items("m.materia_id")} AS por_items,
           {NOMBRE_VISIBLE_INSTRUCTOR} AS instructor,
           {NOMBRE_VISIBLE_INSTRUCTOR.replace("p.", "pc.").replace("i.", "ic.")} AS comandante
    FROM esart.malla_curricular m
    JOIN esart.materias mt ON mt.id = m.materia_id
    LEFT JOIN esart.notas_oficiales o
      ON o.curso_id = :curso AND o.malla_id = m.id AND o.personal_id = :persona
    LEFT JOIN esart.habilitaciones_materia hm
      ON hm.curso_id = :curso AND hm.malla_id = m.id AND hm.personal_id = :persona
    LEFT JOIN esart.cursos_materias_instructor a ON a.curso_id = :curso AND a.malla_id = m.id
    LEFT JOIN esart.instructores i ON i.id = a.instructor_id
    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
    LEFT JOIN esart.instructores ic ON ic.id = :comandante
    LEFT JOIN esart.personal_militar pc ON pc.id = ic.personal_id
    WHERE m.version_id = :version AND m.evaluable
    ORDER BY m.orden
"""  # noqa: S608 (constantes del código; los valores van como parámetros)


def _a_flotante(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def estado_materia(origen: str | None, resultado_habilitacion: str | None) -> str | None:
    """Cómo terminó una materia que pasó por habilitación (null si no la necesitó)."""
    if origen == "CONSEJO":
        return APROBADA_POR_CONSEJO
    if resultado_habilitacion == "APROBADA":
        return HABILITADA
    if resultado_habilitacion == "REPROBADA":
        return HABILITACION_PERDIDA
    return None


def nota_que_cuenta(fila) -> Decimal | None:
    """La nota de la materia que entra al promedio: la oficial o, si perdió la habilitación sin
    aprobación del Consejo, la de habilitación (misma regla que la nota final, S2-15)."""
    if fila.nota is None:
        return None
    if fila.resultado_habilitacion is not None and fila.origen == "ORDINARIA":
        return fila.nota_habilitacion
    return fila.nota


async def historial(sesion: AsyncSession, personal_id: int) -> list[dict]:
    """Cursos del artillero con notas en la plataforma, del más reciente al más antiguo."""
    cursos = []
    for curso in await sesion.execute(text(CONSULTA_CURSOS), {"persona": personal_id}):
        materias = [
            {
                "orden": fila.orden,
                "materia": fila.materia,
                "nota": _a_flotante(nota_que_cuenta(fila)),
                "estado": estado_materia(fila.origen, fila.resultado_habilitacion),
                # La fase de campaña la registra el comandante (S2-16).
                # Sin instructor asignado el nombre sale vacío: se devuelve null.
                "instructor": (fila.comandante if fila.por_items else fila.instructor) or None,
            }
            for fila in await sesion.execute(
                text(CONSULTA_MATERIAS),
                {
                    "curso": curso.id,
                    "persona": personal_id,
                    "version": curso.malla_version_id,
                    "comandante": curso.comandante_id,
                },
            )
        ]
        cursos.append(
            {
                "codigo": curso.codigo,
                "nombre": curso.nombre,
                "tipo_curso": curso.tipo_curso,
                "fecha_inicio": curso.fecha_inicio,
                "fecha_fin": curso.fecha_fin,
                "estado_curso": curso.estado,
                "cerrado": curso.cerrado,
                "nota_minima": _a_flotante(curso.nota_minima),
                "nota_final": _a_flotante(curso.nota_final),
                "resultado": curso.resultado,
                "motivo": curso.motivo,
                "puesto": curso.puesto,
                # Total de aprobados del curso: el puesto se lee "3 de 25".
                "aprobados_del_curso": curso.aprobados_del_curso if curso.cerrado else None,
                "materias_con_nota": sum(1 for materia in materias if materia["nota"] is not None),
                "materias": materias,
            }
        )
    return cursos
