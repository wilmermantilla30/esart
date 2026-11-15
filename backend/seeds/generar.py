"""Regenera SQL desde literales heredados, sin importar ni ejecutar el cargador Vulcano."""

import ast
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ORIGEN = RAIZ.parent / "aplicacion/base_datos/initial_data.py"


def catalogos():
    arbol = ast.parse(ORIGEN.read_text(encoding="utf-8"))
    nombres = {
        "PERMISOS",
        "DIVISIONES",
        "BRIGADAS",
        "BATALLONES_ARTILLERIA",
        "ESTADOS_OPERACIONALES",
        "ESTADOS_LOGISTICOS",
        "TIPOS_UNIDAD",
    }
    return {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in arbol.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in nombres
    }


def literal(valor):
    return "'" + valor.replace("'", "''") + "'"


GUARDIA = """-- HU-04: solo prueba aislada; sin UPDATE, DELETE, DDL ni usuarios.
BEGIN;
SET LOCAL search_path = public, pg_catalog;
DO $$ BEGIN
 IF current_database() <> 'esart_hu03_pruebas' THEN
   RAISE EXCEPTION 'Destino no autorizado: solo esart_hu03_pruebas';
 END IF;
 IF (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) THEN
   RAISE EXCEPTION 'No se permite superusuario';
 END IF;
 IF (SELECT version_num FROM public.alembic_version) IS DISTINCT FROM '0001' THEN
   RAISE EXCEPTION 'Se requiere HU-03 revision 0001';
 END IF;
END $$;
"""


def generar():
    datos = catalogos()
    # Fuente SQL: esart_seguridad_roles_permisos.sql, INSERT INTO esart.roles.
    roles = [
        {"codigo": "ADMINISTRADOR", "nombre": "Administrador"},
        {"codigo": "USUARIO", "nombre": "Usuario"},
    ]
    permisos = [{k: p[k] for k in ("codigo", "descripcion")} for p in datos["PERMISOS"]]
    unidades = [
        {"codigo": u["codigo"], "nombre": u["nombre"], "padre": u.get("padre")}
        for grupo in ("DIVISIONES", "BRIGADAS", "BATALLONES_ARTILLERIA")
        for u in datos[grupo]
    ]
    for archivo, tabla, filas, campo in (
        ("01_roles.sql", "roles", roles, "nombre"),
        ("02_permisos.sql", "permisos", permisos, "descripcion"),
        ("03_unidades_militares.sql", "unidades_militares", unidades, "nombre"),
    ):
        jerarquia = tabla == "unidades_militares"
        bloque = GUARDIA + f"LOCK TABLE public.{tabla} IN SHARE ROW EXCLUSIVE MODE;\n"
        bloque += (
            "DO $seed$\nDECLARE r jsonb; nuevo uuid; padre uuid; "
            "insertados int := 0; omitidos int := 0;\nBEGIN\n"
        )
        filas_sql = literal(json.dumps(filas, ensure_ascii=False))
        # Literales escapados y nombres de tabla definidos arriba, sin entrada del usuario.
        bloque += (  # noqa: S608
            f" FOR r IN SELECT value FROM jsonb_array_elements({filas_sql}::jsonb) LOOP\n"  # noqa: S608
        )
        if jerarquia:
            bloque += """  padre := NULL;
  IF r->>'padre' IS NOT NULL THEN
   SELECT id INTO padre FROM public.unidades_militares WHERE codigo=r->>'padre';
   IF padre IS NULL THEN RAISE EXCEPTION 'Falta padre % de %', r->>'padre', r->>'codigo'; END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM public.unidades_militares WHERE codigo=r->>'codigo'
             AND unidad_superior_id IS DISTINCT FROM padre) THEN
   RAISE EXCEPTION 'Jerarquia existente incompatible: %', r->>'codigo';
  END IF;
"""
        columnas = f"codigo,{campo}" + (",unidad_superior_id" if jerarquia else "")
        valores = f"r->>'codigo',r->>'{campo}'" + (",padre" if jerarquia else "")
        bloque += f"  INSERT INTO public.{tabla} ({columnas}) VALUES ({valores})\n"  # noqa: S608
        bloque += "  ON CONFLICT (codigo) DO NOTHING RETURNING id INTO nuevo;\n"
        bloque += (
            "  IF nuevo IS NULL THEN omitidos := omitidos + 1; "
            "ELSE insertados := insertados + 1; END IF;\n END LOOP;\n"
        )
        bloque += (
            f" RAISE NOTICE '%', json_build_object('tabla','{tabla}',"
            "'insertados',insertados,'omitidos',omitidos,'errores',0);\n"
        )
        bloque += "END $seed$;\nCOMMIT;\n"
        (RAIZ / archivo).write_text(bloque, encoding="utf-8")
    manifiesto = {
        "roles": roles,
        "permisos": permisos,
        "unidades_militares": unidades,
        "sin_tabla": {k: datos[k] for k in ("ESTADOS_OPERACIONALES", "ESTADOS_LOGISTICOS", "TIPOS_UNIDAD")},
    }
    (RAIZ / "catalogos.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    generar()
