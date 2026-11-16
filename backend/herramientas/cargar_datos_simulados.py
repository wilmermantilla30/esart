"""
Datos SIMULADOS para probar la verificación APTO / NO APTO mientras llega la importación por
Excel (HU de SV.Valbuena). Solo para desarrollo: se niega a correr con ENTORNO=produccion.

Uso, desde backend/:
    python -m herramientas.cargar_datos_simulados cargar    # crea los datos (si no existen)
    python -m herramientas.cargar_datos_simulados borrar    # los elimina

Todo lo simulado se reconoce para poder borrarlo sin tocar datos reales:
- cédulas que empiezan por 99000000 (nunca son cédulas reales de este sistema);
- unidades, comités, reentrenamientos y certificados con código que empieza por SIM-.
Los tipos de curso NO son simulados: se cargan del seed oficial de SV.Valbuena
(aplicacion/base_datos/seed_catalogos_academicos.sql) y no se borran.

Las fechas se calculan desde HOY (según PostgreSQL, hora de Colombia), así cada caso da
siempre el mismo resultado sin importar el día en que se cargue.
"""

import asyncio
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

from aplicacion.base_datos.sesion import cerrar_motor_base_datos, obtener_fabrica_sesiones
from aplicacion.configuracion import obtener_configuracion

PREFIJO_CEDULA = "99000000"
PREFIJO_CODIGO = "SIM-"
RUTA_SEED_CURSOS = Path(__file__).resolve().parents[1] / "aplicacion/base_datos/seed_catalogos_academicos.sql"

UNIDADES = [
    ("SIM-BAART3", "Batallón de Artillería No. 3 (simulado)"),
    ("SIM-GRUAR1", "Grupo de Artillería No. 1 (simulado)"),
    ("SIM-ESART", "Escuela de Artillería (simulado)"),
]

# Cada militar representa un caso de la regla. Los cursos y reentrenamientos se expresan en
# días relativos a hoy: negativo = en el pasado.
#   cursos: (codigo_tipo_curso, dias_desde_fin, aprobado)   dias_desde_fin positivo = termina en el futuro
#   reentrenamiento: dias desde la expedición (negativo) o None
MILITARES = [
    {
        "cedula": "9900000001",
        "grado": "MY",
        "nombres": "Andrés Felipe",
        "apellidos": "Rojas Medina",
        "genero": "M",
        "categoria": "OFICIAL",
        "unidad": "SIM-BAART3",
        "activo": True,
        "cursos": [("SACLI", -975, True)],
        "reentrenamiento": None,
        "esperado": "APTO por SACLI aprobado hace 2 años y 8 meses",
    },
    {
        "cedula": "9900000002",
        "grado": "CT",
        "nombres": "Laura Marcela",
        "apellidos": "Gómez Duarte",
        "genero": "F",
        "categoria": "OFICIAL",
        "unidad": "SIM-GRUAR1",
        "activo": True,
        "cursos": [("SACME", -365, True)],
        "reentrenamiento": None,
        "esperado": "APTO por SACME aprobado hace 1 año",
    },
    {
        "cedula": "9900000003",
        "grado": "SV",
        "nombres": "Carlos Arturo",
        "apellidos": "Peña Salazar",
        "genero": "M",
        "categoria": "SUBOFICIAL",
        "unidad": "SIM-BAART3",
        "activo": True,
        "cursos": [],
        "reentrenamiento": -90,
        "esperado": "APTO por reentrenamiento vigente (expedido hace 3 meses)",
    },
    {
        "cedula": "9900000004",
        "grado": "SS",
        "nombres": "Diana Carolina",
        "apellidos": "Ruiz Pardo",
        "genero": "F",
        "categoria": "SUBOFICIAL",
        "unidad": "SIM-ESART",
        "activo": True,
        "cursos": [],
        "reentrenamiento": -335,
        "esperado": "APTO con ALERTA: reentrenamiento vence en unos 30 días",
    },
    {
        "cedula": "9900000005",
        "grado": "CP",
        "nombres": "Jorge Iván",
        "apellidos": "Díaz Moreno",
        "genero": "M",
        "categoria": "SUBOFICIAL",
        "unidad": "SIM-GRUAR1",
        "activo": True,
        "cursos": [],
        "reentrenamiento": -425,
        "esperado": "NO APTO: reentrenamiento vencido hace unos 2 meses",
    },
    {
        "cedula": "9900000006",
        "grado": "TE",
        "nombres": "Paola Andrea",
        "apellidos": "Mejía Torres",
        "genero": "F",
        "categoria": "OFICIAL",
        "unidad": "SIM-ESART",
        "activo": True,
        "cursos": [("SACLI", 30, False)],
        "reentrenamiento": None,
        "esperado": "NO APTO: SACLI en curso, no aprobado",
    },
    {
        "cedula": "9900000007",
        "grado": "SP",
        "nombres": "Hernán Darío",
        "apellidos": "Castro León",
        "genero": "M",
        "categoria": "SUBOFICIAL",
        "unidad": "SIM-BAART3",
        "activo": False,
        "cursos": [("SACLI", -700, True)],
        "reentrenamiento": None,
        "esperado": "NO APTO: tiene SACLI pero está inactivo",
    },
    {
        "cedula": "9900000008",
        "grado": "CS",
        "nombres": "Luis Eduardo",
        "apellidos": "Ortega Ramírez",
        "genero": "M",
        "categoria": "SUBOFICIAL",
        "unidad": "SIM-GRUAR1",
        "activo": True,
        "cursos": [],
        "reentrenamiento": None,
        "esperado": "NO APTO: sin cursos ni reentrenamiento",
    },
    {
        "cedula": "9900000009",
        "grado": "ST",
        "nombres": "Marcela",
        "apellidos": "Vargas Quintero",
        "genero": "F",
        "categoria": "OFICIAL",
        "unidad": "SIM-ESART",
        "activo": True,
        "cursos": [("OA", -200, True)],
        "reentrenamiento": None,
        "esperado": "NO APTO: su curso (OA) no es habilitante",
    },
    {
        "cedula": "9900000010",
        "grado": "SV",
        "nombres": "Felipe",
        "apellidos": "Herrera Cárdenas",
        "genero": "M",
        "categoria": "SUBOFICIAL",
        "unidad": "SIM-BAART3",
        "activo": True,
        "cursos": [("SACME", -500, True)],
        "reentrenamiento": -350,
        "esperado": "APTO por SACME, con ALERTA de reentrenamiento por vencer",
    },
]

DATOS_REENTRENAMIENTO = {
    "proposito": "CERTIFICACION",
    "tipo": "OBUS",
    "movilidad": "REMOLCADO",
    "calibre": "105MM",
}


def exigir_entorno_de_desarrollo() -> None:
    if obtener_configuracion().es_produccion:
        raise SystemExit("Los datos simulados no se cargan en producción.")


def sentencia_tipos_curso() -> str:
    """El INSERT de tipos_curso del seed oficial (repetible: ON CONFLICT DO NOTHING)."""
    contenido = RUTA_SEED_CURSOS.read_text(encoding="utf-8")
    coincidencia = re.search(
        r"INSERT INTO esart\.tipos_curso.*?ON CONFLICT \(codigo\) DO NOTHING", contenido, re.S
    )
    if coincidencia is None:
        raise SystemExit(f"No se encontró el INSERT de tipos_curso en {RUTA_SEED_CURSOS}")
    return coincidencia.group(0)


@dataclass(frozen=True)
class ContextoSimulacion:
    """Datos comunes que necesita cada militar simulado (fecha, catálogos, unidades, comité)."""

    hoy: date
    administrador_id: int
    tipos_curso: dict[str, int]
    unidades: dict[str, int]
    comite_id: int


async def preparar_contexto(sesion) -> ContextoSimulacion:
    """Carga los tipos de curso oficiales y crea (o reutiliza) unidades y comité simulados."""
    hoy: date = await sesion.scalar(text("SELECT (now() AT TIME ZONE 'America/Bogota')::date"))
    administrador_id = await sesion.scalar(
        text("""
            SELECT u.id FROM esart_ref.usuarios u
            JOIN esart.usuario_roles ur ON ur.usuario_id = u.id
            JOIN esart.roles r ON r.id = ur.rol_id AND r.codigo = 'ADMINISTRADOR'
            WHERE u.activo ORDER BY u.id LIMIT 1
        """)
    )
    if administrador_id is None:
        raise SystemExit("No hay un usuario ADMINISTRADOR activo (arranque la API una vez para crearlo).")

    await sesion.execute(text(sentencia_tipos_curso()))
    tipos_curso = dict((await sesion.execute(text("SELECT codigo, id FROM esart.tipos_curso"))).all())

    unidades = {}
    for codigo, nombre in UNIDADES:
        unidades[codigo] = await sesion.scalar(
            text("""
                INSERT INTO esart_ref.unidades_militares (codigo, nombre, activo)
                VALUES (:codigo, :nombre, true)
                ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre RETURNING id
            """),
            {"codigo": codigo, "nombre": nombre},
        )

    comite_id = await sesion.scalar(
        text("""
            INSERT INTO esart.comites_moviles (codigo, director_autoriza_id, fecha_constitucion)
            VALUES ('SIM-COM-01', :administrador, :fecha)
            ON CONFLICT (codigo) DO UPDATE SET activo = true RETURNING id
        """),
        {"administrador": administrador_id, "fecha": hoy - timedelta(days=800)},
    )
    return ContextoSimulacion(hoy, administrador_id, tipos_curso, unidades, comite_id)


async def insertar_militar(sesion, contexto: ContextoSimulacion, militar: dict) -> int:
    """Crea un militar con sus cursos y su reentrenamiento (si los tiene). Devuelve su id."""
    personal_id = await sesion.scalar(
        text("""
            INSERT INTO esart.personal_militar
              (documento_identidad, nombres, apellidos, grado, genero, categoria,
               unidad_actual_id, activo)
            VALUES (:cedula, :nombres, :apellidos, :grado, :genero, :categoria, :unidad, :activo)
            RETURNING id
        """),
        {
            **{k: militar[k] for k in ("cedula", "nombres", "apellidos", "grado", "genero", "categoria")},
            "unidad": contexto.unidades[militar["unidad"]],
            "activo": militar["activo"],
        },
    )
    if militar["cursos"]:
        hoja_vida_id = await sesion.scalar(
            text("INSERT INTO esart.hoja_vida_artillero (artillero_id) VALUES (:id) RETURNING id"),
            {"id": personal_id},
        )
        for codigo_curso, dias_desde_fin, aprobado in militar["cursos"]:
            fin = contexto.hoy + timedelta(days=dias_desde_fin)
            await sesion.execute(
                text("""
                    INSERT INTO esart.artillero_cursos
                      (hoja_vida_id, tipo_curso_id, nombre, institucion,
                       fecha_inicio, fecha_fin, aprobado)
                    SELECT :hoja, tc.id, tc.nombre, 'Escuela de Artillería', :inicio, :fin, :aprobado
                    FROM esart.tipos_curso tc WHERE tc.id = :tipo
                """),
                {
                    "hoja": hoja_vida_id,
                    "tipo": contexto.tipos_curso[codigo_curso],
                    "inicio": fin - timedelta(days=70),
                    "fin": fin,
                    "aprobado": aprobado,
                },
            )
    if militar["reentrenamiento"] is not None:
        expedicion = contexto.hoy + timedelta(days=militar["reentrenamiento"])
        reentrenamiento_id = await sesion.scalar(
            text("""
                INSERT INTO esart.reentrenamientos
                  (comite_id, unidad_id, bateria_designada_por, proposito, tipo, movilidad, calibre,
                   codigo, fecha_inicio, fecha_fin, estado)
                VALUES (:comite, :unidad, :administrador, :proposito, :tipo, :movilidad, :calibre,
                        :codigo, :inicio, :fin, 'FINALIZADO')
                RETURNING id
            """),
            {
                **DATOS_REENTRENAMIENTO,
                "comite": contexto.comite_id,
                "unidad": contexto.unidades[militar["unidad"]],
                "administrador": contexto.administrador_id,
                "codigo": f"{PREFIJO_CODIGO}REE-{militar['cedula']}",
                "inicio": expedicion - timedelta(days=7),
                "fin": expedicion,
            },
        )
        participante_id = await sesion.scalar(
            text("""
                INSERT INTO esart.participantes_reentrenamiento
                  (reentrenamiento_id, personal_id, resultado, fecha_resultado)
                VALUES (:reentrenamiento, :personal, 'CERTIFICADO', :fecha) RETURNING id
            """),
            {"reentrenamiento": reentrenamiento_id, "personal": personal_id, "fecha": expedicion},
        )
        await sesion.execute(
            text("""
                INSERT INTO esart.certificados_reentrenamiento
                  (participante_id, personal_id, proposito, tipo, movilidad, calibre,
                   numero_certificado,
                   fecha_expedicion, apto_para_disparar, vigente, expedido_por_id)
                VALUES (:participante, :personal, :proposito, :tipo, :movilidad, :calibre, :numero,
                        :expedicion, true, true, :administrador)
            """),
            {
                **DATOS_REENTRENAMIENTO,
                "participante": participante_id,
                "personal": personal_id,
                "numero": f"{PREFIJO_CODIGO}CERT-{militar['cedula']}",
                "expedicion": expedicion,
                "administrador": contexto.administrador_id,
            },
        )
    return personal_id


async def cargar() -> None:
    async with obtener_fabrica_sesiones()() as sesion, sesion.begin():
        existentes = await sesion.scalar(
            text("SELECT count(*) FROM esart.personal_militar WHERE documento_identidad LIKE :prefijo"),
            {"prefijo": PREFIJO_CEDULA + "%"},
        )
        if existentes:
            print(f"Ya hay {existentes} militares simulados. Use 'borrar' antes de volver a cargar.")
            return

        contexto = await preparar_contexto(sesion)
        for militar in MILITARES:
            await insertar_militar(sesion, contexto, militar)
            print(
                f"  {militar['cedula']}  {militar['grado']:3} {militar['nombres']} {militar['apellidos']}"
                f"  ->  {militar['esperado']}"
            )
    print(f"Listo: {len(MILITARES)} militares simulados en {len(UNIDADES)} unidades simuladas.")


async def borrar() -> None:
    async with obtener_fabrica_sesiones()() as sesion, sesion.begin():
        valores = {"cedulas": PREFIJO_CEDULA + "%", "codigos": PREFIJO_CODIGO + "%"}
        sentencias = [
            (
                "certificados_reentrenamiento",
                "DELETE FROM esart.certificados_reentrenamiento WHERE personal_id IN "
                "(SELECT id FROM esart.personal_militar WHERE documento_identidad LIKE :cedulas)",
            ),
            (
                "participantes_reentrenamiento",
                "DELETE FROM esart.participantes_reentrenamiento WHERE personal_id IN "
                "(SELECT id FROM esart.personal_militar WHERE documento_identidad LIKE :cedulas)",
            ),
            ("reentrenamientos", "DELETE FROM esart.reentrenamientos WHERE codigo LIKE :codigos"),
            ("comites_moviles", "DELETE FROM esart.comites_moviles WHERE codigo LIKE :codigos"),
            (
                "artillero_cursos",
                "DELETE FROM esart.artillero_cursos WHERE hoja_vida_id IN "
                "(SELECT id FROM esart.hoja_vida_artillero WHERE artillero_id IN "
                "(SELECT id FROM esart.personal_militar WHERE documento_identidad LIKE :cedulas))",
            ),
            (
                "hoja_vida_artillero",
                "DELETE FROM esart.hoja_vida_artillero WHERE artillero_id IN "
                "(SELECT id FROM esart.personal_militar WHERE documento_identidad LIKE :cedulas)",
            ),
            (
                "personal_militar",
                "DELETE FROM esart.personal_militar WHERE documento_identidad LIKE :cedulas",
            ),
            ("unidades_militares", "DELETE FROM esart_ref.unidades_militares WHERE codigo LIKE :codigos"),
        ]
        # Las sentencias son constantes de este archivo; los patrones van como parámetros.
        for tabla, sentencia in sentencias:
            resultado = await sesion.execute(text(sentencia), valores)
            print(f"  {tabla}: {resultado.rowcount} filas borradas")
    print("Datos simulados eliminados (los tipos de curso del seed oficial se conservan).")


async def principal(accion: str) -> None:
    exigir_entorno_de_desarrollo()
    try:
        await (cargar() if accion == "cargar" else borrar())
    finally:
        await cerrar_motor_base_datos()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("cargar", "borrar"):
        raise SystemExit("Uso: python -m herramientas.cargar_datos_simulados cargar|borrar")
    asyncio.run(principal(sys.argv[1]))
