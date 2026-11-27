"""
S2-15: nota final, puesto y cierre del curso (componente CURSOS).

Reglas (decisiones de la Escuela, preguntas 2 y 3 de "Por confirmar", 2026-11-26):
- Nota final = promedio de las notas oficiales de las materias EVALUABLES de la malla del curso
  (notas_oficiales.nota: la ordinaria, la de habilitación o la mínima si el Consejo aprobó la
  materia), con 2 decimales. Aprueba el curso con nota final >= nota mínima del curso.
- "Repite el curso" o "Pierde el curso" del Consejo Académico dejan al alumno REPROBADO.
- Puesto (solo aprobados): primero quienes no habilitaron ninguna materia y después quienes sí;
  dentro de cada grupo, por la nota final con TODOS sus decimales, luego menos materias
  habilitadas y luego el promedio del área profesional específica. Si aún empatan, comparten
  el puesto (1, 2, 2, 4).
- Mientras falte una nota, una habilitación o una decisión del Consejo, el resultado es
  PROVISIONAL. Completo, quien tenga CURSOS "actualizar" cierra el curso con TOTP: queda
  CULMINADO, se guardan los resultados y el curso de los aprobados se marca aprobado en su
  historial (artillero_cursos), que alimenta la regla APTO / NO APTO.
"""

import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp
from aplicacion.servicios.notas import DOS_DECIMALES, alumnos_del_curso

POLITICA_TOTP = "CURSO_CERRAR"
APROBADO = "APROBADO"
REPROBADO = "REPROBADO"
# Decisiones del Consejo que dejan al alumno reprobado sin importar su promedio.
DECISIONES_QUE_REPRUEBAN = {"REPITE_CURSO": "Repite el curso", "PIERDE_CURSO": "Pierde el curso"}
AREA_ESPECIFICA = "profesional especifica"
MAXIMO_PENDIENTES = 50


# --- Cálculo (sin base de datos) ------------------------------------------------------------------


@dataclass
class NotaDeMateria:
    """Nota oficial que cuenta de una materia evaluable."""

    nota: Decimal
    # Pasó por habilitación (la ganara o la decidiera el Consejo).
    habilitada: bool = False
    # Es del área profesional específica (desempate).
    especifica: bool = False


@dataclass
class AlumnoEnCalculo:
    personal_id: int
    cedula: str
    grado: str | None
    apellidos: str
    nombres: str
    notas: list[NotaDeMateria] = field(default_factory=list)
    # Lo que impide el resultado definitivo ("Topografía: falta la nota", ...).
    pendientes: list[str] = field(default_factory=list)
    # Decisión del Consejo que lo reprueba (texto), si la hay.
    reprobado_por_consejo: str | None = None


def es_area_especifica(area: str | None) -> bool:
    """'Profesional Específica' escrita con o sin tildes y en cualquier mayúscula."""
    sin_tildes = "".join(
        letra for letra in unicodedata.normalize("NFD", area or "") if unicodedata.category(letra) != "Mn"
    )
    return AREA_ESPECIFICA in " ".join(sin_tildes.lower().split())


def _promedio(valores: list[Decimal]) -> Decimal | None:
    return sum(valores) / len(valores) if valores else None


def calcular_resultados(alumnos: list[AlumnoEnCalculo], nota_minima: Decimal) -> list[dict]:
    """Nota final, resultado y puesto de cada alumno, ordenados como se muestran."""
    filas = []
    for alumno in alumnos:
        exacta = _promedio([nota.nota for nota in alumno.notas])
        final = exacta.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP) if exacta is not None else None
        habilitadas = sum(1 for nota in alumno.notas if nota.habilitada)
        especifica = _promedio([nota.nota for nota in alumno.notas if nota.especifica])
        resultado = motivo = None
        if not alumno.pendientes and final is not None:
            if alumno.reprobado_por_consejo:
                resultado, motivo = REPROBADO, f"Consejo Académico: {alumno.reprobado_por_consejo}."
            elif final < nota_minima:
                resultado, motivo = REPROBADO, f"Nota final por debajo de la mínima ({nota_minima})."
            else:
                resultado = APROBADO
        filas.append(
            {
                "personal_id": alumno.personal_id,
                "cedula": alumno.cedula,
                "grado": alumno.grado,
                "apellidos": alumno.apellidos,
                "nombres": alumno.nombres,
                "nota_final": final,
                "nota_exacta": exacta,
                "materias_evaluadas": len(alumno.notas),
                "materias_habilitadas": habilitadas,
                "promedio_area_especifica": especifica,
                "pendientes": alumno.pendientes,
                "resultado": resultado,
                "motivo": motivo,
                "puesto": None,
            }
        )

    def clave(fila: dict) -> tuple:
        # Menor clave = mejor puesto (por eso los números van negativos).
        return (
            fila["materias_habilitadas"] > 0,
            -fila["nota_exacta"],
            fila["materias_habilitadas"],
            -(
                fila["promedio_area_especifica"]
                if fila["promedio_area_especifica"] is not None
                else Decimal(-1)
            ),
        )

    aprobados = sorted((fila for fila in filas if fila["resultado"] == APROBADO), key=clave)
    for posicion, fila in enumerate(aprobados):
        empata = posicion > 0 and clave(fila) == clave(aprobados[posicion - 1])
        fila["puesto"] = aprobados[posicion - 1]["puesto"] if empata else posicion + 1
    reprobados = sorted(
        (fila for fila in filas if fila["resultado"] == REPROBADO), key=lambda fila: -fila["nota_exacta"]
    )
    sin_resultado = sorted(
        (fila for fila in filas if fila["resultado"] is None),
        key=lambda fila: (fila["apellidos"], fila["nombres"]),
    )
    return aprobados + reprobados + sin_resultado


# --- Datos del curso ------------------------------------------------------------------------------


CONSULTA_CURSO = """
    SELECT id, codigo, nombre, estado, tipo_curso_id, fecha_inicio, fecha_fin,
           malla_version_id, nota_minima_aprobacion AS nota_minima
    FROM esart.cursos WHERE id = :id
"""
CONSULTA_CURSO_BLOQUEADO = CONSULTA_CURSO + " FOR UPDATE"


async def _curso(sesion: AsyncSession, curso_id: int, *, bloquear: bool = False):
    fila = (
        await sesion.execute(
            text(CONSULTA_CURSO_BLOQUEADO if bloquear else CONSULTA_CURSO),
            {"id": curso_id},
        )
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(404, "CURSO_NO_ENCONTRADO", "El curso no existe.")
    return fila


async def _calcular(sesion: AsyncSession, curso) -> tuple[list[dict], list[str], int]:
    """(filas, pendientes del curso, cantidad de materias evaluables) con las notas oficiales de hoy."""
    if curso.malla_version_id is None or curso.nota_minima is None:
        raise ErrorAplicacion(
            409, "CURSO_SIN_MALLA", "El curso no tiene malla curricular o nota mínima: no hay nota final."
        )
    parametros = {"curso": curso.id, "version": curso.malla_version_id}
    evaluables = {
        fila.id: fila
        for fila in await sesion.execute(
            text("""
                SELECT m.id, mt.nombre AS materia, m.area FROM esart.malla_curricular m
                JOIN esart.materias mt ON mt.id = m.materia_id
                WHERE m.version_id = :version AND m.evaluable
            """),
            parametros,
        )
    }
    oficiales = {
        (fila.personal_id, fila.malla_id): fila
        for fila in await sesion.execute(
            text("""
                SELECT personal_id, malla_id, nota, nota_ordinaria, origen FROM esart.notas_oficiales
                WHERE curso_id = :curso
            """),
            parametros,
        )
    }
    habilitaciones = {
        (fila.personal_id, fila.malla_id): fila
        for fila in await sesion.execute(
            text("""
                SELECT hm.personal_id, hm.malla_id, hm.nota, hm.resultado, d.decision
                FROM esart.habilitaciones_materia hm
                LEFT JOIN esart.decisiones_consejo d ON d.habilitacion_id = hm.id
                WHERE hm.curso_id = :curso
            """),
            parametros,
        )
    }
    # Entregas sin aprobar (en revisión, devueltas o reabiertas): sus notas aún pueden cambiar.
    pendientes_curso = [
        f"{fila.materia}: notas {'de habilitación ' if fila.tipo == 'HABILITACION' else ''}"
        f"{'en revisión' if fila.estado == 'EN_REVISION' else 'devueltas al instructor'}."
        for fila in await sesion.execute(
            text("""
                SELECT e.tipo, e.estado, mt.nombre AS materia FROM esart.entregas_notas e
                JOIN esart.malla_curricular m ON m.id = e.malla_id
                JOIN esart.materias mt ON mt.id = m.materia_id
                WHERE e.curso_id = :curso AND e.estado <> 'APROBADA'
                ORDER BY m.orden, e.tipo
            """),
            parametros,
        )
    ]
    minima = curso.nota_minima
    alumnos = []
    for datos in await alumnos_del_curso(sesion, curso.id):
        alumno = AlumnoEnCalculo(
            personal_id=datos["id"],
            cedula=datos["cedula"],
            grado=datos["grado"],
            apellidos=datos["apellidos"],
            nombres=datos["nombres"],
        )
        for malla_id, materia in evaluables.items():
            oficial = oficiales.get((alumno.personal_id, malla_id))
            habilitacion = habilitaciones.get((alumno.personal_id, malla_id))
            if oficial is None:
                alumno.pendientes.append(f"{materia.materia}: falta la nota aprobada.")
            elif oficial.nota_ordinaria < minima and habilitacion is None:
                alumno.pendientes.append(f"{materia.materia}: debe habilitar.")
            elif (
                habilitacion is not None
                and habilitacion.resultado == "REPROBADA"
                and not habilitacion.decision
            ):
                alumno.pendientes.append(f"{materia.materia}: espera la decisión del Consejo Académico.")
            else:
                # Habilitación perdida sin aprobación del Consejo: cuenta la nota de habilitación.
                nota = oficial.nota
                if habilitacion is not None and oficial.origen == "ORDINARIA":
                    nota = habilitacion.nota
                alumno.notas.append(
                    NotaDeMateria(
                        nota=nota,
                        habilitada=habilitacion is not None,
                        especifica=es_area_especifica(materia.area),
                    )
                )
                if habilitacion is not None and habilitacion.decision in DECISIONES_QUE_REPRUEBAN:
                    alumno.reprobado_por_consejo = DECISIONES_QUE_REPRUEBAN[habilitacion.decision]
        alumnos.append(alumno)
    return calcular_resultados(alumnos, minima), pendientes_curso, len(evaluables)


def _publica(fila: dict) -> dict:
    """La fila tal como la ve el front (sin la nota exacta ni el promedio del desempate)."""
    return {
        "cedula": fila["cedula"],
        "grado": fila["grado"],
        "apellidos": fila["apellidos"],
        "nombres": fila["nombres"],
        "nota_final": float(fila["nota_final"]) if fila["nota_final"] is not None else None,
        "materias_evaluadas": fila["materias_evaluadas"],
        "materias_habilitadas": fila["materias_habilitadas"],
        "pendientes": fila["pendientes"],
        "resultado": fila["resultado"],
        "motivo": fila["motivo"],
        "puesto": fila["puesto"],
    }


# --- Consulta y cierre ----------------------------------------------------------------------------


async def resultados(sesion: AsyncSession, curso_id: int) -> dict:
    """Resultados guardados (curso cerrado) o provisionales con las notas oficiales de hoy."""
    curso = await _curso(sesion, curso_id)
    base = {
        "curso_id": curso.id,
        "codigo_curso": curso.codigo,
        "estado_curso": curso.estado,
        "nota_minima": float(curso.nota_minima) if curso.nota_minima is not None else None,
    }
    guardados = (
        await sesion.execute(
            text("""
                SELECT p.documento_identidad AS cedula, p.grado, p.apellidos, p.nombres, r.nota_final,
                       r.materias_evaluadas, r.materias_habilitadas, r.resultado, r.motivo, r.puesto,
                       r.cerrado_en, u.usuario AS cerrado_por
                FROM esart.resultados_curso r
                JOIN esart.personal_militar p ON p.id = r.personal_id
                LEFT JOIN esart_ref.usuarios u ON u.id = r.cerrado_por_id
                WHERE r.curso_id = :curso
                ORDER BY r.resultado, r.puesto NULLS LAST, r.nota_exacta DESC, p.apellidos
            """),
            {"curso": curso_id},
        )
    ).all()
    if guardados:
        return {
            **base,
            "cerrado": True,
            "cerrado_en": guardados[0].cerrado_en,
            "cerrado_por": guardados[0].cerrado_por,
            "materias_evaluables": max(fila.materias_evaluadas for fila in guardados),
            "completo": True,
            "puede_cerrar": False,
            "pendientes": [],
            "alumnos": [
                {
                    **{clave: getattr(fila, clave) for clave in ("cedula", "grado", "apellidos", "nombres")},
                    "nota_final": float(fila.nota_final),
                    "materias_evaluadas": fila.materias_evaluadas,
                    "materias_habilitadas": fila.materias_habilitadas,
                    "pendientes": [],
                    "resultado": fila.resultado,
                    "motivo": fila.motivo,
                    "puesto": fila.puesto,
                }
                for fila in guardados
            ],
        }
    filas, pendientes_curso, evaluables = await _calcular(sesion, curso)
    completo = bool(filas) and not pendientes_curso and all(fila["resultado"] for fila in filas)
    return {
        **base,
        "cerrado": False,
        "cerrado_en": None,
        "cerrado_por": None,
        "materias_evaluables": evaluables,
        "completo": completo,
        "puede_cerrar": completo and curso.estado == "EN_CURSO",
        "pendientes": pendientes_curso[:MAXIMO_PENDIENTES],
        "alumnos": [_publica(fila) for fila in filas],
    }


async def _verificar_cierre(sesion: AsyncSession, curso) -> list[dict]:
    """Filas definitivas del curso, o el motivo por el que todavía no se puede cerrar."""
    if curso.estado != "EN_CURSO":
        raise ErrorAplicacion(409, "CURSO_NO_EDITABLE", "Solo se cierra un curso EN CURSO.")
    filas, pendientes_curso, _ = await _calcular(sesion, curso)
    if not filas:
        raise ErrorAplicacion(409, "CURSO_SIN_ALUMNOS", "El curso no tiene alumnos registrados.")
    pendientes = pendientes_curso + [
        f"{fila['apellidos']} {fila['nombres']}: {pendiente}"
        for fila in filas
        for pendiente in fila["pendientes"]
    ]
    if pendientes:
        raise ErrorAplicacion(
            409,
            "RESULTADOS_INCOMPLETOS",
            "Todavía no se puede cerrar el curso: faltan notas, habilitaciones o decisiones del Consejo.",
            {"pendientes": pendientes[:MAXIMO_PENDIENTES]},
        )
    return filas


async def cerrar(sesion: AsyncSession, curso_id: int, *, actor: Actor, codigo_totp: str | None) -> dict:
    """Cierra el curso (con TOTP): guarda los resultados, lo pasa a CULMINADO y actualiza el historial."""
    await _verificar_cierre(sesion, await _curso(sesion, curso_id))
    # El código va antes de escribir: si es inválido, exigir_codigo_totp confirma su auditoría.
    await exigir_codigo_totp(
        sesion,
        actor.usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        actor.request,
        prefijo_auditoria="CURSOS",
        mensaje_requerido="Ingrese el código del autenticador para cerrar el curso.",
    )
    # Con el curso reservado se vuelve a calcular: nadie lo cierra dos veces ni cambia notas a la vez.
    curso = await _curso(sesion, curso_id, bloquear=True)
    filas = await _verificar_cierre(sesion, curso)
    await sesion.execute(
        text("""
            INSERT INTO esart.resultados_curso
              (curso_id, personal_id, nota_final, nota_exacta, materias_evaluadas, materias_habilitadas,
               promedio_area_especifica, resultado, motivo, puesto, cerrado_por_id)
            VALUES (:curso, :personal_id, :nota_final, :nota_exacta, :materias_evaluadas,
                    :materias_habilitadas, :promedio_area_especifica, :resultado, :motivo, :puesto, :usuario)
        """),
        [
            {
                **{
                    clave: fila[clave]
                    for clave in (
                        "personal_id",
                        "nota_final",
                        "materias_evaluadas",
                        "materias_habilitadas",
                        "resultado",
                        "motivo",
                        "puesto",
                    )
                },
                "nota_exacta": fila["nota_exacta"].quantize(Decimal("0.00000001")),
                "promedio_area_especifica": (
                    fila["promedio_area_especifica"].quantize(Decimal("0.00000001"))
                    if fila["promedio_area_especifica"] is not None
                    else None
                ),
                "curso": curso.id,
                "usuario": actor.usuario_id,
            }
            for fila in filas
        ],
    )
    await sesion.execute(
        text("UPDATE esart.cursos SET estado = 'CULMINADO' WHERE id = :id"), {"id": curso.id}
    )
    aprobados = [fila["personal_id"] for fila in filas if fila["resultado"] == APROBADO]
    # Historial del artillero: el curso que dejó el cargue (aprobado = false) queda aprobado.
    historial = await sesion.execute(
        text("""
            UPDATE esart.artillero_cursos ac SET aprobado = true
            FROM esart.hoja_vida_artillero hv
            WHERE hv.id = ac.hoja_vida_id AND hv.curso_id = :curso
              AND hv.artillero_id = ANY(:aprobados)
              AND ac.tipo_curso_id = :tipo AND ac.fecha_inicio = :inicio
        """),
        {
            "curso": curso.id,
            "aprobados": aprobados,
            "tipo": curso.tipo_curso_id,
            "inicio": curso.fecha_inicio,
        },
    )
    # registrar_evento confirma: el cierre y su auditoría quedan juntos o no quedan.
    await auditoria.registrar_evento(
        sesion,
        auditoria.CURSO_CERRADO,
        actor.request,
        usuario_id=actor.usuario_id,
        nombre_usuario=actor.nombre_usuario,
        resultado="EXITOSO",
        detalle={
            "curso": curso.codigo,
            "alumnos": len(filas),
            "aprobados": len(aprobados),
            "reprobados": len(filas) - len(aprobados),
            "primer_puesto": [fila["cedula"] for fila in filas if fila["puesto"] == 1],
            "historial_actualizado": historial.rowcount,
        },
    )
    return await resultados(sesion, curso_id)
