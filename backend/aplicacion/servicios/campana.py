"""
S2-16: fase de campaña del CAPINTE calificada por ítems aprobado / no aprobado.

- Una materia se califica por ítems cuando tiene ítems activos en esart.items_campana (hoy la
  materia MAT-074 "FASE DE CAMPAÑA CAPINTE"). Es una materia más de la malla: su nota entra a la
  nota final como las demás.
- La registra el COMANDANTE del curso (va a campaña con los alumnos) con la misma plantilla
  firmada de S2-12, pero con una columna por ítem donde marca "X" en los aprobados. Nota de la
  fase = suma de los puntajes aprobados, con 2 decimales y tope 5,00. Después sigue la misma
  revisión del Inspector (S2-13) y, si queda bajo la mínima, la habilitación (S2-14).
- Los ítems y sus puntajes se editan en Parámetros con TOTP. Puntajes con hasta 4 decimales; la
  suma debe dar 5,00 al redondear (5 ÷ 19 = 0,2632 no suma exacto con 2 decimales).
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.confirmacion_totp import exigir_codigo_totp
from aplicacion.servicios.parametros_habilitacion import POLITICA_TOTP

CODIGO_MATERIA = "MAT-074"
MARCA_APROBADO = "X"
NOTA_TOTAL = Decimal("5")
DOS_DECIMALES = Decimal("0.01")
CUATRO_DECIMALES = Decimal("0.0001")
MAXIMO_ITEMS = 40
LONGITUD_MINIMA_NOMBRE = 3
LONGITUD_MAXIMA_NOMBRE = 200

# Materias de la malla que se califican por ítems: las que tienen ítems activos.
CONDICION_POR_ITEMS = """
    EXISTS (SELECT 1 FROM esart.items_campana ic WHERE ic.materia_id = {materia} AND ic.activo)
"""


def condicion_por_items(columna_materia: str) -> str:
    """Condición SQL: la materia de esa columna (por ejemplo 'm.materia_id') se califica por ítems."""
    return CONDICION_POR_ITEMS.format(materia=columna_materia)


# --- Ítems y cálculo -----------------------------------------------------------------------------


async def items_de_malla(sesion: AsyncSession, malla_id: int) -> list[dict]:
    """Ítems activos de la materia de esa fila de la malla, en orden ([] si se califica con nota)."""
    filas = await sesion.execute(
        text("""
            SELECT ic.id, ic.orden, ic.nombre, ic.puntaje
            FROM esart.items_campana ic
            JOIN esart.malla_curricular m ON m.materia_id = ic.materia_id
            WHERE m.id = :malla AND ic.activo
            ORDER BY ic.orden
        """),
        {"malla": malla_id},
    )
    return [dict(fila._mapping) for fila in filas]


def nota_de_items(puntajes_aprobados: list[Decimal]) -> Decimal:
    """Suma de los puntajes aprobados con 2 decimales y tope 5,00 (17 de 19 a 0,2632 = 4,47)."""
    return min(sum(puntajes_aprobados, Decimal(0)), NOTA_TOTAL).quantize(
        DOS_DECIMALES, rounding=ROUND_HALF_UP
    )


def leer_marca(valor: object) -> bool:
    """True si la celda dice X (aprobado); False si está vacía. ValueError con cualquier otra cosa."""
    texto = "" if valor is None else str(valor).strip()
    if not texto:
        return False
    if texto.upper() == MARCA_APROBADO:
        return True
    raise ValueError(f"Escriba {MARCA_APROBADO} si aprobó o deje la celda vacía (dice '{texto[:20]}').")


def firma_de_items(items: list[dict]) -> list[list]:
    """Lo que la firma de la plantilla guarda de los ítems: si cambian en Parámetros, queda vieja."""
    return [[item["id"], str(Decimal(item["puntaje"]).quantize(CUATRO_DECIMALES))] for item in items]


# --- Parámetros: ítems y puntajes ----------------------------------------------------------------


async def _materia(sesion: AsyncSession):
    fila = (
        await sesion.execute(
            text("SELECT id, codigo, nombre FROM esart.materias WHERE codigo = :codigo"),
            {"codigo": CODIGO_MATERIA},
        )
    ).one_or_none()
    if fila is None:
        raise ErrorAplicacion(
            409, "SIN_MATERIA_CAMPANA", "La malla no tiene la materia de la fase de campaña del CAPINTE."
        )
    return fila


async def obtener(sesion: AsyncSession) -> dict:
    """Ítems activos de la fase de campaña con su puntaje, el total y el último cambio."""
    materia = await _materia(sesion)
    filas = (
        await sesion.execute(
            text("""
                SELECT ic.id, ic.orden, ic.nombre, ic.puntaje, ic.actualizado_en, u.usuario AS actualizado_por
                FROM esart.items_campana ic
                LEFT JOIN esart_ref.usuarios u ON u.id = ic.actualizado_por_id
                WHERE ic.materia_id = :materia AND ic.activo
                ORDER BY ic.orden
            """),
            {"materia": materia.id},
        )
    ).all()
    ultimo = max(filas, key=lambda fila: fila.actualizado_en, default=None)
    return {
        "codigo_materia": materia.codigo,
        "materia": materia.nombre,
        "items": [
            {"id": fila.id, "orden": fila.orden, "nombre": fila.nombre, "puntaje": float(fila.puntaje)}
            for fila in filas
        ],
        "total": float(sum((fila.puntaje for fila in filas), Decimal(0))),
        "actualizado_en": ultimo.actualizado_en if ultimo else None,
        "actualizado_por": ultimo.actualizado_por if ultimo else None,
    }


def validar_items(items: list[dict]) -> list[dict]:
    """Nombres sin repetir (3 a 200 letras) y puntajes de más de 0 con máximo 4 decimales que suman 5,00."""
    if not items:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La fase de campaña debe tener al menos un ítem.")
    if len(items) > MAXIMO_ITEMS:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", f"Máximo {MAXIMO_ITEMS} ítems.")
    limpios, vistos = [], set()
    for posicion, item in enumerate(items, start=1):
        nombre = " ".join(str(item.get("nombre") or "").split())
        if not LONGITUD_MINIMA_NOMBRE <= len(nombre) <= LONGITUD_MAXIMA_NOMBRE:
            raise ErrorAplicacion(
                422,
                "DATOS_INVALIDOS",
                f"Ítem {posicion}: el nombre debe tener entre {LONGITUD_MINIMA_NOMBRE} y "
                f"{LONGITUD_MAXIMA_NOMBRE} caracteres.",
            )
        if nombre.upper() in vistos:
            raise ErrorAplicacion(422, "DATOS_INVALIDOS", f"Ítem {posicion}: '{nombre}' está repetido.")
        vistos.add(nombre.upper())
        try:
            puntaje = Decimal(str(item.get("puntaje")).replace(",", "."))
        except InvalidOperation:
            raise ErrorAplicacion(
                422, "DATOS_INVALIDOS", f"Ítem {posicion}: el puntaje no es un número."
            ) from None
        if not puntaje.is_finite() or puntaje <= 0 or puntaje > NOTA_TOTAL:
            raise ErrorAplicacion(
                422, "DATOS_INVALIDOS", f"Ítem {posicion}: el puntaje debe ser mayor que 0."
            )
        if puntaje != puntaje.quantize(CUATRO_DECIMALES):
            raise ErrorAplicacion(
                422, "DATOS_INVALIDOS", f"Ítem {posicion}: el puntaje admite como máximo 4 decimales."
            )
        limpios.append({"id": item.get("id"), "orden": posicion, "nombre": nombre, "puntaje": puntaje})
    total = sum((item["puntaje"] for item in limpios), Decimal(0))
    if total.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP) != NOTA_TOTAL:
        raise ErrorAplicacion(
            422,
            "DATOS_INVALIDOS",
            f"Los puntajes deben sumar 5,00 y suman {total.quantize(CUATRO_DECIMALES)}.",
        )
    return limpios


async def guardar(
    sesion: AsyncSession,
    items: list[dict],
    version_esperada: datetime | None,
    *,
    usuario_id: int,
    nombre_usuario: str,
    codigo_totp: str | None,
    request: Request,
) -> dict:
    """Reemplaza los ítems activos (con TOTP). Los retirados quedan inactivos: las entregas los usan."""
    nuevos = validar_items(items)
    vigente = await obtener(sesion)
    # Otro administrador guardó después de que este abrió el formulario: no se sobrescribe.
    if version_esperada != vigente["actualizado_en"]:
        raise ErrorAplicacion(
            409,
            "PARAMETROS_DESACTUALIZADOS",
            "Otro usuario cambió los ítems de la fase de campaña mientras usted editaba. Recargue y revise.",
        )
    actuales = {item["id"]: item for item in vigente["items"]}
    for item in nuevos:
        if item["id"] is not None and item["id"] not in actuales:
            raise ErrorAplicacion(
                422, "DATOS_INVALIDOS", "Uno de los ítems ya no existe. Recargue la página."
            )
    antes = [[item["nombre"], f"{Decimal(str(item['puntaje'])):.4f}"] for item in vigente["items"]]
    despues = [[item["nombre"], f"{item['puntaje']:.4f}"] for item in nuevos]
    if antes == despues:
        raise ErrorAplicacion(422, "SIN_CAMBIOS", "Los ítems son iguales a los vigentes.")

    await exigir_codigo_totp(
        sesion,
        usuario_id,
        POLITICA_TOTP,
        codigo_totp,
        request,
        prefijo_auditoria="PARAMETROS",
        mensaje_requerido="Ingrese el código del autenticador para guardar los ítems de la fase de campaña.",
    )
    materia = await _materia(sesion)
    parametros = {"materia": materia.id, "usuario": usuario_id}
    # El orden es único entre los activos: primero se corren todos para poder reordenar sin choques.
    await sesion.execute(
        text("UPDATE esart.items_campana SET orden = orden + 10000 WHERE materia_id = :materia AND activo"),
        parametros,
    )
    conservados = {item["id"] for item in nuevos if item["id"] is not None}
    await sesion.execute(
        text("""
            UPDATE esart.items_campana
            SET activo = false, actualizado_por_id = :usuario, actualizado_en = now()
            WHERE materia_id = :materia AND activo AND NOT (id = ANY(:conservados))
        """),
        {**parametros, "conservados": list(conservados)},
    )
    for item in nuevos:
        datos = {**parametros, "orden": item["orden"], "nombre": item["nombre"], "puntaje": item["puntaje"]}
        if item["id"] is None:
            await sesion.execute(
                text("""
                    INSERT INTO esart.items_campana (materia_id, orden, nombre, puntaje, actualizado_por_id)
                    VALUES (:materia, :orden, :nombre, :puntaje, :usuario)
                """),
                datos,
            )
        else:
            await sesion.execute(
                text("""
                    UPDATE esart.items_campana
                    SET orden = :orden, nombre = :nombre, puntaje = :puntaje,
                        actualizado_por_id = :usuario, actualizado_en = now()
                    WHERE id = :id
                """),
                {**datos, "id": item["id"]},
            )
    # La auditoría va en la misma transacción: si no se puede registrar, no se aplica el cambio.
    await auditoria.registrar_evento(
        sesion,
        auditoria.PARAMETROS_ACTUALIZADOS,
        request,
        usuario_id=usuario_id,
        nombre_usuario=nombre_usuario,
        resultado="EXITOSO",
        detalle={"cambios": {"FASE_CAMPANA_CAPINTE": {"anterior": antes, "nuevo": despues}}},
    )
    return await obtener(sesion)
