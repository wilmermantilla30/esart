"""Reglas, API y persistencia real opcional con rollback exterior."""

import io
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook
from sqlalchemy import select, text

from aplicacion.modelos import PersonalMilitar, UnidadMilitar
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.rutas.importaciones import autorizar_importacion
from aplicacion.servicios.importacion_personal import (
    DatosCurso,
    clave_unidad,
    guardar_personal,
    indice_unidades,
    leer_excel,
    validar_filas,
)
from pruebas.test_importacion_personal_aislada import CURSO_PRUEBA, laboratorio  # noqa: F401

pytestmark = pytest.mark.anyio
CABECERA = ["Documento", "Nombres", "Apellidos", "Grado", "Género", "Categoría", "Unidad"]
UNIDADES = [
    {"id": 712, "codigo": "ESART", "nombre": "Escuela de Artillería"},
    {"id": 913, "codigo": "BAART1", "nombre": "Batallón de Artillería"},
    {"id": 914, "codigo": "BAART2", "nombre": "Batallón de Artillería"},
]
CURSO = DatosCurso(3, "  Curso  básico ", 8, date(2026, 2, 1), date(2026, 3, 1), "EN_CURSO", "  ")
FORMULARIO_CURSO = {
    "tipo_curso_id": "3",
    "nombre_curso": "Curso básico",
    "comandante_id": "8",
    "fecha_inicio": "2026-02-01",
    "fecha_fin": "2026-03-01",
    "estado_curso": "EN_CURSO",
}


class SesionFalsa:
    """Responde según la sentencia; registra lo escrito sin una base real."""

    def __init__(self, existentes=(), cruces=(), permitido=True, fallo_insercion=None):
        self.existentes = list(existentes)
        self.cruces = list(cruces)
        self.permitido = permitido
        self.fallo_insercion = fallo_insercion
        self.escrituras = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def scalar(self, sentencia, parametros=None):
        sql = str(sentencia)
        if "has_column_privilege" in sql:
            return self.permitido
        if sql.startswith("INSERT INTO esart.cursos"):
            self.escrituras.append(("cursos", sentencia.compile().params))
            return 77
        if "COALESCE(MAX" in sql:
            return 5
        return 1  # tipo de curso y comandante activos

    async def scalars(self, sentencia, parametros=None):
        return SimpleNamespace(all=lambda: self.cruces)

    async def execute(self, sentencia, parametros=None):
        sql = str(sentencia)
        tabla = lambda filas: SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: filas))  # noqa: E731
        if sql.startswith("INSERT INTO esart.personal_militar"):
            if self.fallo_insercion:
                raise self.fallo_insercion
            self.escrituras.append(("personal", parametros))
            return SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(id=100 + i, documento_identidad=r["documento_identidad"])
                    for i, r in enumerate(parametros)
                ]
            )
        if sql.startswith("UPDATE esart.personal_militar"):
            self.escrituras.append(("grado", parametros))
        elif sql.startswith("INSERT INTO esart.hoja_vida_artillero"):
            self.escrituras.append(("historial", parametros))
        elif "unidades_militares" in sql:
            return tabla(UNIDADES)
        elif "FROM esart.personal_militar" in sql:
            return tabla(self.existentes)
        return SimpleNamespace()

    def escrito(self, destino):
        return [p for d, p in self.escrituras if d == destino]


def filas(genero="FEMENINO", unidad="esart", documento="00001"):
    return [
        (1, CABECERA.copy(), [False] * 7),
        (2, [documento, "Ana", "Pérez", "SL", genero, "OFICIAL", unidad], [False] * 7),
    ]


@pytest.mark.parametrize("genero,codigo", [("MASCULINO", "M"), (" femenino ", "F"), ("m", "M"), ("F", "F")])
async def test_normaliza_antes_de_validar_longitud(genero, codigo):
    registros, errores = validar_filas("PERSONAL", filas(genero), UNIDADES)
    assert not errores
    assert registros[0]["genero"] == codigo


@pytest.mark.parametrize("unidad", ["ESART", " esart ", " escuela   de ARTILLERÍA "])
async def test_resuelve_unidad_real_por_nombre_o_codigo(unidad):
    registros, errores = validar_filas("PERSONAL", filas(unidad=unidad), UNIDADES)
    assert not errores
    assert registros[0]["unidad_actual_id"] == 712


@pytest.mark.parametrize(
    "unidad,motivo",
    [
        ("No existe", "Unidad no encontrada en el catálogo institucional"),
        ("Batallón de Artillería", "sigla oficial única"),
    ],
)
async def test_no_asigna_unidad_inexistente_o_ambigua(unidad, motivo):
    registros, errores = validar_filas("PERSONAL", filas(unidad=unidad), UNIDADES)
    assert motivo in errores[0]["motivo"]
    assert registros[0]["unidad_actual_id"] is None
    registros, errores = validar_filas("PERSONAL", filas(unidad="BAART2"), UNIDADES)
    assert not errores
    assert registros[0]["unidad_actual_id"] == 914


async def test_revalida_ids_internos_recibidos_del_cliente():
    datos = filas(unidad="999999")
    datos[0][1][-1] = "unidad_actual_id"
    _, errores = validar_filas("PERSONAL", datos, UNIDADES)
    assert "Unidad no encontrada" in errores[0]["motivo"]
    datos[1][1][-1] = "712"
    registros, errores = validar_filas("PERSONAL", datos, UNIDADES)
    assert not errores
    assert registros[0]["unidad_actual_id"] == 712


async def test_lee_archivo_real_y_rechaza_otras_hojas_o_formulas():
    libro = Workbook()
    libro.active.append(CABECERA)
    libro.active.append(["00001", "Ana", "Pérez", "SL", "FEMENINO", "OFICIAL", "ESART"])
    salida = io.BytesIO()
    libro.save(salida)
    nombre, datos = leer_excel(salida.getvalue())
    assert not validar_filas(nombre, datos, UNIDADES)[1]
    libro.active["B2"] = '=CONCAT("Ana")'
    salida = io.BytesIO()
    libro.save(salida)
    nombre, datos = leer_excel(salida.getvalue())
    assert any("fórmulas" in e["motivo"] for e in validar_filas(nombre, datos, UNIDADES)[1])
    libro.create_sheet("OTRA")
    salida = io.BytesIO()
    libro.save(salida)
    with pytest.raises(ErrorAplicacion, match="Seleccione"):
        leer_excel(salida.getvalue())
    with pytest.raises(ErrorAplicacion):
        leer_excel(b"Documento,Nombres\n123,Ana")


async def test_endpoint_exige_csrf_y_sesion(cliente_api):
    ruta = "/api/importaciones/excel"
    respuesta = await cliente_api.post(ruta, files={"archivo": ("datos.xlsx", b"excel")})
    assert respuesta.status_code == 403
    cliente_api.cookies.set("esart_csrf", "csrf-de-prueba")
    respuesta = await cliente_api.post(
        ruta, headers={"X-CSRF-Token": "csrf-de-prueba"}, files={"archivo": ("datos.xlsx", b"excel")}
    )
    assert respuesta.status_code == 401


async def test_endpoint_procesa_multipart_y_envia_id_correcto_a_persistencia(cliente_api, monkeypatch):
    from aplicacion.base_datos.sesion import obtener_sesion_base_datos
    from aplicacion.configuracion import obtener_configuracion
    from aplicacion.principal import aplicacion
    from aplicacion.rutas.importaciones import puede_importar
    from aplicacion.seguridad.sesion_http import obtener_usuario_actual
    from aplicacion.servicios import importacion_personal

    sesion = SesionFalsa()
    actor = SimpleNamespace(id=1, nombre_usuario="prueba")
    aplicacion.dependency_overrides[puede_importar] = lambda: 1
    aplicacion.dependency_overrides[obtener_usuario_actual] = lambda: actor
    aplicacion.dependency_overrides[obtener_sesion_base_datos] = lambda: sesion
    monkeypatch.setattr(importacion_personal.auditoria, "registrar_evento", AsyncMock())
    # Esta prueba cubre la importación con una sesión falsa, sin la confirmación TOTP
    # (que tiene sus propias pruebas): se apaga aunque el entorno de integración la active.
    monkeypatch.setattr(obtener_configuracion(), "totp_habilitado", False)
    libro = Workbook()
    libro.active.append(CABECERA)
    libro.active.append(["00001", "Ana", "Pérez", "SL", "FEMENINO", "OFICIAL", "  esart  "])
    salida = io.BytesIO()
    libro.save(salida)
    cliente_api.cookies.set("esart_csrf", "csrf-de-prueba")
    respuesta = await cliente_api.post(
        "/api/importaciones/excel",
        headers={"X-CSRF-Token": "csrf-de-prueba"},
        files={"archivo": ("personal.xlsx", salida.getvalue())},
        data={"hoja": "Sheet", **FORMULARIO_CURSO},
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["filas_validas"] == 1
    assert respuesta.json()["curso_codigo"] == "5"
    registro = sesion.escrito("personal")[0][0]
    assert registro["unidad_actual_id"] == 712
    assert registro["genero"] == "F"
    sesion.commit.assert_awaited_once()


async def test_endpoint_exige_datos_del_curso(cliente_api):
    from aplicacion.principal import aplicacion
    from aplicacion.rutas.importaciones import puede_importar
    from aplicacion.seguridad.sesion_http import obtener_usuario_actual

    aplicacion.dependency_overrides[puede_importar] = lambda: 1
    aplicacion.dependency_overrides[obtener_usuario_actual] = lambda: SimpleNamespace(id=1)
    cliente_api.cookies.set("esart_csrf", "csrf-de-prueba")
    incompleto = {k: v for k, v in FORMULARIO_CURSO.items() if k != "comandante_id"}
    respuesta = await cliente_api.post(
        "/api/importaciones/excel",
        headers={"X-CSRF-Token": "csrf-de-prueba"},
        files={"archivo": ("personal.xlsx", b"PK")},
        data={"hoja": "Sheet", **incompleto, "estado_curso": "INVENTADO"},
    )
    assert respuesta.status_code == 422


async def test_no_guarda_si_falta_autorizacion_totp(monkeypatch):
    from aplicacion.rutas import importaciones

    monkeypatch.setattr(importaciones, "obtener_configuracion", lambda: SimpleNamespace(totp_habilitado=True))
    politica = AsyncMock(return_value=SimpleNamespace(permiso_requerido=None))
    monkeypatch.setattr(importaciones.TotpService, "politica", politica)
    sesion = AsyncMock()
    with pytest.raises(ErrorAplicacion) as fallo:
        await autorizar_importacion(sesion, SimpleNamespace(id=1), "", None)
    assert fallo.value.codigo == "TOTP_REQUERIDO"
    sesion.commit.assert_not_awaited()
    politica.assert_awaited_once_with("PERSONAL_CARGUE_EXCEL")


async def test_crea_curso_inserta_nuevos_e_historial_en_la_misma_transaccion(monkeypatch):
    from aplicacion.servicios import importacion_personal

    sesion = SesionFalsa()
    auditar = AsyncMock()
    autorizar = AsyncMock()
    monkeypatch.setattr(importacion_personal.auditoria, "registrar_evento", auditar)
    actor = SimpleNamespace(id=1, nombre_usuario="prueba")
    resultado = await guardar_personal(sesion, "PERSONAL", filas(), actor, CURSO, autorizar=autorizar)
    curso = sesion.escrito("cursos")[0]
    assert curso["codigo"] == "5" and curso["nombre"] == "Curso básico"
    assert curso["observaciones"] is None and curso["creado_por_id"] == 1
    assert sesion.escrito("personal")[0][0]["genero"] == "F"
    assert sesion.escrito("historial")[0] == [
        {"artillero_id": 100, "grado": "SL", "curso_id": 77, "unidad_id": 712}
    ]
    assert not sesion.escrito("grado")
    assert resultado["registros_nuevos"] == 1 and resultado["curso_id"] == 77
    autorizar.assert_awaited_once()
    assert auditar.await_args.kwargs["confirmar"] is False
    sesion.commit.assert_awaited_once()


async def test_cedula_repetida_con_otro_grado_actualiza_grado_e_historial(monkeypatch):
    from aplicacion.servicios import importacion_personal

    sesion = SesionFalsa(existentes=[{"id": 40, "documento_identidad": "00001", "grado": "ST"}])
    monkeypatch.setattr(importacion_personal.auditoria, "registrar_evento", AsyncMock())
    resultado = await guardar_personal(
        sesion, "PERSONAL", filas(), SimpleNamespace(id=1, nombre_usuario="prueba"), CURSO
    )
    assert not sesion.escrito("personal")
    assert sesion.escrito("grado")[0] == [{"b_id": 40, "b_grado": "SL"}]
    assert sesion.escrito("historial")[0][0]["artillero_id"] == 40
    assert resultado["grados_actualizados"] == 1 and resultado["registros_nuevos"] == 0


@pytest.mark.parametrize(
    "existente,cruces,columna,motivo",
    [
        ({"id": 40, "documento_identidad": "00001", "grado": " sl "}, [], "grado", "grado SL"),
        ({"id": 40, "documento_identidad": "00001", "grado": "ST"}, [40], "documento_identidad", "se cruzan"),
    ],
)
async def test_cedula_repetida_mismo_grado_o_curso_cruzado_es_error(existente, cruces, columna, motivo):
    sesion = SesionFalsa(existentes=[existente], cruces=cruces)
    with pytest.raises(ErrorAplicacion) as fallo:
        await guardar_personal(
            sesion, "PERSONAL", filas(), SimpleNamespace(id=1, nombre_usuario="prueba"), CURSO
        )
    incidencia = fallo.value.detalle["errores"][0]
    assert incidencia["fila"] == 2 and incidencia["columna"] == columna and motivo in incidencia["motivo"]
    assert not sesion.escrituras
    sesion.commit.assert_not_awaited()


async def test_sin_migracion_p0011_responde_no_disponible_sin_escribir():
    sesion = SesionFalsa(permitido=False)
    with pytest.raises(ErrorAplicacion) as fallo:
        await guardar_personal(
            sesion, "PERSONAL", filas(), SimpleNamespace(id=1, nombre_usuario="prueba"), CURSO
        )
    assert fallo.value.estado_http == 503 and "p0011" in fallo.value.mensaje
    assert not sesion.escrituras


async def test_fecha_final_anterior_a_inicial_es_error():
    curso = DatosCurso(3, "Curso", 8, date(2026, 3, 1), date(2026, 2, 1), "EN_CURSO")
    with pytest.raises(ErrorAplicacion) as fallo:
        await guardar_personal(SesionFalsa(), "PERSONAL", filas(), SimpleNamespace(id=1), curso)
    assert "fecha final" in fallo.value.mensaje


async def test_conflicto_de_insercion_revierte_todo():
    from sqlalchemy.exc import IntegrityError

    sesion = SesionFalsa(fallo_insercion=IntegrityError("insert", {}, Exception("conflicto")))
    with pytest.raises(ErrorAplicacion) as fallo:
        await guardar_personal(
            sesion, "PERSONAL", filas(), SimpleNamespace(id=1, nombre_usuario="prueba"), CURSO
        )
    assert fallo.value.codigo == "IMPORTACION_RECHAZADA"
    sesion.rollback.assert_awaited_once()
    sesion.commit.assert_not_awaited()


@pytest.fixture
async def sesion_importacion(laboratorio):  # noqa: F811
    """Reutiliza exclusivamente el laboratorio aislado, nunca la conexión operativa."""
    yield laboratorio[0]


async def test_postgresql_catalogo_real_resuelve_sigla_sin_modificar_datos(sesion_importacion):
    unidades = (
        (
            await sesion_importacion.execute(
                select(UnidadMilitar.id, UnidadMilitar.codigo, UnidadMilitar.nombre)
            )
        )
        .mappings()
        .all()
    )
    indice = indice_unidades(unidades)
    unidad = next(u for u in unidades if u["codigo"] and len(indice[clave_unidad(u["codigo"])]) == 1)
    registros, errores = validar_filas(
        "PERSONAL", filas("FEMENINO", "  " + unidad["codigo"].lower() + "  "), unidades
    )
    assert not errores
    assert registros[0]["unidad_actual_id"] == unidad["id"]
    assert registros[0]["genero"] == "F"


async def test_postgresql_guarda_genero_y_fk_correctos_y_rechaza_sin_escrituras(
    sesion_importacion, laboratorio,  # noqa: F811
):
    sesion = sesion_importacion
    permitido = await sesion.scalar(
        text("SELECT has_column_privilege('esart.personal_militar','documento_identidad','INSERT')")
    )
    if not permitido:
        pytest.skip("La cuenta de conexión carece de INSERT en personal_militar; requiere revisión del DBA")
    identificador = uuid.uuid4().hex[:16]
    unidades = (
        (await sesion.execute(select(UnidadMilitar.id, UnidadMilitar.codigo, UnidadMilitar.nombre)))
        .mappings()
        .all()
    )
    indice = indice_unidades(unidades)
    unica = next((u for u in unidades if u["codigo"] and len(indice[clave_unidad(u["codigo"])]) == 1), None)
    assert unica is not None, "Se necesita una unidad con sigla única en el catálogo de pruebas"
    codigo, unidad_id = unica["codigo"], unica["id"]
    actor = laboratorio[1]
    curso = DatosCurso(
        CURSO_PRUEBA["tipo_curso_id"],
        "Curso",
        CURSO_PRUEBA["comandante_id"],
        date(2026, 2, 1),
        date(2026, 3, 1),
        "EN_CURSO",
    )
    documento = "99" + str(int(identificador, 16))[:12]
    resultado = await guardar_personal(
        sesion, "PERSONAL", filas("MASCULINO", codigo.lower(), documento), actor, curso
    )
    assert resultado["estado"] == "APLICADA"
    militar = await sesion.scalar(
        select(PersonalMilitar).where(PersonalMilitar.documento_identidad == documento)
    )
    assert militar.unidad_actual_id == unidad_id
    assert militar.genero == "M"
    # La transacción externa revierte el personal y la auditoría; no altera el catálogo.
    with pytest.raises(ErrorAplicacion):
        await guardar_personal(
            sesion,
            "PERSONAL",
            filas(unidad="NO-EXISTE-" + identificador, documento=documento + "X"),
            actor,
            curso,
        )
    assert (
        await sesion.scalar(
            select(PersonalMilitar.id).where(PersonalMilitar.documento_identidad == documento + "X")
        )
        is None
    )
    with pytest.raises(ErrorAplicacion):
        await guardar_personal(sesion, "PERSONAL", filas("M", codigo, documento), actor, curso)
