"""
S2-02: módulo Cursos. Lista de cursos, detalle con su malla e instructor titular de cada materia.

- Ver (componente CURSOS, leer): lista con filtros y detalle de un curso.
- Asignar (CURSOS, actualizar), normalmente el Inspector de Estudios por excepción:
  - el instructor titular de cada materia CON NOTA (uno por materia; militar o civil, activo). Es
    quien cargará las notas de esa materia (S2-12). Cambiarlo o quitarlo queda auditado;
  - la malla VIGENTE de su tipo a un curso EN_CURSO o APLAZADO que se creó antes de cargar las
    mallas (sin malla). También le copia la nota mínima vigente si no tenía.
- Un curso CANCELADO o CULMINADO no se modifica.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.instructores import NOMBRE_VISIBLE_INSTRUCTOR

ESTADOS_CURSO = ("EN_CURSO", "APLAZADO", "CULMINADO", "CANCELADO")
# Estados en los que se pueden asignar instructores o la malla.
ESTADOS_EDITABLES = ("EN_CURSO", "APLAZADO")
LIMITE_LISTADO = 500

# NOMBRE_VISIBLE_INSTRUCTOR y LIMITE_LISTADO son constantes; los filtros van como parámetros.
CONSULTA_LISTADO = f"""
    SELECT c.id, c.codigo, c.nombre, tc.codigo AS tipo_curso, c.fecha_inicio, c.fecha_fin, c.estado,
           (SELECT count(*) FROM esart.hoja_vida_artillero hv WHERE hv.curso_id = c.id) AS alumnos,
           {NOMBRE_VISIBLE_INSTRUCTOR} AS comandante,
           v.numero AS version_malla,
           (SELECT count(*) FROM esart.malla_curricular m
            WHERE m.version_id = c.malla_version_id AND m.evaluable)
             AS materias_con_nota,
           (SELECT count(*) FROM esart.cursos_materias_instructor a WHERE a.curso_id = c.id) AS asignadas
    FROM esart.cursos c
    JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    LEFT JOIN esart.versiones_malla v ON v.id = c.malla_version_id
    LEFT JOIN esart.instructores i ON i.id = c.comandante_id
    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
    WHERE (CAST(:estado AS text) IS NULL OR c.estado = :estado)
      AND (CAST(:tipo AS text) IS NULL OR tc.codigo = :tipo)
      AND (CAST(:texto AS text) IS NULL OR c.codigo ILIKE :patron OR c.nombre ILIKE :patron)
    ORDER BY c.fecha_inicio DESC, c.id DESC
    LIMIT {LIMITE_LISTADO}
"""  # noqa: S608


async def listar(
    sesion: AsyncSession, estado: str | None = None, tipo: str | None = None, texto: str | None = None
) -> list[dict]:
    """Cursos más recientes primero, con cuántas materias con nota tienen instructor asignado."""
    texto = (texto or "").strip() or None
    filas = await sesion.execute(
        text(CONSULTA_LISTADO),
        {
            "estado": estado,
            "tipo": (tipo or "").strip().upper() or None,
            "texto": texto,
            "patron": f"%{texto}%" if texto else None,
        },
    )
    return [dict(fila._mapping) for fila in filas]


async def _curso(sesion: AsyncSession, curso_id: int):
    fila = (
        await sesion.execute(
            text(f"""
                SELECT c.id, c.codigo, c.nombre, c.tipo_curso_id, tc.codigo AS tipo_curso,
                       tc.nombre AS nombre_tipo_curso, c.fecha_inicio, c.fecha_fin, c.estado,
                       c.malla_version_id, c.nota_minima_aprobacion,
                       (SELECT count(*) FROM esart.hoja_vida_artillero hv
                        WHERE hv.curso_id = c.id) AS alumnos,
                       {NOMBRE_VISIBLE_INSTRUCTOR} AS comandante,
                       v.numero AS version_malla, v.anio AS anio_malla, v.estado AS estado_malla
                FROM esart.cursos c
                JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
                LEFT JOIN esart.versiones_malla v ON v.id = c.malla_version_id
                LEFT JOIN esart.instructores i ON i.id = c.comandante_id
                LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
                WHERE c.id = :id
            """),  # noqa: S608 (NOMBRE_VISIBLE_INSTRUCTOR es una constante)
            {"id": curso_id},
        )
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(404, "CURSO_NO_ENCONTRADO", "El curso no existe.")
    return fila


async def detalle(sesion: AsyncSession, curso_id: int) -> dict:
    """El curso, su malla (versión con que se creó) y el instructor de cada materia."""
    curso = await _curso(sesion, curso_id)
    materias = []
    if curso.malla_version_id is not None:
        materias = [
            dict(fila._mapping)
            for fila in await sesion.execute(
                text(f"""
                    SELECT m.id AS malla_id, m.orden, mt.codigo AS codigo_materia, mt.nombre AS materia,
                           m.area, m.modulo, m.evaluable,
                           a.instructor_id, {NOMBRE_VISIBLE_INSTRUCTOR} AS instructor,
                           i.tipo AS tipo_instructor,
                           a.asignado_en, u.usuario AS asignado_por
                    FROM esart.malla_curricular m
                    JOIN esart.materias mt ON mt.id = m.materia_id
                    LEFT JOIN esart.cursos_materias_instructor a ON a.malla_id = m.id AND a.curso_id = :curso
                    LEFT JOIN esart.instructores i ON i.id = a.instructor_id
                    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
                    LEFT JOIN esart_ref.usuarios u ON u.id = a.asignado_por_id
                    WHERE m.version_id = :version
                    ORDER BY m.orden
                """),  # noqa: S608
                {"curso": curso_id, "version": curso.malla_version_id},
            )
        ]
    vigente = await sesion.scalar(
        text("SELECT numero FROM esart.versiones_malla WHERE tipo_curso_id = :tipo AND estado = 'VIGENTE'"),
        {"tipo": curso.tipo_curso_id},
    )
    datos = dict(curso._mapping)
    datos.pop("tipo_curso_id")
    datos.pop("malla_version_id")
    return {
        **datos,
        "nota_minima_aprobacion": (
            float(curso.nota_minima_aprobacion) if curso.nota_minima_aprobacion is not None else None
        ),
        "editable": curso.estado in ESTADOS_EDITABLES,
        # Sin malla, en curso y con una versión vigente de su tipo: se le puede asignar.
        "version_vigente_disponible": (
            vigente if curso.malla_version_id is None and curso.estado in ESTADOS_EDITABLES else None
        ),
        "materias": materias,
    }


async def instructores_disponibles(sesion: AsyncSession) -> list[dict]:
    """Instructores activos (militares y civiles) para el selector de cada materia."""
    filas = await sesion.execute(
        text(f"""
            SELECT i.id, i.tipo, {NOMBRE_VISIBLE_INSTRUCTOR} AS nombre
            FROM esart.instructores i
            LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
            WHERE i.activo
            ORDER BY COALESCE(p.apellidos, i.apellidos), COALESCE(p.nombres, i.nombres)
        """)  # noqa: S608
    )
    return [dict(fila._mapping) for fila in filas]


def _exigir_editable(curso) -> None:
    if curso.estado not in ESTADOS_EDITABLES:
        raise ErrorAplicacion(
            409,
            "CURSO_NO_EDITABLE",
            "Solo se modifican cursos en curso o aplazados (no culminados ni cancelados).",
        )


async def asignar_instructor(
    sesion: AsyncSession, curso_id: int, malla_id: int, instructor_id: int | None, *, actor: Actor
) -> dict:
    """Pone, cambia o quita (instructor_id None) el instructor titular de una materia del curso."""
    curso = await _curso(sesion, curso_id)
    _exigir_editable(curso)
    materia = (
        await sesion.execute(
            text("""
                SELECT m.id, m.evaluable, mt.nombre
                FROM esart.malla_curricular m JOIN esart.materias mt ON mt.id = m.materia_id
                WHERE m.id = :malla AND m.version_id = :version
            """),
            {"malla": malla_id, "version": curso.malla_version_id},
        )
    ).one_or_none()
    if materia is None:
        raise ErrorAplicacion(
            404, "MATERIA_NO_ENCONTRADA", "La materia no pertenece a la malla de este curso."
        )
    if not materia.evaluable:
        raise ErrorAplicacion(
            422,
            "MATERIA_SIN_NOTA",
            "Las materias sin nota (por ejemplo, Tiempo del comandante) no llevan instructor.",
        )
    nuevo = None
    if instructor_id is not None:
        nuevo = (
            await sesion.execute(
                text(f"""
                    SELECT i.id, i.activo, {NOMBRE_VISIBLE_INSTRUCTOR} AS nombre
                    FROM esart.instructores i LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
                    WHERE i.id = :id
                """),  # noqa: S608
                {"id": instructor_id},
            )
        ).one_or_none()
        if nuevo is None or not nuevo.activo:
            raise ErrorAplicacion(422, "INSTRUCTOR_NO_DISPONIBLE", "El instructor no existe o está inactivo.")
    anterior = (
        await sesion.execute(
            text(f"""
                SELECT a.id, a.instructor_id, {NOMBRE_VISIBLE_INSTRUCTOR} AS nombre
                FROM esart.cursos_materias_instructor a
                JOIN esart.instructores i ON i.id = a.instructor_id
                LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
                WHERE a.curso_id = :curso AND a.malla_id = :malla
                FOR UPDATE OF a
            """),  # noqa: S608
            {"curso": curso_id, "malla": malla_id},
        )
    ).one_or_none()
    if (anterior.instructor_id if anterior else None) == instructor_id:
        raise ErrorAplicacion(422, "SIN_CAMBIOS", "La materia ya tiene ese instructor.")

    parametros = {
        "curso": curso_id,
        "malla": malla_id,
        "instructor": instructor_id,
        "usuario": actor.usuario_id,
    }
    if instructor_id is None:
        await sesion.execute(
            text("DELETE FROM esart.cursos_materias_instructor WHERE id = :id"), {"id": anterior.id}
        )
    elif anterior is None:
        await sesion.execute(
            text("""
                INSERT INTO esart.cursos_materias_instructor
                  (curso_id, malla_id, instructor_id, asignado_por_id)
                VALUES (:curso, :malla, :instructor, :usuario)
            """),
            parametros,
        )
    else:
        await sesion.execute(
            text("""
                UPDATE esart.cursos_materias_instructor
                SET instructor_id = :instructor, asignado_por_id = :usuario, asignado_en = now()
                WHERE curso_id = :curso AND malla_id = :malla
            """),
            parametros,
        )
    # registrar_evento confirma: la asignación y su auditoría quedan juntas o no quedan.
    await auditoria.registrar_evento(
        sesion,
        auditoria.INSTRUCTOR_MATERIA_ASIGNADO,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "curso": curso.codigo,
            "materia": materia.nombre,
            "anterior": {"id": anterior.instructor_id, "nombre": anterior.nombre} if anterior else None,
            "nuevo": {"id": nuevo.id, "nombre": nuevo.nombre} if nuevo else None,
        },
    )
    return await detalle(sesion, curso_id)


async def asignar_malla_vigente(sesion: AsyncSession, curso_id: int, *, actor: Actor) -> dict:
    """Liga a un curso sin malla la versión VIGENTE de su tipo (y la nota mínima vigente si no tenía)."""
    curso = await _curso(sesion, curso_id)
    _exigir_editable(curso)
    if curso.malla_version_id is not None:
        raise ErrorAplicacion(
            409, "CURSO_CON_MALLA", "El curso ya tiene malla: se conserva la versión con que se creó."
        )
    vigente = (
        await sesion.execute(
            text("""
                SELECT id, numero FROM esart.versiones_malla
                WHERE tipo_curso_id = :tipo AND estado = 'VIGENTE'
            """),
            {"tipo": curso.tipo_curso_id},
        )
    ).one_or_none()
    if vigente is None:
        raise ErrorAplicacion(
            422,
            "TIPO_SIN_MALLA",
            f"El tipo de curso {curso.tipo_curso} no tiene malla vigente: cárguela en Parámetros.",
        )
    await sesion.execute(
        text("""
            UPDATE esart.cursos
            SET malla_version_id = :version,
                nota_minima_aprobacion = COALESCE(nota_minima_aprobacion, (
                  SELECT (valor #>> '{}')::numeric(3, 2) FROM esart.parametros_habilitacion
                  WHERE codigo = 'NOTA_MINIMA_APROBACION'))
            WHERE id = :id
        """),
        {"version": vigente.id, "id": curso_id},
    )
    await auditoria.registrar_evento(
        sesion,
        auditoria.CURSO_MALLA_ASIGNADA,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={"curso": curso.codigo, "tipo_curso": curso.tipo_curso, "version": vigente.numero},
    )
    return await detalle(sesion, curso_id)
