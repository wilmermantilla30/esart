"""Protecciones del verificador: no inicia procesos con archivos alterados ni destinos existentes."""

import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from herramientas import verificar_respaldo_aislado as verificador


def preparar(tmp_path, monkeypatch, huella):
    archivo = tmp_path / "archivo.backup"
    archivo.write_bytes(b"archivo-sintetico-para-probar-precondiciones")
    (tmp_path / "archivo_verificado.json").write_text(
        json.dumps(
            {
                "archivo": str(archivo),
                "sha256": huella or hashlib.sha256(archivo.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["verificar", "--carpeta", str(tmp_path)])
    ejecutar = Mock()
    monkeypatch.setattr(verificador, "ejecutar", ejecutar)
    return ejecutar


def test_no_inicia_postgres_si_cambio_el_respaldo(tmp_path, monkeypatch):
    ejecutar = preparar(tmp_path, monkeypatch, "huella_distinta")
    with pytest.raises(RuntimeError, match="Cambio el archivo"):
        verificador.main()
    ejecutar.assert_not_called()


def test_no_reutiliza_ni_modifica_un_cluster_existente(tmp_path, monkeypatch):
    ejecutar = preparar(tmp_path, monkeypatch, None)
    cluster = tmp_path / "cluster_aislado"
    cluster.mkdir()
    marcador = cluster / "informacion_existente.txt"
    marcador.write_text("conservar", encoding="utf-8")
    with pytest.raises(RuntimeError, match="No se reutiliza"):
        verificador.main()
    ejecutar.assert_not_called()
    assert marcador.read_text(encoding="utf-8") == "conservar"


def test_lanzador_no_usa_pipes_heredables_ni_clave_en_argumentos(tmp_path, monkeypatch):
    proceso = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(verificador.subprocess, "run", proceso)
    verificador.ejecutar("pg_ctl.exe", ["status"], {"PGPASSWORD": "secreto_sintetico"}, tmp_path)
    argumentos, opciones = proceso.call_args
    assert "secreto_sintetico" not in str(argumentos)
    assert "capture_output" not in opciones
    assert opciones["stdout"] is opciones["stderr"]
