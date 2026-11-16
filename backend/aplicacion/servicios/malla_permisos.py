"""
Malla de permisos editable (pantalla "Malla de permisos").

Reglas acordadas el 2026-11-16:
- El rol ADMINISTRADOR es FIJO: tiene todos los permisos y no se edita.
- Los usuarios con rol ADMINISTRADOR no admiten excepciones (también tienen todo).
- Por usuario, cada módulo está en uno de tres modos:
    HEREDAR  -> sin fila en usuario_permisos: vale lo que dé su rol;
    CONCEDER -> fila con las operaciones marcadas (reemplaza a su rol en ese módulo);
    QUITAR   -> fila sin ninguna operación (niega el módulo aunque su rol lo dé).
- Nadie se quita a sí mismo el acceso a la malla, y siempre debe quedar al menos un usuario
  activo que pueda editarla (para no dejar el sistema sin administración).
- Sin 'acceder' no vale ninguna otra operación (misma regla que el CHECK de la base).
- Todo cambio queda en la auditoría con el antes y el después.
"""

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aplicacion.esquemas.administracion import (
    CambioPermisoUsuario,
    ComponenteMalla,
    FilaPermisoRol,
    FilaPermisoUsuario,
    Operaciones,
    PermisoDeComponente,
    RespuestaPermisosRol,
    RespuestaPermisosUsuario,
    ResumenRol,
    UsuarioMalla,
)
from aplicacion.nucleo.errores import ErrorAplicacion
from aplicacion.seguridad.permisos import obtener_permisos_efectivos
from aplicacion.servicios import auditoria
from aplicacion.servicios.autenticacion import (
    CODIGO_ROL_ADMINISTRADOR,
    UsuarioAutenticado,
    obtener_codigo_rol,
    obtener_nombre_completo,
)

COMPONENTE_MALLA = "PERMISOS"
OPERACIONES = ("crear", "leer", "actualizar", "eliminar")

CONSULTA_COMPONENTES = text("""
    SELECT c.id, c.codigo, c.nombre, c.ruta_angular, padre.codigo AS codigo_padre
    FROM esart.componentes c
    LEFT JOIN esart.componentes padre ON padre.id = c.componente_padre_id
    WHERE c.activo
    ORDER BY c.orden, c.codigo
""")


def _operaciones_de_fila(fila) -> Operaciones:
    """Operaciones de una fila de rol_permisos / usuario_permisos (o todo en falso si no hay fila)."""
    if fila is None:
        return Operaciones()
    acceder = bool(fila.puede_acceder)
    return Operaciones(
        acceder=acceder,
        crear=acceder and bool(fila.puede_crear),
        leer=acceder and bool(fila.puede_leer),
        actualizar=acceder and bool(fila.puede_actualizar),
        eliminar=acceder and bool(fila.puede_eliminar),
    )


def _normalizar(operaciones: Operaciones) -> Operaciones:
    """Aplica la regla de coherencia: sin acceder, nada."""
    if not operaciones.acceder:
        return Operaciones()
    return operaciones


async def _componentes(sesion: AsyncSession) -> list:
    return (await sesion.execute(CONSULTA_COMPONENTES)).all()


def _componente_malla(fila) -> dict:
    return ComponenteMalla(
        codigo=fila.codigo,
        nombre=fila.nombre,
        ruta=fila.ruta_angular,
        codigo_padre=fila.codigo_padre,
        especial=fila.ruta_angular is None,
    ).model_dump()


# --- Roles -------------------------------------------------------------------------------


async def listar_roles(sesion: AsyncSession) -> list[ResumenRol]:
    filas = (
        await sesion.execute(text("SELECT codigo, nombre FROM esart.roles WHERE activo ORDER BY codigo"))
    ).all()
    return [
        ResumenRol(codigo=f.codigo, nombre=f.nombre, editable=f.codigo != CODIGO_ROL_ADMINISTRADOR)
        for f in filas
    ]


async def _rol_por_codigo(sesion: AsyncSession, codigo_rol: str):
    rol = (
        await sesion.execute(
            text("SELECT id, codigo, nombre FROM esart.roles WHERE codigo = :codigo"), {"codigo": codigo_rol}
        )
    ).first()
    if rol is None:
        raise ErrorAplicacion(404, "RECURSO_NO_ENCONTRADO", "No existe ese rol.")
    return rol


async def obtener_permisos_rol(sesion: AsyncSession, codigo_rol: str) -> RespuestaPermisosRol:
    rol = await _rol_por_codigo(sesion, codigo_rol)
    permisos = {
        f.componente_id: f
        for f in (
            await sesion.execute(
                text("SELECT * FROM esart.rol_permisos WHERE rol_id = :rol"), {"rol": rol.id}
            )
        ).all()
    }
    filas = [
        FilaPermisoRol(**_componente_malla(c), permisos=_operaciones_de_fila(permisos.get(c.id)))
        for c in await _componentes(sesion)
    ]
    return RespuestaPermisosRol(
        rol=rol.codigo, nombre=rol.nombre, editable=rol.codigo != CODIGO_ROL_ADMINISTRADOR, filas=filas
    )


async def guardar_permisos_rol(
    sesion: AsyncSession,
    codigo_rol: str,
    cambios: list[PermisoDeComponente],
    actor: UsuarioAutenticado,
    request: Request,
) -> RespuestaPermisosRol:
    """Reemplaza los permisos del rol en los componentes indicados."""
    if codigo_rol == CODIGO_ROL_ADMINISTRADOR:
        raise ErrorAplicacion(
            409, "ROL_NO_EDITABLE", "El rol ADMINISTRADOR es fijo: siempre tiene todos los permisos."
        )
    rol = await _rol_por_codigo(sesion, codigo_rol)
    componentes = {c.codigo: c for c in await _componentes(sesion)}
    antes = {f.codigo: f.permisos for f in (await obtener_permisos_rol(sesion, codigo_rol)).filas}

    diferencias = {}
    for cambio in cambios:
        componente = componentes.get(cambio.componente)
        if componente is None:
            raise ErrorAplicacion(
                422, "DATOS_INVALIDOS", f"El módulo {cambio.componente} no existe o está inactivo."
            )
        nuevo = _normalizar(Operaciones(**cambio.model_dump(exclude={"componente"})))
        if nuevo == antes[cambio.componente]:
            continue
        diferencias[cambio.componente] = {
            "antes": antes[cambio.componente].model_dump(),
            "despues": nuevo.model_dump(),
        }
        if nuevo.acceder:
            await sesion.execute(
                text("""
                    INSERT INTO esart.rol_permisos
                      (rol_id, componente_id, puede_acceder, puede_crear, puede_leer, puede_actualizar,
                       puede_eliminar, actualizado_en)
                    VALUES (:rol, :componente, true, :crear, :leer, :actualizar, :eliminar, now())
                    ON CONFLICT (rol_id, componente_id) DO UPDATE SET
                      puede_acceder = true, puede_crear = EXCLUDED.puede_crear,
                      puede_leer = EXCLUDED.puede_leer,
                      puede_actualizar = EXCLUDED.puede_actualizar, puede_eliminar = EXCLUDED.puede_eliminar,
                      actualizado_en = now()
                """),
                {"rol": rol.id, "componente": componente.id, **nuevo.model_dump(exclude={"acceder"})},
            )
        else:
            # Para un rol, no tener fila ya significa "sin permiso".
            await sesion.execute(
                text("DELETE FROM esart.rol_permisos WHERE rol_id = :rol AND componente_id = :componente"),
                {"rol": rol.id, "componente": componente.id},
            )

    if diferencias:
        await _exigir_administrador_de_malla(sesion)
        await auditoria.registrar_evento(
            sesion,
            auditoria.PERMISOS_ROL_MODIFICADOS,
            request,
            usuario_id=actor.id,
            nombre_usuario=actor.nombre_usuario,
            resultado="EXITOSO",
            detalle={"rol": codigo_rol, "cambios": diferencias},
        )
    return await obtener_permisos_rol(sesion, codigo_rol)


# --- Usuarios ----------------------------------------------------------------------------


async def listar_usuarios(sesion: AsyncSession, texto: str | None) -> list[UsuarioMalla]:
    filas = (
        await sesion.execute(
            text("""
                SELECT u.id, u.usuario, u.documento_identidad, u.activo
                FROM esart_ref.usuarios u
                WHERE u.usuario IS NOT NULL AND (CAST(:texto AS text) IS NULL OR u.usuario ILIKE :patron)
                ORDER BY u.usuario
                LIMIT 200
            """),
            {"texto": texto or None, "patron": f"%{(texto or '').strip()}%"},
        )
    ).all()
    return [
        UsuarioMalla(
            id=f.id,
            usuario=f.usuario,
            nombre_completo=await obtener_nombre_completo(sesion, f.documento_identidad, f.usuario),
            rol=await obtener_codigo_rol(sesion, f.id),
            activo=f.activo,
        )
        for f in filas
    ]


async def _usuario_por_id(sesion: AsyncSession, usuario_id: int) -> UsuarioMalla:
    fila = (
        await sesion.execute(
            text("SELECT id, usuario, documento_identidad, activo FROM esart_ref.usuarios WHERE id = :id"),
            {"id": usuario_id},
        )
    ).first()
    if fila is None or fila.usuario is None:
        raise ErrorAplicacion(404, "RECURSO_NO_ENCONTRADO", "No existe ese usuario.")
    return UsuarioMalla(
        id=fila.id,
        usuario=fila.usuario,
        nombre_completo=await obtener_nombre_completo(sesion, fila.documento_identidad, fila.usuario),
        rol=await obtener_codigo_rol(sesion, fila.id),
        activo=fila.activo,
    )


async def obtener_permisos_usuario(sesion: AsyncSession, usuario_id: int) -> RespuestaPermisosUsuario:
    usuario = await _usuario_por_id(sesion, usuario_id)
    # Permisos por rol: la mejor concesión entre sus roles activos (misma regla que el backend).
    por_rol = {
        f.componente_id: f
        for f in (
            await sesion.execute(
                text("""
                    SELECT rp.componente_id,
                           bool_or(rp.puede_acceder) AS puede_acceder,
                           bool_or(rp.puede_acceder AND rp.puede_crear) AS puede_crear,
                           bool_or(rp.puede_acceder AND rp.puede_leer) AS puede_leer,
                           bool_or(rp.puede_acceder AND rp.puede_actualizar) AS puede_actualizar,
                           bool_or(rp.puede_acceder AND rp.puede_eliminar) AS puede_eliminar
                    FROM esart.rol_permisos rp
                    JOIN esart.usuario_roles ur ON ur.rol_id = rp.rol_id
                    JOIN esart.roles r ON r.id = ur.rol_id AND r.activo
                    WHERE ur.usuario_id = :usuario
                    GROUP BY rp.componente_id
                """),
                {"usuario": usuario_id},
            )
        ).all()
    }
    excepciones = {
        f.componente_id: f
        for f in (
            await sesion.execute(
                text("SELECT * FROM esart.usuario_permisos WHERE usuario_id = :usuario"),
                {"usuario": usuario_id},
            )
        ).all()
    }
    efectivos = {p.codigo: p for p in await obtener_permisos_efectivos(sesion, usuario_id)}

    filas = []
    for componente in await _componentes(sesion):
        excepcion = excepciones.get(componente.id)
        if excepcion is None:
            modo = "HEREDAR"
        elif excepcion.puede_acceder:
            modo = "CONCEDER"
        else:
            modo = "QUITAR"
        efectivo = efectivos.get(componente.codigo)
        filas.append(
            FilaPermisoUsuario(
                **_componente_malla(componente),
                rol=_operaciones_de_fila(por_rol.get(componente.id)),
                modo=modo,
                excepcion=_operaciones_de_fila(excepcion) if excepcion is not None else None,
                efectivo=Operaciones(
                    acceder=efectivo.puede_acceder,
                    crear=efectivo.puede_crear,
                    leer=efectivo.puede_leer,
                    actualizar=efectivo.puede_actualizar,
                    eliminar=efectivo.puede_eliminar,
                )
                if efectivo
                else Operaciones(),
            )
        )
    return RespuestaPermisosUsuario(
        usuario=usuario, editable=usuario.rol != CODIGO_ROL_ADMINISTRADOR, filas=filas
    )


async def guardar_permisos_usuario(
    sesion: AsyncSession,
    usuario_id: int,
    cambios: list[CambioPermisoUsuario],
    actor: UsuarioAutenticado,
    request: Request,
) -> RespuestaPermisosUsuario:
    """Aplica excepciones por usuario (HEREDAR / CONCEDER / QUITAR) en los módulos indicados."""
    actual = await obtener_permisos_usuario(sesion, usuario_id)
    if not actual.editable:
        raise ErrorAplicacion(
            409,
            "USUARIO_NO_EDITABLE",
            "Los usuarios con rol ADMINISTRADOR tienen todos los permisos y no admiten excepciones.",
        )
    componentes = {c.codigo: c for c in await _componentes(sesion)}
    filas_actuales = {f.codigo: f for f in actual.filas}

    diferencias = {}
    for cambio in cambios:
        componente = componentes.get(cambio.componente)
        if componente is None:
            raise ErrorAplicacion(
                422, "DATOS_INVALIDOS", f"El módulo {cambio.componente} no existe o está inactivo."
            )
        if usuario_id == actor.id and cambio.componente == COMPONENTE_MALLA and cambio.modo != "HEREDAR":
            raise ErrorAplicacion(
                409, "AUTOBLOQUEO", "No puede cambiar sus propios permisos sobre la malla de permisos."
            )
        anterior = filas_actuales[cambio.componente]
        operaciones = {op: getattr(cambio, op) for op in OPERACIONES}
        if cambio.modo == "CONCEDER" and not any(operaciones.values()):
            raise ErrorAplicacion(
                422, "DATOS_INVALIDOS", f"Para conceder {cambio.componente} marque al menos una operación."
            )
        if cambio.modo == anterior.modo and (
            cambio.modo != "CONCEDER" or anterior.excepcion == Operaciones(acceder=True, **operaciones)
        ):
            continue
        diferencias[cambio.componente] = {
            "antes": {
                "modo": anterior.modo,
                **(anterior.excepcion.model_dump() if anterior.excepcion else {}),
            },
            "despues": {"modo": cambio.modo, **(operaciones if cambio.modo == "CONCEDER" else {})},
        }
        if cambio.modo == "HEREDAR":
            await sesion.execute(
                text(
                    "DELETE FROM esart.usuario_permisos"
                    " WHERE usuario_id = :usuario AND componente_id = :componente"
                ),
                {"usuario": usuario_id, "componente": componente.id},
            )
            continue
        conceder = cambio.modo == "CONCEDER"
        await sesion.execute(
            text("""
                INSERT INTO esart.usuario_permisos
                  (usuario_id, componente_id, puede_acceder, puede_crear, puede_leer, puede_actualizar,
                   puede_eliminar, actualizado_por_id, actualizado_en)
                VALUES (:usuario, :componente, :acceder, :crear, :leer, :actualizar, :eliminar, :actor, now())
                ON CONFLICT (usuario_id, componente_id) DO UPDATE SET
                  puede_acceder = EXCLUDED.puede_acceder, puede_crear = EXCLUDED.puede_crear,
                  puede_leer = EXCLUDED.puede_leer, puede_actualizar = EXCLUDED.puede_actualizar,
                  puede_eliminar = EXCLUDED.puede_eliminar, actualizado_por_id = EXCLUDED.actualizado_por_id,
                  actualizado_en = now()
            """),
            {
                "usuario": usuario_id,
                "componente": componente.id,
                "acceder": conceder,
                **{op: conceder and valor for op, valor in operaciones.items()},
                "actor": actor.id,
            },
        )

    if diferencias:
        await _exigir_administrador_de_malla(sesion)
        await auditoria.registrar_evento(
            sesion,
            auditoria.PERMISOS_USUARIO_MODIFICADOS,
            request,
            usuario_id=actor.id,
            nombre_usuario=actor.nombre_usuario,
            resultado="EXITOSO",
            detalle={"usuario_modificado": actual.usuario.usuario, "cambios": diferencias},
        )
    return await obtener_permisos_usuario(sesion, usuario_id)


async def _exigir_administrador_de_malla(sesion: AsyncSession) -> None:
    """
    Antes de confirmar, comprueba que quede al menos un usuario activo que pueda editar la malla.
    Si no, deshace los cambios: el sistema nunca se queda sin quien administre los permisos.
    """
    usuarios_activos = list(
        (
            await sesion.execute(
                text("SELECT id FROM esart_ref.usuarios WHERE activo AND usuario IS NOT NULL")
            )
        ).scalars()
    )
    for usuario_id in usuarios_activos:
        permisos = {p.codigo: p for p in await obtener_permisos_efectivos(sesion, usuario_id)}
        malla = permisos.get(COMPONENTE_MALLA)
        if malla and malla.puede_acceder and malla.puede_actualizar:
            return
    await sesion.rollback()
    raise ErrorAplicacion(
        409,
        "SIN_ADMINISTRADOR_DE_MALLA",
        "El cambio dejaría el sistema sin nadie que pueda administrar los permisos.",
    )
