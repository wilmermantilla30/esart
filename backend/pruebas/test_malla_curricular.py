"""
S2-01: malla curricular versionada y escala de notas de 0 a 5.

- Lectura del Excel y reglas de la malla: sin base de datos.
- Versiones, catálogo, trigger del curso y escala: con PostgreSQL (ESART_URL_BD_INTEGRACION);
  todo se revierte al final.
"""

import uuid
from datetime import date

import pytest
from openpyxl import Workbook
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from aplicacion.modelos import AuditoriaEvento, MallaCurricular, TipoCurso, VersionMalla
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import malla_curricular as servicio
from aplicacion.servicios.administracion_usuarios import Actor
from herramientas.cargar_malla_curricular import ArchivoInvalido, leer_libro
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401

pytestmark = pytest.mark.anyio

FilaMalla = servicio.FilaMalla


def libro_malla(ruta, materias, malla, sin_hoja=None):
    """Excel con el formato de docs/backlog_sprint2_esart.xlsx (datos desde la fila 5)."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Materias"
    for numero, (nombre, revision) in enumerate(materias, start=5):
        hoja.cell(row=numero, column=1, value=f"MAT-{numero - 4:03d}")
        hoja.cell(row=numero, column=2, value=nombre)
        hoja.cell(row=numero, column=7, value=revision)
    hoja = libro.create_sheet("Malla por curso")
    for numero, (curso, orden, materia, evaluable) in enumerate(malla, start=5):
        for columna, valor in (
            (1, curso),
            (2, orden),
            (3, "PROFESIONAL GENERAL"),
            (4, "TÁCTICO"),
            (6, materia),
            (8, evaluable),
        ):
            hoja.cell(row=numero, column=columna, value=valor)
    if sin_hoja:
        del libro[sin_hoja]
    libro.save(ruta)
    return ruta


# --- Sin base de datos ------------------------------------------------------------


def test_normaliza_espacios_y_mayusculas():
    assert servicio.normalizar_nombre("  Centro   director de tiro ") == "CENTRO DIRECTOR DE TIRO"


def test_lee_el_excel_y_omite_materias_que_ninguna_malla_usa(tmp_path):
    ruta = libro_malla(
        tmp_path / "malla.xlsx",
        [("LIDERAZGO", "Confirmada"), ("DOCTRINA", "Por confirmar"), ("SIN USO", "Confirmada")],
        [("comando", 1, "Liderazgo", "Sí"), ("COMANDO", 2, "doctrina", "No"), ("TECNICA", None, None, None)],
    )
    contenido = leer_libro(ruta)
    assert contenido.materias == ["LIDERAZGO", "DOCTRINA"]
    assert contenido.pendientes == ["DOCTRINA (Por confirmar)"]
    assert list(contenido.mallas) == ["COMANDO"]  # TECNICA sin materias no se carga
    assert contenido.mallas["COMANDO"] == [
        FilaMalla(1, "LIDERAZGO", True, "PROFESIONAL GENERAL", "TÁCTICO"),
        FilaMalla(2, "DOCTRINA", False, "PROFESIONAL GENERAL", "TÁCTICO"),
    ]


@pytest.mark.parametrize(
    ("materias", "malla", "sin_hoja", "mensaje"),
    [
        ([("A", "Confirmada")], [("ADA", 1, "A", "Sí")], "Materias", "Faltan las hojas"),
        ([("A", "Confirmada"), ("a ", "Confirmada")], [("ADA", 1, "A", "Sí")], None, "repetida"),
        ([("A", "Confirmada")], [("ADA", 1, "B", "Sí")], None, "no está en Materias"),
        ([("A", "Confirmada")], [("ADA", 1, "A", "Tal vez")], None, "Sí o No"),
        ([("A", "Confirmada")], [("ADA", "uno", "A", "Sí")], None, "no es un número"),
        ([("A", "Confirmada")], [], None, "no tiene materias"),
    ],
)
def test_rechaza_excel_con_errores(tmp_path, materias, malla, sin_hoja, mensaje):
    ruta = libro_malla(tmp_path / "malla.xlsx", materias, malla, sin_hoja)
    with pytest.raises(ArchivoInvalido, match=mensaje):
        leer_libro(ruta)


def test_rechaza_un_archivo_que_no_es_excel(tmp_path):
    ruta = tmp_path / "malla.xlsx"
    ruta.write_bytes(b"esto no es un Excel")
    with pytest.raises(ArchivoInvalido, match="No se pudo abrir"):
        leer_libro(ruta)


@pytest.mark.parametrize(
    "filas",
    [
        [],
        [FilaMalla(1, "A", True), FilaMalla(1, "B", True)],  # orden repetido
        [FilaMalla(0, "A", True)],  # orden menor que 1
        [FilaMalla(1, "Liderazgo", True), FilaMalla(2, " LIDERAZGO", True)],  # misma materia
        [FilaMalla(1, "TIEMPO DEL COMANDANTE", False)],  # ninguna con nota
        [FilaMalla(1, "A" * 201, True)],
        [FilaMalla(1, "A", True, area="X" * 101)],
    ],
)
def test_reglas_de_la_malla(filas):
    with pytest.raises(ErrorAplicacion) as error:
        servicio.validar_filas(filas)
    assert error.value.codigo == "MALLA_INVALIDA"


# --- Con PostgreSQL -------------------------------------------------------------------

FILAS_BASE = [
    FilaMalla(1, "MATERIA PRUEBA UNO", True, "PROFESIONAL GENERAL", "TÁCTICO"),
    FilaMalla(2, "MATERIA PRUEBA DOS", True),
    FilaMalla(3, "TIEMPO DEL COMANDANTE", False),
]


async def tipo_curso_nuevo(sesion) -> TipoCurso:
    tipo = TipoCurso(
        codigo=f"T{uuid.uuid4().hex[:8].upper()}",
        nombre="Curso de prueba",
        modalidad="PRESENCIAL",
        duracion_semanas=4,
    )
    sesion.add(tipo)
    await sesion.flush()
    return tipo


@requiere_postgresql
async def test_crea_versiones_y_deja_historica_la_anterior(sesion_bd):  # noqa: F811
    tipo = await tipo_curso_nuevo(sesion_bd)
    actor = Actor.consola("pruebas")
    primera = await servicio.crear_version(sesion_bd, tipo, 2026, FILAS_BASE, actor)
    segunda = await servicio.crear_version(
        sesion_bd, tipo, 2027, FILAS_BASE[:2] + [FilaMalla(3, "Liderazgo", True)], actor
    )
    await sesion_bd.refresh(primera)
    assert (primera.numero, primera.estado) == (1, "HISTORICA")
    assert (segunda.numero, segunda.estado, segunda.anio) == (2, "VIGENTE", 2027)
    assert (await servicio.version_vigente(sesion_bd, tipo.id)).id == segunda.id

    filas = (
        await sesion_bd.scalars(select(MallaCurricular).where(MallaCurricular.version_id == primera.id))
    ).all()
    assert sorted((f.orden, f.evaluable) for f in filas) == [(1, True), (2, True), (3, False)]
    # La versión anterior conserva sus materias y la misma materia se reutiliza en las dos versiones.
    uno = await sesion_bd.scalar(
        select(MallaCurricular.materia_id).where(
            MallaCurricular.version_id == segunda.id, MallaCurricular.orden == 1
        )
    )
    assert uno == next(f.materia_id for f in filas if f.orden == 1)

    evento = await sesion_bd.scalar(
        select(AuditoriaEvento)
        .where(AuditoriaEvento.accion == "MALLA_CURRICULAR_CARGADA")
        .order_by(AuditoriaEvento.id.desc())
    )
    assert evento.detalle["tipo_curso"] == tipo.codigo
    assert (evento.detalle["version"], evento.detalle["version_anterior"]) == (2, 1)
    assert evento.nombre_usuario == "consola"


@requiere_postgresql
async def test_asegurar_materias_no_duplica_el_catalogo(sesion_bd):  # noqa: F811
    nombre = f"MATERIA {uuid.uuid4().hex[:6].upper()}"
    primera = await servicio.asegurar_materias(sesion_bd, [nombre])
    segunda = await servicio.asegurar_materias(sesion_bd, [f"  {nombre.lower()} "])
    assert primera[nombre].id == segunda[nombre].id
    assert primera[nombre].codigo.startswith("MAT-")


@requiere_postgresql
async def test_solo_una_version_vigente_por_tipo_de_curso(sesion_bd):  # noqa: F811
    tipo = await tipo_curso_nuevo(sesion_bd)
    await servicio.crear_version(sesion_bd, tipo, 2026, FILAS_BASE, Actor.consola("pruebas"))
    with pytest.raises(DBAPIError):
        async with sesion_bd.begin_nested():
            sesion_bd.add(VersionMalla(tipo_curso_id=tipo.id, numero=9, anio=2026, estado="VIGENTE"))
            await sesion_bd.flush()


async def insertar_curso(sesion, tipo_id, malla_version_id=None) -> int:
    instructor = await sesion.scalar(text("SELECT id FROM esart.instructores ORDER BY id LIMIT 1"))
    usuario = await sesion.scalar(text("SELECT id FROM esart_ref.usuarios ORDER BY id LIMIT 1"))
    if instructor is None or usuario is None:
        pytest.skip("La base de integración no tiene instructores o usuarios")
    return await sesion.scalar(
        text("""
            INSERT INTO esart.cursos (tipo_curso_id, comandante_id, codigo, nombre, fecha_inicio, fecha_fin,
                                      creado_por_id, malla_version_id)
            VALUES (:tipo, :instructor, :codigo, 'Curso de prueba', :inicio, :fin, :usuario, :malla)
            RETURNING malla_version_id
        """),
        {
            "tipo": tipo_id,
            "instructor": instructor,
            "codigo": f"PRUEBA-{uuid.uuid4().hex[:8]}",
            "inicio": date(2026, 1, 15),
            "fin": date(2026, 3, 15),
            "usuario": usuario,
            "malla": malla_version_id,
        },
    )


@requiere_postgresql
async def test_el_curso_nuevo_toma_la_malla_vigente_de_su_tipo(sesion_bd):  # noqa: F811
    tipo = await tipo_curso_nuevo(sesion_bd)
    assert await insertar_curso(sesion_bd, tipo.id) is None  # sin malla todavía: queda vacío
    version = await servicio.crear_version(sesion_bd, tipo, 2026, FILAS_BASE, Actor.consola("pruebas"))
    assert await insertar_curso(sesion_bd, tipo.id) == version.id


@requiere_postgresql
async def test_el_curso_no_acepta_la_malla_de_otro_tipo(sesion_bd):  # noqa: F811
    tipo, otro = await tipo_curso_nuevo(sesion_bd), await tipo_curso_nuevo(sesion_bd)
    ajena = await servicio.crear_version(sesion_bd, otro, 2026, FILAS_BASE, Actor.consola("pruebas"))
    with pytest.raises(DBAPIError, match="no pertenece al tipo de curso"):
        async with sesion_bd.begin_nested():
            await insertar_curso(sesion_bd, tipo.id, ajena.id)


@requiere_postgresql
@pytest.mark.parametrize(
    ("tabla", "columna"),
    [
        ("notas_materia", "nota"),
        ("habilitaciones", "nota_obtenida"),
        ("notas_finales_egresado", "nota"),
        ("egresados_curso", "nota_final"),
        ("inscripciones_curso", "nota_final"),
    ],
)
async def test_las_notas_van_de_0_a_5(sesion_bd, tabla, columna):  # noqa: F811
    definicion = await sesion_bd.scalar(
        text("""
            SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c
            WHERE c.conrelid = ('esart.' || :tabla)::regclass AND c.contype = 'c'
              AND pg_get_constraintdef(c.oid) LIKE '%' || :columna || ' <=%'
        """),
        {"tabla": tabla, "columna": columna},
    )
    assert definicion is not None and "(5)" in definicion.replace(" ", "").replace("::numeric", "")


@requiere_postgresql
async def test_una_sola_habilitacion_por_materia(sesion_bd):  # noqa: F811
    definicion = await sesion_bd.scalar(
        text("""
            SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conname = 'habilitaciones_numero_habilitacion_check'
        """)
    )
    assert "numero_habilitacion = 1" in definicion
