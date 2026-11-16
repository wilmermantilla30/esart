"""Valida el manifiesto completo antes de enviar cualquier INSERT."""

import re

from sqlalchemy import String

from aplicacion import modelos  # noqa: F401
from aplicacion.modelos.historico.base import BaseModelo


def validar_catalogos(datos):
    for nombre in ("roles", "permisos", "unidades_militares"):
        tabla = BaseModelo.metadata.tables[nombre]
        vistos = set()
        for fila in datos[nombre]:
            codigo = fila["codigo"]
            patron = r"[a-z][a-z0-9_]*" if nombre == "permisos" else r"[A-Z][A-Z0-9_]*"
            if not isinstance(codigo, str) or not re.fullmatch(patron, codigo) or codigo in vistos:
                raise ValueError("Codigo invalido o duplicado en " + nombre)
            for columna in tabla.c:
                if columna.name in fila and isinstance(columna.type, String):
                    valor = fila[columna.name]
                    if not isinstance(valor, str) or not valor.strip() or len(valor) > columna.type.length:
                        raise ValueError("Longitud o texto invalido en " + nombre)
            campo = "descripcion" if nombre == "permisos" else "nombre"
            if campo not in fila:
                raise ValueError("Campo obligatorio ausente en " + nombre)
            if nombre == "roles" and codigo not in {"ADMINISTRADOR", "USUARIO"}:
                raise ValueError("Rol fuera del CHECK HU-03")
            if nombre == "unidades_militares" and fila["padre"] is not None:
                if fila["padre"] not in vistos:
                    raise ValueError("Padre ausente, ciclo u orden jerarquico invalido")
            vistos.add(codigo)
