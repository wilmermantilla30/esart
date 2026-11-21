"""
S2-01: carga inicial de la malla curricular desde el Excel revisado por la Escuela.

El archivo es docs/backlog_sprint2_esart.xlsx (o una copia con el mismo formato):
- Hoja "Materias": catálogo único (columna B = nombre oficial, G = revisión).
- Hoja "Malla por curso": A = curso, B = orden, C = área, D = módulo, F = materia oficial,
  H = evaluable (Sí / No).

Uso, desde backend/:
    python -m herramientas.cargar_malla_curricular listar
    python -m herramientas.cargar_malla_curricular cargar RUTA.xlsx --anio 2026             # solo revisa
    python -m herramientas.cargar_malla_curricular cargar RUTA.xlsx --anio 2026 --ejecutar  # guarda

- Sin --ejecutar no escribe nada: valida el archivo y muestra qué haría.
- Rechaza el archivo si alguna materia sigue "Por confirmar", "Unificar" o "Eliminar". Solo en
  ENTORNO=desarrollo se puede forzar con --aceptar-pendientes (para pruebas locales).
- Un tipo de curso que ya tiene malla vigente se omite: los cambios se hacen desde Parámetros
  (S2-09), que crea una versión nueva y deja auditado el antes y el después.
- Todo en una sola transacción: o se cargan todas las mallas o ninguna. Cada malla queda en la
  auditoría (MALLA_CURRICULAR_CARGADA) como "consola", con el usuario del sistema operativo.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import obtener_configuracion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import malla_curricular as servicio
from aplicacion.servicios.administracion_usuarios import Actor
from herramientas.administrar_usuarios import operador_del_sistema

HOJA_MATERIAS = "Materias"
HOJA_MALLA = "Malla por curso"
FILA_DATOS = 5  # filas 1-4: título, subtítulo y encabezados
REVISION_CONFIRMADA = "Confirmada"
EVALUABLE = {"SÍ": True, "SI": True, "NO": False}
TAMANO_MAXIMO_ARCHIVO = 5 * 1024 * 1024


@dataclass
class LibroMalla:
    """Contenido del Excel ya validado."""

    materias: list[str] = field(default_factory=list)  # orden del catálogo (define MAT-001...)
    pendientes: list[str] = field(default_factory=list)  # materias sin revisión "Confirmada"
    mallas: dict[str, list[servicio.FilaMalla]] = field(default_factory=dict)


class ArchivoInvalido(Exception):
    """El Excel no tiene el formato esperado; el mensaje dice qué corregir."""


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def leer_libro(ruta: Path) -> LibroMalla:
    """Lee y valida las dos hojas. No toca la base de datos."""
    if not ruta.is_file():
        raise ArchivoInvalido(f"No existe el archivo {ruta}.")
    if ruta.stat().st_size > TAMANO_MAXIMO_ARCHIVO:
        raise ArchivoInvalido("El archivo supera 5 MB: no parece la malla curricular.")
    try:
        libro = load_workbook(ruta, read_only=True, data_only=True)
    except Exception as error:  # noqa: BLE001 - cualquier archivo dañado se informa igual
        raise ArchivoInvalido(f"No se pudo abrir el Excel: {type(error).__name__}.") from None
    try:
        faltantes = {HOJA_MATERIAS, HOJA_MALLA} - set(libro.sheetnames)
        if faltantes:
            raise ArchivoInvalido(f"Faltan las hojas: {', '.join(sorted(faltantes))}.")
        resultado = LibroMalla()

        # Catálogo: el nombre oficial y su revisión.
        catalogo = {}
        for numero, fila in enumerate(
            libro[HOJA_MATERIAS].iter_rows(min_row=FILA_DATOS, values_only=True), FILA_DATOS
        ):
            nombre = servicio.normalizar_nombre(_texto(fila[1] if len(fila) > 1 else None))
            if not nombre:
                continue
            if nombre in catalogo:
                raise ArchivoInvalido(f"Hoja Materias, fila {numero}: '{nombre}' está repetida.")
            revision = _texto(fila[6] if len(fila) > 6 else None)
            catalogo[nombre] = revision
            resultado.materias.append(nombre)
            if revision != REVISION_CONFIRMADA:
                resultado.pendientes.append(f"{nombre} ({revision or 'sin revisión'})")

        # Malla de cada curso.
        for numero, fila in enumerate(
            libro[HOJA_MALLA].iter_rows(min_row=FILA_DATOS, values_only=True), FILA_DATOS
        ):
            fila = tuple(fila) + (None,) * (8 - len(fila))
            curso, materia = _texto(fila[0]).upper(), servicio.normalizar_nombre(_texto(fila[5]))
            if not curso or not materia:
                continue  # fila vacía o curso sin materias (TECNICA)
            if materia not in catalogo:
                raise ArchivoInvalido(
                    f"Hoja Malla por curso, fila {numero}: '{materia}' no está en Materias."
                )
            evaluable = EVALUABLE.get(_texto(fila[7]).upper())
            if evaluable is None:
                raise ArchivoInvalido(f"Hoja Malla por curso, fila {numero}: Evaluable debe ser Sí o No.")
            try:
                orden = int(fila[1])
            except (TypeError, ValueError):
                raise ArchivoInvalido(
                    f"Hoja Malla por curso, fila {numero}: el orden no es un número."
                ) from None
            resultado.mallas.setdefault(curso, []).append(
                servicio.FilaMalla(
                    orden=orden,
                    materia=materia,
                    evaluable=evaluable,
                    area=_texto(fila[2]) or None,
                    modulo=_texto(fila[3]) or None,
                )
            )
        if not resultado.mallas:
            raise ArchivoInvalido("La hoja Malla por curso no tiene materias.")
        # Las materias del catálogo que ninguna malla usa no se crean.
        usadas = {fila.materia for filas in resultado.mallas.values() for fila in filas}
        resultado.materias = [nombre for nombre in resultado.materias if nombre in usadas]
        return resultado
    finally:
        libro.close()


async def listar() -> int:
    try:
        async with obtener_fabrica_sesiones()() as sesion:
            vigentes = await servicio.resumen_vigentes(sesion)
    finally:
        await cerrar_motor_base_datos()
    if not vigentes:
        print("Ningún tipo de curso tiene malla curricular todavía.")
    for item in vigentes:
        print(
            f"{item.tipo_curso:<14} versión {item.numero} ({item.anio}): "
            f"{item.materias} materias, {item.evaluables} con nota"
        )
    return 0


async def cargar(ruta: Path, anio: int, ejecutar: bool, aceptar_pendientes: bool) -> int:
    try:
        contenido = leer_libro(ruta)
    except ArchivoInvalido as error:
        print(f"Archivo rechazado: {error}")
        return 1
    if contenido.pendientes:
        print(f"{len(contenido.pendientes)} materias no están confirmadas por la Escuela:")
        for pendiente in contenido.pendientes:
            print(f"  - {pendiente}")
        if not aceptar_pendientes:
            print("Rechazado: confirme o unifique esas materias en la hoja Materias.")
            return 1
        if obtener_configuracion().entorno != "desarrollo":
            print("Rechazado: --aceptar-pendientes solo se admite con ENTORNO=desarrollo.")
            return 1
        print("Se aceptan por --aceptar-pendientes (solo desarrollo).")

    actor = Actor.consola(operador_del_sistema())
    try:
        async with obtener_fabrica_sesiones()() as sesion:
            # Primero se valida todo: un tipo inexistente o una malla inválida no deja nada a medias.
            tipos = {}
            for codigo, filas in contenido.mallas.items():
                tipos[codigo] = await servicio.tipo_curso_por_codigo(sesion, codigo)
                servicio.validar_filas(filas)
            omitidos, a_cargar = [], []
            for codigo, tipo in tipos.items():
                actual = await servicio.version_vigente(sesion, tipo.id)
                (omitidos if actual else a_cargar).append((codigo, tipo, actual))

            for codigo, _, actual in omitidos:
                print(
                    f"{codigo:<14} se omite: ya tiene la versión {actual.numero} vigente "
                    "(edítela en Parámetros)."
                )
            for codigo, _, _ in a_cargar:
                filas = contenido.mallas[codigo]
                evaluables = sum(1 for fila in filas if fila.evaluable)
                sin_nota = len(filas) - evaluables
                print(f"{codigo:<14} {len(filas)} materias ({evaluables} con nota, {sin_nota} sin nota).")
            if not a_cargar:
                print("Nada que cargar.")
                return 0
            if not ejecutar:
                print("Revisión sin cambios. Para guardar, repita el comando con --ejecutar.")
                return 0

            # El catálogo se crea en el orden de la hoja Materias (MAT-001, MAT-002...).
            await servicio.asegurar_materias(sesion, contenido.materias)
            for codigo, tipo, _ in a_cargar:
                await servicio.crear_version(sesion, tipo, anio, contenido.mallas[codigo], actor)
            await sesion.commit()
    except ErrorAplicacion as error:
        print(f"Operación detenida: {error.mensaje} {error.detalle or ''}".strip())
        return 1
    except Exception as error:  # noqa: BLE001 - nunca se muestra la URL ni datos de conexión
        print(f"Operación detenida: {type(error).__name__}; no se guardó nada.")
        return 1
    finally:
        await cerrar_motor_base_datos()
    print(f"Listo: {len(a_cargar)} mallas cargadas para {anio}.")
    return 0


def construir_argumentos() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="python -m herramientas.cargar_malla_curricular", description="Malla curricular de ESART."
    )
    comandos = analizador.add_subparsers(dest="comando", required=True)
    comandos.add_parser("listar", help="Malla vigente de cada tipo de curso.")
    cargar_parser = comandos.add_parser("cargar", help="Carga las mallas desde el Excel revisado.")
    cargar_parser.add_argument("archivo", type=Path, help="Excel con las hojas Materias y Malla por curso.")
    cargar_parser.add_argument("--anio", type=int, required=True, help="Año de la malla, por ejemplo 2026.")
    cargar_parser.add_argument(
        "--ejecutar", action="store_true", help="Guarda los cambios (sin esto solo revisa)."
    )
    cargar_parser.add_argument(
        "--aceptar-pendientes",
        action="store_true",
        help="Solo desarrollo: carga aunque haya materias sin confirmar.",
    )
    return analizador


def principal(argumentos: list[str] | None = None) -> int:
    opciones = construir_argumentos().parse_args(argumentos)
    if opciones.comando == "listar":
        return asyncio.run(listar())
    return asyncio.run(
        cargar(opciones.archivo, opciones.anio, opciones.ejecutar, opciones.aceptar_pendientes)
    )


if __name__ == "__main__":
    sys.exit(principal())
