"""
Prueba de punta a punta de la firma desde el celular en un PostgreSQL efímero (nunca toca esart_db).

Reutiliza el laboratorio de p0018 (copia en p0014 + esquema heredado + Alembic con sus guardas) y
migra hasta head (p0019). Luego, como esart_aplicacion y con los servicios reales:
  solicitar firma (borrador v1 + QR) → abrir desde el "celular" → descargar borrador →
  firmar con rúbrica + TOTP real → PDF final v2 con la rúbrica, evidencias y auditoría encadenada.
Y los casos de rechazo: TOTP inválido, token reutilizado, enlace vencido, rúbrica vacía, firmante
sin autenticador, firmante sin autorización, sin aceptar la declaración.

Uso desde backend/:  .venv\\Scripts\\python.exe herramientas\\probar_firma_movil_aislada.py
"""

# ruff: noqa: E501, S608

import asyncio
import base64
import io
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
CARPETA_DOCUMENTOS = Path(tempfile.mkdtemp(prefix="esart-firma-docs-")).resolve()
# Configuración solo de este proceso (no se escribe en .env): TOTP con clave efímera y almacén temporal.
os.environ.update(
    TOTP_HABILITADO="true",
    TOTP_CLAVE_CIFRADO=base64.b64encode(secrets.token_bytes(32)).decode(),
    DOCUMENTOS_PERSISTENCIA_HABILITADA="true",
    DIRECTORIO_DOCUMENTOS_PRIVADOS=str(CARPETA_DOCUMENTOS),
)

import pyotp  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from herramientas.probar_p0018_aislada import (  # noqa: E402
    RESULTADOS,
    Laboratorio,
    comprobar,
    crear_base,
    instalar_heredado,
)

# Quién lee la base para verificar: el dueño de las tablas nuevas (esart_migrador si se migró con
# Alembic; el superusuario si se aplicó el SQL manual como postgres).
USUARIO_VERIFICACION = "esart_migrador"


class Peticion:
    """Lo mínimo de fastapi.Request que usan los servicios (IP y agente de usuario)."""

    def __init__(self):
        self.headers = {"user-agent": "Celular de laboratorio"}
        self.client = type("Cliente", (), {"host": "127.0.0.1"})()


def texto_pdf(pdf: bytes) -> str:
    """Texto de los flujos de contenido del PDF (ReportLab los comprime con zlib); sin dependencias extra."""
    import re
    import zlib

    partes = []
    for flujo in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        datos = flujo.strip()
        if datos.endswith(b"~>"):  # ReportLab: /ASCII85Decode /FlateDecode
            datos = base64.a85decode(datos if datos.startswith(b"<~") else b"<~" + datos, adobe=True)
        try:
            partes.append(zlib.decompress(datos).decode("latin-1"))
        except zlib.error:
            partes.append(datos.decode("latin-1", "ignore"))
    return "".join(partes)


def rubrica(vacia: bool = False) -> str:
    imagen = Image.new("RGBA", (600, 220), (0, 0, 0, 0))
    if not vacia:
        ImageDraw.Draw(imagen).line(
            [(40, 160), (140, 50), (240, 170), (340, 60), (440, 150), (560, 90)],
            fill=(15, 30, 90, 255),
            width=7,
        )
    salida = io.BytesIO()
    imagen.save(salida, "PNG")
    return "data:image/png;base64," + base64.b64encode(salida.getvalue()).decode()


async def preparar_datos(lab: Laboratorio) -> dict:
    """Usuarios, militar y TOTP del firmante (como migrador, dueño de la copia)."""
    from aplicacion.servicios.totp import TotpService

    con = await lab.conectar("esart_migrador")
    try:
        # Permisos que la API ya tiene en esart_db sobre esart/esart_ref/seguridad (fuera de esart_firma,
        # que es lo que se prueba: ahí solo valen los GRANT de p0018 y p0019).
        for esquema in ("esart", "esart_ref", "seguridad"):
            await con.execute(f"GRANT USAGE ON SCHEMA {esquema} TO esart_aplicacion")
            await con.execute(
                f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {esquema} TO esart_aplicacion"
            )
            await con.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {esquema} TO esart_aplicacion")
        await con.execute(
            "INSERT INTO esart.personal_militar (documento_identidad, nombres, apellidos, grado, genero, categoria) VALUES ('1024589632','Carlos Andrés','Colorado Gil','SV','M','SUBOFICIAL'), ('80111222','Juan','Pérez Gómez','CR','M','OFICIAL')"
        )
        ids = {}
        for nombre, documento in (
            ("generador", None),
            ("director", "80111222"),
            ("sin_totp", None),
            ("admin", None),
        ):
            ids[nombre] = await con.fetchval(
                "INSERT INTO esart_ref.usuarios (usuario, documento_identidad) VALUES ($1, $2) RETURNING id",
                nombre,
                documento,
            )
        secreto = pyotp.random_base32()
        await con.execute(
            "INSERT INTO seguridad.usuario_totp (usuario_id, secreto_cifrado, estado, activado_en) VALUES ($1, $2, 'ACTIVO', now())",
            ids["director"],
            TotpService.cifrar(ids["director"], secreto),
        )
        return {**ids, "secreto": secreto}
    finally:
        await con.close()


async def flujo(lab: Laboratorio) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aplicacion.nucleo.errores import ErrorAplicacion
    from aplicacion.rutas.verificacion import armar_datos_documento
    from aplicacion.servicios import firma_movil
    from aplicacion.servicios.almacenamiento_documental import hash_evento_firma

    datos_lab = await preparar_datos(lab)
    motor = create_async_engine(lab.url("esart_aplicacion"), connect_args={"ssl": False})
    peticion = Peticion()

    async def esperar_error(codigo: str, corrutina) -> bool:
        try:
            await corrutina
        except ErrorAplicacion as error:
            if error.codigo != codigo:
                print(f"   esperado {codigo}, recibido {error.codigo}: {error.mensaje}")
            return error.codigo == codigo
        print(f"   esperado {codigo}, no hubo error")
        return False

    try:
        async with AsyncSession(motor, expire_on_commit=False) as sesion:
            # El administrador autoriza al Director para ambos tipos; al usuario sin TOTP solo certificación.
            for tipo in firma_movil.TIPOS_FIRMABLES:
                await firma_movil.autorizar_firmante(
                    sesion,
                    usuario_id=datos_lab["director"],
                    tipo=tipo,
                    cargo="Director de la Escuela de Artillería",
                    grado=None,
                    concedido_por=datos_lab["admin"],
                    request=peticion,
                )
            await firma_movil.autorizar_firmante(
                sesion,
                usuario_id=datos_lab["sin_totp"],
                tipo="CERTIFICACION",
                cargo="Subdirector",
                grado="TC",
                concedido_por=datos_lab["admin"],
                request=peticion,
            )
            await sesion.commit()
            candidatos = {c["usuario_id"]: c for c in await firma_movil.listar_candidatos(sesion)}
            comprobar(
                "Candidatos a firmante con nombre y estado del autenticador",
                candidatos[datos_lab["director"]]["totp_activo"] is True
                and candidatos[datos_lab["director"]]["nombre"] == "CR Juan Pérez Gómez"
                and candidatos[datos_lab["sin_totp"]]["totp_activo"] is False,
            )
            firmantes = await firma_movil.listar_firmantes(sesion, "CERTIFICACION")
            director = next(f for f in firmantes if f["usuario_id"] == datos_lab["director"])
            sin_totp = next(f for f in firmantes if f["usuario_id"] == datos_lab["sin_totp"])
            comprobar(
                "Firmantes vigentes con nombre desde personal militar",
                director["nombre"] == "CR Juan Pérez Gómez" and len(firmantes) == 2,
            )
            comprobar(
                "Autorización repetida rechazada",
                await esperar_error(
                    "AUTORIZACION_EXISTENTE",
                    firma_movil.autorizar_firmante(
                        sesion,
                        usuario_id=datos_lab["director"],
                        tipo="CERTIFICACION",
                        cargo="Director",
                        grado=None,
                        concedido_por=datos_lab["admin"],
                        request=peticion,
                    ),
                ),
            )
            await sesion.rollback()

            async def solicitar(tipo, autorizacion):
                fila, datos = await armar_datos_documento(
                    sesion, "1024589632", datos_lab["generador"], "generador"
                )
                respuesta, _ = await firma_movil.solicitar_firma(
                    sesion,
                    datos=datos,
                    tipo=tipo,
                    personal_id=fila.id,
                    autorizacion_id=autorizacion,
                    usuario_id=datos_lab["generador"],
                    directorio=CARPETA_DOCUMENTOS,
                    request=peticion,
                )
                await sesion.commit()
                return respuesta

            comprobar(
                "Firmante sin autenticador no recibe solicitudes",
                await esperar_error(
                    "FIRMANTE_SIN_AUTENTICADOR", solicitar("CERTIFICACION", sin_totp["autorizacion_id"])
                ),
            )
            await sesion.rollback()
            oficio_director = next(
                f
                for f in await firma_movil.listar_firmantes(sesion, "OFICIO_REMISORIO")
                if f["usuario_id"] == datos_lab["director"]
            )
            comprobar(
                "Autorización de otro tipo no sirve",
                await esperar_error(
                    "FIRMANTE_NO_AUTORIZADO", solicitar("CERTIFICACION", oficio_director["autorizacion_id"])
                ),
            )
            await sesion.rollback()

            # --- Solicitud de certificación y "celular" ---
            solicitud = await solicitar("CERTIFICACION", director["autorizacion_id"])
            token = solicitud["token"]
            comprobar(
                "Token del QR de 256 bits (solo se guarda su hash)",
                len(token) >= 43
                and not await sesion.scalar(
                    __import__("sqlalchemy").text(
                        "SELECT 1 FROM esart_firma.solicitudes_firma WHERE token_qr_hash = :t"
                    ),
                    {"t": token},
                ),
            )
            resumen = await firma_movil.abrir_solicitud(sesion, token)
            await sesion.commit()
            comprobar(
                "El celular ve el documento y el firmante",
                resumen["estado"] == "ABIERTA"
                and resumen["firmante"] == "CR Juan Pérez Gómez"
                and "Carlos" in resumen["artillero"],
            )
            borrador, _ = await firma_movil.pdf_borrador(sesion, token, CARPETA_DOCUMENTOS)
            comprobar("Borrador PDF disponible para revisar", borrador.startswith(b"%PDF-"))

            comprobar(
                "Sin aceptar la declaración no firma",
                await esperar_error(
                    "CONSENTIMIENTO_REQUERIDO",
                    firma_movil.firmar(
                        sesion,
                        token=token,
                        rubrica_png=rubrica(),
                        codigo_totp="000000",
                        acepto=False,
                        directorio=CARPETA_DOCUMENTOS,
                        request=peticion,
                    ),
                ),
            )
            comprobar(
                "Rúbrica vacía rechazada",
                await esperar_error(
                    "RUBRICA_VACIA",
                    firma_movil.firmar(
                        sesion,
                        token=token,
                        rubrica_png=rubrica(vacia=True),
                        codigo_totp="000000",
                        acepto=True,
                        directorio=CARPETA_DOCUMENTOS,
                        request=peticion,
                    ),
                ),
            )
            codigo_malo = "000000" if pyotp.TOTP(datos_lab["secreto"]).now() != "000000" else "111111"
            comprobar(
                "Código TOTP inválido rechazado",
                await esperar_error(
                    "TOTP_INVALIDO",
                    firma_movil.firmar(
                        sesion,
                        token=token,
                        rubrica_png=rubrica(),
                        codigo_totp=codigo_malo,
                        acepto=True,
                        directorio=CARPETA_DOCUMENTOS,
                        request=peticion,
                    ),
                ),
            )
            await sesion.rollback()

            resultado, _ = await firma_movil.firmar(
                sesion,
                token=token,
                rubrica_png=rubrica(),
                codigo_totp=pyotp.TOTP(datos_lab["secreto"]).now(),
                acepto=True,
                directorio=CARPETA_DOCUMENTOS,
                request=peticion,
            )
            await sesion.commit()
            comprobar(
                "Firma aprobada con rúbrica + TOTP",
                resultado["estado"] == "APROBADA" and resultado["codigo_verificacion"].startswith("F-"),
            )
            comprobar(
                "Token de un solo uso (reutilizarlo falla)",
                await esperar_error(
                    "SOLICITUD_CERRADA",
                    firma_movil.firmar(
                        sesion,
                        token=token,
                        rubrica_png=rubrica(),
                        codigo_totp=pyotp.TOTP(datos_lab["secreto"]).now(),
                        acepto=True,
                        directorio=CARPETA_DOCUMENTOS,
                        request=peticion,
                    ),
                ),
            )
            await sesion.rollback()

            estado = await firma_movil.estado_solicitud(
                sesion, solicitud["solicitud_id"], datos_lab["generador"], ver_todas=False
            )
            comprobar(
                "El PC ve la solicitud aprobada y el documento firmado",
                estado["estado"] == "APROBADA" and estado["estado_documento"] == "FIRMADO",
            )
            comprobar(
                "Otro usuario no ve la solicitud",
                await esperar_error(
                    "SOLICITUD_NO_ENCONTRADA",
                    firma_movil.estado_solicitud(
                        sesion, solicitud["solicitud_id"], datos_lab["sin_totp"], ver_todas=False
                    ),
                ),
            )
    finally:
        await motor.dispose()

    # --- Verificación en la base (como dueño de las tablas nuevas) ---
    con = await lab.conectar(USUARIO_VERIFICACION)
    try:
        documento = solicitud["documento_id"]
        versiones = await con.fetch(
            "SELECT numero_version, sha256, ubicacion_privada FROM esart_firma.versiones_documento WHERE documento_id=$1 ORDER BY numero_version",
            documento,
        )
        comprobar(
            "Versión 1 (borrador) y versión 2 (firmada)", [v["numero_version"] for v in versiones] == [1, 2]
        )
        final = (CARPETA_DOCUMENTOS / versiones[1]["ubicacion_privada"]).read_bytes()
        import hashlib

        comprobar(
            "PDF final íntegro (sha256 registrado)",
            hashlib.sha256(final).hexdigest() == versiones[1]["sha256"].strip(),
        )
        texto = texto_pdf(final)
        comprobar(
            "PDF final con firmante, fecha y código",
            "CR Juan P" in texto and "Firmado electr" in texto and resultado["codigo_verificacion"] in texto,
        )
        consentimiento = await con.fetchval(
            "SELECT c.documento_sha256 FROM esart_firma.consentimientos_firma c JOIN esart_firma.solicitudes_firma s ON s.id=c.solicitud_id WHERE s.documento_id=$1",
            documento,
        )
        comprobar(
            "El consentimiento sella el hash del borrador revisado",
            consentimiento.strip() == versiones[0]["sha256"].strip(),
        )
        comprobar(
            "Desafío FIRMAR registrado y consumido",
            await con.fetchval(
                "SELECT count(*) FROM esart_firma.desafios_autenticacion WHERE proposito='FIRMAR' AND consumido_en IS NOT NULL"
            )
            == 1,
        )
        comprobar(
            "Firma RUBRICA_ELECTRONICA con hashes",
            await con.fetchval(
                "SELECT count(*) FROM esart_firma.firmas_certificado WHERE metodo='RUBRICA_ELECTRONICA' AND pdf_resultante_sha256=$1",
                versiones[1]["sha256"],
            )
            == 1,
        )
        clases = sorted(
            await con.fetch("SELECT clase FROM esart_firma.evidencias WHERE documento_id=$1", documento),
            key=lambda f: f["clase"],
        )
        comprobar(
            "Evidencias: PDF original, rúbrica y PDF firmado",
            [c["clase"] for c in clases] == ["PDF_FIRMADO", "PDF_ORIGINAL", "RUBRICA"],
        )
        eventos = await con.fetch("SELECT * FROM esart_firma.auditoria_eventos ORDER BY id")
        cadena = all(
            e["hash_anterior"] == (eventos[i - 1]["hash_evento"] if i else None)
            for i, e in enumerate(eventos)
        )
        for e in eventos:
            campos = {
                "evento_id": str(e["evento_id"]),
                "actor_id": e["actor_id"],
                "correlacion_id": str(e["correlacion_id"]),
                "accion": e["accion"],
                "recurso_tipo": e["recurso_tipo"],
                "recurso_id": e["recurso_id"],
                "resultado": e["resultado"],
                "detalle": json.loads(e["detalle_filtrado"]),
            }
            cadena = (
                cadena
                and hash_evento_firma(e["hash_anterior"].strip() if e["hash_anterior"] else None, campos)
                == e["hash_evento"].strip()
            )
        acciones = [e["accion"] for e in eventos]
        comprobar(
            "Auditoría encadenada: autorizaciones, solicitud y firma",
            cadena and "FIRMA_SOLICITADA" in acciones and "DOCUMENTO_FIRMADO" in acciones,
            f"{len(eventos)} eventos",
        )
        comprobar(
            "TOTP inválido auditado en seguridad",
            await con.fetchval("SELECT count(*) FROM seguridad.auditoria WHERE accion='TOTP_INVALIDO'") >= 1,
        )
        # Enlace vencido: se fuerza la expiración de otra solicitud.
        await con.execute(
            "UPDATE esart_firma.solicitudes_firma SET expira_en = creada_en + interval '1 second' WHERE estado = 'PENDIENTE'"
        )
    finally:
        await con.close()


async def vencida(lab: Laboratorio) -> None:
    """Una solicitud nueva que vence antes de abrirse queda EXPIRADA y no se puede firmar."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aplicacion.nucleo.errores import ErrorAplicacion
    from aplicacion.rutas.verificacion import armar_datos_documento
    from aplicacion.servicios import firma_movil

    motor = create_async_engine(lab.url("esart_aplicacion"), connect_args={"ssl": False})
    try:
        async with AsyncSession(motor, expire_on_commit=False) as sesion:
            from sqlalchemy import text

            generador = await sesion.scalar(
                text("SELECT id FROM esart_ref.usuarios WHERE usuario='generador'")
            )
            director = next(
                f
                for f in await firma_movil.listar_firmantes(sesion, "OFICIO_REMISORIO")
                if f["nombre"].startswith("CR")
            )
            fila, datos = await armar_datos_documento(sesion, "1024589632", generador, "generador")
            respuesta, _ = await firma_movil.solicitar_firma(
                sesion,
                datos=datos,
                tipo="OFICIO_REMISORIO",
                personal_id=fila.id,
                autorizacion_id=director["autorizacion_id"],
                usuario_id=generador,
                directorio=CARPETA_DOCUMENTOS,
                request=Peticion(),
            )
            await sesion.commit()
        con = await lab.conectar("esart_migrador")
        await con.execute(
            "UPDATE esart_firma.solicitudes_firma SET creada_en = now() - interval '20 minutes', expira_en = now() - interval '5 minutes' WHERE id=$1",
            respuesta["solicitud_id"],
        )
        await con.close()
        async with AsyncSession(motor, expire_on_commit=False) as sesion:
            resumen = await firma_movil.abrir_solicitud(sesion, respuesta["token"])
            await sesion.commit()
            try:
                await firma_movil.pdf_borrador(sesion, respuesta["token"], CARPETA_DOCUMENTOS)
                cerrado = False
            except ErrorAplicacion as error:
                cerrado = error.codigo == "SOLICITUD_CERRADA"
            comprobar("Enlace vencido: EXPIRADA y sin borrador", resumen["estado"] == "EXPIRADA" and cerrado)
    finally:
        await motor.dispose()


async def estado_firma(lab: Laboratorio) -> str:
    """Lo que respondería la API (como esart_aplicacion) antes de cualquier operación de firma."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aplicacion.nucleo.errores import ErrorAplicacion
    from aplicacion.servicios.firma_movil import verificar_estructura_firma

    motor = create_async_engine(lab.url("esart_aplicacion"), connect_args={"ssl": False})
    try:
        async with AsyncSession(motor) as sesion:
            await verificar_estructura_firma(sesion)
            return "OK"
    except ErrorAplicacion as error:
        return error.codigo
    finally:
        await motor.dispose()


async def principal(lab: Laboratorio) -> None:
    await crear_base(lab, "p0014_cursos_del_instructor")
    await instalar_heredado(lab)
    comprobar(
        "Sin p0018: mensaje claro FIRMA_NO_DISPONIBLE (no error interno)",
        await estado_firma(lab) == "FIRMA_NO_DISPONIBLE",
    )
    lab.alembic("upgrade", "p0018_firma_documental")
    comprobar(
        "Con p0018 sin p0019: también FIRMA_NO_DISPONIBLE", await estado_firma(lab) == "FIRMA_NO_DISPONIBLE"
    )
    lab.alembic("upgrade", "head")
    comprobar("Con p0019: la firma queda disponible", await estado_firma(lab) == "OK")
    con = await lab.conectar("esart_migrador")
    comprobar(
        "Copia migrada hasta p0019",
        await con.fetchval("SELECT version_num FROM esart.alembic_version") == "p0019_firma_movil",
    )
    await con.close()
    await flujo(lab)
    await vencida(lab)


def main() -> int:
    lab = Laboratorio()
    try:
        lab.iniciar()
        asyncio.run(principal(lab))
    finally:
        lab.detener()
        import shutil

        shutil.rmtree(CARPETA_DOCUMENTOS, ignore_errors=True)
    fallidas = [r for r in RESULTADOS if not r[1]]
    print(f"\n{len(RESULTADOS) - len(fallidas)}/{len(RESULTADOS)} comprobaciones correctas")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())
