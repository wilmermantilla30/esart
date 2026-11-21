"""
Prueba de la cadena p0015 → p0018 en un clúster PostgreSQL efímero (nunca toca esart_db).

Reproduce el procedimiento del operador (docs/ESART_P0018_OPERADOR_SEGURO.md) sin datos reales:
1. Base esart_db_p0018_restore_test con dueño esart_migrador (no superusuario), como la copia
   restaurada con --no-owner. Migraciones p0000 → p0014 con Alembic y las guardas reales.
2. Esquema heredado esart_firma construido desde el inventario (21 tablas) con 5 roles y 8 permisos
   de ejemplo (los valores reales no son legibles con la cuenta de la API; aquí se mide que no cambien).
3. alembic upgrade head (p0015 → p0018) y verificación de preservación, estructura y permisos.
4. Pruebas funcionales como esart_aplicacion: certificación y oficio persistidos, auditoría encadenada,
   evidencias, identidad enlazada sin duplicar, inmutabilidad, TOTP heredado bloqueado.
5. Downgrade (falla cerrado con documentos; sin ellos conserva lo heredado), guardas de
   precondición (aborta sin cambios) e instalación nueva sin esquema heredado.

Uso desde backend/:  .venv\\Scripts\\python.exe herramientas\\probar_p0018_aislada.py
PG_BIN permite indicar otra instalación de PostgreSQL (por defecto la 18 de Windows).
"""

# SQL de laboratorio armado con constantes e inventario versionado; líneas largas para leer cada caso.
# ruff: noqa: E501, S608

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import asyncpg

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
PG = Path(os.environ.get("PG_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
SUFIJO = ".exe" if os.name == "nt" else ""
BASE = "esart_db_p0018_restore_test"
HEREDADO = json.loads(
    (RAIZ / "migraciones_principal" / "datos" / "p0018_esart_firma_heredado.json").read_text(encoding="utf-8")
)["tablas"]
TABLAS_HEREDADAS = [t["tabla"] for t in HEREDADO]
RESULTADOS: list[tuple[str, bool, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    RESULTADOS.append((nombre, bool(condicion), detalle))
    print(f"[{'OK' if condicion else 'FALLA'}] {nombre}{(' — ' + detalle) if detalle else ''}")


def ejecutar(argumentos, *, entorno=None, permitir_fallo=False) -> tuple[int, str]:
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as salida:
        resultado = subprocess.run(  # noqa: S603 -- ejecutables y argumentos internos, sin shell
            argumentos,
            cwd=RAIZ,
            env=entorno,
            stdout=salida,
            stderr=salida,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        salida.seek(0)
        texto = salida.read()
    if resultado.returncode and not permitir_fallo:
        print(texto[-3000:])
        raise RuntimeError(f"Falló {Path(str(argumentos[0])).name} {' '.join(map(str, argumentos[1:4]))}")
    return resultado.returncode, texto


class Laboratorio:
    def __init__(self):
        self.temporal = Path(tempfile.mkdtemp(prefix="esart-p0018-")).resolve()
        self.datos = self.temporal / "datos"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.puerto = s.getsockname()[1]
        if self.puerto in (5432, 5433):
            raise RuntimeError("No se usan puertos operativos")

    def iniciar(self):
        ejecutar([str(PG / f"initdb{SUFIJO}"), "-D", str(self.datos), "-A", "trust", "-U", "lab_admin",
                  "--no-locale", "--encoding=UTF8"])  # fmt: skip
        ejecutar([str(PG / f"pg_ctl{SUFIJO}"), "-D", str(self.datos), "-l", str(self.temporal / "pg.log"),
                  "-o", f"-h 127.0.0.1 -p {self.puerto}", "-w", "start"])  # fmt: skip

    def detener(self):
        ejecutar(
            [str(PG / f"pg_ctl{SUFIJO}"), "-D", str(self.datos), "-m", "fast", "-w", "stop"],
            permitir_fallo=True,
        )
        shutil.rmtree(self.temporal, ignore_errors=True)

    async def conectar(self, usuario: str, base: str = BASE) -> asyncpg.Connection:
        return await asyncpg.connect(
            host="127.0.0.1", port=self.puerto, user=usuario, database=base, ssl=False
        )

    def url(self, usuario: str, base: str = BASE) -> str:
        return f"postgresql+asyncpg://{usuario}@127.0.0.1:{self.puerto}/{base}"

    def alembic(self, *argumentos, permitir_fallo=False, base=BASE) -> tuple[int, str]:
        entorno = os.environ.copy()
        entorno.update(
            ESART_MIGRACIONES_URL=self.url("esart_migrador", base),
            ESART_VALIDAR_P0018_COPIA="1",
            PYTHONIOENCODING="utf-8",
        )
        return ejecutar(
            [sys.executable, "-m", "alembic", *argumentos], entorno=entorno, permitir_fallo=permitir_fallo
        )


async def crear_base(lab: Laboratorio, revision: str) -> None:
    """
    Copia de ensayo en `revision`. p0001 exige el nombre esart_db, así que hasta `revision` se migra con
    ese nombre (solo dentro del clúster efímero) y después se renombra a esart_db_p0018_restore_test,
    igual que la copia restaurada del operador, que ya llega en p0014. Todo queda a nombre de
    esart_migrador, como en una restauración con --no-owner.
    """
    admin = await lab.conectar("lab_admin", "postgres")
    try:
        for base in (BASE, "esart_db"):
            await admin.execute(f"DROP DATABASE IF EXISTS {base}")
        for rol in ("esart_migrador", "esart_aplicacion"):
            if not await admin.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", rol):
                await admin.execute(f"CREATE ROLE {rol} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
        await admin.execute("CREATE DATABASE esart_db OWNER esart_migrador")
        # En esart_db las tablas TOTP de seguridad se crearon a mano (p0005 solo las adopta):
        # se reproduce con aplicacion/base_datos/seguridad.sql entre p0004 y p0005.
        lab.alembic("upgrade", "p0004_captcha_local", base="esart_db")
        migrador = await lab.conectar("esart_migrador", "esart_db")
        try:
            await migrador.execute(
                (RAIZ / "aplicacion" / "base_datos" / "seguridad.sql").read_text(encoding="utf-8-sig")
            )
        finally:
            await migrador.close()
        lab.alembic("upgrade", revision, base="esart_db")
        await admin.execute(f"ALTER DATABASE esart_db RENAME TO {BASE}")
    finally:
        await admin.close()


def ddl_heredado(tablas: list[dict]) -> list[str]:
    """Esquema heredado tal como lo restauraría pg_restore --no-owner (independiente de p0018)."""
    sentencias = [
        "CREATE SCHEMA esart_firma",
        "CREATE FUNCTION esart_firma.bloquear_mutacion_evidencia() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'evidencia inmutable'; END $$",
    ]
    for t in tablas:
        columnas = []
        for nombre, tipo, no_nulo, defecto in t["columnas"]:
            extra = (
                " GENERATED BY DEFAULT AS IDENTITY"
                if nombre in t["secuencias"]
                else (f" DEFAULT {defecto}" if defecto else "")
            )
            columnas.append(f"{nombre} {tipo}{extra}{' NOT NULL' if no_nulo else ''}")
        sentencias.append(f"CREATE TABLE esart_firma.{t['tabla']} ({', '.join(columnas)})")
    for tipos in ("pu", "c", "f"):
        for t in tablas:
            sentencias += [
                f"ALTER TABLE esart_firma.{t['tabla']} ADD CONSTRAINT {n} {d}"
                for c, n, d in t["restricciones"]
                if c in tipos
            ]
    for t in tablas:
        propios = {r[1] for r in t["restricciones"]}
        sentencias += [d for n, d in t["indices"] if n not in propios] + [d for _, d in t["disparadores"]]
    return sentencias


async def instalar_heredado(lab: Laboratorio, *, alterar=None, fila_sesion=False) -> None:
    con = await lab.conectar("esart_migrador")
    try:
        for sentencia in ddl_heredado(HEREDADO):
            await con.execute(sentencia)
        for i in range(1, 6):
            await con.execute(
                "INSERT INTO esart_firma.roles_firma (codigo, descripcion) VALUES ($1, $2)",
                f"ROL_{i}",
                f"Rol de ejemplo {i}",
            )
        for i in range(1, 9):
            await con.execute(
                "INSERT INTO esart_firma.permisos_firma (codigo, descripcion) VALUES ($1, $2)",
                f"PERMISO_{i}",
                f"Permiso de ejemplo {i}",
            )
        if alterar:
            await con.execute(alterar)
        if fila_sesion:
            await con.execute(
                "INSERT INTO esart_firma.identidades (usuario_externo_id, nombre_mostrado) VALUES ('x','x')"
            )
            await con.execute(
                "INSERT INTO esart_firma.sesiones_firma (identidad_id, refresh_token_hash, expira_en) "
                "VALUES (1, 'h', now() + interval '1 hour')"
            )
    finally:
        await con.close()


async def huella(con: asyncpg.Connection) -> dict:
    datos = {t: await con.fetchval(f"SELECT count(*) FROM esart_firma.{t}") for t in TABLAS_HEREDADAS}  # noqa: S608
    for tabla, orden in (("roles_firma", "id"), ("permisos_firma", "id")):
        datos[tabla + "#filas"] = [
            tuple(f) for f in await con.fetch(f"SELECT * FROM esart_firma.{tabla} ORDER BY {orden}")
        ]  # noqa: S608
    return datos


async def version(con) -> str | None:
    return await con.fetchval("SELECT version_num FROM esart.alembic_version")


async def tabla_existe(con, nombre: str) -> bool:
    return await con.fetchval("SELECT to_regclass($1) IS NOT NULL", nombre)


async def falla(con, sql: str, *args) -> str | None:
    """Ejecuta en un savepoint y devuelve el mensaje de error (None si no falló)."""
    try:
        async with con.transaction():
            await con.execute(sql, *args)
    except asyncpg.PostgresError as error:
        return str(error)
    return None


async def preparar_personal(con) -> tuple[int, int]:
    usuario = await con.fetchval(
        "INSERT INTO esart_ref.usuarios (usuario) VALUES ('emisor.prueba') RETURNING id"
    )
    personal = await con.fetchval(
        "INSERT INTO esart.personal_militar (documento_identidad, nombres, apellidos, grado, genero, categoria) "
        "VALUES ('1024589632', 'Carlos', 'Colorado', 'SV', 'M', 'SUBOFICIAL') RETURNING id"
    )
    return usuario, personal


async def pruebas_funcionales(lab: Laboratorio) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aplicacion.servicios.almacenamiento_documental import hash_evento_firma, registrar_documento

    migrador = await lab.conectar("esart_migrador")
    usuario_id, personal_id = await preparar_personal(migrador)
    motor = create_async_engine(lab.url("esart_aplicacion"), connect_args={"ssl": False})
    directorio = lab.temporal / "almacen_privado"
    peticion = type("Peticion", (), {"headers": {"user-agent": "laboratorio"}, "client": None})()
    try:
        async with AsyncSession(motor) as sesion:
            for tipo in ("CERTIFICACION", "OFICIO_REMISORIO"):
                import aplicacion.servicios.almacenamiento_documental as almacen

                almacen.obtener_ip_cliente = lambda _r: "127.0.0.1"
                await registrar_documento(
                    sesion, directorio=directorio, pdf=b"%PDF-1.7\n" + tipo.encode(), numero=f"ESART-{tipo}",
                    tipo=tipo, personal_id=personal_id, usuario_id=usuario_id, datos_emitidos={"tipo": tipo},
                    request=peticion,
                )  # fmt: skip
                await sesion.commit()
            comprobar(
                "API: no puede leer TOTP heredado",
                await _sin_permiso(sesion, text("SELECT 1 FROM esart_firma.totp_factores")),
            )
    finally:
        await motor.dispose()

    comprobar(
        "Documentos certificación + oficio",
        await migrador.fetchval("SELECT count(*) FROM esart_firma.documentos") == 2,
    )
    comprobar(
        "Una versión por documento",
        await migrador.fetchval("SELECT count(*) FROM esart_firma.versiones_documento") == 2,
    )
    comprobar(
        "Identidad enlazada 1:1 al usuario ESART (sin duplicar)",
        await migrador.fetchval(
            "SELECT count(*) FROM esart_firma.identidades WHERE usuario_id=$1", usuario_id
        )
        == 1
        and await migrador.fetchval("SELECT count(*) FROM esart_firma.identidades") == 1,
    )
    eventos = await migrador.fetch(
        "SELECT evento_id, actor_id, correlacion_id, accion, recurso_tipo, recurso_id, resultado, detalle_filtrado, "
        "hash_anterior, hash_evento FROM esart_firma.auditoria_eventos ORDER BY id"
    )
    cadena = (
        len(eventos) == 2
        and eventos[0]["hash_anterior"] is None
        and eventos[1]["hash_anterior"] == eventos[0]["hash_evento"]
    )
    for evento in eventos:
        campos = {
            "evento_id": str(evento["evento_id"]), "actor_id": evento["actor_id"],
            "correlacion_id": str(evento["correlacion_id"]), "accion": evento["accion"],
            "recurso_tipo": evento["recurso_tipo"], "recurso_id": evento["recurso_id"],
            "resultado": evento["resultado"], "detalle": json.loads(evento["detalle_filtrado"]),
        }  # fmt: skip
        anterior = evento["hash_anterior"].strip() if evento["hash_anterior"] else None
        cadena = cadena and hash_evento_firma(anterior, campos) == evento["hash_evento"].strip()
    comprobar("Auditoría heredada encadenada y verificable", cadena, f"{len(eventos)} eventos")
    comprobar(
        "Evidencias PDF_ORIGINAL ligadas a documento y evento",
        await migrador.fetchval(
            "SELECT count(*) FROM esart_firma.evidencias e JOIN esart_firma.documentos d ON d.id=e.documento_id "
            "JOIN esart_firma.auditoria_eventos a ON a.evento_id=e.evento_id WHERE e.clase='PDF_ORIGINAL'"
        )
        == 2,
    )
    comprobar(
        "Versión de documento inmutable",
        await falla(migrador, "UPDATE esart_firma.versiones_documento SET tamano_bytes=1") is not None,
    )
    comprobar(
        "Auditoría inmutable", await falla(migrador, "DELETE FROM esart_firma.auditoria_eventos") is not None
    )
    error = await falla(
        migrador,
        "INSERT INTO esart_firma.totp_factores (identidad_id, secreto_cifrado, clave_version) VALUES (1, '\\x00', 'v1')",
    )
    comprobar("TOTP heredado no admite registros nuevos", error is not None and "heredado" in error)
    identidad = await migrador.fetchval("SELECT id FROM esart_firma.identidades")
    comprobar(
        "Desafío de login heredado rechazado",
        await falla(
            migrador,
            "INSERT INTO esart_firma.desafios_autenticacion (identidad_id, proposito, expira_en) VALUES ($1,'LOGIN', now()+interval '5 min')",
            identidad,
        )
        is not None,
    )
    desafio = await migrador.fetchval(
        "INSERT INTO esart_firma.desafios_autenticacion (identidad_id, proposito, expira_en) "
        "VALUES ($1,'FIRMAR', now()+interval '5 min') RETURNING id",
        identidad,
    )
    documento, version_id = await migrador.fetchrow(
        "SELECT documento_id, id FROM esart_firma.versiones_documento ORDER BY creado_en LIMIT 1"
    )
    autorizacion = await migrador.fetchval(
        "INSERT INTO esart_firma.autorizaciones_firmantes (identidad_id, tipo_certificado, cargo, vigente_desde) "
        "VALUES ($1, 'CERTIFICACION', 'Director', now()) RETURNING id",
        identidad,
    )
    solicitud = await migrador.fetchval(
        "INSERT INTO esart_firma.solicitudes_firma (documento_id, documento_version_id, firmante_id, autorizacion_id, "
        "token_qr_hash, creada_por, expira_en) VALUES ($1,$2,$3,$4,$5,$3, now()+interval '1 day') RETURNING id",
        documento, version_id, identidad, autorizacion, "a" * 64,
    )  # fmt: skip
    consentimiento = await migrador.fetchval(
        "INSERT INTO esart_firma.consentimientos_firma (solicitud_id, texto_aceptado, version_texto, documento_sha256, desafio_id) "
        "VALUES ($1, 'Acepto', 'v1', $2, $3) RETURNING id",
        solicitud, "b" * 64, desafio,
    )  # fmt: skip
    firma = await migrador.fetchval(
        "INSERT INTO esart_firma.firmas_certificado (solicitud_id, consentimiento_id, metodo, rubrica_archivo_sha256, "
        "pdf_resultante_sha256, pdf_resultante_ubicacion_segura) VALUES ($1,$2,'RUBRICA_ELECTRONICA',$3,$3,'x') RETURNING id",
        solicitud, consentimiento, "c" * 64,
    )  # fmt: skip
    comprobar("Cadena heredada de firma reutilizable para un documento ESART", firma is not None)
    comprobar(
        "Solicitud sin objeto (ni certificado ni documento) rechazada",
        await falla(
            migrador,
            "INSERT INTO esart_firma.solicitudes_firma (firmante_id, autorizacion_id, token_qr_hash, creada_por, expira_en) "
            "VALUES ($1,$2,$3,$1, now()+interval '1 day')",
            identidad,
            autorizacion,
            "d" * 64,
        )  # fmt: skip
        is not None,
    )
    await migrador.close()


async def _sin_permiso(sesion, sentencia) -> bool:
    from sqlalchemy.exc import ProgrammingError

    try:
        await sesion.execute(sentencia)
    except ProgrammingError as error:
        await sesion.rollback()
        return "permission denied" in str(error.orig) or "permiso denegado" in str(error.orig)
    return False


async def escenario_principal(lab: Laboratorio) -> None:
    await crear_base(lab, "p0014_cursos_del_instructor")
    await instalar_heredado(lab)
    con = await lab.conectar("esart_migrador")
    antes = await huella(con)
    comprobar("Copia en p0014 con 21 tablas heredadas y 13 registros",
              await version(con) == "p0014_cursos_del_instructor" and len(TABLAS_HEREDADAS) == 21
              and sum(v for k, v in antes.items() if "#" not in k) == 13)  # fmt: skip
    await con.close()

    lab.alembic("upgrade", "p0018_firma_documental")
    con = await lab.conectar("esart_migrador")
    despues = await huella(con)
    comprobar("Revisión final p0018", await version(con) == "p0018_firma_documental")
    comprobar(
        "Las 21 tablas heredadas existen",
        all([await tabla_existe(con, f"esart_firma.{t}") for t in TABLAS_HEREDADAS]),
    )
    comprobar(
        "Conteos de las 21 tablas sin cambios",
        {k: v for k, v in despues.items() if "#" not in k}
        == {k: v for k, v in antes.items() if "#" not in k},
    )
    comprobar("5 roles y 8 permisos intactos (ids, códigos, descripciones)",
              despues["roles_firma#filas"] == antes["roles_firma#filas"] and len(antes["roles_firma#filas"]) == 5
              and despues["permisos_firma#filas"] == antes["permisos_firma#filas"] and len(antes["permisos_firma#filas"]) == 8)  # fmt: skip
    comprobar("Solo se crearon documentos y versiones_documento",
              await con.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='esart_firma'") == 23
              and await tabla_existe(con, "esart_firma.documentos") and not await tabla_existe(con, "esart_firma.eventos_auditoria"))  # fmt: skip
    comprobar("Componente FIRMA_DOCUMENTOS en la malla",
              await con.fetchval("SELECT count(*) FROM esart.componentes WHERE codigo='FIRMA_DOCUMENTOS'") == 1)  # fmt: skip
    await con.close()

    codigo, salida = lab.alembic("downgrade", "p0017_restablecer_totp_admin", permitir_fallo=True)
    con = await lab.conectar("esart_migrador")
    comprobar("Downgrade sin documentos también falla cerrado",
              codigo != 0 and "No se puede revertir p0018" in salida
              and await version(con) == "p0018_firma_documental"
              and await huella(con) == antes and await tabla_existe(con, "esart_firma.documentos"))  # fmt: skip
    await con.close()

    await pruebas_funcionales(lab)
    codigo, salida = lab.alembic("downgrade", "p0017_restablecer_totp_admin", permitir_fallo=True)
    con = await lab.conectar("esart_migrador")
    comprobar("Downgrade con documentos falla cerrado",
              codigo != 0 and "No se puede revertir p0018" in salida and await version(con) == "p0018_firma_documental")  # fmt: skip
    final = await huella(con)
    comprobar("Roles y permisos siguen intactos tras las pruebas",
              final["roles_firma#filas"] == antes["roles_firma#filas"] and final["permisos_firma#filas"] == antes["permisos_firma#filas"])  # fmt: skip
    await con.close()


async def escenario_guardas(lab: Laboratorio) -> None:
    for descripcion, opciones, texto in (
        ("estructura heredada distinta", {"alterar": "ALTER TABLE esart_firma.certificados ADD COLUMN extra text"}, "no coincide con el inventario"),
        ("sesión heredada con datos", {"fila_sesion": True}, "sesiones_firma tiene registros"),
    ):  # fmt: skip
        await crear_base(lab, "p0017_restablecer_totp_admin")
        await instalar_heredado(lab, **opciones)
        codigo, salida = lab.alembic("upgrade", "p0018_firma_documental", permitir_fallo=True)
        con = await lab.conectar("esart_migrador")
        comprobar(f"Guarda: {descripcion} → aborta sin cambios",
                  codigo != 0 and texto in salida and await version(con) == "p0017_restablecer_totp_admin"
                  and not await tabla_existe(con, "esart_firma.documentos"))  # fmt: skip
        await con.close()


async def escenario_componente_previo(lab: Laboratorio) -> None:
    """propuestas/componente_firma_documentos.sql antes de p0018: la malla ya lo muestra y p0018 lo acepta."""
    await crear_base(lab, "p0017_restablecer_totp_admin")
    await instalar_heredado(lab)
    con = await lab.conectar("esart_migrador")
    await con.execute((RAIZ / "propuestas" / "componente_firma_documentos.sql").read_text(encoding="utf-8"))
    # Un ajuste hecho en la malla antes de p0018 (rol USUARIO con lectura) debe conservarse.
    await con.execute(
        "UPDATE esart.rol_permisos SET puede_acceder=true, puede_leer=true WHERE componente_id=(SELECT id FROM esart.componentes WHERE codigo='FIRMA_DOCUMENTOS') "
        "AND rol_id=(SELECT id FROM esart.roles WHERE codigo='USUARIO')"
    )
    await con.close()
    codigo, salida = lab.alembic("upgrade", "p0018_firma_documental", permitir_fallo=True)
    con = await lab.conectar("esart_migrador")
    comprobar("Componente agregado antes: p0018 lo acepta sin duplicar ni cambiar la malla",
              codigo == 0 and await version(con) == "p0018_firma_documental"
              and await con.fetchval("SELECT count(*) FROM esart.componentes WHERE codigo='FIRMA_DOCUMENTOS'") == 1
              and await con.fetchval("SELECT rp.puede_leer FROM esart.rol_permisos rp JOIN esart.roles r ON r.id=rp.rol_id "
                                     "JOIN esart.componentes c ON c.id=rp.componente_id WHERE c.codigo='FIRMA_DOCUMENTOS' AND r.codigo='USUARIO'"),
              "" if codigo == 0 else salida[-300:])  # fmt: skip
    await con.close()


async def escenario_instalacion_nueva(lab: Laboratorio) -> None:
    await crear_base(lab, "p0017_restablecer_totp_admin")
    lab.alembic("upgrade", "p0018_firma_documental")
    con = await lab.conectar("esart_migrador")
    comprobar("Instalación nueva: crea las 21 tablas heredadas + 2 nuevas",
              await version(con) == "p0018_firma_documental"
              and await con.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='esart_firma'") == 23)  # fmt: skip
    await con.close()


async def principal(lab: Laboratorio) -> None:
    await escenario_principal(lab)
    await escenario_guardas(lab)
    await escenario_componente_previo(lab)
    await escenario_instalacion_nueva(lab)


def main() -> int:
    lab = Laboratorio()
    try:
        lab.iniciar()
        asyncio.run(principal(lab))
    finally:
        lab.detener()
    fallidas = [r for r in RESULTADOS if not r[1]]
    print(f"\n{len(RESULTADOS) - len(fallidas)}/{len(RESULTADOS)} comprobaciones correctas")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())
