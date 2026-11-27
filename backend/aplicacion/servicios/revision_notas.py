"""
S2-13: revisión de las entregas de notas por el Inspector de Estudios (componente NOTAS_REVISION).

Flujo:
1. Bandeja: entregas por estado (por defecto, las EN_REVISION), con curso, materia, instructor,
   promedio y cuántas notas quedan por debajo de la mínima del curso.
2. Detalle: la nota de cada alumno y, si la materia ya tenía notas oficiales, la anterior.
3. Acciones (permiso "actualizar"):
   - Aprobar (confirmación, sin TOTP: decisión de la Escuela, 2026-11-27, por ser la tarea más
     repetida del Inspector; la sesión ya exige TOTP y todo queda auditado): las notas de la
     entrega pasan a esart.notas_oficiales, que son las que cuentan. Si ya había oficiales
     (corrección), la auditoría guarda el antes y el después.
   - Devolver (observación): el instructor corrige y vuelve a subir (S2-12).
   - Reabrir una entrega APROBADA (TOTP y observación): queda DEVUELTA para que el instructor
     suba la corrección; las notas oficiales siguen vigentes hasta la nueva aprobación.
4. Aprobar y devolver exigen la "versión" (subido_en) que el Inspector revisó: si el instructor
   subió otra planilla mientras tanto, no se aprueba algo que no se vio.
5. S2-14: las entregas de HABILITACION siguen el mismo flujo. Al aprobarlas, quien alcanza la
   mínima queda con la nota de habilitación (origen HABILITACION) y quien no, pasa al Consejo
   Académico. No se reabren notas ordinarias de una materia con habilitación, ni una habilitación
   con decisiones del Consejo.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp
from aplicacion.servicios.habilitaciones import alumnos_a_habilitar
from aplicacion.servicios.instructores import NOMBRE_VISIBLE_INSTRUCTOR
from aplicacion.servicios.notas import (
    DOS_DECIMALES,
    ESTADO_APROBADA,
    ESTADO_DEVUELTA,
    ESTADO_EN_REVISION,
    TIPO_HABILITACION,
    TIPO_ORDINARIA,
    alumnos_del_curso,
)

# Política TOTP de REABRIR notas aprobadas (el código conserva el nombre de la migración p0023).
POLITICA_TOTP = "NOTAS_APROBAR"
ESTADOS = (ESTADO_EN_REVISION, ESTADO_DEVUELTA, ESTADO_APROBADA)
LONGITUD_MINIMA_OBSERVACION = 5
LONGITUD_MAXIMA_OBSERVACION = 1000

# Una fila por entrega con sus datos de curso, materia e instructor y el resumen de sus notas.
CONSULTA_ENTREGAS = f"""
    SELECT e.id, e.tipo, e.estado, e.nombre_archivo, e.subido_en, e.revisado_en, e.observacion_revision,
           us.usuario AS subido_por, ur.usuario AS revisado_por,
           c.id AS curso_id, c.codigo AS codigo_curso, c.nombre AS nombre_curso, c.estado AS estado_curso,
           tc.codigo AS tipo_curso, m.id AS malla_id, m.orden, mt.codigo AS codigo_materia,
           mt.nombre AS materia, c.nota_minima_aprobacion AS nota_minima,
           {NOMBRE_VISIBLE_INSTRUCTOR} AS instructor,
           resumen.alumnos, resumen.promedio,
           (SELECT count(*) FROM esart.notas_entrega n
            WHERE n.entrega_id = e.id AND n.nota < c.nota_minima_aprobacion) AS por_debajo_de_la_minima,
           -- Ya hay un resultado aprobado de ese tipo (la entrega es una corrección).
           CASE WHEN e.tipo = 'ORDINARIA'
                THEN EXISTS (SELECT 1 FROM esart.notas_oficiales o
                             WHERE o.curso_id = e.curso_id AND o.malla_id = e.malla_id)
                ELSE EXISTS (SELECT 1 FROM esart.habilitaciones_materia hm
                             WHERE hm.curso_id = e.curso_id AND hm.malla_id = e.malla_id)
           END AS tiene_notas_oficiales
    FROM esart.entregas_notas e
    JOIN esart.cursos c ON c.id = e.curso_id
    JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    JOIN esart.malla_curricular m ON m.id = e.malla_id
    JOIN esart.materias mt ON mt.id = m.materia_id
    JOIN esart.instructores i ON i.id = e.instructor_id
    LEFT JOIN esart.personal_militar p ON p.id = i.personal_id
    LEFT JOIN esart_ref.usuarios us ON us.id = e.subido_por_id
    LEFT JOIN esart_ref.usuarios ur ON ur.id = e.revisado_por_id
    CROSS JOIN LATERAL (
        SELECT count(*) AS alumnos, round(avg(n.nota), 2) AS promedio
        FROM esart.notas_entrega n WHERE n.entrega_id = e.id
    ) resumen
"""  # noqa: S608 (NOMBRE_VISIBLE_INSTRUCTOR es una constante; los valores van como parámetros)


def _a_flotante(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _resumen(fila) -> dict:
    """Fila de CONSULTA_ENTREGAS como diccionario, con las notas como número."""
    datos = dict(fila._mapping)
    for campo in ("nota_minima", "promedio"):
        datos[campo] = _a_flotante(datos[campo])
    return datos


# --- Consultas -----------------------------------------------------------------------------------


async def bandeja(sesion: AsyncSession, estado: str | None) -> list[dict]:
    """Entregas en ese estado (None = todas). Las pendientes, de la más antigua a la más reciente."""
    if estado is not None and estado not in ESTADOS:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Estado de entrega desconocido.")
    filas = await sesion.execute(
        text(
            CONSULTA_ENTREGAS
            + " WHERE (CAST(:estado AS varchar) IS NULL OR e.estado = :estado)"
            + " ORDER BY e.subido_en, e.id"
        ),
        {"estado": estado},
    )
    return [_resumen(fila) for fila in filas]


async def _fila_entrega(sesion: AsyncSession, entrega_id: int, *, bloquear: bool = False):
    """La entrega con sus datos; 404 si no existe. Con bloquear, la reserva hasta el commit."""
    if bloquear:
        # FOR UPDATE no admite agregados: se bloquea la fila sola y luego se lee el resumen.
        await sesion.execute(
            text("SELECT 1 FROM esart.entregas_notas WHERE id = :id FOR UPDATE"), {"id": entrega_id}
        )
    fila = (
        await sesion.execute(text(CONSULTA_ENTREGAS + " WHERE e.id = :id"), {"id": entrega_id})
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(404, "ENTREGA_NO_ENCONTRADA", "La entrega de notas no existe.")
    return fila


async def _notas_con_oficial(sesion: AsyncSession, entrega) -> list[dict]:
    """Nota de cada alumno en la entrega y la aprobada antes del mismo tipo (None si no había):
    la ordinaria oficial o, en una habilitación, la de la habilitación anterior. También la ordinaria."""
    filas = await sesion.execute(
        text("""
            SELECT a.id AS personal_id, a.documento_identidad AS cedula, a.grado, a.apellidos, a.nombres,
                   n.nota, o.nota_ordinaria,
                   CASE WHEN :tipo = 'ORDINARIA' THEN o.nota_ordinaria ELSE hm.nota END AS nota_oficial
            FROM esart.notas_entrega n
            JOIN esart.personal_militar a ON a.id = n.personal_id
            LEFT JOIN esart.notas_oficiales o
              ON o.curso_id = :curso AND o.malla_id = :malla AND o.personal_id = n.personal_id
            LEFT JOIN esart.habilitaciones_materia hm
              ON hm.curso_id = :curso AND hm.malla_id = :malla AND hm.personal_id = n.personal_id
            WHERE n.entrega_id = :entrega
            ORDER BY a.apellidos, a.nombres
        """),
        {"curso": entrega.curso_id, "malla": entrega.malla_id, "entrega": entrega.id, "tipo": entrega.tipo},
    )
    return [dict(fila._mapping) for fila in filas]


async def detalle(sesion: AsyncSession, entrega_id: int) -> dict:
    """Resumen de la entrega y la nota de cada alumno junto a la oficial vigente."""
    fila = await _fila_entrega(sesion, entrega_id)
    notas = await _notas_con_oficial(sesion, fila)
    return {
        **_resumen(fila),
        "notas": [
            {
                "cedula": nota["cedula"],
                "grado": nota["grado"],
                "apellidos": nota["apellidos"],
                "nombres": nota["nombres"],
                "nota": float(nota["nota"]),
                "nota_oficial": _a_flotante(nota["nota_oficial"]),
                "nota_ordinaria": _a_flotante(nota["nota_ordinaria"]),
            }
            for nota in notas
        ],
    }


# --- Validaciones comunes ------------------------------------------------------------------------


def validar_observacion(observacion: str | None) -> str:
    """La observación es obligatoria para devolver o reabrir: el instructor debe saber qué corregir."""
    limpia = " ".join((observacion or "").split())
    if len(limpia) < LONGITUD_MINIMA_OBSERVACION:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "Escriba una observación que explique al instructor qué debe corregir."
        )
    if len(limpia) > LONGITUD_MAXIMA_OBSERVACION:
        raise ErrorAplicacion(
            422,
            "DATOS_INVALIDOS",
            f"La observación admite como máximo {LONGITUD_MAXIMA_OBSERVACION} caracteres.",
        )
    return limpia


def _verificar_estado(fila, estado_esperado: str, accion: str) -> None:
    if fila.estado_curso == "CANCELADO":
        raise ErrorAplicacion(409, "CURSO_NO_EDITABLE", "El curso está cancelado: sus notas no se revisan.")
    if fila.estado != estado_esperado:
        raise ErrorAplicacion(
            409,
            "ESTADO_NO_PERMITE",
            f"Solo se puede {accion} una entrega {estado_esperado.replace('_', ' ')}.",
        )


def _verificar_version(fila, version: datetime | None) -> None:
    """La entrega debe ser la misma que el Inspector revisó (el instructor no subió otra)."""
    if version != fila.subido_en:
        raise ErrorAplicacion(
            409,
            "ENTREGA_CAMBIO",
            "El instructor subió una nueva planilla mientras usted revisaba. Recargue y revísela de nuevo.",
        )


async def _registrar_revision(
    sesion: AsyncSession, entrega_id: int, estado: str, observacion: str | None, actor: Actor
) -> None:
    await sesion.execute(
        text("""
            UPDATE esart.entregas_notas
            SET estado = :estado, revisado_por_id = :usuario, revisado_en = now(),
                observacion_revision = :observacion
            WHERE id = :id
        """),
        {"estado": estado, "usuario": actor.usuario_id, "observacion": observacion, "id": entrega_id},
    )


def _detalle_auditoria(fila) -> dict:
    """Lo que identifica la entrega en cualquier evento de revisión."""
    return {
        "entrega_id": fila.id,
        "tipo": fila.tipo,
        "curso": fila.codigo_curso,
        "materia": fila.materia,
        "instructor": fila.instructor,
    }


async def _notas_completas(sesion: AsyncSession, fila) -> list[dict]:
    """Notas de la entrega, solo si traen a todos los alumnos que hoy corresponden: los del curso
    (ordinaria) o los que deben habilitar (habilitación)."""
    notas = await _notas_con_oficial(sesion, fila)
    if fila.tipo == TIPO_HABILITACION:
        esperados = await alumnos_a_habilitar(sesion, fila.curso_id, fila.malla_id)
    else:
        esperados = await alumnos_del_curso(sesion, fila.curso_id)
    alumnos = {alumno["id"] for alumno in esperados}
    if {nota["personal_id"] for nota in notas} != alumnos:
        raise ErrorAplicacion(
            409,
            "ENTREGA_DESACTUALIZADA",
            "La lista de alumnos del curso cambió desde que el instructor subió la planilla. "
            "Devuélvala para que la suba de nuevo.",
        )
    return notas


async def _verificar_reabrible(sesion: AsyncSession, fila) -> None:
    """S2-14: una corrección no puede dejar sin sentido una habilitación ni una decisión del Consejo."""
    parametros = {"curso": fila.curso_id, "malla": fila.malla_id}
    if fila.tipo == TIPO_ORDINARIA:
        con_habilitacion = await sesion.scalar(
            text("""
                SELECT EXISTS (SELECT 1 FROM esart.entregas_notas
                               WHERE curso_id = :curso AND malla_id = :malla AND tipo = 'HABILITACION')
            """),
            parametros,
        )
        if con_habilitacion:
            raise ErrorAplicacion(
                409,
                "MATERIA_CON_HABILITACION",
                "Esta materia ya tiene habilitaciones registradas: sus notas ordinarias no se reabren.",
            )
        return
    con_decision = await sesion.scalar(
        text("""
            SELECT EXISTS (SELECT 1 FROM esart.decisiones_consejo d
                           JOIN esart.habilitaciones_materia hm ON hm.id = d.habilitacion_id
                           WHERE hm.curso_id = :curso AND hm.malla_id = :malla)
        """),
        parametros,
    )
    if con_decision:
        raise ErrorAplicacion(
            409,
            "HABILITACION_CON_DECISION",
            "El Consejo Académico ya decidió sobre esta habilitación: no se puede reabrir.",
        )


# --- Acciones ------------------------------------------------------------------------------------


async def aprobar(
    sesion: AsyncSession,
    entrega_id: int,
    version: datetime | None,
    *,
    actor: Actor,
) -> dict:
    """Aprueba la entrega (sin TOTP): sus notas pasan a ser las oficiales de la materia en el curso."""
    # Con la fila reservada: nadie la cambia entre la revisión y la aprobación.
    fila = await _fila_entrega(sesion, entrega_id, bloquear=True)
    _verificar_estado(fila, ESTADO_EN_REVISION, "aprobar")
    _verificar_version(fila, version)

    notas = await _notas_completas(sesion, fila)
    hubo_oficiales = bool(fila.tiene_notas_oficiales)
    cambios = [
        {
            "cedula": nota["cedula"],
            "antes": str(nota["nota_oficial"]) if nota["nota_oficial"] is not None else None,
            "despues": str(nota["nota"]),
        }
        for nota in notas
        if nota["nota_oficial"] != nota["nota"]
    ]

    parametros = {
        "curso": fila.curso_id,
        "malla": fila.malla_id,
        "entrega": fila.id,
        "usuario": actor.usuario_id,
        "minima": fila.nota_minima,
    }
    resultado = {}
    if fila.tipo == TIPO_HABILITACION:
        resultado = await _aplicar_habilitacion(sesion, parametros)
    else:
        await sesion.execute(
            text("DELETE FROM esart.notas_oficiales WHERE curso_id = :curso AND malla_id = :malla"),
            parametros,
        )
        await sesion.execute(
            text("""
                INSERT INTO esart.notas_oficiales
                  (curso_id, malla_id, personal_id, nota, nota_ordinaria, entrega_id, aprobado_por_id)
                SELECT :curso, :malla, n.personal_id, n.nota, n.nota, :entrega, :usuario
                FROM esart.notas_entrega n WHERE n.entrega_id = :entrega
            """),
            parametros,
        )
    await _registrar_revision(sesion, fila.id, ESTADO_APROBADA, None, actor)
    # registrar_evento confirma: la aprobación y su auditoría quedan juntas o no quedan.
    await auditoria.registrar_evento(
        sesion,
        auditoria.NOTAS_APROBADAS,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            **_detalle_auditoria(fila),
            "alumnos": len(notas),
            "promedio": str(Decimal(str(fila.promedio)).quantize(DOS_DECIMALES)),
            "por_debajo_de_la_minima": fila.por_debajo_de_la_minima,
            "es_correccion": hubo_oficiales,
            # En una corrección, solo las notas que cambiaron (antes = oficial anterior).
            "cambios": cambios if hubo_oficiales else [],
            **resultado,
        },
    )
    return await detalle(sesion, entrega_id)


async def _aplicar_habilitacion(sesion: AsyncSession, parametros: dict) -> dict:
    """Aplica una habilitación aprobada. Si había una anterior (corrección tras reabrir), primero se
    deshace: las notas vuelven a la ordinaria. Devuelve cuántos habilitaron y cuántos van al Consejo."""
    await sesion.execute(
        text("""
            UPDATE esart.notas_oficiales SET nota = nota_ordinaria, origen = 'ORDINARIA'
            WHERE curso_id = :curso AND malla_id = :malla AND origen = 'HABILITACION'
        """),
        parametros,
    )
    await sesion.execute(
        text("DELETE FROM esart.habilitaciones_materia WHERE curso_id = :curso AND malla_id = :malla"),
        parametros,
    )
    # Resultado de cada alumno: APROBADA si alcanza la nota mínima del curso.
    filas = await sesion.execute(
        text("""
            INSERT INTO esart.habilitaciones_materia
              (curso_id, malla_id, personal_id, entrega_id, nota, resultado, aprobado_por_id)
            SELECT :curso, :malla, n.personal_id, :entrega, n.nota,
                   CASE WHEN n.nota >= :minima THEN 'APROBADA' ELSE 'REPROBADA' END, :usuario
            FROM esart.notas_entrega n WHERE n.entrega_id = :entrega
            RETURNING resultado
        """),
        parametros,
    )
    resultados = [fila.resultado for fila in filas]
    # Quien habilitó queda con la nota de habilitación: es la que entra al promedio.
    await sesion.execute(
        text("""
            UPDATE esart.notas_oficiales o SET nota = hm.nota, origen = 'HABILITACION'
            FROM esart.habilitaciones_materia hm
            WHERE hm.curso_id = :curso AND hm.malla_id = :malla AND hm.resultado = 'APROBADA'
              AND o.curso_id = hm.curso_id AND o.malla_id = hm.malla_id AND o.personal_id = hm.personal_id
        """),
        parametros,
    )
    return {
        "habilitaron": resultados.count("APROBADA"),
        "al_consejo_academico": resultados.count("REPROBADA"),
    }


async def devolver(
    sesion: AsyncSession, entrega_id: int, version: datetime | None, observacion: str | None, *, actor: Actor
) -> dict:
    """Devuelve la entrega al instructor con la observación de lo que debe corregir."""
    limpia = validar_observacion(observacion)
    fila = await _fila_entrega(sesion, entrega_id, bloquear=True)
    _verificar_estado(fila, ESTADO_EN_REVISION, "devolver")
    _verificar_version(fila, version)
    await _registrar_revision(sesion, fila.id, ESTADO_DEVUELTA, limpia, actor)
    await auditoria.registrar_evento(
        sesion,
        auditoria.NOTAS_DEVUELTAS,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={**_detalle_auditoria(fila), "observacion": limpia},
    )
    return await detalle(sesion, entrega_id)


async def reabrir(
    sesion: AsyncSession, entrega_id: int, observacion: str | None, *, actor: Actor, codigo_totp: str | None
) -> dict:
    """Reabre una entrega aprobada para corregirla. Las notas oficiales siguen vigentes mientras tanto."""
    limpia = validar_observacion(observacion)
    fila = await _fila_entrega(sesion, entrega_id)
    _verificar_estado(fila, ESTADO_APROBADA, "reabrir")
    await _verificar_reabrible(sesion, fila)
    await exigir_codigo_totp(
        sesion,
        actor.usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        actor.request,
        prefijo_auditoria="NOTAS",
        mensaje_requerido="Ingrese el código del autenticador para reabrir las notas aprobadas.",
    )
    fila = await _fila_entrega(sesion, entrega_id, bloquear=True)
    _verificar_estado(fila, ESTADO_APROBADA, "reabrir")
    await _verificar_reabrible(sesion, fila)
    await _registrar_revision(sesion, fila.id, ESTADO_DEVUELTA, limpia, actor)
    await auditoria.registrar_evento(
        sesion,
        auditoria.NOTAS_REABIERTAS,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={**_detalle_auditoria(fila), "observacion": limpia},
    )
    return await detalle(sesion, entrega_id)
