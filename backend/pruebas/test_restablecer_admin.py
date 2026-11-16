"""Comando administrativo cerrado: pruebas sin PostgreSQL ni contraseñas reales."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from herramientas import restablecer_admin as comando


@pytest.mark.parametrize(
    "url",
    [
        "",
        "postgresql://operador@localhost/esart_db",
        "postgresql+asyncpg://postgres@localhost/otra_base",
        "postgresql+asyncpg://esart_aplicacion@localhost/esart_db",
    ],
)
def test_rechazar_url_incorrecta_o_cuenta_de_aplicacion(url):
    with pytest.raises(comando.RestablecimientoRechazado):
        comando.validar_url_administrativa(url)


@pytest.mark.parametrize(
    "cambio",
    [
        {"base": "otra_base"},
        {"operador": "esart_aplicacion"},
        {"autenticado": "otra_cuenta"},
        {"superusuario": False, "propietario": "otro_propietario"},
    ],
)
@pytest.mark.anyio
async def test_exigir_operador_directo_autorizado(cambio):
    datos = {
        "base": "esart_db",
        "operador": "postgres",
        "autenticado": "postgres",
        "superusuario": True,
        "propietario": "postgres",
        **cambio,
    }
    sesion = MagicMock()
    resultado = MagicMock()
    resultado.mappings.return_value.one_or_none.return_value = datos
    sesion.execute = AsyncMock(return_value=resultado)
    with pytest.raises(comando.RestablecimientoRechazado):
        await comando.comprobar_operador(sesion)


def test_exigir_confirmacion_exacta(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "si")
    with pytest.raises(comando.RestablecimientoRechazado):
        comando.confirmar_operacion()
    monkeypatch.setattr("builtins.input", lambda _: comando.CONFIRMACION)
    comando.confirmar_operacion()


def fila(**cambios):
    return {
        "id": 1,
        "usuario": "admin.esart",
        "activo": True,
        "contrasena_hash": "hash-anterior",
        "actualizado_en": "fecha-original",
        **cambios,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("cambios", [{"usuario": "otra_cuenta"}, {"activo": False}])
async def test_rechazar_usuario_distinto_o_inactivo(monkeypatch, cambios):
    monkeypatch.setattr(comando, "comprobar_operador", AsyncMock())
    sesion = MagicMock()
    sesion.scalar = AsyncMock(return_value=False)
    resultado = MagicMock()
    resultado.mappings.return_value.one_or_none.return_value = fila(**cambios)
    sesion.execute = AsyncMock(return_value=resultado)
    with pytest.raises(comando.RestablecimientoRechazado):
        await comando.inspeccionar(sesion)


@pytest.mark.anyio
async def test_no_actualizar_si_hay_automatismos(monkeypatch):
    monkeypatch.setattr(comando, "comprobar_operador", AsyncMock())
    sesion = MagicMock()
    sesion.scalar = AsyncMock(return_value=True)
    with pytest.raises(comando.RestablecimientoRechazado):
        await comando.inspeccionar(sesion)
    sesion.execute.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "cambios", [{}, {"actualizado_en": "otra-fecha"}, {"contrasena_hash": "no-coincide"}]
)
async def test_actualizar_solo_hash_y_verificar_relectura(monkeypatch, cambios):
    monkeypatch.setattr(comando, "inspeccionar", AsyncMock(return_value=fila()))
    monkeypatch.setattr(comando, "generar_hash_contrasena", lambda _: "hash-nuevo")
    monkeypatch.setattr(comando, "verificar_contrasena", lambda _, almacenado: almacenado == "hash-nuevo")
    sesion = MagicMock()
    resultado_update = MagicMock(rowcount=1)
    resultado_select = MagicMock()
    resultado_select.mappings.return_value.one.return_value = fila(contrasena_hash="hash-nuevo") | cambios
    sesion.execute = AsyncMock(side_effect=[resultado_update, resultado_select])
    if cambios:
        with pytest.raises(comando.RestablecimientoRechazado):
            await comando.actualizar(sesion, "clave-en-memoria")
    else:
        await comando.actualizar(sesion, "clave-en-memoria")
    consulta = sesion.execute.call_args_list[0].args[0]
    sql = str(consulta.compile(dialect=postgresql.dialect()))
    assert sql.startswith("UPDATE esart_ref.usuarios SET contrasena_hash=")
    assert set(consulta.compile().params) == {"contrasena_hash", "id_1", "usuario_1"}
    assert "clave-en-memoria" not in sql
    sesion.commit.assert_not_called()
    sesion.add.assert_not_called()


@pytest.mark.anyio
async def test_usuario_sin_rol_administrador_se_rechaza(monkeypatch):
    monkeypatch.setattr(comando, "comprobar_operador", AsyncMock())
    sesion = MagicMock()
    sesion.scalar = AsyncMock(return_value=False)
    usuario, roles = MagicMock(), MagicMock()
    usuario.mappings.return_value.one_or_none.return_value = fila()
    roles.mappings.return_value.all.return_value = [{"codigo": "USUARIO", "activo": True}]
    sesion.execute = AsyncMock(side_effect=[usuario, roles])
    with pytest.raises(comando.RestablecimientoRechazado):
        await comando.inspeccionar(sesion)
