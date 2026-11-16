"""
Pruebas de la verificación APTO / NO APTO y de los listados de habilitación.

- Utilidades (cédula, fechas, motivos): sin base de datos.
- Regla, permisos y enmascaramiento: con PostgreSQL (ESART_URL_BD_INTEGRACION) y la malla de
  p0005. Los militares se crean con el mismo código del cargador de datos simulados, con
  cédulas que empiezan por 98 (nunca chocan con las simuladas 99...), y todo se revierte.
"""

from datetime import date

import pytest

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.habilitacion import (
    Criterio,
    describir_antiguedad,
    enmascarar_cedula,
    formatear_fecha,
    motivos_no_apto,
    normalizar_cedula,
)
from herramientas.cargar_datos_simulados import insertar_militar, preparar_contexto
from pruebas.test_login_hu05 import crear_usuario, iniciar_sesion, requiere_postgresql, sesion_bd  # noqa: F401

pytestmark = pytest.mark.anyio


# --- Sin base de datos --------------------------------------------------------------


@pytest.mark.parametrize("entrada", ["1.234.567.890", " 1234567890 ", "1234-567-890"])
def test_normalizar_cedula_quita_puntos_espacios_y_guiones(entrada):
    assert normalizar_cedula(entrada) == "1234567890"


@pytest.mark.parametrize("entrada", ["", "abc123", "1234", "1" * 16, "12345' OR 1=1"])
def test_normalizar_cedula_rechaza_formatos_invalidos(entrada):
    with pytest.raises(ErrorAplicacion) as error:
        normalizar_cedula(entrada)
    assert error.value.estado_http == 422


def test_enmascarar_cedula_deja_solo_los_ultimos_4_digitos():
    assert enmascarar_cedula("1234567890", ver_completa=False) == "******7890"
    assert enmascarar_cedula("1234567890", ver_completa=True) == "1234567890"


def test_describir_antiguedad_y_formatear_fecha():
    assert describir_antiguedad(date(2024, 3, 16), date(2026, 11, 16)) == "hace 2 años y 8 meses"
    assert describir_antiguedad(date(2025, 11, 16), date(2026, 11, 16)) == "hace 1 año"
    assert describir_antiguedad(date(2026, 11, 2), date(2026, 11, 16)) == "este mes"
    assert formatear_fecha(date(2027, 11, 16)) == "16-nov-2027"


def test_motivos_no_apto_basta_un_criterio_alternativo():
    activo = Criterio("Activo", "OBLIGATORIO", True, None, None)
    curso = Criterio("Curso", "ALTERNATIVO", True, "SACLI", None)
    reentrenamiento = Criterio("Reentrenamiento", "ALTERNATIVO", False, None, "Vencido")
    assert motivos_no_apto([activo, curso, reentrenamiento]) == []
    sin_curso = Criterio("Curso", "ALTERNATIVO", False, None, "Sin curso")
    assert motivos_no_apto([activo, sin_curso, reentrenamiento]) == ["Sin curso", "Vencido"]


# --- Con PostgreSQL -------------------------------------------------------------------

# Mismo formato que MILITARES del cargador de datos simulados.
CASOS = {
    "sacli": {"cursos": [("SACLI", -975, True)], "reentrenamiento": None, "activo": True},
    "reentrenamiento_vigente": {"cursos": [], "reentrenamiento": -90, "activo": True},
    "por_vencer": {"cursos": [], "reentrenamiento": -335, "activo": True},
    "vencido": {"cursos": [], "reentrenamiento": -425, "activo": True},
    "en_curso": {"cursos": [("SACLI", 30, False)], "reentrenamiento": None, "activo": True},
    "inactivo": {"cursos": [("SACME", -700, True)], "reentrenamiento": None, "activo": False},
    "curso_no_habilitante": {"cursos": [("OA", -200, True)], "reentrenamiento": None, "activo": True},
}


async def crear_militar(sesion, caso: str, numero: int) -> str:
    cedula = f"98000000{numero:02d}"
    militar = {
        "cedula": cedula,
        "grado": "SV",
        "nombres": f"Prueba {caso}",
        "apellidos": "Integración",
        "genero": "M",
        "categoria": "SUBOFICIAL",
        "unidad": "SIM-BAART3",
        **CASOS[caso],
    }
    await insertar_militar(sesion, await preparar_contexto(sesion), militar)
    return cedula


async def entrar(cliente_api, sesion, rol: str):
    usuario = await crear_usuario(sesion, roles=(rol,))
    await iniciar_sesion(cliente_api, usuario.usuario)


@requiere_postgresql
@pytest.mark.parametrize(
    ("caso", "resultado_esperado", "estado_reentrenamiento"),
    [
        ("sacli", "APTO", None),
        ("reentrenamiento_vigente", "APTO", "VIGENTE"),
        ("por_vencer", "APTO", "POR_VENCER"),
        ("vencido", "NO_APTO", "VENCIDO"),
        ("en_curso", "NO_APTO", None),
        ("inactivo", "NO_APTO", None),
        ("curso_no_habilitante", "NO_APTO", None),
    ],
)
async def test_regla_de_habilitacion(
    cliente_api,
    sesion_bd,  # noqa: F811
    caso,
    resultado_esperado,
    estado_reentrenamiento,
):
    cedula = await crear_militar(sesion_bd, caso, 1)
    await entrar(cliente_api, sesion_bd, "USUARIO")

    respuesta = await cliente_api.get(f"/api/verificar/artillero/{cedula}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["resultado"] == resultado_esperado, caso
    assert (cuerpo["motivos"] == []) == (resultado_esperado == "APTO")
    if estado_reentrenamiento:
        assert cuerpo["reentrenamientos"][0]["estado"] == estado_reentrenamiento
    assert (cuerpo["alerta"] is not None) == (caso == "por_vencer")


@requiere_postgresql
async def test_verificacion_muestra_desde_cuando_tiene_el_curso(cliente_api, sesion_bd):  # noqa: F811
    cedula = await crear_militar(sesion_bd, "sacli", 2)
    await entrar(cliente_api, sesion_bd, "USUARIO")

    cuerpo = (await cliente_api.get(f"/api/verificar/artillero/{cedula}")).json()

    criterio_curso = next(c for c in cuerpo["criterios"] if c["descripcion"].startswith("Curso habilitante"))
    assert criterio_curso["cumple"] is True
    assert (
        "SACLI aprobado el" in criterio_curso["detalle"]
        and "hace 2 años y 8 meses" in criterio_curso["detalle"]
    )
    assert cuerpo["cursos"][0]["estado"] == "APROBADO" and cuerpo["cursos"][0]["habilitante"] is True


@requiere_postgresql
async def test_motivo_de_curso_en_progreso_nombra_el_curso(cliente_api, sesion_bd):  # noqa: F811
    cedula = await crear_militar(sesion_bd, "en_curso", 3)
    await entrar(cliente_api, sesion_bd, "USUARIO")
    cuerpo = (await cliente_api.get(f"/api/verificar/artillero/{cedula}")).json()
    assert "Tiene el curso SACLI en curso, aún no aprobado." in cuerpo["motivos"]


@requiere_postgresql
async def test_cedula_completa_para_usuario_y_enmascarada_sin_el_permiso(cliente_api, sesion_bd):  # noqa: F811
    cedula = await crear_militar(sesion_bd, "sacli", 4)
    await entrar(cliente_api, sesion_bd, "USUARIO")
    assert (await cliente_api.get(f"/api/verificar/artillero/{cedula}")).json()["artillero"][
        "numero_documento"
    ] == cedula

    # Se le quita VER_DOCUMENTO_COMPLETO solo a un usuario nuevo mediante una excepción.
    from sqlalchemy import select

    from aplicacion.modelos import Componente, UsuarioPermiso

    usuario = await crear_usuario(sesion_bd, roles=("USUARIO",))
    componente = await sesion_bd.scalar(
        select(Componente).where(Componente.codigo == "VER_DOCUMENTO_COMPLETO")
    )
    sesion_bd.add(UsuarioPermiso(usuario_id=usuario.id, componente_id=componente.id, puede_acceder=False))
    await sesion_bd.flush()
    cliente_api.cookies.clear()
    await iniciar_sesion(cliente_api, usuario.usuario)

    numero = (await cliente_api.get(f"/api/verificar/artillero/{cedula}")).json()["artillero"][
        "numero_documento"
    ]
    assert numero == "******" + cedula[-4:]


@requiere_postgresql
async def test_errores_de_verificacion(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, "USUARIO")
    no_existe = await cliente_api.get("/api/verificar/artillero/1111111111")
    assert no_existe.status_code == 404
    assert no_existe.json()["error"]["codigo"] == "ARTILLERO_NO_ENCONTRADO"
    invalida = await cliente_api.get("/api/verificar/artillero/abc")
    assert invalida.status_code == 422


@requiere_postgresql
async def test_sin_permiso_de_verificar_responde_403(cliente_api, sesion_bd):  # noqa: F811
    # Un USUARIO con la verificación revocada por excepción.
    from sqlalchemy import select

    from aplicacion.modelos import Componente, UsuarioPermiso

    usuario = await crear_usuario(sesion_bd, roles=("USUARIO",))
    componente = await sesion_bd.scalar(select(Componente).where(Componente.codigo == "PERSONAL_VERIFICAR"))
    sesion_bd.add(UsuarioPermiso(usuario_id=usuario.id, componente_id=componente.id, puede_acceder=False))
    await sesion_bd.flush()
    await iniciar_sesion(cliente_api, usuario.usuario)

    respuesta = await cliente_api.get("/api/verificar/artillero/1234567890")
    assert respuesta.status_code == 403
    assert respuesta.json()["error"]["codigo"] == "SIN_PERMISO"


@requiere_postgresql
async def test_listados_filtran_por_estado_y_texto(cliente_api, sesion_bd):  # noqa: F811
    apto = await crear_militar(sesion_bd, "sacli", 5)
    no_apto = await crear_militar(sesion_bd, "vencido", 6)
    por_vencer = await crear_militar(sesion_bd, "por_vencer", 7)
    await entrar(cliente_api, sesion_bd, "USUARIO")

    def cedulas(respuesta):
        return {e["numero_documento"] for e in respuesta.json()["elementos"]}

    habilitados = await cliente_api.get("/api/verificar/habilitados", params={"texto": "Integración"})
    assert {apto, por_vencer} <= cedulas(habilitados) and no_apto not in cedulas(habilitados)

    no_habilitados = await cliente_api.get("/api/verificar/no-habilitados", params={"texto": "Integración"})
    elemento = next(e for e in no_habilitados.json()["elementos"] if e["numero_documento"] == no_apto)
    assert elemento["resultado"] == "NO_APTO" and elemento["motivos"]

    vencer = await cliente_api.get(
        "/api/verificar/habilitacion", params={"estado": "POR_VENCER", "texto": "98000000"}
    )
    assert cedulas(vencer) == {por_vencer}

    pagina = await cliente_api.get(
        "/api/verificar/habilitacion", params={"tamano_pagina": 1, "texto": "Integración"}
    )
    assert pagina.json()["tamano_pagina"] == 1 and pagina.json()["total_paginas"] >= 3


@requiere_postgresql
async def test_resumen_solo_con_permiso_del_modulo(cliente_api, sesion_bd):  # noqa: F811
    await crear_militar(sesion_bd, "sacli", 8)
    await entrar(cliente_api, sesion_bd, "USUARIO")
    resumen = await cliente_api.get("/api/verificar/resumen")
    assert resumen.status_code == 200
    datos = resumen.json()
    assert datos["total"] >= 1 and datos["aptos"] + datos["no_aptos"] == datos["total"]
    assert datos["dias_alerta_vencimiento"] == 60
