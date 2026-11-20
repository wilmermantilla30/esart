"""Limitador TOTP: ventana fija robusta ante retrocesos del reloj y cabecera Retry-After."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios import totp

AHORA = datetime(2026, 11, 19, 1, 7, 39, tzinfo=UTC)


def servicio_con(fila, monkeypatch, ahora=AHORA):
    """`fila` es el contador por IP; el contador por usuario queda libre."""
    libre = SimpleNamespace(inicio=ahora, intentos=0)
    sesion = SimpleNamespace(
        execute=AsyncMock(), scalar=AsyncMock(side_effect=[fila, libre]), add=MagicMock(), commit=AsyncMock()
    )
    servicio = totp.TotpService(sesion)
    monkeypatch.setattr(servicio, "preparar", AsyncMock())
    monkeypatch.setattr(servicio, "auditar", AsyncMock())
    monkeypatch.setattr(totp, "reloj_servidor", AsyncMock(return_value=ahora))
    monkeypatch.setattr(totp, "seudonimo", lambda dominio, valor: dominio)
    return servicio, sesion


@pytest.mark.anyio
async def test_bloqueo_devuelve_retry_after_con_tiempo_restante(monkeypatch):
    fila = SimpleNamespace(inicio=AHORA - timedelta(minutes=4), intentos=10)
    servicio, sesion = servicio_con(fila, monkeypatch)
    with pytest.raises(ErrorAplicacion) as error:
        await servicio.limitar("127.0.0.1", 7)
    assert error.value.estado_http == 429
    assert error.value.cabeceras == {"Retry-After": "360"}
    assert fila.intentos == 10
    sesion.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_ventana_en_el_futuro_se_ancla_al_reloj_actual_sin_borrar_intentos(monkeypatch):
    # El reloj iba ~2 h adelantado cuando se abrió la ventana y luego NTP lo corrigió.
    fila = SimpleNamespace(inicio=AHORA + timedelta(hours=2, minutes=18), intentos=10)
    servicio, _ = servicio_con(fila, monkeypatch)
    with pytest.raises(ErrorAplicacion) as error:
        await servicio.limitar("127.0.0.1", 7)
    assert fila.inicio == AHORA
    assert fila.intentos == 10
    assert error.value.cabeceras == {"Retry-After": "600"}


@pytest.mark.anyio
async def test_ventana_vencida_se_reinicia_y_cuenta_la_solicitud(monkeypatch):
    fila = SimpleNamespace(inicio=AHORA - timedelta(minutes=10), intentos=10)
    servicio, _ = servicio_con(fila, monkeypatch)
    await servicio.limitar("127.0.0.1", 7)
    assert fila.inicio == AHORA
    assert fila.intentos == 1


@pytest.mark.anyio
async def test_dentro_del_limite_incrementa_sin_bloquear(monkeypatch):
    inicio = AHORA - timedelta(minutes=3)
    fila = SimpleNamespace(inicio=inicio, intentos=9)
    servicio, sesion = servicio_con(fila, monkeypatch)
    await servicio.limitar("127.0.0.1", 7)
    assert fila.inicio == inicio
    assert fila.intentos == 10
    sesion.commit.assert_not_awaited()
