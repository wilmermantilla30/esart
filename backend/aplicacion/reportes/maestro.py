"""
Script maestro de documentos del artillero.

Recibe la opción de reporte y delega en el script que la genera:

    Opción              Script                 Archivo que entrega
    -----------------   --------------------   ------------------------------------------
    DIPLOMA             diploma.py             diploma_<cédula>.pdf
    OFICIO_REMISORIO    oficio_remisorio.py    oficio_remisorio_<cédula>.pdf
    CERTIFICACION       certificacion.py       certificacion_<cédula>.pdf

Para agregar un documento nuevo: crear su script con una función generar(datos) -> bytes y
registrarlo en REPORTES. El endpoint y el selector del front toman la lista de aquí.

Uso en código:
    pdf, nombre = generar_documento("CERTIFICACION", datos)

Uso en consola (PDF de ejemplo con datos ficticios, sin base de datos):
    python -m aplicacion.reportes.maestro DIPLOMA ejemplo.pdf
"""

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from aplicacion.reportes import certificacion, diploma, oficio_remisorio
from aplicacion.reportes.comun import (
    CriterioDocumento,
    CursoDocumento,
    DatosDocumento,
    DocumentoNoDisponible,
    ReentrenamientoDocumento,
)


@dataclass(frozen=True)
class Reporte:
    nombre: str  # texto para el selector del front
    archivo: str  # prefijo del nombre del PDF
    generar: Callable[[DatosDocumento], bytes]


REPORTES: dict[str, Reporte] = {
    "DIPLOMA": Reporte("Diploma", "diploma", diploma.generar),
    "OFICIO_REMISORIO": Reporte("Oficio remisorio", "oficio_remisorio", oficio_remisorio.generar),
    "CERTIFICACION": Reporte("Certificación", "certificacion", certificacion.generar),
}


class ReporteDesconocido(ValueError):
    """La opción recibida no está en REPORTES."""


def generar_documento(opcion: str, datos: DatosDocumento) -> tuple[bytes, str]:
    """
    Genera el PDF de la opción indicada. Devuelve (bytes del PDF, nombre de archivo sugerido).

    Lanza ReporteDesconocido si la opción no existe y DocumentoNoDisponible si el documento no
    aplica a este artillero (por ejemplo, diploma sin curso aprobado).
    """
    clave = (opcion or "").strip().upper()
    reporte = REPORTES.get(clave)
    if reporte is None:
        raise ReporteDesconocido(f"Opción de reporte desconocida: {opcion!r}. Use {', '.join(REPORTES)}.")
    # La cédula puede venir enmascarada (****1234): el nombre del archivo solo usa caracteres seguros.
    sufijo = re.sub(r"[^0-9A-Za-z]", "", datos.cedula)[-10:] or "artillero"
    return reporte.generar(datos), f"{reporte.archivo}_{sufijo}.pdf"


def datos_de_ejemplo() -> DatosDocumento:
    """Artillero ficticio para probar los formatos desde la consola."""
    return DatosDocumento(
        cedula="1024589632",
        grado="SS",
        nombres="Carlos Andrés",
        apellidos="Colorado Gil",
        categoria="SUBOFICIAL",
        unidad="Batallón de Artillería de Campaña N.º 5",
        activo=True,
        resultado="NO_APTO",
        fecha_expedicion=date.today(),
        numero="EJEMPLO-0001",
        expedido_por="consola",
        motivos=["El reentrenamiento venció el 01/10/2026."],
        criterios=[
            CriterioDocumento("Servicio activo", "OBLIGATORIO", True, "Activo"),
            CriterioDocumento(
                "Curso habilitante aprobado (SACLI o SACME)", "ALTERNATIVO", False, "Sin curso"
            ),
            CriterioDocumento("Reentrenamiento vigente (12 meses)", "ALTERNATIVO", False, "Vencido"),
        ],
        cursos=[
            CursoDocumento(
                "Curso básico de artillería", "CBA", "ESART", date(2025, 2, 3), date(2025, 6, 27), True
            ),
        ],
        reentrenamientos=[
            ReentrenamientoDocumento(
                "RT-2025-001", "Campaña", "105 mm", date(2025, 10, 1), date(2026, 10, 1), "VENCIDO"
            ),
        ],
    )


def main(argumentos: list[str]) -> int:
    if len(argumentos) != 2:
        print(f"Uso: python -m aplicacion.reportes.maestro <{'|'.join(REPORTES)}> <salida.pdf>")
        return 2
    opcion, salida = argumentos
    try:
        pdf, _ = generar_documento(opcion, datos_de_ejemplo())
    except (ReporteDesconocido, DocumentoNoDisponible) as error:
        print(error)
        return 1
    Path(salida).write_bytes(pdf)
    print(f"{opcion.upper()}: {len(pdf)} bytes -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
