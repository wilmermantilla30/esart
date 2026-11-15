"""Seed — Catalogo de tipos de cargo para artilleros.

Carga los 5 cargos oficiales iniciales del modulo ESART.
Los cargos marcados con cuenta_para_coofu=True acreditan experiencia
de mando en la evaluacion de idoneidad COOFU.

Uso:
    docker exec vulcano_backend python seeds/tipos_cargo_artillero.py
"""

import asyncio
import os
import sys

# Permite importar modulos del proyecto desde la raiz del contenedor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models.esart import TipoCargo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Conexion directa usando la variable de entorno del contenedor
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://vulcano_usr:vulcano_pass@vulcano_postgres:5432/vulcano_db",
)

# Cargos iniciales del catalogo artillero
CARGOS_INICIALES = [
    {
        "nombre": "Comandante de pieza",
        "descripcion": (
            "Oficial o suboficial responsable de la operacion y empleo tactico" " de una pieza de artilleria."
        ),
        "cuenta_para_coofu": True,
    },
    {
        "nombre": "Comandante de Bateria",
        "descripcion": (
            "Oficial responsable del mando, control y empleo operacional de un" "a bateria de artilleria."
        ),
        "cuenta_para_coofu": True,
    },
    {
        "nombre": "Armamento Mayor",
        "descripcion": (
            "Suboficial tecnico responsable del mantenimiento y control del ar" "mamento de la unidad."
        ),
        "cuenta_para_coofu": False,
    },
    {
        "nombre": "Tecnico Mantenimiento",
        "descripcion": "Especialista tecnico en mantenimiento de sistemas y equipos de artilleria.",
        "cuenta_para_coofu": False,
    },
    {
        "nombre": "Coordinador de Fuegos",
        "descripcion": (
            "Oficial responsable de planear, coordinar y controlar el empleo d"
            "el fuego de artilleria en apoyo de la maniobra."
        ),
        "cuenta_para_coofu": True,
    },
]


async def cargar_tipos_cargo():
    motor = create_async_engine(DATABASE_URL, echo=False)
    FabricaSesion = sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)

    async with FabricaSesion() as sesion:
        async with sesion.begin():
            insertados = 0
            omitidos = 0

            for datos in CARGOS_INICIALES:
                # Verifica si ya existe para evitar duplicados
                resultado = await sesion.execute(select(TipoCargo).where(TipoCargo.nombre == datos["nombre"]))
                existente = resultado.scalar_one_or_none()

                if existente is not None:
                    print(f"  [omitido] '{datos['nombre']}' ya existe (id={existente.id})")
                    omitidos += 1
                    continue

                cargo = TipoCargo(**datos)
                sesion.add(cargo)
                print(f"  [creado]  '{datos['nombre']}' — coofu={datos['cuenta_para_coofu']}")
                insertados += 1

    print(f"\nSeed completado: {insertados} creados, {omitidos} omitidos.")
    await motor.dispose()


if __name__ == "__main__":
    asyncio.run(cargar_tipos_cargo())
