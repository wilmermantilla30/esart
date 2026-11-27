"""
S2-14: decisiones del Consejo Académico (componente CONSEJO_ACADEMICO).

- Caso: alumno que perdió la habilitación de una materia (habilitaciones_materia REPROBADA).
- El Consejo decide UNA vez por caso, de una lista fija (pregunta 5 del backlog): aprueba la
  materia, repite el curso, pierde el curso u otra (esta exige observación). Se registra el número
  y la fecha del acta, con el código del autenticador y en la auditoría. No se edita después.
- "Aprueba la materia" deja la materia con la nota mínima del curso (origen CONSEJO), que es la
  que entra al promedio. Las demás decisiones no cambian la nota: las aplica S2-15 al cerrar el curso.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp

POLITICA_TOTP = "CONSEJO_REGISTRAR"
APRUEBA_MATERIA = "APRUEBA_MATERIA"
OTRA = "OTRA"
DECISIONES = (APRUEBA_MATERIA, "REPITE_CURSO", "PIERDE_CURSO", OTRA)
FILTROS = ("PENDIENTES", "DECIDIDOS", "TODOS")
LONGITUD_MAXIMA_ACTA = 50
LONGITUD_MAXIMA_OBSERVACION = 1000

CONSULTA_CASOS = """
    SELECT hm.id, hm.curso_id, c.codigo AS codigo_curso, c.nombre AS nombre_curso, c.estado AS estado_curso,
           tc.codigo AS tipo_curso, hm.malla_id, mt.codigo AS codigo_materia, mt.nombre AS materia,
           c.nota_minima_aprobacion AS nota_minima,
           a.documento_identidad AS cedula, a.grado, a.apellidos, a.nombres,
           o.nota_ordinaria, hm.nota AS nota_habilitacion, hm.aprobado_en AS habilitacion_aprobada_en,
           d.decision, d.numero_acta, d.fecha_acta, d.observacion, d.registrado_en,
           ur.usuario AS registrado_por
    FROM esart.habilitaciones_materia hm
    JOIN esart.cursos c ON c.id = hm.curso_id
    JOIN esart.tipos_curso tc ON tc.id = c.tipo_curso_id
    JOIN esart.malla_curricular m ON m.id = hm.malla_id
    JOIN esart.materias mt ON mt.id = m.materia_id
    JOIN esart.personal_militar a ON a.id = hm.personal_id
    JOIN esart.notas_oficiales o
      ON o.curso_id = hm.curso_id AND o.malla_id = hm.malla_id AND o.personal_id = hm.personal_id
    LEFT JOIN esart.decisiones_consejo d ON d.habilitacion_id = hm.id
    LEFT JOIN esart_ref.usuarios ur ON ur.id = d.registrado_por_id
    WHERE hm.resultado = 'REPROBADA'
"""


def _caso(fila) -> dict:
    datos = dict(fila._mapping)
    for campo in ("nota_minima", "nota_ordinaria", "nota_habilitacion"):
        datos[campo] = float(datos[campo]) if datos[campo] is not None else None
    return datos


async def casos(sesion: AsyncSession, filtro: str) -> list[dict]:
    """Alumnos que perdieron una habilitación: pendientes de decisión, ya decididos o todos."""
    if filtro not in FILTROS:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Filtro de casos desconocido.")
    condicion = {"PENDIENTES": " AND d.id IS NULL", "DECIDIDOS": " AND d.id IS NOT NULL", "TODOS": ""}[filtro]
    filas = await sesion.execute(
        text(CONSULTA_CASOS + condicion + " ORDER BY hm.aprobado_en, c.codigo, a.apellidos, a.nombres")
    )
    return [_caso(fila) for fila in filas]


def validar_decision(decision: str, numero_acta: str, fecha_acta: date, observacion: str | None) -> dict:
    """Decisión de la lista, acta con número y fecha no futura; observación obligatoria en 'Otra'."""
    if decision not in DECISIONES:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Decisión del Consejo desconocida.")
    acta = " ".join((numero_acta or "").split())
    if not acta or len(acta) > LONGITUD_MAXIMA_ACTA:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", f"Escriba el número del acta (máximo {LONGITUD_MAXIMA_ACTA} caracteres)."
        )
    if fecha_acta > date.today():
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La fecha del acta no puede ser futura.")
    limpia = " ".join((observacion or "").split()) or None
    if decision == OTRA and not limpia:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Explique en la observación cuál fue la decisión.")
    if limpia and len(limpia) > LONGITUD_MAXIMA_OBSERVACION:
        raise ErrorAplicacion(
            422,
            "DATOS_INVALIDOS",
            f"La observación admite como máximo {LONGITUD_MAXIMA_OBSERVACION} caracteres.",
        )
    return {"decision": decision, "numero_acta": acta, "fecha_acta": fecha_acta, "observacion": limpia}


async def _caso_pendiente(sesion: AsyncSession, habilitacion_id: int, *, bloquear: bool = False):
    if bloquear:
        await sesion.execute(
            text("SELECT 1 FROM esart.habilitaciones_materia WHERE id = :id FOR UPDATE"),
            {"id": habilitacion_id},
        )
    fila = (
        await sesion.execute(text(CONSULTA_CASOS + " AND hm.id = :id"), {"id": habilitacion_id})
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(404, "CASO_NO_ENCONTRADO", "No hay una habilitación perdida con ese número.")
    if fila.decision is not None:
        raise ErrorAplicacion(
            409, "CASO_DECIDIDO", "El Consejo Académico ya registró su decisión en este caso."
        )
    if fila.estado_curso == "CANCELADO":
        raise ErrorAplicacion(409, "CURSO_NO_EDITABLE", "El curso está cancelado.")
    return fila


async def registrar_decision(
    sesion: AsyncSession,
    habilitacion_id: int,
    decision: str,
    numero_acta: str,
    fecha_acta: date,
    observacion: str | None,
    *,
    actor: Actor,
    codigo_totp: str | None,
) -> dict:
    """Registra la decisión del Consejo (con TOTP). 'Aprueba la materia' la deja con la nota mínima."""
    datos = validar_decision(decision, numero_acta, fecha_acta, observacion)
    await _caso_pendiente(sesion, habilitacion_id)
    # El código va antes de escribir: si es inválido, exigir_codigo_totp confirma su auditoría.
    await exigir_codigo_totp(
        sesion,
        actor.usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        actor.request,
        prefijo_auditoria="CONSEJO",
        mensaje_requerido="Ingrese el código del autenticador para registrar la decisión del Consejo.",
    )
    fila = await _caso_pendiente(sesion, habilitacion_id, bloquear=True)
    await sesion.execute(
        text("""
            INSERT INTO esart.decisiones_consejo
              (habilitacion_id, decision, numero_acta, fecha_acta, observacion, registrado_por_id)
            VALUES (:id, :decision, :numero_acta, :fecha_acta, :observacion, :usuario)
        """),
        {**datos, "id": habilitacion_id, "usuario": actor.usuario_id},
    )
    nota_que_cuenta = fila.nota_habilitacion
    if decision == APRUEBA_MATERIA:
        await sesion.execute(
            text("""
                UPDATE esart.notas_oficiales o SET nota = c.nota_minima_aprobacion, origen = 'CONSEJO'
                FROM esart.cursos c
                WHERE c.id = o.curso_id AND o.curso_id = :curso AND o.malla_id = :malla
                  AND o.personal_id = (SELECT personal_id FROM esart.habilitaciones_materia WHERE id = :id)
            """),
            {"curso": fila.curso_id, "malla": fila.malla_id, "id": habilitacion_id},
        )
        nota_que_cuenta = fila.nota_minima
    # registrar_evento confirma: la decisión y su auditoría quedan juntas o no quedan.
    await auditoria.registrar_evento(
        sesion,
        auditoria.CONSEJO_DECISION_REGISTRADA,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "habilitacion_id": habilitacion_id,
            "curso": fila.codigo_curso,
            "materia": fila.materia,
            "cedula": fila.cedula,
            "decision": decision,
            "numero_acta": datos["numero_acta"],
            "fecha_acta": datos["fecha_acta"].isoformat(),
            "observacion": datos["observacion"],
            "nota_habilitacion": str(fila.nota_habilitacion),
            "nota_que_cuenta": str(nota_que_cuenta) if decision == APRUEBA_MATERIA else None,
        },
    )
    return _caso(
        (await sesion.execute(text(CONSULTA_CASOS + " AND hm.id = :id"), {"id": habilitacion_id})).one()
    )
