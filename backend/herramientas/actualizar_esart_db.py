"""Aplica la cadena operativa de Alembic a esart_db y verifica el catálogo antes del commit."""

import argparse
import asyncio
from importlib import import_module

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from herramientas.aplicar_p0018_ensayo import configuracion_alembic, url_migradora, verificar_destino

BASE = "esart_db"
OBJETIVO = "p0019_firma_movil"
TRAMO_REVISADO = (
    "p0014_cursos_del_instructor",
    "p0015_registro_manual_personal",
    "p0016_cursos_artilleros",
    "p0017_restablecer_totp_admin",
    "p0018_firma_documental",
    OBJETIVO,
)
REEMPLAZOS_CHECK = {TRAMO_REVISADO[1], TRAMO_REVISADO[3]}
CHECK_AUDITORIA = "esart.auditoria_eventos.ck_auditoria_eventos_ck_auditoria_eventos_accion"


def actualizar(conexion, autorizar_check_auditoria=False):
    verificar_destino(conexion, BASE)
    conexion.execute(text("SET LOCAL lock_timeout TO '5s'"))
    conexion.execute(text("LOCK TABLE esart.alembic_version IN EXCLUSIVE MODE"))
    revisiones = conexion.scalars(text("SELECT version_num FROM esart.alembic_version")).all()
    print(f"Revisión actual en {BASE}: {revisiones!r}", flush=True)
    if len(revisiones) != 1 or revisiones[0] not in TRAMO_REVISADO:
        raise RuntimeError("La revisión activa queda fuera del tramo revisado para esta actualización.")
    config = configuracion_alembic()
    scripts = ScriptDirectory.from_config(config)
    pendientes = tuple(r.revision for r in reversed(list(scripts.iterate_revisions(OBJETIVO, revisiones[0]))))
    print(f"Revisiones pendientes: {', '.join(pendientes) or 'ninguna'}", flush=True)
    if pendientes != TRAMO_REVISADO[TRAMO_REVISADO.index(revisiones[0]) + 1 :]:
        raise RuntimeError("La cadena local difiere del tramo revisado.")
    reemplazar_check = REEMPLAZOS_CHECK.intersection(pendientes)
    if reemplazar_check:
        if not autorizar_check_auditoria:
            raise RuntimeError(
                f"p0015 y p0017 pueden sustituir {CHECK_AUDITORIA}. "
                "Se requiere --autorizar-check-auditoria."
            )
        validar_check_auditoria(conexion)
    if pendientes:
        config.attributes["connection"] = conexion
        command.upgrade(config, OBJETIVO)
    if conexion.scalars(text("SELECT version_num FROM esart.alembic_version")).all() != [OBJETIVO]:
        raise RuntimeError("La revisión final no corresponde a p0019.")
    if reemplazar_check:
        validar_check_auditoria(conexion)
    conexion.execute(text("SET LOCAL search_path TO pg_catalog, pg_temp"))
    firma = import_module("migraciones_principal.versions.p0018_firma_documental")
    firma._validar_estructura_heredada_ampliada(conexion, firma._heredado())
    for tabla, referencia in firma._referencia_documental().items():
        firma._validar_documental(conexion, tabla, referencia)


def validar_check_auditoria(conexion):
    if not conexion.scalar(
        text("""
            SELECT EXISTS (
                SELECT FROM pg_constraint
                WHERE conrelid = to_regclass('esart.auditoria_eventos')
                  AND conname = :nombre AND contype = 'c' AND convalidated AND conenforced
            )
        """),
        {"nombre": CHECK_AUDITORIA.rsplit(".", 1)[1]},
    ):
        raise RuntimeError(f"Falta el CHECK validado y aplicado {CHECK_AUDITORIA}.")


async def principal(autorizar_check_auditoria=False):
    motor = create_async_engine(
        url_migradora(BASE), connect_args={"ssl": False, "timeout": 5}, hide_parameters=True
    )
    try:
        async with motor.begin() as conexion:
            await conexion.run_sync(actualizar, autorizar_check_auditoria)
    finally:
        await motor.dispose()
    print(f"{BASE}: {OBJETIVO} confirmado, con catálogo de firma verificado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--autorizar-check-auditoria",
        action="store_true",
        help=f"Autoriza únicamente que p0015 y p0017 sustituyan {CHECK_AUDITORIA}.",
    )
    asyncio.run(principal(parser.parse_args().autorizar_check_auditoria))
