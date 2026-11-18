"""
Regla de habilitación de artilleros: APTO / NO APTO.

    APTO = militar ACTIVO  y  ( curso habilitante APROBADO  o  reentrenamiento VIGENTE )

- Curso habilitante: tipos de curso de CURSOS_HABILITANTES (hoy SACLI y SACME). Cuenta como
  aprobado si está marcado 'aprobado' y ya terminó (fecha_fin hoy o antes). No vence.
- Reentrenamiento vigente: certificado marcado vigente (y apto para disparar, si el parámetro
  lo exige) cuya fecha de expedición + MESES_VIGENCIA_REENTRENAMIENTO es hoy o posterior.
- "Por vencer": vigente y le quedan DIAS_ALERTA_VENCIMIENTO días o menos.

El estado se calcula en UNA consulta SQL (CONSULTA_ESTADO). La usan la verificación individual,
el listado y el resumen: así nunca dan resultados distintos y el listado escala a decenas de
miles de militares. 'Hoy' es la fecha de Colombia según el reloj de PostgreSQL.
"""

import math
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.modelos import ParametroHabilitacion
from aplicacion.nucleo.errores import ErrorAplicacion

RESULTADO_APTO = "APTO"
RESULTADO_NO_APTO = "NO_APTO"

ESTADO_REENTRENAMIENTO_VIGENTE = "VIGENTE"
ESTADO_REENTRENAMIENTO_POR_VENCER = "POR_VENCER"
ESTADO_REENTRENAMIENTO_VENCIDO = "VENCIDO"
ESTADO_REENTRENAMIENTO_SIN_REGISTRO = "SIN_REGISTRO"

# Filtros del listado de habilitación.
FILTRO_APTO = "APTO"
FILTRO_NO_APTO = "NO_APTO"
FILTRO_POR_VENCER = "POR_VENCER"
FILTROS_ESTADO = (FILTRO_APTO, FILTRO_NO_APTO, FILTRO_POR_VENCER)

# Cédula: solo dígitos tras quitar puntos, espacios y guiones (contrato §3).
PATRON_CEDULA = re.compile(r"^\d{5,15}$")
CARACTERES_A_QUITAR_DE_CEDULA = re.compile(r"[\s.\-]")
DIGITOS_VISIBLES_CEDULA = 4

MESES_ABREVIADOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


@dataclass(frozen=True)
class ParametrosHabilitacion:
    """Valores vigentes de la regla, leídos de esart.parametros_habilitacion."""

    cursos_habilitantes: list[str]
    meses_vigencia_reentrenamiento: int
    dias_alerta_vencimiento: int
    exige_apto_para_disparar: bool


async def cargar_parametros(sesion: AsyncSession) -> ParametrosHabilitacion:
    """Lee los parámetros. Si falta alguno, la verificación no puede decidir: error 500 controlado."""
    valores = {p.codigo: p.valor for p in await sesion.scalars(select(ParametroHabilitacion))}
    try:
        return ParametrosHabilitacion(
            cursos_habilitantes=[str(codigo) for codigo in valores["CURSOS_HABILITANTES"]],
            meses_vigencia_reentrenamiento=int(valores["MESES_VIGENCIA_REENTRENAMIENTO"]),
            dias_alerta_vencimiento=int(valores["DIAS_ALERTA_VENCIMIENTO"]),
            exige_apto_para_disparar=bool(valores["EXIGE_APTO_PARA_DISPARAR"]),
        )
    except (KeyError, TypeError, ValueError):
        raise ErrorAplicacion(
            500, "ERROR_INTERNO", "Los parámetros de habilitación no están configurados correctamente."
        ) from None


# Estado de habilitación de cada militar. Los filtros se agregan como condiciones fijas
# (nunca texto del usuario): los valores siempre van como parámetros enlazados.
CONSULTA_ESTADO = """
WITH hoy AS (
    SELECT (now() AT TIME ZONE 'America/Bogota')::date AS fecha
),
cursos AS (
    SELECT hv.artillero_id AS personal_id,
           min(ac.fecha_fin) FILTER (WHERE ac.aprobado AND ac.fecha_fin <= hoy.fecha) AS fecha_curso,
           (array_agg(tc.codigo ORDER BY ac.fecha_fin)
              FILTER (WHERE ac.aprobado AND ac.fecha_fin <= hoy.fecha))[1] AS codigo_curso,
           bool_or(NOT (ac.aprobado AND ac.fecha_fin IS NOT NULL AND ac.fecha_fin <= hoy.fecha))
              AS curso_en_progreso,
           (array_agg(tc.codigo ORDER BY ac.fecha_inicio DESC)
              FILTER (WHERE NOT (ac.aprobado AND ac.fecha_fin IS NOT NULL AND ac.fecha_fin <= hoy.fecha)))[1]
              AS codigo_en_progreso
    FROM esart.artillero_cursos ac
    JOIN esart.hoja_vida_artillero hv ON hv.id = ac.hoja_vida_id
    JOIN esart.tipos_curso tc ON tc.id = ac.tipo_curso_id
    CROSS JOIN hoy
    WHERE tc.codigo = ANY(CAST(:cursos_habilitantes AS text[]))
    GROUP BY hv.artillero_id
),
reentrenamientos AS (
    SELECT cr.personal_id,
           max((cr.fecha_expedicion + make_interval(months => CAST(:meses_vigencia AS integer)))::date)
             AS fecha_vencimiento
    FROM esart.certificados_reentrenamiento cr
    WHERE cr.vigente
      AND (cr.apto_para_disparar OR NOT CAST(:exige_apto_para_disparar AS boolean))
    GROUP BY cr.personal_id
),
estado AS (
    SELECT p.id, p.documento_identidad, p.nombres, p.apellidos, p.grado, p.categoria, p.activo,
           p.unidad_actual_id, u.codigo AS unidad_codigo, u.nombre AS unidad_nombre,
           c.codigo_curso, c.fecha_curso, coalesce(c.curso_en_progreso, false) AS curso_en_progreso,
           c.codigo_en_progreso,
           r.fecha_vencimiento AS reentrenamiento_vence,
           coalesce(r.fecha_vencimiento >= hoy.fecha, false) AS reentrenamiento_vigente,
           coalesce(r.fecha_vencimiento >= hoy.fecha
                    AND r.fecha_vencimiento <= hoy.fecha + CAST(:dias_alerta AS integer), false)
             AS reentrenamiento_por_vencer,
           CASE WHEN p.activo AND (c.fecha_curso IS NOT NULL OR r.fecha_vencimiento >= hoy.fecha)
                THEN 'APTO' ELSE 'NO_APTO' END AS resultado,
           hoy.fecha AS hoy
    FROM esart.personal_militar p
    CROSS JOIN hoy
    LEFT JOIN esart_ref.unidades_militares u ON u.id = p.unidad_actual_id
    LEFT JOIN cursos c ON c.personal_id = p.id
    LEFT JOIN reentrenamientos r ON r.personal_id = p.id
)
"""

CONDICIONES_FILTRO_ESTADO = {
    FILTRO_APTO: "resultado = 'APTO'",
    FILTRO_NO_APTO: "resultado = 'NO_APTO'",
    FILTRO_POR_VENCER: "reentrenamiento_por_vencer",
}


def _parametros_sql(parametros: ParametrosHabilitacion) -> dict:
    return {
        "cursos_habilitantes": parametros.cursos_habilitantes,
        "meses_vigencia": parametros.meses_vigencia_reentrenamiento,
        "dias_alerta": parametros.dias_alerta_vencimiento,
        "exige_apto_para_disparar": parametros.exige_apto_para_disparar,
    }


# --- Utilidades de presentación ---------------------------------------------------------


def normalizar_cedula(numero_documento: str) -> str:
    """Quita puntos, espacios y guiones; exige solo dígitos (5 a 15). Si no, 422 DATOS_INVALIDOS."""
    cedula = CARACTERES_A_QUITAR_DE_CEDULA.sub("", numero_documento or "")
    if not PATRON_CEDULA.match(cedula):
        raise ErrorAplicacion(
            422,
            "DATOS_INVALIDOS",
            "La cédula debe tener solo números (entre 5 y 15 dígitos).",
            {"campos": [{"campo": "numero_documento", "motivo": "Formato de cédula inválido"}]},
        )
    return cedula


def enmascarar_cedula(cedula: str, ver_completa: bool) -> str:
    """Sin el permiso VER_DOCUMENTO_COMPLETO solo se ven los últimos 4 dígitos (******5678)."""
    if ver_completa or len(cedula) <= DIGITOS_VISIBLES_CEDULA:
        return cedula
    return "*" * (len(cedula) - DIGITOS_VISIBLES_CEDULA) + cedula[-DIGITOS_VISIBLES_CEDULA:]


def formatear_fecha(fecha: date) -> str:
    """Fecha legible en español: 16-nov-2027."""
    return f"{fecha.day:02d}-{MESES_ABREVIADOS[fecha.month - 1]}-{fecha.year}"


def describir_antiguedad(desde: date, hasta: date) -> str:
    """Tiempo transcurrido en palabras: 'hace 2 años y 8 meses', 'hace 3 meses', 'este mes'."""
    meses_totales = (hasta.year - desde.year) * 12 + (hasta.month - desde.month)
    if hasta.day < desde.day:
        meses_totales -= 1
    anios, meses = divmod(max(meses_totales, 0), 12)
    partes = []
    if anios:
        partes.append(f"{anios} año{'s' if anios != 1 else ''}")
    if meses:
        partes.append(f"{meses} mes{'es' if meses != 1 else ''}")
    return "hace " + " y ".join(partes) if partes else "este mes"


def estado_reentrenamiento(fila) -> str:
    if fila.reentrenamiento_vence is None:
        return ESTADO_REENTRENAMIENTO_SIN_REGISTRO
    if fila.reentrenamiento_por_vencer:
        return ESTADO_REENTRENAMIENTO_POR_VENCER
    if fila.reentrenamiento_vigente:
        return ESTADO_REENTRENAMIENTO_VIGENTE
    return ESTADO_REENTRENAMIENTO_VENCIDO


def nombre_completo(fila) -> str:
    return f"{fila.nombres} {fila.apellidos}".strip()


# --- Criterios (lo que se le muestra al Comandante) -------------------------------------


@dataclass(frozen=True)
class Criterio:
    descripcion: str
    # OBLIGATORIO: debe cumplirse. ALTERNATIVO: basta que se cumpla uno de los alternativos.
    tipo: str
    cumple: bool
    detalle: str | None
    motivo: str | None


def construir_criterios(fila, parametros: ParametrosHabilitacion) -> list[Criterio]:
    """Traduce el estado calculado en SQL a criterios legibles, con su motivo cuando no se cumplen."""
    cursos_texto = " o ".join(parametros.cursos_habilitantes) or "(ninguno configurado)"
    criterios = [
        Criterio(
            descripcion="Estado de servicio activo",
            tipo="OBLIGATORIO",
            cumple=fila.activo,
            detalle=None,
            motivo=None if fila.activo else "El militar figura como inactivo.",
        )
    ]

    if fila.fecha_curso is not None:
        detalle_curso = (
            f"{fila.codigo_curso} aprobado el {formatear_fecha(fila.fecha_curso)} "
            f"({describir_antiguedad(fila.fecha_curso, fila.hoy)})."
        )
        motivo_curso = None
    elif fila.curso_en_progreso:
        detalle_curso = None
        motivo_curso = f"Tiene el curso {fila.codigo_en_progreso} en curso, aún no aprobado."
    else:
        detalle_curso = None
        motivo_curso = f"No tiene curso {cursos_texto} aprobado."
    criterios.append(
        Criterio(
            descripcion=f"Curso habilitante aprobado ({cursos_texto})",
            tipo="ALTERNATIVO",
            cumple=fila.fecha_curso is not None,
            detalle=detalle_curso,
            motivo=motivo_curso,
        )
    )

    estado = estado_reentrenamiento(fila)
    detalle_reentrenamiento = motivo_reentrenamiento = None
    if estado in (ESTADO_REENTRENAMIENTO_VIGENTE, ESTADO_REENTRENAMIENTO_POR_VENCER):
        dias = (fila.reentrenamiento_vence - fila.hoy).days
        detalle_reentrenamiento = (
            f"Vigente hasta el {formatear_fecha(fila.reentrenamiento_vence)} (faltan {dias} días)."
        )
    elif estado == ESTADO_REENTRENAMIENTO_VENCIDO:
        motivo_reentrenamiento = f"Reentrenamiento vencido el {formatear_fecha(fila.reentrenamiento_vence)}."
    else:
        motivo_reentrenamiento = "No tiene reentrenamiento vigente registrado."
    criterios.append(
        Criterio(
            descripcion="Reentrenamiento vigente",
            tipo="ALTERNATIVO",
            cumple=fila.reentrenamiento_vigente,
            detalle=detalle_reentrenamiento,
            motivo=motivo_reentrenamiento,
        )
    )
    return criterios


def construir_alerta(fila) -> str | None:
    """Aviso para planear el próximo reentrenamiento cuando está por vencer."""
    if not fila.reentrenamiento_por_vencer:
        return None
    dias = (fila.reentrenamiento_vence - fila.hoy).days
    return (
        f"El reentrenamiento vence el {formatear_fecha(fila.reentrenamiento_vence)} "
        f"(faltan {dias} días). Planee el próximo reentrenamiento."
    )


def motivos_no_apto(criterios: list[Criterio]) -> list[str]:
    """Motivos que explican un NO APTO (vacío si es APTO)."""
    obligatorio_falla = [c.motivo for c in criterios if c.tipo == "OBLIGATORIO" and not c.cumple and c.motivo]
    alternativos = [c for c in criterios if c.tipo == "ALTERNATIVO"]
    if any(c.cumple for c in alternativos):
        return obligatorio_falla
    return obligatorio_falla + [c.motivo for c in alternativos if c.motivo]


# --- Consultas -------------------------------------------------------------------------


async def verificar_artillero(sesion: AsyncSession, numero_documento: str):
    """
    Estado de un militar por cédula, con sus criterios, cursos y reentrenamientos.
    Devuelve (fila_estado, criterios, cursos, reentrenamientos, parametros). 404 si no existe.
    """
    cedula = normalizar_cedula(numero_documento)
    parametros = await cargar_parametros(sesion)
    fila = (
        await sesion.execute(
            # SQL solo de constantes de este archivo; la cédula va como parámetro enlazado.
            text(CONSULTA_ESTADO + "SELECT * FROM estado WHERE documento_identidad = :cedula"),  # noqa: S608
            {**_parametros_sql(parametros), "cedula": cedula},
        )
    ).first()
    if fila is None:
        raise ErrorAplicacion(404, "ARTILLERO_NO_ENCONTRADO", "No se encontró un militar con esa cédula.")

    cursos = (
        await sesion.execute(
            text("""
                SELECT coalesce(tc.nombre, ac.nombre) AS nombre, tc.codigo, ac.institucion,
                       ac.fecha_inicio, ac.fecha_fin, ac.aprobado,
                       (ac.aprobado AND ac.fecha_fin IS NOT NULL
                        AND ac.fecha_fin <= (now() AT TIME ZONE 'America/Bogota')::date)
                         AS finalizado_aprobado,
                       tc.codigo = ANY(CAST(:cursos_habilitantes AS text[])) AS habilitante
                FROM esart.artillero_cursos ac
                JOIN esart.hoja_vida_artillero hv ON hv.id = ac.hoja_vida_id
                LEFT JOIN esart.tipos_curso tc ON tc.id = ac.tipo_curso_id
                WHERE hv.artillero_id = :personal_id
                ORDER BY ac.fecha_inicio DESC
            """),
            {"personal_id": fila.id, "cursos_habilitantes": parametros.cursos_habilitantes},
        )
    ).all()
    reentrenamientos = (
        await sesion.execute(
            text("""
                SELECT cr.numero_certificado, cr.tipo, cr.calibre, cr.fecha_expedicion,
                       (cr.fecha_expedicion + make_interval(months => CAST(:meses_vigencia AS integer)))::date
                         AS fecha_vencimiento,
                       cr.vigente, cr.apto_para_disparar
                FROM esart.certificados_reentrenamiento cr
                WHERE cr.personal_id = :personal_id
                ORDER BY cr.fecha_expedicion DESC
            """),
            {"personal_id": fila.id, "meses_vigencia": parametros.meses_vigencia_reentrenamiento},
        )
    ).all()
    return fila, construir_criterios(fila, parametros), cursos, reentrenamientos, parametros


def _condiciones_listado(estado: str | None, unidad_id: int | None, grado: str | None, texto: str | None):
    """Condiciones WHERE fijas + parámetros enlazados (los valores nunca se pegan al SQL)."""
    condiciones, valores = [], {}
    if estado:
        condiciones.append(CONDICIONES_FILTRO_ESTADO[estado])
    if unidad_id is not None:
        condiciones.append("unidad_actual_id = :unidad_id")
        valores["unidad_id"] = unidad_id
    if grado:
        condiciones.append("grado = :grado")
        valores["grado"] = grado
    if texto:
        condiciones.append(
            "(documento_identidad LIKE :texto_cedula OR (nombres || ' ' || apellidos) ILIKE :texto_nombre)"
        )
        busqueda = texto.strip()
        valores["texto_cedula"] = CARACTERES_A_QUITAR_DE_CEDULA.sub("", busqueda) + "%"
        valores["texto_nombre"] = "%" + busqueda.replace("%", r"\%").replace("_", r"\_") + "%"
    clausula = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    return clausula, valores


async def listar_habilitacion(
    sesion: AsyncSession,
    *,
    estado: str | None,
    unidad_id: int | None,
    grado: str | None,
    texto: str | None,
    pagina: int,
    tamano_pagina: int,
):
    """Listado paginado con el estado de cada militar. Devuelve (filas, total, parametros)."""
    parametros = await cargar_parametros(sesion)
    clausula, valores = _condiciones_listado(estado, unidad_id, grado, texto)
    valores.update(_parametros_sql(parametros))
    # El SQL se arma solo con constantes (CONDICIONES_FILTRO_ESTADO y condiciones fijas); los
    # valores del usuario van siempre como parámetros enlazados.
    consulta_total = CONSULTA_ESTADO + "SELECT count(*) FROM estado" + clausula  # noqa: S608
    total = await sesion.scalar(text(consulta_total), valores)
    filas = (
        await sesion.execute(
            text(
                CONSULTA_ESTADO  # noqa: S608
                + "SELECT * FROM estado"
                + clausula
                + " ORDER BY apellidos, nombres, id LIMIT :limite OFFSET :desplazamiento"
            ),
            {**valores, "limite": tamano_pagina, "desplazamiento": (pagina - 1) * tamano_pagina},
        )
    ).all()
    return filas, total or 0, parametros


async def resultados_por_militar(sesion: AsyncSession, parametros: ParametrosHabilitacion) -> dict[int, str]:
    """
    APTO / NO_APTO de cada militar con los parámetros dados (los vigentes o unos propuestos).
    Lo usa la simulación del panel de Parámetros para contar quién cambiaría de resultado.
    """
    filas = await sesion.execute(
        text(CONSULTA_ESTADO + " SELECT id, resultado FROM estado"),  # noqa: S608
        _parametros_sql(parametros),
    )
    return {fila.id: fila.resultado for fila in filas}


async def resumir_habilitacion(
    sesion: AsyncSession, parametros: ParametrosHabilitacion | None = None
) -> dict:
    """Indicadores del panel de Personal militar (con los parámetros vigentes, o los indicados)."""
    parametros = parametros or await cargar_parametros(sesion)
    fila = (
        await sesion.execute(
            text(
                CONSULTA_ESTADO  # noqa: S608
                + """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE resultado = 'APTO') AS aptos,
                       count(*) FILTER (WHERE resultado = 'NO_APTO') AS no_aptos,
                       count(*) FILTER (WHERE reentrenamiento_por_vencer) AS por_vencer,
                       count(*) FILTER (WHERE activo) AS activos,
                       count(DISTINCT unidad_actual_id) AS unidades
                FROM estado
                """
            ),
            _parametros_sql(parametros),
        )
    ).one()
    return {
        "total": fila.total,
        "aptos": fila.aptos,
        "no_aptos": fila.no_aptos,
        "reentrenamiento_por_vencer": fila.por_vencer,
        "activos": fila.activos,
        "unidades": fila.unidades,
        "dias_alerta_vencimiento": parametros.dias_alerta_vencimiento,
    }


def total_paginas(total: int, tamano_pagina: int) -> int:
    return max(1, math.ceil(total / tamano_pagina))
