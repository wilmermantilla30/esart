"""Integración optativa y aditiva; jamás borra datos ni crea esquemas.

ESART_SEEDS_INTEGRACION=1 .venv/Scripts/python -m unittest seeds.test_integracion -v
"""

import asyncio
import json
import os
import unittest
from types import SimpleNamespace

from seeds.ejecutar import RAIZ, ejecutar


@unittest.skipUnless(os.environ.get("ESART_SEEDS_INTEGRACION") == "1", "Integracion optativa")
class IntegracionSeeds(unittest.TestCase):
    def test_carga_repetida_registros_jerarquia_y_preservacion(self):
        async def comprobar():
            args = SimpleNamespace(
                archivo_env=RAIZ.parent / ".env",
                aplicar=True,
                catalogo=["roles", "permisos", "unidades_militares"],
            )
            for numero in (1, 2):
                informe = {"destino": "esart_hu03_pruebas", "errores": []}
                await ejecutar(args, informe)
                (RAIZ / f"carga_{numero}.json").write_text(
                    json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                self.assertEqual(informe["estado"], "validado")
                self.assertTrue(informe["tablas_ajenas_sin_cambios"])
                self.assertFalse(any(informe["integridad"].values()))
                self.assertEqual(len(informe["resultados"]), 3)
                for resultado in informe["resultados"]:
                    self.assertTrue(resultado["confirmado"])
                    validacion = informe["validacion"][resultado["tabla"]]
                    self.assertEqual(validacion["faltantes"], [])
                    self.assertEqual(validacion["diferencias_conservadas"], [])
                    self.assertEqual(resultado["insertados"] + resultado["omitidos"], validacion["esperados"])
                    if numero == 2:
                        self.assertEqual(resultado["insertados"], 0)
                # SQL adicional: duplicados, huérfanos y ciclos.
                # El ejecutor ya comprueba cada padre por código contra el manifiesto.

        asyncio.run(comprobar())
