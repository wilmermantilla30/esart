"""Seed: tipos de curso ofrecidos por la ESART.

Inserta los 14 tipos de curso oficiales de la Escuela de Artilleria.
Fuente: cursos_esart.xlsx — documento oficial SMCA.

Categorias:
    EDUCACION_SUPERIOR  — Tecnico profesional (convenio universitario)
    EDUCACION_MILITAR   — Cursos militares de formacion y capacitacion
    ESPECIALIZACION     — Fases de especializacion del arma por jerarquia

Nota: El comite movil (reentrenamiento) NO va aqui — pertenece a la tabla
reentrenamientos y se gestiona por el modulo de reentrenamiento.

Uso:
    docker exec vulcano_backend python seeds/tipos_curso_esart.py
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Carga la configuracion del proyecto para obtener DATABASE_URL
sys.path.insert(0, "/app")
from app.configuracion import configuracion
from app.db.models.academia import TipoCurso

# -----------------------------------------------------------------------------
# Catalogo oficial de tipos de curso ESART
# -----------------------------------------------------------------------------
# Cada entrada: (codigo, nombre, tipo, modalidad, duracion_semanas)
TIPOS_CURSO = [
    # ── Educacion superior ────────────────────────────────────────────────────
    (
        "TECNICA",
        "Tecnico profesional en mantenimiento mecanico aplicado a la operacion de armas de artilleria",
        "EDUCACION_SUPERIOR",
        "PRESENCIAL",
        43,
    ),
    # ── Coordinacion de fuegos — fundamental para evaluacion COOFU ───────────
    (
        "COOFU",
        "Coordinador de Fuegos",
        "EDUCACION_MILITAR",
        "VIRTUAL",
        2,
    ),
    # ── Educacion militar — cursos de formacion basica ────────────────────────
    (
        "SACLI",
        "Curso sistemas de artilleria liviana",
        "EDUCACION_MILITAR",
        "PRESENCIAL",
        10,
    ),
    (
        "SACME",
        "Curso sistemas de artilleria mediana",
        "EDUCACION_MILITAR",
        "PRESENCIAL",
        11,
    ),
    (
        "COSET",
        "Curso control y seguimiento al tiro",
        "EDUCACION_MILITAR",
        "PRESENCIAL",
        10,
    ),
    (
        "ADA",
        "Curso de artilleria de defensa aerea",
        "EDUCACION_MILITAR",
        "PRESENCIAL",
        8,
    ),
    (
        "OA",
        "Curso observacion adelantada",
        "EDUCACION_MILITAR",
        "PRESENCIAL",
        5,
    ),
    (
        "CAPINTE",
        "Curso capacitacion intermedia",
        "EDUCACION_MILITAR",
        "PRESENCIAL",
        12,
    ),
    # ── Especializacion del arma — fases por jerarquia ────────────────────────
    (
        "COMANDO",
        "Especializacion del arma — curso Comando",
        "ESPECIALIZACION",
        "PRESENCIAL",
        4,
    ),
    (
        "INTERMEDIO",
        "Especializacion del arma — curso Intermedio",
        "ESPECIALIZACION",
        "PRESENCIAL",
        5,
    ),
    (
        "COTAC",
        "Especializacion del arma — curso COTAC",
        "ESPECIALIZACION",
        "PRESENCIAL",
        2,
    ),
    (
        "CAPAVAN",
        "Especializacion del arma — curso CAPAVAN",
        "ESPECIALIZACION",
        "PRESENCIAL",
        2,
    ),
    (
        "ALFEREZ",
        "Especializacion del arma — curso Alfereces",
        "ESPECIALIZACION",
        "PRESENCIAL",
        5,
    ),
    (
        "DRAGONEANTES",
        "Especializacion del arma — curso Dragoneantes",
        "ESPECIALIZACION",
        "PRESENCIAL",
        8,
    ),
]


async def insertar_tipos_curso() -> None:
    """Inserta los tipos de curso en la BD usando upsert logico (skip si ya existe)."""
    motor = create_async_engine(configuracion.DATABASE_URL, echo=False)
    SesionAsync = sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)

    async with SesionAsync() as sesion:
        async with sesion.begin():
            insertados = 0
            omitidos = 0

            for codigo, nombre, tipo, modalidad, duracion_semanas in TIPOS_CURSO:
                # Verifica si el tipo ya existe para evitar duplicados
                existente = await sesion.execute(select(TipoCurso).where(TipoCurso.codigo == codigo))
                if existente.scalar_one_or_none():
                    print(f"  [OMITIDO]  {codigo} — ya existe en BD")
                    omitidos += 1
                    continue

                # Inserta el tipo de curso nuevo
                tipo_curso = TipoCurso(
                    codigo=codigo,
                    nombre=nombre,
                    tipo=tipo,
                    modalidad=modalidad,
                    duracion_semanas=duracion_semanas,
                    activo=True,
                )
                sesion.add(tipo_curso)
                print(f"  [INSERTADO] {codigo} — {nombre[:60]}...")
                insertados += 1

    print(f"\nResumen: {insertados} insertados, {omitidos} omitidos.")
    await motor.dispose()


if __name__ == "__main__":
    print("=== Seed: Tipos de Curso ESART ===\n")
    asyncio.run(insertar_tipos_curso())
    print("\nDone.")
