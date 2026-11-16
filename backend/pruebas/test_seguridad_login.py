"""Reglas de umbral y privacidad offline; integración real en test_seguridad_login_pg."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from aplicacion.modelos import IntentoInicioSesion
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.captcha import CaptchaNoDisponible
from aplicacion.servicios import seguridad_login as seguridad


@pytest.mark.parametrize("fallos", range(7))
@pytest.mark.anyio
async def test_fallos_y_transicion_bloqueo(fallos):
    ahora = datetime(2026, 11, 15, tzinfo=UTC)
    estado = SimpleNamespace(intentos_fallidos_consecutivos=fallos, bloqueado_hasta=None)
    contexto = seguridad.ContextoIntento("a" * 64, None, ahora, estado=estado)
    sesion = MagicMock()
    sesion.flush = AsyncMock()
    sesion.commit = AsyncMock()
    sesion.execute = AsyncMock()
    sesion.add.side_effect = (
        lambda obj: setattr(obj, "id", 1) if isinstance(obj, IntentoInicioSesion) else None
    )
    with pytest.raises(ErrorAplicacion) as error:
        await seguridad.rechazar(sesion, contexto, "CREDENCIALES_INVALIDAS")
    assert estado.intentos_fallidos_consecutivos == fallos + 1
    assert error.value.detalle["captcha_requerido"] == (3 <= fallos + 1 < 7)
    assert estado.bloqueado_hasta == (ahora + timedelta(hours=3) if fallos == 6 else None)
    assert error.value.estado_http == (423 if fallos == 6 else 401)
    if fallos == 6:
        assert error.value.codigo == "CUENTA_BLOQUEADA"
        assert error.value.detalle["segundos_restantes"] == 10800
    sesion.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_no_extender_plazo_bloqueado():
    ahora = datetime(2026, 11, 15, tzinfo=UTC)
    fin = ahora + timedelta(hours=1)
    estado = SimpleNamespace(intentos_fallidos_consecutivos=7, bloqueado_hasta=fin)
    contexto = seguridad.ContextoIntento("b" * 64, None, ahora, estado=estado)
    sesion = MagicMock(flush=AsyncMock(), commit=AsyncMock(), execute=AsyncMock())
    sesion.add.side_effect = (
        lambda obj: setattr(obj, "id", 1) if isinstance(obj, IntentoInicioSesion) else None
    )
    with pytest.raises(ErrorAplicacion):
        await seguridad.rechazar(sesion, contexto, "BLOQUEO_VIGENTE", contar=False)
    assert estado.bloqueado_hasta == fin and estado.intentos_fallidos_consecutivos == 7


@pytest.mark.anyio
async def test_captcha_por_defecto_no_autoriza():
    assert not await CaptchaNoDisponible().verificar("cualquier-id", "cualquier-respuesta", "contexto")


def test_seudonimos_separados_e_ip_canonica():
    clave = seguridad.seudonimo("usuario", "dato-privado")
    assert len(clave) == 64 and "dato-privado" not in clave
    assert clave == seguridad.seudonimo("usuario", "dato-privado")
    assert clave != seguridad.seudonimo("ip", "dato-privado")
    assert seguridad.ip_canonica("::ffff:127.0.0.1") == "127.0.0.1"
    assert seguridad.ip_canonica("IP enviada por cliente") is None


@pytest.mark.anyio
async def test_503_por_esquema_ausente_antes_de_escribir_o_verificar_captcha():
    sesion = MagicMock()
    sesion.scalar = AsyncMock(return_value=False)
    proveedor = MagicMock(verificar=AsyncMock())
    with pytest.raises(ErrorAplicacion) as error:
        await seguridad.preparar(sesion, "cuenta.local", None, None, None, proveedor)
    assert error.value.estado_http == 503
    assert error.value.codigo == "SEGURIDAD_NO_DISPONIBLE"
    sesion.add.assert_not_called()
    sesion.execute.assert_not_called()
    sesion.commit.assert_not_called()
    proveedor.verificar.assert_not_awaited()
