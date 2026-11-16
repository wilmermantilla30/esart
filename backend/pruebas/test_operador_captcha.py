"""La autorización no permite aplicar p0004 con un respaldo distinto o inválido."""

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from herramientas import aplicar_captcha_local as operador


def test_respaldo_debe_coincidir_con_el_restaurado(tmp_path, monkeypatch):
    respaldo = tmp_path / "respaldo.backup"
    respaldo.write_bytes(b"respaldo diferente")
    monkeypatch.setattr(operador, "RESPALDO", respaldo)
    comando = Mock()
    monkeypatch.setattr(operador.subprocess, "run", comando)
    with pytest.raises(RuntimeError, match="no coincide"):
        operador.comprobar_respaldo()
    comando.assert_not_called()


def test_respaldo_ilegible_por_pg_restore_detiene_el_procedimiento(tmp_path, monkeypatch):
    respaldo = tmp_path / "respaldo.backup"
    respaldo.write_bytes(b"catalogo de prueba")
    monkeypatch.setattr(operador, "RESPALDO", respaldo)
    monkeypatch.setattr(operador, "HUELLA", hashlib.sha256(respaldo.read_bytes()).hexdigest())
    monkeypatch.setattr(operador.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=1)))
    with pytest.raises(RuntimeError, match="no puede leer"):
        operador.comprobar_respaldo()
