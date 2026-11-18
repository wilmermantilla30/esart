"""Genera SQL de revisión 0002; --aplicar solo después de aprobación del usuario."""

import argparse
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from aplicacion.base_datos.configuracion import ConfiguracionConexion
from seeds.ejecutar import DESTINO

RAIZ = Path(__file__).resolve().parents[1]


def configurar(archivo_env):
    """No confiar en el nombre de base del .env ni modificarlo permanentemente."""
    origen = ConfiguracionConexion(_env_file=archivo_env, entorno="pruebas")
    url = make_url(origen.url_base_datos.get_secret_value()).set(database=DESTINO)
    config = Config(str(RAIZ / "alembic.ini"))
    config.attributes["configuracion_conexion"] = ConfiguracionConexion(
        _env_file=None,
        entorno="pruebas",
        nivel_registro="WARNING",
        url_base_datos=url.render_as_string(hide_password=False),
    )
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo-env", default=".env")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--revertir", action="store_true")
    parser.add_argument("--salida", type=Path, default=RAIZ / "seeds/sql/fase3_upgrade_propuesto.sql")
    args = parser.parse_args()
    try:
        config = configurar(args.archivo_env)
        if args.aplicar:
            if args.revertir:
                command.downgrade(config, "0001")
            else:
                command.upgrade(config, "0002")
            print("Operacion confirmada exclusivamente en " + DESTINO)
        else:
            config.output_buffer = StringIO()
            if args.revertir:
                command.downgrade(config, "0002:0001", sql=True)
            else:
                command.upgrade(config, "0001:0002", sql=True)
            args.salida.write_text(config.output_buffer.getvalue(), encoding="utf-8")
            print("SQL propuesto generado sin conexion: " + str(args.salida))
    except Exception as error:
        print("Operacion fallida: " + type(error).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
