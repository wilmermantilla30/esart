"""
Pruebas de las convenciones obligatorias del proyecto.

Fallan si alguien rompe una regla que no se ve hasta que causa un problema
(por ejemplo, una tilde en requirements.txt rompe pip en Windows).
"""

from pathlib import Path

# backend/pruebas/test_convenciones.py -> parents[1]=backend, parents[2]=raíz del repositorio
CARPETA_BACKEND = Path(__file__).resolve().parents[1]
RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]


def test_archivos_de_requisitos_son_ascii_puro():
    for nombre_archivo in ("requirements.txt", "requirements-desarrollo.txt"):
        contenido = (CARPETA_BACKEND / nombre_archivo).read_bytes()
        # decode lanza error si hay un carácter fuera de ASCII.
        contenido.decode("ascii")


def test_passlib_no_se_usa():
    # passlib es incompatible con bcrypt 5.x: se usa bcrypt directo.
    lineas = (CARPETA_BACKEND / "requirements.txt").read_text(encoding="ascii").lower().splitlines()
    # Solo se revisan las líneas de dependencias; los comentarios pueden mencionar passlib.
    dependencias = [linea for linea in lineas if linea.strip() and not linea.lstrip().startswith("#")]
    assert not any(linea.startswith("passlib") for linea in dependencias)


def test_env_esta_excluido_de_git():
    reglas_gitignore = (RAIZ_REPOSITORIO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in reglas_gitignore


def test_configuracion_lee_el_env_de_la_raiz_del_repositorio():
    from aplicacion.configuracion import RUTA_ARCHIVO_ENV

    assert RUTA_ARCHIVO_ENV == RAIZ_REPOSITORIO / ".env"
