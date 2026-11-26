"""
S2-14: habilitación de materias perdidas (lado del instructor, componente NOTAS_CARGA).

- Debe habilitar el alumno cuya nota oficial ORDINARIA de la materia quedó por debajo de la nota
  mínima del curso (notas_oficiales.nota_ordinaria, S2-13). Una sola habilitación por materia.
- El instructor titular escribe la nota de habilitación de esos alumnos en un formulario en
  pantalla (decisión de la Escuela: suelen ser pocos). Se exige la de TODOS, de 0 a 5 con 2
  decimales, igual que la planilla.
- Se guarda como una entrega de tipo HABILITACION que pasa por la misma revisión del Inspector
  (S2-13). Mientras esté en revisión o devuelta, registrar de nuevo la reemplaza.
- Al aprobarla (revision_notas.aprobar) se aplica el resultado: quien alcanza la mínima queda con
  la nota de habilitación ("Habilitada"); quien no, pasa al Consejo Académico.
"""

import hashlib
import json
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.administracion_usuarios import Actor
from aplicacion.servicios.autenticacion import UsuarioAutenticado
from aplicacion.servicios.notas import (
    MAXIMO_ERRORES,
    TIPO_HABILITACION,
    entrega_reemplazable,
    guardar_entrega,
    leer_nota,
    materia_asignada,
)

NOMBRE_ENTREGA = "Formulario de habilitación"


async def alumnos_a_habilitar(sesion: AsyncSession, curso_id: int, malla_id: int) -> list[dict]:
    """Alumnos cuya nota ordinaria oficial de la materia quedó por debajo de la mínima del curso."""
    filas = await sesion.execute(
        text("""
            SELECT p.id, p.documento_identidad AS cedula, p.grado, p.apellidos, p.nombres, o.nota_ordinaria
            FROM esart.notas_oficiales o
            JOIN esart.cursos c ON c.id = o.curso_id
            JOIN esart.personal_militar p ON p.id = o.personal_id
            WHERE o.curso_id = :curso AND o.malla_id = :malla AND o.nota_ordinaria < c.nota_minima_aprobacion
            ORDER BY p.apellidos, p.nombres, p.id
        """),
        {"curso": curso_id, "malla": malla_id},
    )
    return [dict(fila._mapping) for fila in filas]


async def formulario(sesion: AsyncSession, usuario: UsuarioAutenticado, curso_id: int, malla_id: int) -> dict:
    """Alumnos que deben habilitar la materia y, si ya se registró, la entrega de habilitación."""
    materia = await materia_asignada(sesion, usuario, curso_id, malla_id)
    alumnos = await alumnos_a_habilitar(sesion, curso_id, malla_id)
    entrega = (
        await sesion.execute(
            text("""
                SELECT id, estado, subido_en, revisado_en, observacion_revision
                FROM esart.entregas_notas
                WHERE curso_id = :c AND malla_id = :m AND tipo = 'HABILITACION'
            """),
            {"c": curso_id, "m": malla_id},
        )
    ).one_or_none()
    notas: dict[int, Decimal] = {}
    if entrega is not None:
        notas = {
            fila.personal_id: fila.nota
            for fila in await sesion.execute(
                text("SELECT personal_id, nota FROM esart.notas_entrega WHERE entrega_id = :e"),
                {"e": entrega.id},
            )
        }
    return {
        "curso_id": materia.curso_id,
        "codigo_curso": materia.codigo_curso,
        "materia": materia.materia,
        "nota_minima": float(materia.nota_minima) if materia.nota_minima is not None else None,
        "alumnos": [
            {
                "cedula": alumno["cedula"],
                "grado": alumno["grado"],
                "apellidos": alumno["apellidos"],
                "nombres": alumno["nombres"],
                "nota_ordinaria": float(alumno["nota_ordinaria"]),
                "nota_habilitacion": float(notas[alumno["id"]]) if alumno["id"] in notas else None,
            }
            for alumno in alumnos
        ],
        "estado": entrega.estado if entrega else None,
        "subido_en": entrega.subido_en if entrega else None,
        "revisado_en": entrega.revisado_en if entrega else None,
        "observacion_revision": entrega.observacion_revision if entrega else None,
    }


def leer_notas_formulario(notas: list[dict], alumnos: list[dict]) -> dict[int, Decimal]:
    """{personal_id: nota} con la nota de TODOS los alumnos a habilitar; 422 con la lista de errores."""
    por_cedula = {alumno["cedula"]: alumno for alumno in alumnos}
    errores: list[dict] = []
    leidas: dict[int, Decimal] = {}
    for fila in notas:
        alumno = por_cedula.get(str(fila.get("cedula") or "").strip())
        if alumno is None:
            errores.append(
                {"fila": None, "mensaje": f"{fila.get('cedula')}: no debe habilitar esta materia."}
            )
            continue
        if alumno["id"] in leidas:
            errores.append({"fila": None, "mensaje": f"{alumno['cedula']}: aparece dos veces."})
            continue
        try:
            leidas[alumno["id"]] = leer_nota(fila.get("nota"))
        except ValueError as motivo:
            errores.append({"fila": None, "mensaje": f"{alumno['apellidos']} ({alumno['cedula']}): {motivo}"})
            leidas[alumno["id"]] = None
    for alumno in alumnos:
        if alumno["id"] not in leidas:
            errores.append(
                {"fila": None, "mensaje": f"{alumno['apellidos']} ({alumno['cedula']}): Falta la nota."}
            )
    if errores:
        raise ErrorAplicacion(
            422,
            "NOTAS_INVALIDAS",
            f"Hay {len(errores)} error(es) en las notas de habilitación: no se guardó nada.",
            {"errores": errores[:MAXIMO_ERRORES]},
        )
    return leidas


async def registrar(
    sesion: AsyncSession,
    usuario: UsuarioAutenticado,
    curso_id: int,
    malla_id: int,
    notas: list[dict],
    *,
    actor: Actor,
) -> dict:
    """Guarda las notas de habilitación como entrega EN_REVISION para el Inspector."""
    materia = await materia_asignada(sesion, usuario, curso_id, malla_id)
    alumnos = await alumnos_a_habilitar(sesion, curso_id, malla_id)
    if not alumnos:
        raise ErrorAplicacion(
            409,
            "SIN_HABILITACIONES",
            "Ningún alumno debe habilitar esta materia (o sus notas no están aprobadas).",
        )
    anterior = await entrega_reemplazable(sesion, materia, TIPO_HABILITACION)
    leidas = leer_notas_formulario(notas, alumnos)
    # Huella de lo enviado: identifica la entrega igual que el sha256 del archivo en la planilla.
    contenido = json.dumps(sorted((pid, str(nota)) for pid, nota in leidas.items()), separators=(",", ":"))
    await guardar_entrega(
        sesion,
        materia,
        TIPO_HABILITACION,
        anterior,
        NOMBRE_ENTREGA,
        hashlib.sha256(contenido.encode()).hexdigest(),
        leidas,
        actor=actor,
    )
    return await formulario(sesion, usuario, curso_id, malla_id)
