"""
Pruebas del panel de instructores (militares y civiles, foto y especialidades).

- Tratamiento de la foto: sin base de datos.
- Endpoints: con PostgreSQL (ESART_URL_BD_INTEGRACION); todo se revierte al final.
"""

import io
import uuid
from datetime import date, timedelta

import pytest
from PIL import Image
from sqlalchemy import select, text

from aplicacion.modelos import AuditoriaEvento
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.servicios.instructores import TAMANO_MAXIMO_FOTO_SUBIDA, preparar_foto
from pruebas.test_auditoria_y_malla import cabecera_csrf, entrar
from pruebas.test_login_hu05 import requiere_postgresql, sesion_bd  # noqa: F401
from pruebas.test_verificacion_habilitacion import crear_militar

pytestmark = pytest.mark.anyio

ETIQUETA_GPS_EXIF = 0x8825


def imagen(formato: str, modo: str = "RGB", tamano=(1200, 900), exif: bytes | None = None) -> bytes:
    salida = io.BytesIO()
    color = (32, 169, 211, 128) if modo == "RGBA" else (32, 169, 211)
    opciones = {"exif": exif} if exif else {}
    Image.new(modo, tamano, color).save(salida, format=formato, **opciones)
    return salida.getvalue()


# --- Foto (sin base de datos) ---------------------------------------------------------


@pytest.mark.parametrize(("formato", "modo"), [("JPEG", "RGB"), ("PNG", "RGBA"), ("WEBP", "RGB")])
def test_la_foto_se_guarda_como_jpeg_reducido(formato, modo):
    foto = preparar_foto(imagen(formato, modo))
    with Image.open(io.BytesIO(foto)) as guardada:
        assert guardada.format == "JPEG"
        assert max(guardada.size) == 800


def test_la_foto_pierde_los_metadatos_gps():
    exif = Image.Exif()
    exif[0x010F] = "Camara del celular"
    exif[ETIQUETA_GPS_EXIF] = {1: "N", 2: (4.0, 36.0, 0.0)}
    foto = preparar_foto(imagen("JPEG", exif=exif.tobytes()))
    with Image.open(io.BytesIO(foto)) as guardada:
        assert not guardada.getexif()


@pytest.mark.parametrize(
    "contenido",
    [
        b"",
        b"esto no es una imagen",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"\xff\xd8\xff\xe0 JPEG truncado",
        imagen("GIF", "P", (10, 10)),  # formato no admitido
    ],
)
def test_rechaza_archivos_que_no_son_fotos_admitidas(contenido):
    with pytest.raises(ErrorAplicacion) as error:
        preparar_foto(contenido)
    assert error.value.codigo == "FOTO_INVALIDA"


def test_rechaza_fotos_de_mas_de_5_mb():
    with pytest.raises(ErrorAplicacion):
        preparar_foto(b"\xff" * (TAMANO_MAXIMO_FOTO_SUBIDA + 1))


# --- Con PostgreSQL -------------------------------------------------------------------


async def ultimo_evento(sesion, accion: str) -> AuditoriaEvento:
    return await sesion.scalar(
        select(AuditoriaEvento).where(AuditoriaEvento.accion == accion).order_by(AuditoriaEvento.id.desc())
    )


def documento_civil() -> str:
    return f"7{uuid.uuid4().int % 10**9:09d}"


@requiere_postgresql
async def test_registrar_militar_y_civil_con_especialidades(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    cedula = await crear_militar(sesion_bd, "sacli", 61)
    csrf = cabecera_csrf(cliente_api)

    militar = await cliente_api.get(f"/api/instructores/militar/{cedula}")
    assert militar.status_code == 200 and militar.json()["ya_es_instructor"] is False

    registrado = await cliente_api.post(
        "/api/instructores",
        json={
            "tipo": "MILITAR",
            "documento": cedula,
            "fecha_ingreso_escuela": "2024-02-01",
            "especialidades": ["OA", "tp"],
        },
        headers=csrf,
    )
    assert registrado.status_code == 201, registrado.text
    datos = registrado.json()
    assert datos["nombre_completo"].startswith("SV ") and datos["tipo"] == "MILITAR"
    assert {e["codigo"] for e in datos["especialidades"]} == {"OA", "TP"}
    assert datos["tiene_foto"] is False and datos["nombre_usuario"] is None
    evento = await ultimo_evento(sesion_bd, "INSTRUCTOR_REGISTRADO")
    assert evento.detalle["instructor_id"] == datos["id"]

    repetido = await cliente_api.post(
        "/api/instructores",
        json={"tipo": "MILITAR", "documento": cedula, "fecha_ingreso_escuela": "2024-02-01"},
        headers=csrf,
    )
    assert repetido.status_code == 409 and repetido.json()["error"]["codigo"] == "INSTRUCTOR_EXISTENTE"

    # Un civil: con sus propios datos y su profesión.
    documento = documento_civil()
    civil = await cliente_api.post(
        "/api/instructores",
        json={
            "tipo": "CIVIL",
            "documento": documento,
            "nombres": "María Fernanda",
            "apellidos": "López Ruiz",
            "profesion": "Ingeniera de sistemas",
            "fecha_ingreso_escuela": "2025-06-15",
            "especialidades": ["CDT"],
        },
        headers=csrf,
    )
    assert civil.status_code == 201, civil.text
    assert civil.json()["nombre_completo"] == "María Fernanda López Ruiz" and civil.json()["grado"] is None

    # El documento de un militar no se puede registrar como civil.
    disfrazado = await cliente_api.post(
        "/api/instructores",
        json={
            "tipo": "CIVIL",
            "documento": cedula,
            "nombres": "Otro",
            "apellidos": "Nombre",
            "fecha_ingreso_escuela": "2025-01-01",
        },
        headers=csrf,
    )
    assert disfrazado.status_code == 409 and disfrazado.json()["error"]["codigo"] == "ES_MILITAR"

    # Filtros: por especialidad y por texto.
    por_cdt = (await cliente_api.get("/api/instructores", params={"especialidad": "CDT"})).json()
    assert civil.json()["id"] in {i["id"] for i in por_cdt} and datos["id"] not in {i["id"] for i in por_cdt}
    por_texto = (await cliente_api.get("/api/instructores", params={"texto": "fernanda"})).json()
    assert [i["id"] for i in por_texto] == [civil.json()["id"]]

    # El cargue por Excel ofrece también al civil como comandante del curso.
    curso = (await cliente_api.get("/api/importaciones/datos-curso")).json()
    assert civil.json()["id"] in {i["id"] for i in curso["instructores"]}


@requiere_postgresql
async def test_validaciones_al_registrar(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    csrf = cabecera_csrf(cliente_api)
    base = {"tipo": "CIVIL", "documento": documento_civil(), "nombres": "Ana", "apellidos": "Pérez"}

    especialidad_inexistente = await cliente_api.post(
        "/api/instructores",
        json={**base, "fecha_ingreso_escuela": "2025-01-01", "especialidades": ["INVENTADA"]},
        headers=csrf,
    )
    assert especialidad_inexistente.status_code == 422
    futura = await cliente_api.post(
        "/api/instructores", json={**base, "fecha_ingreso_escuela": "2999-01-01"}, headers=csrf
    )
    assert futura.status_code == 422
    sin_nombre = await cliente_api.post(
        "/api/instructores", json={**base, "nombres": "", "fecha_ingreso_escuela": "2025-01-01"}, headers=csrf
    )
    assert sin_nombre.status_code == 422
    no_existe = await cliente_api.get("/api/instructores/militar/1234567")
    assert no_existe.status_code == 404


@requiere_postgresql
async def test_editar_foto_y_desactivar(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    csrf = cabecera_csrf(cliente_api)
    creado = (
        await cliente_api.post(
            "/api/instructores",
            json={
                "tipo": "CIVIL",
                "documento": documento_civil(),
                "nombres": "Carlos",
                "apellidos": "Díaz",
                "fecha_ingreso_escuela": "2023-03-01",
                "especialidades": ["OA", "ACL"],
            },
            headers=csrf,
        )
    ).json()
    ruta = f"/api/instructores/{creado['id']}"

    editado = await cliente_api.put(
        ruta,
        json={
            "fecha_ingreso_escuela": "2023-03-01",
            "especialidades": ["ACL"],
            "nombres": "Carlos",
            "apellidos": "Díaz",
        },
        headers=csrf,
    )
    assert editado.status_code == 200
    assert [e["codigo"] for e in editado.json()["especialidades"]] == ["ACL"]

    con_foto = await cliente_api.put(
        f"{ruta}/foto", files={"archivo": ("foto.png", imagen("PNG", "RGBA"))}, headers=csrf
    )
    assert con_foto.status_code == 200 and con_foto.json()["tiene_foto"] is True
    assert con_foto.json()["version"] != creado["version"]
    foto = await cliente_api.get(f"{ruta}/foto")
    assert foto.status_code == 200 and foto.headers["content-type"] == "image/jpeg"
    assert foto.content.startswith(b"\xff\xd8\xff")
    falsa = await cliente_api.put(
        f"{ruta}/foto", files={"archivo": ("foto.jpg", b"no soy foto")}, headers=csrf
    )
    assert falsa.status_code == 422

    sin_foto = await cliente_api.delete(f"{ruta}/foto", headers=csrf)
    assert sin_foto.json()["tiene_foto"] is False
    assert (await cliente_api.get(f"{ruta}/foto")).status_code == 404

    desactivado = await cliente_api.post(f"{ruta}/desactivar", headers=csrf)
    assert desactivado.json()["activo"] is False
    activos = (await cliente_api.get("/api/instructores")).json()
    assert creado["id"] not in {i["id"] for i in activos}
    inactivos = (await cliente_api.get("/api/instructores", params={"estado": "INACTIVOS"})).json()
    assert creado["id"] in {i["id"] for i in inactivos}
    assert (await ultimo_evento(sesion_bd, "INSTRUCTOR_DESACTIVADO")).detalle["instructor_id"] == creado["id"]


@requiere_postgresql
async def test_el_usuario_consulta_pero_no_registra(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    assert (await cliente_api.get("/api/instructores")).status_code == 200
    assert (await cliente_api.get("/api/instructores/especialidades")).status_code == 200
    registrar = await cliente_api.post(
        "/api/instructores",
        json={
            "tipo": "CIVIL",
            "documento": documento_civil(),
            "nombres": "A",
            "apellidos": "B",
            "fecha_ingreso_escuela": "2025-01-01",
        },
        headers=cabecera_csrf(cliente_api),
    )
    assert registrar.status_code == 403


@requiere_postgresql
async def test_catalogo_inicial_de_especialidades(cliente_api, sesion_bd):  # noqa: F811
    await entrar(cliente_api, sesion_bd, roles=("USUARIO",))
    codigos = {e["codigo"] for e in (await cliente_api.get("/api/instructores/especialidades")).json()}
    assert {"OA", "ACL", "ACM", "RSOP", "CDT", "TP"} <= codigos


@requiere_postgresql
async def test_cursos_donde_es_comandante_y_donde_participa(cliente_api, sesion_bd):  # noqa: F811
    administrador = await entrar(cliente_api, sesion_bd, roles=("ADMINISTRADOR",))
    csrf = cabecera_csrf(cliente_api)
    instructor = (
        await cliente_api.post(
            "/api/instructores",
            json={
                "tipo": "CIVIL",
                "documento": documento_civil(),
                "nombres": "Jorge",
                "apellidos": "Ramírez",
                "fecha_ingreso_escuela": "2022-01-10",
            },
            headers=csrf,
        )
    ).json()
    sin_cursos = (await cliente_api.get(f"/api/instructores/{instructor['id']}/cursos")).json()
    assert sin_cursos == {"comandante": [], "participa": []}

    # Un curso donde es comandante (con un alumno) y otro donde participa como docente.
    alumno = await crear_militar(sesion_bd, "sacli", 71)
    sufijo = uuid.uuid4().hex[:6]
    cursos = {}
    otro_comandante = (
        await cliente_api.post(
            "/api/instructores",
            json={
                "tipo": "CIVIL",
                "documento": documento_civil(),
                "nombres": "Otro",
                "apellidos": "Comandante",
                "fecha_ingreso_escuela": "2020-01-10",
            },
            headers=csrf,
        )
    ).json()
    for clave, fecha in (("comandante", date(2026, 2, 1)), ("participa", date(2025, 8, 1))):
        cursos[clave] = await sesion_bd.scalar(
            text("""
                INSERT INTO esart.cursos
                  (tipo_curso_id, comandante_id, codigo, nombre, fecha_inicio, fecha_fin, estado,
                   creado_por_id)
                SELECT tc.id, :comandante, :codigo, :nombre, :inicio, :fin, 'EN_CURSO', :creador
                FROM esart.tipos_curso tc WHERE tc.codigo = 'SACLI'
                RETURNING id
            """),
            {
                # En el segundo curso el comandante es otro: el mismo instructor solo participa.
                "comandante": instructor["id"] if clave == "comandante" else otro_comandante["id"],
                "codigo": f"PRUEBA-{clave}-{sufijo}",
                "nombre": f"Curso de prueba {clave}",
                "inicio": fecha,
                "fin": fecha + timedelta(days=70),
                "creador": administrador.id,
            },
        )
    await sesion_bd.execute(
        text("""
            INSERT INTO esart.hoja_vida_artillero (artillero_id, curso_id)
            SELECT id, :curso FROM esart.personal_militar WHERE documento_identidad = :cedula
        """),
        {"curso": cursos["comandante"], "cedula": alumno},
    )
    await sesion_bd.execute(
        text(
            "INSERT INTO esart.cursos_instructores (curso_id, instructor_id, rol_en_curso) "
            "VALUES (:c, :i, 'DOCENTE')"
        ),
        {"c": cursos["participa"], "i": instructor["id"]},
    )

    detalle = (await cliente_api.get(f"/api/instructores/{instructor['id']}/cursos")).json()
    assert [c["id"] for c in detalle["comandante"]] == [cursos["comandante"]]
    assert detalle["comandante"][0]["tipo_curso"] == "SACLI" and detalle["comandante"][0]["alumnos"] == 1
    assert [(c["id"], c["rol_en_curso"]) for c in detalle["participa"]] == [(cursos["participa"], "DOCENTE")]
    assert (await cliente_api.get("/api/instructores/999999999/cursos")).status_code == 404
