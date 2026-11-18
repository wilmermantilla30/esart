"""
HU-21: FastAPI sirve el dashboard (Angular compilado) en la misma dirección que la API.

El Comandante solo abre el navegador en https://<servidor>/ :
- /api/...           -> la API (las rutas que no existen siguen respondiendo 404 en JSON).
- archivo existente  -> el archivo compilado (main-XXXX.js, estilos, fuentes, íconos...).
- cualquier otra ruta -> index.html, para que Angular resuelva /instructores, /dashboard, etc.
  (así recargar la página o abrir un enlace directo no da 404).

Caché:
- Los archivos con huella en el nombre (main-V3DA5O76.js) no cambian nunca: un año.
- index.html y los archivos sin huella se revalidan siempre (no-cache): tras un despliegue,
  los usuarios reciben la versión nueva al recargar.

Seguridad:
- El archivo pedido debe quedar DENTRO de la carpeta del front (sin "../").
- Una ruta con extensión que no existe (p. ej. /secreto.env) da 404, nunca index.html.
- Cabeceras: CSP estricta para el front (solo scripts propios, sin CDN), nosniff,
  sin incrustarse en otros sitios, y no-store en las respuestas de datos de la API.
"""

import logging
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as ExcepcionHttpStarlette

registrador = logging.getLogger(__name__)

PREFIJO_API = "/api"
CACHE_INMUTABLE = "public, max-age=31536000, immutable"
CACHE_REVALIDAR = "no-cache"
# Nombre con huella del build de Angular: main-V3DA5O76.js, chunk-PHleWKyu.js, styles-7PBOQQUO.css
PATRON_HUELLA = re.compile(r"-[A-Za-z0-9_]{8,}\.[a-z0-9]+$")

# CSP del dashboard: el build no tiene scripts en línea (inlineCritical desactivado). Los estilos
# en línea los necesitan los componentes de Angular; las imágenes data:/blob: son el QR del
# autenticador y las vistas previas de fotos; el worker del cargue por Excel es un archivo propio.
POLITICA_CONTENIDO = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
CABECERAS_COMUNES = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}
# La documentación interactiva (solo fuera de producción) carga Swagger desde un CDN: sin CSP.
RUTAS_DOCUMENTACION = ("/api/documentacion", "/api/openapi.json")


def registrar_cabeceras_seguridad(aplicacion: FastAPI, *, https: bool) -> None:
    """Cabeceras de seguridad en todas las respuestas y no-store en las de datos."""

    @aplicacion.middleware("http")
    async def cabeceras_seguridad(request: Request, call_next):
        respuesta = await call_next(request)
        ruta = request.url.path
        for nombre, valor in CABECERAS_COMUNES.items():
            respuesta.headers.setdefault(nombre, valor)
        if https:
            # El navegador recuerda usar siempre HTTPS con este servidor (solo con cookies seguras).
            respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if ruta.startswith(PREFIJO_API):
            # Datos personales: ni el navegador ni un intermediario guardan copias, salvo que la
            # ruta haya fijado su propia política (p. ej. la foto del instructor, privada).
            respuesta.headers.setdefault("Cache-Control", "no-store")
        elif not ruta.startswith(RUTAS_DOCUMENTACION):
            respuesta.headers.setdefault("Content-Security-Policy", POLITICA_CONTENIDO)
        return respuesta


def carpeta_front_valida(carpeta: Path | None) -> Path | None:
    """La carpeta del build si existe y tiene index.html; si no, None (se sirve solo la API)."""
    if carpeta is None:
        return None
    carpeta = carpeta.resolve()
    return carpeta if (carpeta / "index.html").is_file() else None


def registrar_front(aplicacion: FastAPI, carpeta: Path | None) -> bool:
    """
    Agrega la ruta comodín que sirve el front. Debe registrarse DESPUÉS de los routers de la
    API para no taparlos. Devuelve False (y no registra nada) si no hay front compilado.
    """
    raiz = carpeta_front_valida(carpeta)
    if raiz is None:
        registrador.info("Front no compilado o RUTA_FRONT inexistente: se sirve solo la API")
        return False
    indice = raiz / "index.html"

    @aplicacion.api_route("/{ruta:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def servir_front(ruta: str) -> FileResponse:
        # Una ruta de la API que no existe sigue siendo un 404 en JSON, nunca la página.
        if ruta == "api" or ruta.startswith("api/"):
            raise ExcepcionHttpStarlette(404)
        if ruta:
            archivo = (raiz / ruta).resolve()
            if archivo.is_relative_to(raiz) and archivo.is_file():
                cache = CACHE_INMUTABLE if PATRON_HUELLA.search(archivo.name) else CACHE_REVALIDAR
                return FileResponse(archivo, headers={"Cache-Control": cache})
            # Pidió un archivo (tiene extensión) que no existe: 404, no la página.
            if "." in Path(ruta).name:
                raise ExcepcionHttpStarlette(404)
        return FileResponse(indice, headers={"Cache-Control": CACHE_REVALIDAR})

    registrador.info("Dashboard servido desde %s", raiz)
    return True
