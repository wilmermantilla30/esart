"""Importación atómica de personal, curso e historial de grados, sin DDL."""

import io
import logging
import re
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date

import xlrd
from openpyxl import load_workbook
from sqlalchemy import bindparam, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from aplicacion.modelos import Cursos, HojaVidaArtillero, PersonalMilitar, UnidadMilitar
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import auditoria
from aplicacion.servicios.habilitacion import normalizar_cedula

MAX_ARCHIVO = 20 * 1024 * 1024
registrador = logging.getLogger(__name__)


def estado_sql_seguro(error):
    """Obtiene solo SQLSTATE; nunca registra sentencia, parámetros, archivo o persona."""
    codigo = getattr(getattr(error, "orig", None), "sqlstate", None)
    if codigo is None:
        codigo = getattr(getattr(error, "orig", None), "pgcode", None)
    return codigo if isinstance(codigo, str) and re.fullmatch(r"[A-Z0-9]{5}", codigo) else "NO_DISPONIBLE"


CAMPOS = {
    "documento_identidad": (50, True, ("documento", "numero_documento", "cedula")),
    "nombres": (150, True, ("nombre",)),
    "apellidos": (150, True, ("apellido",)),
    "grado": (20, True, ()),
    "genero": (1, True, ("sexo",)),
    "categoria": (30, True, ()),
    "unidad_actual_id": (
        None,
        False,
        ("unidad", "unidad_id", "unidad_actual", "nombre_unidad", "sigla_unidad"),
    ),
    "especialidad_actual": (100, False, ("especialidad",)),
    "activo": (None, False, ()),
}


def clave_unidad(valor):
    """Compara nombres y siglas exactos, ignorando caso y espacios repetidos."""
    return " ".join(str(valor or "").split()).lower()


def clave_campo(valor):
    """Convierte encabezados de presentación a los alias institucionales."""
    return "_".join(
        "".join(c for c in unicodedata.normalize("NFD", str(valor or "")) if not unicodedata.combining(c))
        .lower()
        .split()
    )


def indice_unidades(unidades):
    """Conserva todas las coincidencias; nunca elige la primera unidad ambigua."""
    indice = {}
    for unidad in unidades:
        for campo in ("nombre", "codigo"):
            clave = clave_unidad(unidad[campo])
            if clave:
                indice.setdefault(clave, set()).add(int(unidad["id"]))
    return indice


def resolver_unidad(valor, indice, ids, permitir_id=False):
    """Resuelve exclusivamente IDs reales del catálogo; no crea unidades."""
    valor = str(valor).strip()
    if permitir_id and valor.isascii() and valor.isdigit() and int(valor) in ids:
        return int(valor)
    candidatos = indice.get(clave_unidad(valor), set())
    if not candidatos:
        raise ValueError("Unidad no encontrada en el catálogo institucional")
    if len(candidatos) != 1:
        raise ValueError(
            "Varias unidades coinciden con ese nombre. "
            "Indique la sigla oficial única de la unidad en el Excel."
        )
    return next(iter(candidatos))


def normalizar_genero(valor):
    """Normaliza el género antes de aplicar el límite de un carácter del modelo."""
    genero = str(valor).strip().upper()
    if genero in ("M", "MASCULINO"):
        return "M"
    if genero in ("F", "FEMENINO"):
        return "F"
    raise ValueError("Género inválido. Utilice MASCULINO, FEMENINO, M o F.")


def leer_excel(contenido, hoja_seleccionada=None, nombre_archivo="personal.xlsx"):
    """Lee solo la hoja solicitada del original y conserva fila 1 como encabezado.

    Los XLSX se inspeccionan antes de descomprimir. Los XLS se leen con xlrd,
    sin ejecutar macros ni fórmulas. Las filas vacías no se importan ni renumeran.
    """
    if not contenido or len(contenido) > MAX_ARCHIVO:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Se requiere un archivo Excel válido de máximo 20 MB.")
    extension = nombre_archivo.rsplit(".", 1)[-1].lower()
    if extension not in ("xls", "xlsx"):
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Solo se permiten archivos .xlsx y .xls.")

    def elegir(nombres):
        if hoja_seleccionada is None and len(nombres) != 1:
            raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Seleccione una hoja del libro Excel.")
        nombre = hoja_seleccionada if hoja_seleccionada is not None else nombres[0]
        if nombre not in nombres:
            raise ErrorAplicacion(
                422, "HOJA_NO_ENCONTRADA", "La hoja seleccionada no existe en el archivo Excel."
            )
        return nombre

    def como_texto(valor):
        if valor is None:
            return ""
        if isinstance(valor, float) and valor.is_integer():
            return str(int(valor))
        return str(valor).strip()

    try:
        if extension == "xls":
            if not contenido.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
                raise ValueError("Firma XLS inválida")
            libro_xls = xlrd.open_workbook(file_contents=contenido, on_demand=True, formatting_info=True)
            try:
                nombre = elegir(libro_xls.sheet_names())
                hoja_xls = libro_xls.sheet_by_name(nombre)
                if hoja_xls.nrows > 100000 or hoja_xls.ncols > 200:
                    raise ValueError("Rango excesivo")
                filas = []
                for r in range(hoja_xls.nrows):
                    valores, invalidas = [], []
                    for celda in hoja_xls.row(r):
                        valor = como_texto(celda.value)
                        if celda.ctype == xlrd.XL_CELL_BOOLEAN:
                            valor = "true" if celda.value else "false"
                        formato = libro_xls.format_map[
                            libro_xls.xf_list[celda.xf_index].format_key
                        ].format_str
                        if celda.ctype == xlrd.XL_CELL_NUMBER and re.fullmatch(r"0+", formato):
                            valor = valor.zfill(len(formato))
                        valores.append(valor)
                        invalidas.append(celda.ctype == xlrd.XL_CELL_ERROR)
                    if r == 0 or any(valores):
                        filas.append((r + 1, valores, invalidas))
                return nombre, filas
            finally:
                libro_xls.release_resources()
        if not contenido.startswith(b"PK\x03\x04"):
            raise ValueError("Firma XLSX inválida")
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
            if sum(e.file_size for e in archivo.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Libro demasiado grande al descomprimir")
            if "xl/workbook.xml" not in archivo.namelist():
                raise ValueError("No es un libro XLSX")
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=False, keep_links=False)
        try:
            hoja = libro[elegir(libro.sheetnames)]
            if (hoja.max_row or 0) > 100000 or (hoja.max_column or 0) > 200:
                raise ValueError("Rango excesivo")
            filas = []
            for numero, fila in enumerate(hoja.iter_rows(), 1):
                if numero > 100000 or len(fila) > 200:
                    raise ValueError("Rango excesivo")
                valores = [como_texto(c.value) for c in fila]
                for i, celda in enumerate(fila):
                    if (
                        isinstance(celda.value, int)
                        and not isinstance(celda.value, bool)
                        and re.fullmatch(r"0+", celda.number_format or "")
                    ):
                        valores[i] = valores[i].zfill(len(celda.number_format))
                if numero == 1 or any(valores):
                    filas.append((numero, valores, [c.data_type in ("f", "e") for c in fila]))
            return hoja.title, filas
        finally:
            libro.close()
    except ErrorAplicacion:
        raise
    except Exception as error:
        registrador.warning("IMPORTACION_RECHAZADA etapa=lectura tipo=%s", type(error).__name__)
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "No fue posible leer el Excel. Compruebe su formato y sus dimensiones."
        ) from None


def validar_filas(hoja, filas, unidades):
    """Valida el encabezado real y normaliza datos antes de cualquier escritura."""
    errores = []

    def error(fila, columna, motivo, valor=""):
        errores.append({"hoja": hoja, "fila": fila, "columna": columna, "valor": valor, "motivo": motivo})

    if not filas:
        error(1, "Hoja", "La hoja está vacía.")
        return [], errores
    numero_cabecera, cabecera, _ = filas[0]
    if numero_cabecera != 1:
        error(1, "Hoja", "La fila 1 debe contener los encabezados.")
    columnas = {}
    for indice, nombre in enumerate(cabecera):
        campo = next((c for c, (_, _, alias) in CAMPOS.items() if clave_campo(nombre) in (c, *alias)), None)
        if campo:
            if campo in columnas:
                error(numero_cabecera, campo, "Más de una columna corresponde al mismo atributo.")
            columnas[campo] = indice
    for campo, (_, requerido, _) in CAMPOS.items():
        if requerido and campo not in columnas:
            error(numero_cabecera, campo, "Falta una columna obligatoria.")
    if len(filas) == 1:
        error(numero_cabecera, "Hoja", "La hoja no contiene registros.")
    indice_catalogo = indice_unidades(unidades)
    ids = {int(u["id"]) for u in unidades}
    documentos = set()
    registros = []
    for numero, valores, invalidas in filas[1:]:
        registro = {"unidad_actual_id": None, "especialidad_actual": None, "activo": True}
        for campo, posicion in columnas.items():
            valor = valores[posicion] if posicion < len(valores) else ""
            maximo, requerido, _ = CAMPOS[campo]
            if posicion < len(invalidas) and invalidas[posicion]:
                error(numero, campo, "Reemplace fórmulas y errores de Excel por valores válidos.", valor)
            if not valor:
                if requerido:
                    error(numero, campo, "Dato obligatorio sin diligenciar.")
                continue
            try:
                if campo == "documento_identidad":
                    valor = normalizar_cedula(valor)
                if campo in ("nombres", "apellidos", "grado", "categoria", "especialidad_actual"):
                    valor = " ".join(valor.split())
                if campo == "genero":
                    valor = normalizar_genero(valor)
                if maximo and len(valor) > maximo:
                    raise ValueError(f"Máximo {maximo} caracteres.")
                if campo == "unidad_actual_id":
                    valor = resolver_unidad(
                        valor,
                        indice_catalogo,
                        ids,
                        clave_campo(cabecera[posicion]) in ("unidad_actual_id", "unidad_id"),
                    )
                if campo == "activo":
                    booleano = clave_campo(valor)
                    if booleano not in ("true", "false", "1", "0", "si", "no", "verdadero", "falso"):
                        raise ValueError("Utilice sí/no, true/false o 1/0.")
                    valor = booleano in ("true", "1", "si", "verdadero")
                registro[campo] = valor
            except (ValueError, ErrorAplicacion) as fallo:
                error(numero, campo, str(fallo), valor)
        documento = registro.get("documento_identidad")
        if documento in documentos:
            error(numero, "documento_identidad", "Documento duplicado en la hoja.", documento)
        documentos.add(documento)
        registros.append(registro)
    return registros, errores


def rechazar(errores, total):
    """Expone incidencias del contrato sin aplicar ninguna fila del libro."""
    raise ErrorAplicacion(
        422,
        "IMPORTACION_RECHAZADA",
        "El archivo contiene errores. No se guardó ningún registro.",
        {"filas_totales": total, "errores": errores},
    )


ESTADOS_CURSO = ("EN_CURSO", "CULMINADO", "CANCELADO", "APLAZADO")


@dataclass(frozen=True)
class DatosCurso:
    """Curso que se crea con la importación; el código lo asigna el servidor."""

    tipo_curso_id: int
    nombre: str
    comandante_id: int
    fecha_inicio: date
    fecha_fin: date
    estado: str
    observacion: str | None = None


COLUMNAS_INSERT_CURSO = (
    "tipo_curso_id",
    "comandante_id",
    "codigo",
    "nombre",
    "fecha_inicio",
    "fecha_fin",
    "estado",
    "observaciones",
    "creado_por_id",
)
# Privilegios de columna que necesita la transacción completa (migración p0011).
PRIVILEGIOS_IMPORTACION = (
    *(("esart.personal_militar", c, "INSERT") for c in CAMPOS),
    ("esart.personal_militar", "grado", "UPDATE"),
    ("esart.personal_militar", "actualizado_en", "UPDATE"),
    ("esart.tipos_curso", "activo", "SELECT"),
    ("esart.instructores", "activo", "SELECT"),
    ("esart.cursos", "codigo", "SELECT"),
    ("esart.cursos", "tipo_curso_id", "SELECT"),
    *(("esart.cursos", c, "INSERT") for c in COLUMNAS_INSERT_CURSO),
    ("esart.hoja_vida_artillero", "curso_id", "SELECT"),
    *(("esart.hoja_vida_artillero", c, "INSERT") for c in ("artillero_id", "grado", "curso_id", "unidad_id")),
)
MENSAJE_SIN_ESTRUCTURA = (
    "El servicio no tiene habilitado el guardado de cursos y personal "
    "(migración p0011 pendiente o privilegios insuficientes). "
    "Contacte al administrador; no se guardó ningún registro."
)
SQL_SIGUIENTE_CODIGO = text(
    "SELECT COALESCE(MAX(CAST(codigo AS bigint)), 0) + 1 FROM esart.cursos WHERE codigo ~ '^[0-9]{1,18}$'"
)
SQL_CRUCES = text("""
    SELECT DISTINCT hv.artillero_id
    FROM esart.hoja_vida_artillero hv
    JOIN esart.cursos c ON c.id = hv.curso_id
    WHERE hv.artillero_id = ANY(CAST(:ids AS bigint[]))
      AND c.tipo_curso_id = :tipo
      AND c.fecha_inicio <= :fin AND c.fecha_fin >= :inicio
""")
# p0013: el instructor puede ser militar (personal_id o su usuario) o civil (nombres propios),
# y no necesita usuario de ESART; por eso los JOIN son opcionales.
SQL_INSTRUCTORES = text("""
    SELECT i.id,
           COALESCE(NULLIF(TRIM(CONCAT_WS(' ', p.grado, p.nombres, p.apellidos)), ''),
                    NULLIF(TRIM(CONCAT_WS(' ', i.nombres, i.apellidos)), ''),
                    u.usuario, 'Instructor ' || i.id) AS nombre
    FROM esart.instructores i
    LEFT JOIN esart_ref.usuarios u ON u.id = i.usuario_id
    LEFT JOIN esart.personal_militar p
      ON p.id = i.personal_id OR (i.personal_id IS NULL AND p.documento_identidad = u.documento_identidad)
    WHERE i.activo
    ORDER BY nombre
""")


def clave_grado(valor):
    """Compara grados ignorando mayúsculas y espacios repetidos."""
    return " ".join(str(valor or "").split()).upper()


def normalizar_curso(curso):
    """Normaliza los datos del formulario; las fechas y el estado se validan aquí."""
    nombre = " ".join((curso.nombre or "").split())
    if not nombre or len(nombre) > 200:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Indique el nombre del curso (máximo 200 caracteres).")
    if curso.estado not in ESTADOS_CURSO:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "Seleccione un estado válido para el curso.")
    if curso.fecha_fin < curso.fecha_inicio:
        raise ErrorAplicacion(
            422, "DATOS_INVALIDOS", "La fecha final del curso no puede ser anterior a la fecha inicial."
        )
    observacion = (curso.observacion or "").strip() or None
    if observacion and len(observacion) > 2000:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "La observación admite máximo 2000 caracteres.")
    return DatosCurso(
        curso.tipo_curso_id,
        nombre,
        curso.comandante_id,
        curso.fecha_inicio,
        curso.fecha_fin,
        curso.estado,
        observacion,
    )


async def verificar_estructura(sesion, privilegios=PRIVILEGIOS_IMPORTACION):
    """Comprueba tablas y privilegios de columna sin fallar si una tabla aún no existe."""
    permitido = await sesion.scalar(
        text("""
        SELECT bool_and(
          CASE WHEN to_regclass(tabla) IS NULL THEN false
               ELSE has_column_privilege(tabla, columna, privilegio) END)
        FROM unnest(CAST(:tablas AS text[]), CAST(:columnas AS text[]), CAST(:privilegios AS text[]))
          AS p(tabla, columna, privilegio)
    """),
        {
            "tablas": [p[0] for p in privilegios],
            "columnas": [p[1] for p in privilegios],
            "privilegios": [p[2] for p in privilegios],
        },
    )
    if not permitido:
        registrador.error("IMPORTACION_NO_DISPONIBLE etapa=privilegios causa=estructura_o_privilegios")
        raise ErrorAplicacion(503, "IMPORTACION_NO_DISPONIBLE", MENSAJE_SIN_ESTRUCTURA)


async def datos_formulario_curso(sesion):
    """Catálogos del formulario: tipos de curso, instructores activos y siguiente número."""
    await verificar_estructura(
        sesion,
        (
            ("esart.tipos_curso", "nombre", "SELECT"),
            ("esart.instructores", "usuario_id", "SELECT"),
            ("esart_ref.usuarios", "usuario", "SELECT"),
            ("esart.cursos", "codigo", "SELECT"),
        ),
    )
    consulta_tipos = text(
        "SELECT id, codigo, nombre FROM esart.tipos_curso WHERE activo ORDER BY codigo, nombre"
    )
    tipos = (await sesion.execute(consulta_tipos)).mappings().all()
    instructores = (await sesion.execute(SQL_INSTRUCTORES)).mappings().all()
    siguiente = await sesion.scalar(SQL_SIGUIENTE_CODIGO)
    return {
        "tipos_curso": [dict(t) for t in tipos],
        "instructores": [dict(i) for i in instructores],
        "siguiente_codigo": str(siguiente or 1),
    }


async def guardar_personal(sesion, hoja, filas, actor, curso, request=None, autorizar=None):
    """Crea el curso, inserta o actualiza personal y registra el historial en un solo commit."""
    try:
        return await _guardar_personal(sesion, hoja, filas, actor, curso, request, autorizar)
    except IntegrityError as error:
        registrador.warning(
            "IMPORTACION_RECHAZADA etapa=persistencia tipo=integridad sqlstate=%s", estado_sql_seguro(error)
        )
        await sesion.rollback()
        raise ErrorAplicacion(
            422,
            "IMPORTACION_RECHAZADA",
            "La importación entró en conflicto con los datos actuales. "
            "No se guardó ningún registro; vuelva a validar.",
        ) from None
    except SQLAlchemyError as error:
        registrador.error(
            "IMPORTACION_FALLIDA etapa=base_datos tipo=%s sqlstate=%s",
            type(error).__name__,
            estado_sql_seguro(error),
        )
        await sesion.rollback()
        raise ErrorAplicacion(
            503,
            "IMPORTACION_BD_NO_DISPONIBLE",
            "No fue posible confirmar la operación en la base de datos. "
            "Consulte el personal antes de reintentar.",
        ) from None
    except Exception as error:
        registrador.info(
            "IMPORTACION_INTERRUMPIDA tipo=%s codigo=%s",
            type(error).__name__,
            error.codigo if isinstance(error, ErrorAplicacion) else "NO_DISPONIBLE",
        )
        await sesion.rollback()
        raise


async def _validar_referencias_curso(sesion, curso):
    """El tipo de curso y el comandante deben existir y estar activos."""
    tipo = await sesion.scalar(
        text("SELECT id FROM esart.tipos_curso WHERE id = :id AND activo"), {"id": curso.tipo_curso_id}
    )
    if tipo is None:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "El tipo de curso no existe o está inactivo.")
    comandante = await sesion.scalar(
        text("SELECT id FROM esart.instructores WHERE id = :id AND activo"), {"id": curso.comandante_id}
    )
    if comandante is None:
        raise ErrorAplicacion(422, "DATOS_INVALIDOS", "El comandante del curso no es un instructor activo.")


async def _consultar_existentes(sesion, documentos):
    """Personal ya registrado por documento: id y grado actual."""
    existentes = {}
    for inicio in range(0, len(documentos), 1000):
        consulta = select(
            PersonalMilitar.id, PersonalMilitar.documento_identidad, PersonalMilitar.grado
        ).where(PersonalMilitar.documento_identidad.in_(documentos[inicio : inicio + 1000]))
        for fila in (await sesion.execute(consulta)).mappings().all():
            existentes[fila["documento_identidad"]] = fila
    return existentes


def validar_repetidos(hoja, filas, registros, existentes, cruces):
    """Cédula repetida: mismo grado o curso del mismo tipo con fechas cruzadas es error."""
    errores = []
    for (numero, _, _), registro in zip(filas[1:], registros, strict=True):
        previo = existentes.get(registro["documento_identidad"])
        if previo is None:
            continue
        if clave_grado(previo["grado"]) == clave_grado(registro["grado"]):
            errores.append(
                {
                    "hoja": hoja,
                    "fila": numero,
                    "columna": "grado",
                    "valor": registro["grado"],
                    "motivo": (
                        f"El documento ya está registrado con el grado {clave_grado(previo['grado'])}. "
                        "Solo se actualiza si el grado es distinto."
                    ),
                }
            )
        elif int(previo["id"]) in cruces:
            errores.append(
                {
                    "hoja": hoja,
                    "fila": numero,
                    "columna": "documento_identidad",
                    "valor": registro["documento_identidad"],
                    "motivo": "La persona ya está en un curso del mismo tipo con fechas que se cruzan.",
                }
            )
    return errores


async def _guardar_personal(sesion, hoja, filas, actor, curso, request, autorizar):
    """Ejecuta el trabajo de la transacción; guardar_personal centraliza el rollback."""
    curso = normalizar_curso(curso)
    registrador.info("IMPORTACION_ETAPA etapa=consulta_catalogo")
    unidades = (
        (await sesion.execute(select(UnidadMilitar.id, UnidadMilitar.codigo, UnidadMilitar.nombre)))
        .mappings()
        .all()
    )
    registros, errores = validar_filas(hoja, filas, unidades)
    if errores:
        registrador.info("IMPORTACION_RECHAZADA etapa=validacion incidencias=%d", len(errores))
        rechazar(errores, len(registros))
    await verificar_estructura(sesion)
    await _validar_referencias_curso(sesion, curso)

    existentes = await _consultar_existentes(sesion, [r["documento_identidad"] for r in registros])
    cruces = set()
    if existentes:
        parametros = {
            "ids": [int(e["id"]) for e in existentes.values()],
            "tipo": curso.tipo_curso_id,
            "inicio": curso.fecha_inicio,
            "fin": curso.fecha_fin,
        }
        cruces = set((await sesion.scalars(SQL_CRUCES, parametros)).all())
    errores = validar_repetidos(hoja, filas, registros, existentes, cruces)
    if errores:
        registrador.info("IMPORTACION_RECHAZADA etapa=repetidos incidencias=%d", len(errores))
        rechazar(errores, len(registros))
    if autorizar:
        registrador.info("IMPORTACION_ETAPA etapa=autorizacion")
        await autorizar()

    referencia = str(uuid.uuid4())
    # Serializa la numeración de cursos sin privilegios de LOCK TABLE.
    await sesion.execute(text("SELECT pg_advisory_xact_lock(hashtext('esart.cursos.codigo'))"))
    codigo = str(await sesion.scalar(SQL_SIGUIENTE_CODIGO))
    tabla_cursos = Cursos.__table__
    curso_id = await sesion.scalar(
        insert(tabla_cursos)
        .values(
            tipo_curso_id=curso.tipo_curso_id,
            comandante_id=curso.comandante_id,
            codigo=codigo,
            nombre=curso.nombre,
            fecha_inicio=curso.fecha_inicio,
            fecha_fin=curso.fecha_fin,
            estado=curso.estado,
            observaciones=curso.observacion,
            creado_por_id=actor.id,
        )
        .returning(tabla_cursos.c.id)
    )
    nuevos = [r for r in registros if r["documento_identidad"] not in existentes]
    actualizados = [r for r in registros if r["documento_identidad"] in existentes]
    registrador.info(
        "IMPORTACION_ETAPA etapa=insercion nuevos=%d actualizados=%d referencia=%s",
        len(nuevos),
        len(actualizados),
        referencia,
    )
    ids = {d: int(e["id"]) for d, e in existentes.items()}
    tabla_personal = PersonalMilitar.__table__
    for inicio in range(0, len(nuevos), 500):
        resultado = await sesion.execute(
            insert(tabla_personal).returning(tabla_personal.c.id, tabla_personal.c.documento_identidad),
            nuevos[inicio : inicio + 500],
        )
        ids.update({fila.documento_identidad: int(fila.id) for fila in resultado.all()})
    if actualizados:
        await sesion.execute(
            update(tabla_personal)
            .where(tabla_personal.c.id == bindparam("b_id"))
            .values(grado=bindparam("b_grado"), actualizado_en=func.now()),
            [{"b_id": ids[r["documento_identidad"]], "b_grado": r["grado"]} for r in actualizados],
        )
    historial = [
        {
            "artillero_id": ids[r["documento_identidad"]],
            "grado": r["grado"],
            "curso_id": curso_id,
            "unidad_id": r["unidad_actual_id"],
        }
        for r in registros
    ]
    for inicio in range(0, len(historial), 500):
        await sesion.execute(insert(HojaVidaArtillero.__table__), historial[inicio : inicio + 500])
    await auditoria.registrar_evento(
        sesion,
        "IMPORTACION_EXCEL",
        request,
        usuario_id=actor.id,
        nombre_usuario=actor.nombre_usuario,
        resultado="APLICADA",
        detalle={
            "importacion_id": referencia,
            "hoja": hoja,
            "filas_totales": len(registros),
            "curso_id": curso_id,
            "curso_codigo": codigo,
            "registros_nuevos": len(nuevos),
            "grados_actualizados": len(actualizados),
        },
        confirmar=False,
    )
    await sesion.commit()
    registrador.info("IMPORTACION_APLICADA registros=%d referencia=%s", len(registros), referencia)
    return {
        "importacion_id": referencia,
        "estado": "APLICADA",
        "filas_totales": len(registros),
        "filas_validas": len(registros),
        "filas_rechazadas": 0,
        "curso_id": curso_id,
        "curso_codigo": codigo,
        "registros_nuevos": len(nuevos),
        "grados_actualizados": len(actualizados),
    }
