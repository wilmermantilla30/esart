"""Validaciones del comando de alta: ninguna conexión ni inserción real."""

import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from herramientas import crear_administrador_inicial as comando


@pytest.mark.parametrize(
    "cambio",
    [
        {"usuario_existe": True},
        {"rol_activo": False},
        {"administradores_asignados": 1},
    ],
)
def test_no_modificar_cuentas_ni_crear_roles(cambio):
    plan = {"usuario_existe": False, "rol_activo": True, "administradores_asignados": 0, **cambio}
    with pytest.raises(comando.AltaRechazada):
        comando.exigir_alta_posible(plan)


@pytest.mark.parametrize("nombre", ["ab", "x" * 81, "admin\nesart"])
def test_nombre_invalido(nombre):
    with pytest.raises(comando.AltaRechazada):
        comando.validar_nombre(nombre)


def test_entrada_oculta_sin_recurrir_a_eco(monkeypatch):
    def entrada_visible(_):
        warnings.warn("sin terminal", comando.getpass.GetPassWarning, stacklevel=1)

    monkeypatch.setattr(comando.getpass, "getpass", entrada_visible)
    with pytest.raises(comando.AltaRechazada, match="terminal"):
        comando.leer_contrasena(confirmar=True)


@pytest.mark.parametrize("valores", [[""], ["á" * 37], ["clave-local", "diferente"]])
def test_no_aceptar_clave_vacia_larga_o_confirmacion_distinta(monkeypatch, valores):
    respuestas = iter(valores)
    monkeypatch.setattr(comando.getpass, "getpass", lambda _: next(respuestas))
    with pytest.raises(comando.AltaRechazada):
        comando.leer_contrasena(confirmar=True)


@pytest.mark.anyio
async def test_revalidar_antes_de_insertar_y_no_modificar_si_ya_existe(monkeypatch):
    sesion = MagicMock()
    sesion.execute = AsyncMock()
    inspeccion = AsyncMock(
        return_value={"usuario_existe": True, "rol_activo": True, "administradores_asignados": 1}
    )
    monkeypatch.setattr(comando, "inspeccionar", inspeccion)
    with pytest.raises(comando.AltaRechazada):
        await comando.insertar(sesion, "cuenta.local", "hash-no-utilizado")
    sesion.add.assert_not_called()
    assert "pg_advisory_xact_lock" in str(sesion.execute.call_args.args[0])


@pytest.mark.anyio
async def test_alta_solo_agrega_usuario_y_vinculo_sin_commit_interno(monkeypatch):
    sesion = MagicMock()
    sesion.execute = AsyncMock()
    sesion.flush = AsyncMock()
    sesion.add.side_effect = lambda obj: setattr(obj, "id", 99) if isinstance(obj, comando.Usuario) else None
    monkeypatch.setattr(
        comando,
        "inspeccionar",
        AsyncMock(
            return_value={
                "usuario_existe": False,
                "rol_activo": True,
                "administradores_asignados": 0,
                "rol_id": 1,
            }
        ),
    )
    from aplicacion.servicios import autenticacion

    monkeypatch.setattr(autenticacion, "obtener_codigo_rol", AsyncMock(return_value="ADMINISTRADOR"))
    assert await comando.insertar(sesion, "cuenta.local", "hash-no-real") == 99
    creados = [args.args[0] for args in sesion.add.call_args_list]
    assert [type(obj) for obj in creados] == [comando.Usuario, comando.UsuarioRoles]
    assert creados[0].activo is True and creados[0].documento_identidad is None
    assert creados[1].usuario_id == 99 and creados[1].rol_id == 1
    sesion.commit.assert_not_called()


@pytest.mark.anyio
async def test_arranque_no_realiza_altas_automaticas(monkeypatch):
    from aplicacion import principal
    from aplicacion.base_datos import sesion as modulo_sesion
    from aplicacion.servicios import autenticacion

    bootstrap = AsyncMock()
    fabrica = MagicMock()
    monkeypatch.setattr(autenticacion, "asegurar_administrador_inicial", bootstrap)
    monkeypatch.setattr(modulo_sesion, "obtener_fabrica_sesiones", fabrica)
    monkeypatch.setattr(principal, "cerrar_motor_base_datos", AsyncMock())
    async with principal.ciclo_de_vida(None):
        pass
    bootstrap.assert_not_awaited()
    fabrica.assert_not_called()
