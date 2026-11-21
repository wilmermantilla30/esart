"""
Prueba propuestas/p0018_p0019_firma_manual.sql tal como lo ejecutará el operador: con psql, como
superusuario, sobre una copia como esart_db hoy (Alembic en p0016 + esquema heredado esart_firma con
5 roles y 8 permisos). Clúster PostgreSQL efímero; nunca toca esart_db.

Escenarios:
  1. Ejecución normal → 23 tablas, datos heredados intactos, alembic_version sin tocar, componente en
     la malla; después el flujo completo de firma desde el celular (como esart_aplicacion).
  2. Segunda ejecución → aborta ("No se ejecuta dos veces") sin cambiar nada.
  3. Estructura heredada distinta → aborta sin crear nada.
  4. Con propuestas/componente_firma_documentos.sql ejecutado antes → funciona y respeta la malla.

Uso desde backend/:  .venv\\Scripts\\python.exe herramientas\\probar_sql_p0018_p0019_aislada.py
"""

# ruff: noqa: E501

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Importar primero el laboratorio de la firma: configura TOTP y almacén temporales para este proceso.
import herramientas.probar_firma_movil_aislada as laboratorio_firma  # noqa: E402
from herramientas.probar_firma_movil_aislada import CARPETA_DOCUMENTOS, estado_firma, flujo  # noqa: E402
from herramientas.probar_p0018_aislada import (  # noqa: E402
    BASE,
    PG,
    RESULTADOS,
    SUFIJO,
    Laboratorio,
    comprobar,
    crear_base,
    ejecutar,
    huella,
    instalar_heredado,
    tabla_existe,
    version,
)

SCRIPT = RAIZ / "propuestas" / "p0018_p0019_firma_manual.sql"
COMPONENTE = RAIZ / "propuestas" / "componente_firma_documentos.sql"
REVISION_ACTUAL = "p0016_cursos_artilleros"  # como esart_db: p0015/p0016 aplicadas, p0017 no


def psql(lab: Laboratorio, archivo: Path) -> tuple[int, str]:
    """Igual que el operador: psql -X -f archivo, con ON_ERROR_STOP del propio script."""
    return ejecutar(
        [str(PG / f"psql{SUFIJO}"), "-X", "-h", "127.0.0.1", "-p", str(lab.puerto), "-U", "lab_admin", "-d", BASE, "-f", str(archivo)],
        permitir_fallo=True,
    )


async def tablas_firma(con) -> int:
    return await con.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='esart_firma'")


async def escenario_normal(lab: Laboratorio) -> None:
    await crear_base(lab, REVISION_ACTUAL)
    await instalar_heredado(lab)
    comprobar("Antes del script: la API responde FIRMA_NO_DISPONIBLE", await estado_firma(lab) == "FIRMA_NO_DISPONIBLE")
    con = await lab.conectar("esart_migrador")
    antes = await huella(con)
    await con.close()

    codigo, salida = psql(lab, SCRIPT)
    con = await lab.conectar("esart_migrador")
    despues = await huella(con)
    comprobar("Script ejecutado con psql sin errores (COMMIT)", codigo == 0 and "COMMIT" in salida, "" if codigo == 0 else salida[-400:])
    comprobar("esart_firma: 21 tablas heredadas + documentos y versiones_documento", await tablas_firma(con) == 23)
    comprobar("Conteos, 5 roles y 8 permisos idénticos", despues == antes)
    comprobar("alembic_version no se modificó", await version(con) == REVISION_ACTUAL)
    comprobar("FIRMA_DOCUMENTOS en la malla", await con.fetchval("SELECT count(*) FROM esart.componentes WHERE codigo='FIRMA_DOCUMENTOS'") == 1)
    await con.close()
    comprobar("Después del script: la firma queda disponible", await estado_firma(lab) == "OK")

    # Con el SQL manual las tablas nuevas son del superusuario (como postgres en esart_db).
    laboratorio_firma.USUARIO_VERIFICACION = "lab_admin"
    tamano_previo = len(RESULTADOS)
    await flujo(lab)
    fallas_flujo = [r for r in RESULTADOS[tamano_previo:] if not r[1]]
    comprobar("Flujo completo de firma desde el celular sobre la base migrada con el script",
              not fallas_flujo, f"{len(RESULTADOS) - tamano_previo} comprobaciones del flujo")  # fmt: skip

    con = await lab.conectar("lab_admin")
    previo = (await tablas_firma(con), await con.fetchval("SELECT count(*) FROM esart_firma.documentos"))
    await con.close()
    codigo, salida = psql(lab, SCRIPT)
    con = await lab.conectar("lab_admin")
    comprobar("Segunda ejecución: aborta sin cambios",
              codigo != 0 and "No se ejecuta dos veces" in salida
              and (await tablas_firma(con), await con.fetchval("SELECT count(*) FROM esart_firma.documentos")) == previo)  # fmt: skip
    await con.close()


async def escenario_estructura_distinta(lab: Laboratorio) -> None:
    await crear_base(lab, REVISION_ACTUAL)
    await instalar_heredado(lab, alterar="ALTER TABLE esart_firma.evidencias ADD COLUMN extra text")
    codigo, salida = psql(lab, SCRIPT)
    con = await lab.conectar("esart_migrador")
    comprobar("Estructura heredada distinta: aborta y no crea nada",
              codigo != 0 and "no coincide con el inventario" in salida
              and not await tabla_existe(con, "esart_firma.documentos")
              and not await con.fetchval("SELECT count(*) FROM esart.componentes WHERE codigo='FIRMA_DOCUMENTOS'"))  # fmt: skip
    await con.close()


async def escenario_componente_previo(lab: Laboratorio) -> None:
    await crear_base(lab, REVISION_ACTUAL)
    await instalar_heredado(lab)
    codigo_componente, _ = psql(lab, COMPONENTE)
    con = await lab.conectar("esart_migrador")
    await con.execute(
        "UPDATE esart.rol_permisos SET puede_acceder=true, puede_leer=true WHERE componente_id=(SELECT id FROM esart.componentes WHERE codigo='FIRMA_DOCUMENTOS') AND rol_id=(SELECT id FROM esart.roles WHERE codigo='USUARIO')"
    )
    await con.close()
    codigo, salida = psql(lab, SCRIPT)
    con = await lab.conectar("esart_migrador")
    comprobar("Con el componente agregado antes: funciona y respeta la malla",
              codigo_componente == 0 and codigo == 0 and await tablas_firma(con) == 23
              and await con.fetchval("SELECT rp.puede_leer FROM esart.rol_permisos rp JOIN esart.roles r ON r.id=rp.rol_id JOIN esart.componentes c ON c.id=rp.componente_id WHERE c.codigo='FIRMA_DOCUMENTOS' AND r.codigo='USUARIO'"),
              "" if codigo == 0 else salida[-400:])  # fmt: skip
    await con.close()


async def principal(lab: Laboratorio) -> None:
    await escenario_normal(lab)
    await escenario_estructura_distinta(lab)
    await escenario_componente_previo(lab)


def main() -> int:
    import shutil

    lab = Laboratorio()
    try:
        lab.iniciar()
        asyncio.run(principal(lab))
    finally:
        lab.detener()
        shutil.rmtree(CARPETA_DOCUMENTOS, ignore_errors=True)
    fallidas = [r for r in RESULTADOS if not r[1]]
    print(f"\n{len(RESULTADOS) - len(fallidas)}/{len(RESULTADOS)} comprobaciones correctas")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())
