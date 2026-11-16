"""Consultas institucionales sobre las tablas reales, sin rutas de escritura."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.base_datos.sesion import obtener_sesion_base_datos
from aplicacion.modelos import TipoCargo, TipoCurso, TipoUnidad, UnidadMilitar
from aplicacion.seguridad.sesion_http import obtener_id_usuario_actual

enrutador = APIRouter(prefix="/catalogos", tags=["Catálogos"])
Sesion = Annotated[AsyncSession, Depends(obtener_sesion_base_datos)]


# Solo identidad validada por el servidor (cookie de sesión firmada + sesión vigente).
enrutador.dependencies.append(Depends(obtener_id_usuario_actual))


async def filas_unidades(sesion: AsyncSession) -> list[dict]:
    superiores = UnidadMilitar.__table__.alias("superiores")
    consulta = (
        select(
            UnidadMilitar.__table__,
            TipoUnidad.codigo.label("tipo_codigo"),
            TipoUnidad.nombre.label("tipo_nombre"),
            superiores.c.codigo.label("padre_codigo"),
        )
        .outerjoin(TipoUnidad, TipoUnidad.id == UnidadMilitar.tipo_unidad_id)
        .outerjoin(superiores, superiores.c.id == UnidadMilitar.unidad_padre_id)
        .order_by(UnidadMilitar.codigo)
    )
    filas = (await sesion.execute(consulta)).mappings()
    salida = []
    for fila in filas:
        dato = dict(fila)
        for campo in ("id", "tipo_unidad_id", "unidad_padre_id"):
            dato[campo] = str(dato[campo]) if dato[campo] is not None else None
        dato["clasificacion_pendiente"] = dato["tipo_unidad_id"] is None
        salida.append(dato)
    return salida


@enrutador.get("/unidades")
async def unidades(
    sesion: Sesion,
    buscar: str = Query("", max_length=200),
    tipo_id: int | None = None,
    activo: bool | None = None,
    padre_id: int | None = None,
    pendientes: bool | None = None,
):
    filas = await filas_unidades(sesion)
    return [
        u
        for u in filas
        if (not buscar or buscar.casefold() in (u["codigo"] + " " + u["nombre"]).casefold())
        and (tipo_id is None or u["tipo_unidad_id"] == str(tipo_id))
        and (activo is None or u["activo"] == activo)
        and (padre_id is None or u["unidad_padre_id"] == str(padre_id))
        and (pendientes is None or u["clasificacion_pendiente"] == pendientes)
    ]


@enrutador.get("/unidades/jerarquia")
async def jerarquia(sesion: Sesion):
    filas = await filas_unidades(sesion)
    nodos = {u["id"]: {**u, "subordinadas": []} for u in filas}
    raices = []
    for u in nodos.values():
        vistos = {u["id"]}
        padre = u["unidad_padre_id"]
        while padre is not None:
            if padre in vistos or padre not in nodos:
                raise HTTPException(409, "La jerarquía contiene ciclos o referencias inexistentes")
            vistos.add(padre)
            padre = nodos[padre]["unidad_padre_id"]
        if u["unidad_padre_id"] is None:
            raices.append(u)
        else:
            nodos[u["unidad_padre_id"]]["subordinadas"].append(u)
    return raices


@enrutador.get("/unidades/{unidad_id}")
async def unidad(unidad_id: int, sesion: Sesion):
    for u in await filas_unidades(sesion):
        if u["id"] == str(unidad_id):
            return u
    raise HTTPException(404, "Unidad inexistente")


@enrutador.get("/unidades/{unidad_id}/subordinadas")
async def subordinadas(unidad_id: int, sesion: Sesion):
    filas = await filas_unidades(sesion)
    if not any(u["id"] == str(unidad_id) for u in filas):
        raise HTTPException(404, "Unidad inexistente")
    return [u for u in filas if u["unidad_padre_id"] == str(unidad_id)]


async def catalogo(sesion: AsyncSession, modelo):
    return [
        {**dict(r), "id": str(r["id"])}
        for r in (await sesion.execute(select(modelo.__table__).order_by(modelo.id))).mappings()
    ]


@enrutador.get("/tipos-unidad")
async def tipos(sesion: Sesion):
    return await catalogo(sesion, TipoUnidad)


@enrutador.get("/cargos")
async def cargos(sesion: Sesion):
    return await catalogo(sesion, TipoCargo)


@enrutador.get("/cursos")
async def cursos(sesion: Sesion):
    return await catalogo(sesion, TipoCurso)
