"""El diagnóstico no requiere permisos de escritura ni expone contraseñas."""

from pathlib import Path

from sqlalchemy.engine import make_url

from herramientas import diagnosticar_integracion as diagnostico


def test_identificadores_de_catalogo_se_escapan():
    assert diagnostico.completo('esart"extra', 'tabla"uno') == '"esart""extra"."tabla""uno"'


def test_respaldo_fallido_no_se_declara_recuperable(tmp_path, monkeypatch):
    llamadas = []

    def fallar(argumentos, entorno=None):
        llamadas.append((argumentos, entorno))
        raise RuntimeError("Sin permiso de lectura")

    monkeypatch.setattr(diagnostico, "verificar_proceso", fallar)
    url = make_url("postgresql+asyncpg://cuenta:secreto_de_prueba@localhost:5432/esart_db")
    informe = diagnostico.respaldar(url, tmp_path, "snapshot_prueba")
    assert not informe["respaldo_completo_valido"]
    assert not informe["restauracion_real_probada"]
    assert len(llamadas) == 2
    for argumentos, entorno in llamadas:
        assert all("secreto_de_prueba" not in argumento for argumento in argumentos)
        assert entorno["PGDATABASE"] == "esart_db"
        assert entorno["PGOPTIONS"] == "-c default_transaction_read_only=on"


def test_herramienta_no_contiene_ejecucion_de_migraciones():
    fuente = Path(diagnostico.__file__).read_text(encoding="utf-8")
    assert "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY" in fuente
    assert "command.upgrade" not in fuente
    assert "command.stamp" not in fuente
