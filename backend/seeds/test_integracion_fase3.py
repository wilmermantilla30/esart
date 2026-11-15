"""Ciclo estructural optativo. NO ejecutar sin aprobación expresa de 0002.

Requiere ESART_FASE3_DDL_APROBADO=1 y revisión 0001. Todo el ciclo usa una
transacción externa que se revierte; no borra filas preexistentes.
"""

import asyncio
import os
import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from seeds.fase3 import RAIZ, TEMPORAL, motor_pruebas, poblar_tipos_unidad


def migrar(conexion, comando, destino):
    """Alembic comparte la conexión de la transacción externa de la prueba."""
    # Toda reversión y prueba estructural pertenece exclusivamente a la temporal.
    base = conexion.execute(text("SELECT current_database()")).scalar_one()
    if base != TEMPORAL:
        raise RuntimeError("Pruebas estructurales solo en base temporal")
    config = Config(str(RAIZ.parent / "alembic.ini"))
    config.attributes["connection"] = conexion
    # Configuración sintética: env.py la requiere, pero no crea otra conexión.
    from aplicacion.base_datos.configuracion import ConfiguracionConexion

    config.attributes["configuracion_conexion"] = ConfiguracionConexion(
        _env_file=None,
        entorno="pruebas",
        url_base_datos="postgresql+asyncpg://prueba:prueba@localhost/esart_hu03_pruebas",
    )
    getattr(command, comando)(config, destino)


async def huellas(conexion):
    """Compara las filas completas sin escribir ni imprimir su contenido."""
    tablas = (
        (
            await conexion.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            )
        )
        .scalars()
        .all()
    )
    resultado = {}
    for tabla in tablas:
        identificador = '"' + tabla.replace('"', '""') + '"'
        resultado[tabla] = await conexion.scalar(
            text(
                "SELECT md5(coalesce(string_agg(row_to_json(t)::text, '' "  # noqa: S608
                "ORDER BY row_to_json(t)::text), '')) FROM public." + identificador + " t"
            )
        )
    return resultado


@unittest.skipUnless(os.environ.get("ESART_FASE3_DDL_APROBADO") == "1", "0002 pendiente de aprobacion")
class IntegracionFase3(unittest.TestCase):
    def test_upgrade_seed_repeticion_restricciones_y_reversion(self):
        async def ciclo():
            motor = motor_pruebas(RAIZ.parent / ".env", TEMPORAL)
            try:
                async with motor.connect() as conexion:
                    async with conexion.begin():
                        await conexion.execute(text("SET TRANSACTION READ ONLY"))
                        self.assertEqual(await conexion.scalar(text("SELECT current_database()")), TEMPORAL)
                        self.assertEqual(
                            await conexion.scalar(text("SELECT version_num FROM public.alembic_version")),
                            "0001",
                        )
                        antes = await huellas(conexion)
                    transaccion = await conexion.begin()
                    try:
                        await conexion.run_sync(lambda c: migrar(c, "upgrade", "0002"))
                        self.assertEqual(
                            await conexion.scalar(
                                text(
                                    "SELECT count(*) FROM public.unidades_militares "
                                    "WHERE tipo_unidad_id IS NOT NULL"
                                )
                            ),
                            0,
                        )
                        semillas = await conexion.begin_nested()
                        primero = await poblar_tipos_unidad(conexion, TEMPORAL)
                        segundo = await poblar_tipos_unidad(conexion, TEMPORAL)
                        self.assertEqual((primero["insertados"], primero["omitidos"]), (9, 0))
                        self.assertEqual((segundo["insertados"], segundo["omitidos"]), (0, 9))

                        # Las restricciones se prueban sin confirmar ninguna fila adicional.
                        for sentencia, parametros in (
                            ("INSERT INTO public.tipos_unidad(codigo,nombre) VALUES ('DIV','Duplicado')", {}),
                            (
                                "INSERT INTO public.tipos_unidad(codigo,nombre) VALUES ('invalido','Texto')",
                                {},
                            ),
                            ("INSERT INTO public.tipos_unidad(codigo,nombre) VALUES ('PRUEBA','   ')", {}),
                            (
                                "INSERT INTO public.unidades_militares(codigo,nombre,tipo_unidad_id) "
                                "VALUES ('HU04_PRUEBA','Temporal',:id)",
                                {"id": uuid4()},
                            ),
                        ):
                            with self.assertRaises(IntegrityError):
                                async with conexion.begin_nested():
                                    await conexion.execute(text(sentencia), parametros)

                        # RESTRICT protege un tipo realmente referenciado por una unidad temporal.
                        temporal = await conexion.begin_nested()
                        await conexion.execute(
                            text(
                                "INSERT INTO public.unidades_militares(codigo,nombre,tipo_unidad_id) "
                                "SELECT 'HU04_PRUEBA','Temporal',id FROM public.tipos_unidad "
                                "WHERE codigo='DIV'"
                            )
                        )
                        with self.assertRaises(IntegrityError):
                            async with conexion.begin_nested():
                                await conexion.execute(
                                    text("DELETE FROM public.tipos_unidad WHERE codigo='DIV'")
                                )
                        await temporal.rollback()

                        # Downgrade se niega a borrar incluso semillas sin unidades clasificadas.
                        with self.assertRaises(DBAPIError) as rechazo:
                            async with conexion.begin_nested():
                                await conexion.run_sync(lambda c: migrar(c, "downgrade", "0001"))
                        self.assertIn("Reversion rechazada", str(rechazo.exception.orig))
                        self.assertEqual(
                            await conexion.scalar(text("SELECT count(*) FROM public.tipos_unidad")), 9
                        )
                        await semillas.rollback()
                        # Ahora no hay datos nuevos: reversión y segundo upgrade válidos.
                        await conexion.run_sync(lambda c: migrar(c, "downgrade", "0001"))
                        self.assertIsNone(
                            await conexion.scalar(text("SELECT to_regclass('public.tipos_unidad')"))
                        )
                        await conexion.run_sync(lambda c: migrar(c, "upgrade", "0002"))
                    finally:
                        await transaccion.rollback()
                    self.assertEqual(await huellas(conexion), antes)
                    self.assertIsNone(
                        await conexion.scalar(text("SELECT to_regclass('public.tipos_unidad')"))
                    )
            finally:
                await motor.dispose()

        asyncio.run(ciclo())
