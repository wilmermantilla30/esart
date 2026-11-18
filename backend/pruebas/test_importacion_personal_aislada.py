"""Pruebas HTTP y PostgreSQL; solo aceptan una base efímera marcada por el lanzador."""

import io
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook
from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aplicacion.base_datos.base import BaseModelo
from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.modelos import (
    AuditoriaEvento,
    Componente,
    Cursos,
    HojaVidaArtillero,
    Instructores,
    PersonalMilitar,
    Rol,
    RolPermiso,
    SemestresAcademicos,
    TipoCurso,
    TipoUnidad,
    UnidadMilitar,
    Usuario,
    UsuarioPermiso,
    UsuarioRoles,
)
from aplicacion.principal import aplicacion
from aplicacion.seguridad.sesion_http import obtener_usuario_actual
from aplicacion.servicios.importacion_personal import leer_excel

pytestmark = pytest.mark.anyio
CABECERA = ["Documento", "Nombres", "Apellidos", "Grado", "Género", "Categoría", "Unidad", "Activo"]
# Ids del tipo de curso y del instructor creados por el laboratorio.
CURSO_PRUEBA = {}


def excel_personal(cantidad=1, *, unidad="SIM-ESART", duplicado=False, grado="SL"):
    """Genera un libro ficticio con otra hoja que nunca debe importarse."""
    libro = Workbook()
    libro.active.title = "OTRA_HOJA"
    libro.active.append(["No importar"])
    libro.active.append(["No es personal"])
    hoja = libro.create_sheet("CARGUE_PERSONAL")
    hoja.append(CABECERA)
    for indice in range(cantidad):
        documento = str(9900000000 + (0 if duplicado else indice))
        hoja.append(
            [
                documento,
                "Persona  ficticia",
                "Prueba",
                grado,
                "FEMENINO" if indice % 2 else "MASCULINO",
                "OFICIAL",
                unidad,
                "Sí",
            ]
        )
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


@pytest.fixture
async def laboratorio():
    """Crea solo tablas de modelos existentes en un clúster aislado verificado.

    Cada prueba usa savepoints dentro de una transacción exterior revertida.
    Nunca utiliza URL_BASE_DATOS ni ESART_URL_BD_INTEGRACION.
    """
    valor = os.environ.get("ESART_IMPORTACION_TEST_URL")
    if not valor:
        pytest.skip("Ejecute herramientas/probar_importacion_aislada.py")
    url = make_url(valor)
    if (
        url.host not in ("127.0.0.1", "localhost")
        or url.database != "esart_importacion_pruebas"
        or url.port in (None, 5432, 5433)
    ):
        pytest.fail("La prueba requiere una base local efímera con nombre y puerto exclusivos")
    motor = create_async_engine(url, hide_parameters=True, connect_args={"ssl": False})
    async with motor.begin() as conexion:
        marca = await conexion.scalar(
            text(
                "SELECT shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=current_database()"
            )
        )
        if marca != "ESART_SOLO_PRUEBAS_IMPORTACION":
            pytest.fail("La base no tiene la marca explícita del laboratorio de importación")
        await conexion.execute(text("CREATE SCHEMA IF NOT EXISTS esart"))
        await conexion.execute(text("CREATE SCHEMA IF NOT EXISTS esart_ref"))
        tablas = [
            TipoUnidad,
            UnidadMilitar,
            Usuario,
            PersonalMilitar,
            AuditoriaEvento,
            Rol,
            Componente,
            UsuarioRoles,
            RolPermiso,
            UsuarioPermiso,
            SemestresAcademicos,
            TipoCurso,
            Instructores,
            Cursos,
            HojaVidaArtillero,
        ]
        await conexion.run_sync(
            lambda c: BaseModelo.metadata.create_all(c, tables=[t.__table__ for t in tablas])
        )
    async with motor.connect() as conexion:
        exterior = await conexion.begin()
        async with AsyncSession(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as sesion:
            unidad_id = await sesion.scalar(
                insert(UnidadMilitar.__table__)
                .values(codigo="SIM-ESART", nombre="Unidad ficticia de pruebas")
                .returning(UnidadMilitar.id)
            )
            usuario_id = await sesion.scalar(
                insert(Usuario.__table__).values(usuario="prueba_importacion").returning(Usuario.id)
            )
            componente_id = await sesion.scalar(
                insert(Componente.__table__)
                .values(codigo="PERSONAL_CARGUE_EXCEL", nombre="Importar", activo=True)
                .returning(Componente.id)
            )
            sesion.add(
                UsuarioPermiso(
                    usuario_id=usuario_id, componente_id=componente_id, puede_acceder=True, puede_crear=True
                )
            )
            CURSO_PRUEBA["tipo_curso_id"] = await sesion.scalar(
                insert(TipoCurso.__table__)
                .values(codigo="SIM-CUR", nombre="Curso ficticio", modalidad="PRESENCIAL", duracion_semanas=4)
                .returning(TipoCurso.id)
            )
            CURSO_PRUEBA["comandante_id"] = await sesion.scalar(
                insert(Instructores.__table__)
                .values(usuario_id=usuario_id, fecha_ingreso_escuela=date(2026, 1, 1))
                .returning(Instructores.id)
            )
            await sesion.commit()
            actor = SimpleNamespace(id=usuario_id, nombre_usuario="prueba_importacion")
            aplicacion.dependency_overrides[obtener_sesion_base_datos] = lambda: sesion
            aplicacion.dependency_overrides[obtener_usuario_actual] = lambda: actor
            try:
                yield sesion, actor, unidad_id
            finally:
                aplicacion.dependency_overrides.pop(obtener_sesion_base_datos, None)
                aplicacion.dependency_overrides.pop(obtener_usuario_actual, None)
        await exterior.rollback()
    await motor.dispose()


def datos_curso(fecha_inicio="2026-02-01", fecha_fin="2026-03-01"):
    """Campos del curso que el formulario envía junto al archivo."""
    return {
        "tipo_curso_id": str(CURSO_PRUEBA["tipo_curso_id"]),
        "nombre_curso": "  Curso   ficticio ",
        "comandante_id": str(CURSO_PRUEBA["comandante_id"]),
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "estado_curso": "EN_CURSO",
        "observacion_curso": "Cohorte de prueba",
    }


async def enviar(
    cliente, contenido, hoja="CARGUE_PERSONAL", nombre="original.xlsx", codigo_totp="", curso=None
):
    """Usa el contrato multipart original y las protecciones CSRF reales."""
    cliente.cookies.set("esart_csrf", "csrf-de-prueba")
    return await cliente.post(
        "/api/importaciones/excel",
        headers={"X-CSRF-Token": "csrf-de-prueba"},
        data={
            "hoja": hoja,
            **(curso or datos_curso()),
            **({"codigo_totp": codigo_totp} if codigo_totp else {}),
        },
        files={"archivo": (nombre, contenido)},
    )


async def test_importa_200_original_hoja_elegida_sin_encabezado(cliente_api, laboratorio):
    sesion, _, unidad_id = laboratorio
    respuesta = await enviar(cliente_api, excel_personal(200))
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["filas_validas"] == 200
    assert respuesta.json()["filas_rechazadas"] == 0
    filas = (await sesion.scalars(select(PersonalMilitar))).all()
    assert len(filas) == 200
    assert {f.unidad_actual_id for f in filas} == {unidad_id}
    assert {f.genero for f in filas} == {"M", "F"}
    assert all(f.documento_identidad != "Documento" for f in filas)
    assert all(f.nombres == "Persona ficticia" and f.activo for f in filas)
    curso = await sesion.scalar(select(Cursos))
    assert curso.codigo == "1" and curso.nombre == "Curso ficticio" and curso.estado == "EN_CURSO"
    assert respuesta.json()["curso_codigo"] == "1"
    assert respuesta.json()["registros_nuevos"] == 200
    historial = (await sesion.scalars(select(HojaVidaArtillero))).all()
    assert len(historial) == 200
    assert {(h.curso_id, h.grado, h.unidad_id) for h in historial} == {(curso.id, "SL", unidad_id)}
    assert (
        await sesion.scalar(
            select(func.count())
            .select_from(AuditoriaEvento)
            .where(AuditoriaEvento.accion == "IMPORTACION_EXCEL")
        )
        == 1
    )


async def test_lee_xls_original_con_varias_hojas(cliente_api, laboratorio):
    sesion, _, unidad_id = laboratorio
    contenido = (Path(__file__).parent / "fixtures" / "personal_importacion.xls").read_bytes()
    respuesta = await enviar(cliente_api, contenido, nombre="original.xls")
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["filas_validas"] == 1
    militar = await sesion.scalar(select(PersonalMilitar))
    assert militar.unidad_actual_id == unidad_id and militar.genero == "F"


@pytest.mark.parametrize(
    "contenido,hoja,nombre,motivo",
    [
        (excel_personal(2, duplicado=True), "CARGUE_PERSONAL", "original.xlsx", "duplicado"),
        (
            excel_personal(unidad="UNIDAD-INEXISTENTE"),
            "CARGUE_PERSONAL",
            "original.xlsx",
            "Unidad no encontrada",
        ),
        (excel_personal(), "NO_EXISTE", "original.xlsx", "no existe"),
        (excel_personal(), "OTRA_HOJA", "original.xlsx", "columna obligatoria"),
        (b"", "CARGUE_PERSONAL", "original.xlsx", "Excel válido"),
        (b"no es Excel", "CARGUE_PERSONAL", "original.xlsx", "leer el Excel"),
        (b"texto", "CARGUE_PERSONAL", "original.csv", "Solo se permiten"),
    ],
)
async def test_rechaza_libros_invalidos_sin_insertar(
    cliente_api, laboratorio, contenido, hoja, nombre, motivo
):
    sesion, _, _ = laboratorio
    respuesta = await enviar(cliente_api, contenido, hoja, nombre)
    assert respuesta.status_code == 422, respuesta.text
    assert motivo in respuesta.text
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0


async def test_documento_existente_con_mismo_grado_es_error(cliente_api, laboratorio):
    sesion, _, _ = laboratorio
    assert (await enviar(cliente_api, excel_personal())).status_code == 201
    otro_periodo = datos_curso("2026-06-01", "2026-07-01")
    respuesta = await enviar(cliente_api, excel_personal(), curso=otro_periodo)
    assert respuesta.status_code == 422
    incidencia = respuesta.json()["error"]["detalle"]["errores"][0]
    assert incidencia["fila"] == 2 and incidencia["columna"] == "grado" and incidencia["valor"] == "SL"
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 1
    assert await sesion.scalar(select(func.count()).select_from(Cursos)) == 1


async def test_documento_existente_con_otro_grado_actualiza_y_guarda_historial(cliente_api, laboratorio):
    sesion, _, _ = laboratorio
    assert (await enviar(cliente_api, excel_personal())).status_code == 201
    otro_periodo = datos_curso("2026-06-01", "2026-07-01")
    respuesta = await enviar(cliente_api, excel_personal(grado="CS"), curso=otro_periodo)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["grados_actualizados"] == 1
    assert respuesta.json()["registros_nuevos"] == 0
    assert respuesta.json()["curso_codigo"] == "2"
    militar = await sesion.scalar(select(PersonalMilitar))
    await sesion.refresh(militar)
    assert militar.grado == "CS"
    grados = (await sesion.scalars(select(HojaVidaArtillero.grado).order_by(HojaVidaArtillero.id))).all()
    assert grados == ["SL", "CS"]


async def test_otro_grado_en_curso_del_mismo_tipo_con_fechas_cruzadas_es_error(cliente_api, laboratorio):
    sesion, _, _ = laboratorio
    assert (await enviar(cliente_api, excel_personal())).status_code == 201
    cruzado = datos_curso("2026-02-15", "2026-04-01")
    respuesta = await enviar(cliente_api, excel_personal(grado="CS"), curso=cruzado)
    assert respuesta.status_code == 422
    assert "fechas que se cruzan" in respuesta.text
    militar = await sesion.scalar(select(PersonalMilitar))
    await sesion.refresh(militar)
    assert militar.grado == "SL"


async def test_datos_curso_entrega_catalogos_y_siguiente_numero(cliente_api, laboratorio):
    assert (await enviar(cliente_api, excel_personal())).status_code == 201
    respuesta = await cliente_api.get("/api/importaciones/datos-curso")
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["siguiente_codigo"] == "2"
    assert datos["tipos_curso"] == [
        {"id": CURSO_PRUEBA["tipo_curso_id"], "codigo": "SIM-CUR", "nombre": "Curso ficticio"}
    ]
    assert datos["instructores"][0]["id"] == CURSO_PRUEBA["comandante_id"]


async def test_fecha_final_anterior_rechazada_sin_insertar(cliente_api, laboratorio):
    sesion, _, _ = laboratorio
    respuesta = await enviar(cliente_api, excel_personal(), curso=datos_curso("2026-03-01", "2026-02-01"))
    assert respuesta.status_code == 422
    assert "fecha final" in respuesta.text
    assert await sesion.scalar(select(func.count()).select_from(Cursos)) == 0


async def test_filas_vacias_no_renumeran_error(cliente_api, laboratorio):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "CARGUE_PERSONAL"
    hoja.append(CABECERA)
    hoja.append([])
    hoja.append(["9900000001", "Ana", "Prueba", "SL", "FEMENINO", "OFICIAL", "NO-EXISTE", True])
    salida = io.BytesIO()
    libro.save(salida)
    respuesta = await enviar(cliente_api, salida.getvalue())
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["detalle"]["errores"][0]["fila"] == 3


async def test_fallo_segundo_lote_hace_rollback_de_500_filas(cliente_api, laboratorio, monkeypatch):
    sesion, actor, _ = laboratorio
    ejecutar = sesion.execute
    lotes = 0

    async def fallar_segundo(consulta, *args, **kwargs):
        nonlocal lotes
        if getattr(consulta, "is_insert", False) and consulta.table.name == "personal_militar":
            lotes += 1
            if lotes == 2:
                raise OperationalError("insert", {}, RuntimeError("fallo de prueba"))
        return await ejecutar(consulta, *args, **kwargs)

    monkeypatch.setattr(sesion, "execute", fallar_segundo)
    respuesta = await enviar(cliente_api, excel_personal(501))
    assert respuesta.status_code == 503
    assert lotes == 2
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0
    assert await sesion.scalar(select(func.count()).select_from(Cursos)) == 0
    assert await sesion.scalar(select(func.count()).select_from(AuditoriaEvento)) == 0


async def test_usuario_sin_permiso_denegado_y_auditado(cliente_api, laboratorio):
    sesion, actor, _ = laboratorio
    permiso = await sesion.scalar(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == actor.id))
    permiso.puede_crear = False
    await sesion.commit()
    respuesta = await enviar(cliente_api, excel_personal())
    assert respuesta.status_code == 403
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0
    assert await sesion.scalar(select(AuditoriaEvento.accion)) == "ACCESO_DENEGADO"


async def test_restriccion_unique_real_en_segundo_lote_revierte_todo(cliente_api, laboratorio, monkeypatch):
    """Fuerza una colisión concurrente real, después de que ya se escribió un lote."""
    sesion, _, _ = laboratorio
    ejecutar = sesion.execute
    lotes = 0

    async def insertar_duplicado(consulta, *args, **kwargs):
        nonlocal lotes
        if getattr(consulta, "is_insert", False) and consulta.table.name == "personal_militar":
            lotes += 1
            if lotes == 2:
                args[0][0]["documento_identidad"] = "9900000000"
        return await ejecutar(consulta, *args, **kwargs)

    monkeypatch.setattr(sesion, "execute", insertar_duplicado)
    respuesta = await enviar(cliente_api, excel_personal(501))
    assert respuesta.status_code == 422
    assert lotes == 2
    assert await sesion.scalar(select(func.count()).select_from(PersonalMilitar)) == 0


async def test_no_desplaza_encabezado_a_fila_2(cliente_api, laboratorio):
    """Una fila 1 vacía no convierte silenciosamente los encabezados en datos."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "CARGUE_PERSONAL"
    hoja.append([])
    hoja.append(CABECERA)
    hoja.append(["9900000001", "Ana", "Prueba", "SL", "F", "OFICIAL", "SIM-ESART", True])
    salida = io.BytesIO()
    libro.save(salida)
    respuesta = await enviar(cliente_api, salida.getvalue())
    assert respuesta.status_code == 422
    assert any(e["fila"] == 1 for e in respuesta.json()["error"]["detalle"]["errores"])


async def test_limite_de_20_mb_y_firma_correspondiente(laboratorio):
    """El formato real debe concordar con la extensión, también en envíos directos."""
    from aplicacion.nucleo.errores import ErrorAplicacion

    with pytest.raises(ErrorAplicacion):
        leer_excel(b"x" * (20 * 1024 * 1024 + 1), "CARGUE_PERSONAL")
    with pytest.raises(ErrorAplicacion):
        leer_excel(excel_personal(), "CARGUE_PERSONAL", "renombrado.xls")
