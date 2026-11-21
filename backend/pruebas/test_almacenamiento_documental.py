import hashlib
import uuid

import pytest

from aplicacion.servicios.almacenamiento_documental import (
    guardar_pdf_temporalmente,
    resolver_archivo_privado,
)


def test_guarda_pdf_fuera_de_rutas_publicas_y_calcula_sha256(tmp_path):
    contenido = b"%PDF-1.7\ncontenido de prueba"
    raiz = tmp_path / "privado"

    relativo, destino, sha = guardar_pdf_temporalmente(raiz, uuid.uuid4(), contenido)

    assert destino.is_relative_to(raiz.resolve())
    assert destino.read_bytes() == contenido
    assert sha == hashlib.sha256(contenido).hexdigest()
    assert resolver_archivo_privado(raiz, relativo) == destino


def test_no_acepta_archivos_que_salen_de_la_raiz_privada(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        resolver_archivo_privado(tmp_path, "../secreto.pdf")


def test_rechaza_entradas_que_no_son_pdf(tmp_path):
    with pytest.raises(ValueError, match="cabecera PDF"):
        guardar_pdf_temporalmente(tmp_path, uuid.uuid4(), b"no es un pdf")
