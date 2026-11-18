"""Comprobaciones locales sin conexión ni dependencias de producción.

Desde backend: python -m unittest seeds.test_seeds -v
La idempotencia real requiere ejecutar dos veces sobre PostgreSQL.
"""

import ast
import json
import unittest
from copy import deepcopy
from pathlib import Path

from seeds.generar import GUARDIA, catalogos

RAIZ = Path(__file__).resolve().parent


class PruebasSeeds(unittest.TestCase):
    def setUp(self):
        self.datos = json.loads((RAIZ / "catalogos.json").read_text(encoding="utf-8"))

    def test_codigos_unicos_y_longitudes_contractuales(self):
        for tabla, limite, campo, largo in (
            ("roles", 30, "nombre", 100),
            ("permisos", 50, "descripcion", 200),
            ("unidades_militares", 20, "nombre", 200),
        ):
            filas = self.datos[tabla]
            self.assertEqual(len(filas), len({f["codigo"] for f in filas}))
            for fila in filas:
                self.assertTrue(0 < len(fila["codigo"]) <= limite)
                self.assertTrue(0 < len(fila[campo]) <= largo)

    def test_roles_respetan_check_y_fuente_sql(self):
        fuente = (RAIZ.parent / "aplicacion/base_datos/esart_seguridad_roles_permisos.sql").read_text(
            encoding="utf-8"
        )
        self.assertEqual({r["codigo"] for r in self.datos["roles"]}, {"ADMINISTRADOR", "USUARIO"})
        for rol in self.datos["roles"]:
            self.assertIn(f"('{rol['codigo']}','{rol['nombre']}'", fuente)

    def test_jerarquia_completa_ordenada_sin_ciclos(self):
        vistos = set()
        for unidad in self.datos["unidades_militares"]:
            if unidad["padre"] is not None:
                self.assertIn(unidad["padre"], vistos)
            vistos.add(unidad["codigo"])
        self.assertEqual(len(vistos), 40)
        self.assertEqual(self.datos["unidades_militares"][-1]["codigo"], "ESART")

    def test_catalogos_heredados_preservados_sin_importar(self):
        origen = catalogos()
        for clave, valor in self.datos["sin_tabla"].items():
            self.assertEqual(valor, origen[clave])
        self.assertEqual(
            self.datos["permisos"], [{k: p[k] for k in ("codigo", "descripcion")} for p in origen["PERMISOS"]]
        )

    def test_guardias_atomicidad_y_ausencia_de_operaciones_destructivas(self):
        for ruta in sorted(RAIZ.glob("*.sql")):
            sql = ruta.read_text(encoding="utf-8")
            self.assertTrue(sql.startswith(GUARDIA))
            self.assertLess(sql.index("current_database()"), sql.index("INSERT INTO"))
            self.assertIn("ON CONFLICT (codigo) DO NOTHING", sql)
            self.assertTrue(sql.endswith("COMMIT;\n"))
            self.assertNotRegex(sql, r"(?im)^\s*(UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE|GRANT)\b")
            self.assertNotIn("INSERT INTO public.usuarios", sql)
        unidades = (RAIZ / "03_unidades_militares.sql").read_text(encoding="utf-8")
        self.assertIn("IF padre IS NULL THEN RAISE EXCEPTION", unidades)
        self.assertIn("unidad_superior_id IS DISTINCT FROM padre", unidades)

    def test_sintaxis_python_compatible_312(self):
        for ruta in RAIZ.glob("*.py"):
            ast.parse(ruta.read_text(encoding="utf-8"), feature_version=(3, 12))

    def test_validacion_previa_rechaza_codigos_y_jerarquias_invalidas(self):
        from seeds.validar import validar_catalogos

        validar_catalogos(self.datos)
        for cambio in ("duplicado", "longitud", "check", "padre", "ciclo", "formato"):
            datos = deepcopy(self.datos)
            if cambio == "duplicado":
                datos["permisos"].append(datos["permisos"][0].copy())
            elif cambio == "longitud":
                datos["roles"][0]["nombre"] = "a" * 101
            elif cambio == "check":
                datos["roles"][0]["codigo"] = "OTRO"
            elif cambio == "padre":
                datos["unidades_militares"][-1]["padre"] = "AUSENTE"
            elif cambio == "ciclo":
                datos["unidades_militares"][0]["padre"] = "ESART"
            else:
                datos["permisos"][0]["codigo"] = "codigo invalido"
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                validar_catalogos(datos)


if __name__ == "__main__":
    unittest.main()
