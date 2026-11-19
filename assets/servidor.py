"""
Lanzador grafico: servidor estatico para Angular (carpeta dist) + servidor Uvicorn.

- Angular: seleccionas la carpeta dist, el puerto, y se sirve con soporte de rutas SPA
  (cualquier ruta desconocida devuelve index.html).
- Uvicorn: seleccionas la carpeta del proyecto API, el modulo (ej. main:app),
  el Python (se detecta .venv / venv automaticamente) y el puerto.
- Muestra las URLs (localhost y red local) como enlaces clicables.
- La configuracion se guarda en servidor_config.json junto al script.

Requisitos: Python 3.8+ (tkinter incluido). Uvicorn debe estar instalado en el
Python que elijas para la API.
"""

import ast
import json
import mimetypes
import os
import queue
import socket
import subprocess
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "servidor_config.json"
IS_WIN = os.name == "nt"

# En Windows el registro a veces trae MIME incorrectos para .js (rompe Angular).
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")


# ----------------------------------------------------------------------------- utilidades
def ip_local() -> str:
    """IP de la maquina en la red local (para abrir desde otro equipo/celular)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def puerto_libre(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def urls_para(host: str, port: int) -> list[str]:
    if host in ("0.0.0.0", ""):
        return [f"http://localhost:{port}", f"http://{ip_local()}:{port}"]
    if host in ("127.0.0.1", "localhost"):
        return [f"http://localhost:{port}"]
    return [f"http://{host}:{port}"]


def resolver_dist(carpeta: str) -> Path | None:
    """Encuentra la carpeta que contiene index.html.

    Angular 17+ genera dist/<app>/browser/index.html, asi que se busca hacia abajo.
    """
    p = Path(carpeta)
    if not p.is_dir():
        return None
    candidatos = [p, p / "browser"]
    for sub in sorted(x for x in p.iterdir() if x.is_dir()):
        candidatos += [sub, sub / "browser"]
    for c in candidatos:
        if (c / "index.html").is_file():
            return c
    return None


def detectar_python(carpeta_api: str) -> str:
    p = Path(carpeta_api)
    rel = ("Scripts/python.exe",) if IS_WIN else ("bin/python",)
    for venv in (".venv", "venv", "env", ".env"):
        for r in rel:
            exe = p / venv / r
            if exe.is_file():
                return str(exe)
    return sys.executable


CLASES_ASGI = {"FastAPI", "Starlette", "Litestar", "Quart"}
DIRS_IGNORADOS = {".venv", "venv", "env", ".env", "node_modules", "__pycache__", ".git",
                  "pruebas", "tests", "test", "migraciones", "migrations", "alembic",
                  "site-packages", "build", "dist"}


def _nombre_llamada(nodo) -> str | None:
    if isinstance(nodo, ast.Call):
        f = nodo.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
    return None


def detectar_apps(carpeta_api: str, max_archivos: int = 400) -> list[str]:
    """Busca objetos ASGI (FastAPI, Starlette...) a nivel de modulo.

    Devuelve candidatos tipo "paquete.modulo:variable" relativos a la carpeta API,
    ordenados con los mas probables primero (main.py, principal.py, app.py...).
    Detecta tanto `app = FastAPI()` como `app = crear_app()` si la funcion
    construye o devuelve un FastAPI.
    """
    raiz = Path(carpeta_api)
    if not raiz.is_dir():
        return []
    candidatos = []
    vistos = 0
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = [d for d in dirnames if d not in DIRS_IGNORADOS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py") or fn.startswith("test"):
                continue
            vistos += 1
            if vistos > max_archivos:
                break
            ruta = Path(dirpath) / fn
            try:
                arbol = ast.parse(ruta.read_text(encoding="utf-8", errors="replace"))
            except (SyntaxError, ValueError, OSError):
                continue
            # funciones "fabrica" que crean/devuelven una app ASGI
            fabricas = set()
            for n in arbol.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    anot = n.returns
                    anot_txt = getattr(anot, "id", None) or getattr(anot, "attr", None)
                    crea = any(_nombre_llamada(x) in CLASES_ASGI for x in ast.walk(n))
                    if anot_txt in CLASES_ASGI or crea:
                        fabricas.add(n.name)
            for n in arbol.body:
                objetivos, valor = [], None
                if isinstance(n, ast.Assign):
                    objetivos, valor = n.targets, n.value
                elif isinstance(n, ast.AnnAssign) and n.value is not None:
                    objetivos, valor = [n.target], n.value
                nombre = _nombre_llamada(valor)
                if nombre and (nombre in CLASES_ASGI or nombre in fabricas):
                    for t in objetivos:
                        if isinstance(t, ast.Name):
                            modulo = ".".join(ruta.relative_to(raiz).with_suffix("").parts)
                            candidatos.append(f"{modulo}:{t.id}")
    preferidos = ("main", "principal", "app", "aplicacion", "server", "asgi")

    def puntaje(c):
        mod = c.split(":")[0]
        ultimo = mod.rsplit(".", 1)[-1]
        return (0 if ultimo in preferidos else 1, mod.count("."), c)

    return sorted(dict.fromkeys(candidatos), key=puntaje)


# ----------------------------------------------------------------------------- servidor Angular
SALTO_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
             "te", "trailers", "transfer-encoding", "upgrade", "content-length"}


def leer_proxy_conf(carpeta_dist: str) -> list[str]:
    """Busca proxy.conf.json subiendo desde la carpeta dist y devuelve sus prefijos."""
    p = Path(carpeta_dist)
    for _ in range(6):
        f = p / "proxy.conf.json"
        if f.is_file():
            try:
                datos = json.loads(f.read_text(encoding="utf-8"))
                return [k.rstrip("/*") or "/" for k in datos]
            except (OSError, ValueError):
                return []
        if p.parent == p:
            break
        p = p.parent
    return []


class SPAHandler(SimpleHTTPRequestHandler):
    log_callback = None
    proxy_prefijos: tuple = ()      # ej. ("/api",)
    proxy_destino = None            # (host, puerto) del backend

    # ---- proxy hacia Uvicorn (equivalente a proxy.conf.json de ng serve)
    def _es_proxy(self):
        ruta = self.path.split("?", 1)[0]
        return self.proxy_destino and any(
            ruta == p or ruta.startswith(p.rstrip("/") + "/") for p in self.proxy_prefijos)

    def _proxy(self):
        import http.client
        host, port = self.proxy_destino
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo) if largo else None
        cabeceras = {k: v for k, v in self.headers.items() if k.lower() not in SALTO_HOP}
        cabeceras["X-Forwarded-For"] = self.client_address[0]
        cabeceras["X-Forwarded-Proto"] = "http"
        try:
            con = http.client.HTTPConnection(host, port, timeout=120)
            con.request(self.command, self.path, body=cuerpo, headers=cabeceras)
            resp = con.getresponse()
            datos = resp.read()
        except OSError as e:
            msg = f"No se pudo conectar con la API en http://{host}:{port} ({e})".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():  # conserva varios Set-Cookie
            if k.lower() not in SALTO_HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)
        con.close()

    def do_GET(self):
        self._proxy() if self._es_proxy() else super().do_GET()

    def do_HEAD(self):
        self._proxy() if self._es_proxy() else super().do_HEAD()

    def _solo_proxy(self):
        if self._es_proxy():
            self._proxy()
        else:
            self.send_error(405, "Metodo no permitido en archivos estaticos")

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _solo_proxy

    # ---- archivos estaticos con soporte de rutas SPA
    def send_head(self):
        ruta = Path(self.translate_path(self.path))
        if not ruta.exists():
            # Ruta de Angular (ej. /usuarios/5) -> index.html
            self.path = "/index.html"
        return super().send_head()

    def end_headers(self):
        if self.path.endswith("index.html") or self.path == "/":
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        if self.log_callback:
            self.log_callback(f"[Angular] {self.address_string()} - {fmt % args}")


class ServidorAngular:
    def __init__(self, log):
        self.log = log
        self.httpd = None
        self.hilo = None

    @property
    def activo(self):
        return self.httpd is not None

    def iniciar(self, carpeta: Path, host: str, port: int, prefijos=(), destino=None):
        clase = type("Handler", (SPAHandler,), {
            "log_callback": staticmethod(self.log),
            "proxy_prefijos": tuple(prefijos),
            "proxy_destino": destino,
        })
        handler = partial(clase, directory=str(carpeta))
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.hilo.start()

    def detener(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


# ----------------------------------------------------------------------------- servidor Uvicorn
class ServidorUvicorn:
    def __init__(self, log):
        self.log = log
        self.proc = None

    @property
    def activo(self):
        return self.proc is not None and self.proc.poll() is None

    def iniciar(self, python, carpeta, modulo, host, port, reload, extra):
        cmd = [python, "-m", "uvicorn", modulo, "--host", host, "--port", str(port)]
        if reload:
            cmd.append("--reload")
        if extra.strip():
            cmd += extra.split()
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
        self.log("[Uvicorn] $ " + " ".join(cmd))
        self.proc = subprocess.Popen(
            cmd, cwd=carpeta, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            creationflags=flags,
        )
        threading.Thread(target=self._leer, args=(self.proc,), daemon=True).start()

    def _leer(self, proc):
        for linea in proc.stdout:
            self.log("[Uvicorn] " + linea.rstrip())
        self.log(f"[Uvicorn] proceso terminado (codigo {proc.wait()})")

    def detener(self):
        if not self.proc:
            return
        if self.proc.poll() is None:
            if IS_WIN:
                # /T mata tambien los hijos (--reload crea subprocesos)
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


# ----------------------------------------------------------------------------- tema ESART
import tkinter.font as tkfont

ASSETS = BASE_DIR / "assets"

# Paleta del sistema de diseno ESART
PRIMARY = "#0284C7"
PRIMARY_CONT = "#EAF7FC"
SECONDARY = "#20A9D3"
AZUL_CLARO = "#70CBE7"
PIZARRA = "#17263B"
FONDO = "#F8FAFC"
SURFACE = "#FFFFFF"
BORDE = "#E2E8F0"
OUTLINE = "#CBD5E1"
GRIS_CLARO = "#F1F5F9"
TEXTO_SUAVE = "#64748B"
SUCCESS = "#15803D"
SUCCESS_CONT = "#F0FDF4"
SUCCESS_BORDE = "#BBF7D0"
ERROR = "#DC2626"
ERROR_CONT = "#FEF2F2"
WARNING = "#D97706"

ACENTO_ANG = {"c": PRIMARY, "cont": PRIMARY_CONT, "borde": "#BAE6FD"}
ACENTO_UVI = {"c": SUCCESS, "cont": SUCCESS_CONT, "borde": SUCCESS_BORDE}
ACENTO_LOG = {"c": PIZARRA, "cont": GRIS_CLARO, "borde": BORDE}

FUENTE = "Segoe UI"
FUENTE_TITULO = "Segoe UI Semibold"
FUENTE_MONO = "Consolas"
ICONOS = None  # se resuelve al crear la ventana (Segoe Fluent Icons / MDL2)

# Glifos de Segoe Fluent Icons / Segoe MDL2 Assets
IC = {
    "carpeta": "", "play": "", "stop": "", "copiar": "",
    "buscar": "", "abrir": "", "globo": "", "codigo": "",
    "rayo": "", "lista": "", "borrar": "", "consola": "",
    "info": "",
}

ESCALA = 1.0


def px(n):
    return int(round(n * ESCALA))


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mezclar(c1, c2, t):
    a, b = _hex(c1), _hex(c2)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def redondeado(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


class Boton(tk.Canvas):
    """Boton redondeado estilo ESART: 'solido' (relleno) u 'borde' (contorno)."""

    def __init__(self, padre, texto, comando, color=PRIMARY, estilo="solido", icono=None,
                 alto=38, tam=10, ancho=None):
        super().__init__(padre, height=px(alto), bg=padre["bg"], highlightthickness=0,
                         bd=0, cursor="hand2")
        self.texto, self.comando, self.color, self.estilo = texto, comando, color, estilo
        self.icono, self.ancho_fijo, self.alto = icono, ancho, px(alto)
        self.f_txt = tkfont.Font(family=FUENTE, size=tam, weight="bold")
        self.f_ico = tkfont.Font(family=ICONOS or FUENTE, size=tam)
        self._hover = self._presion = False
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False, presion=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(presion=True))
        self.bind("<ButtonRelease-1>", self._soltar)
        self._dibujar()

    def _set(self, hover=None, presion=None):
        if hover is not None:
            self._hover = hover
        if presion is not None:
            self._presion = presion
        self._dibujar()

    def _soltar(self, _e):
        ok = self._presion and self._hover
        self._set(presion=False)
        if ok and self.comando:
            self.comando()

    def configurar(self, texto=None, icono=None, color=None, estilo=None):
        if texto is not None:
            self.texto = texto
        if icono is not None:
            self.icono = icono
        if color is not None:
            self.color = color
        if estilo is not None:
            self.estilo = estilo
        self._dibujar()

    def _dibujar(self):
        ico = self.icono if ICONOS else None
        tw = self.f_txt.measure(self.texto) if self.texto else 0
        iw = self.f_ico.measure(ico) if ico else 0
        gap = px(8) if (tw and iw) else 0
        h = self.alto
        w = self.ancho_fijo and px(self.ancho_fijo) or (tw + iw + gap + 2 * px(16) if tw else h)
        self.configure(width=w)
        self.delete("all")
        c = self.color
        if self.estilo == "solido":
            fill = mezclar(c, "#000000", 0.22 if self._presion else 0.12 if self._hover else 0)
            borde, fg = fill, "#ffffff"
        else:
            fill = mezclar(c, "#ffffff", 0.80 if self._presion else 0.90 if self._hover else 1)
            borde, fg = mezclar(c, "#ffffff", 0.55), c
        redondeado(self, 1, 1, w - 2, h - 2, px(8), fill=fill, outline=borde)
        x = (w - (iw + gap + tw)) / 2
        cy = h / 2 + (1 if self._presion else 0)
        if ico:
            self.create_text(x, cy, anchor="w", text=ico, font=self.f_ico, fill=fg)
            x += iw + gap
        if tw:
            self.create_text(x, cy, anchor="w", text=self.texto, font=self.f_txt, fill=fg)


class Chip(tk.Canvas):
    """Etiqueta tipo pildora (badges y estado)."""

    def __init__(self, padre, texto, fg, bg, borde=None, punto=False, tam=8):
        super().__init__(padre, height=px(24), bg=padre["bg"], highlightthickness=0, bd=0)
        self.f = tkfont.Font(family=FUENTE, size=tam, weight="bold")
        self.configurar(texto, fg, bg, borde, punto)

    def configurar(self, texto, fg, bg, borde=None, punto=False):
        self.delete("all")
        h = px(24)
        extra = px(14) if punto else 0
        w = self.f.measure(texto) + 2 * px(11) + extra
        self.configure(width=w)
        redondeado(self, 1, 1, w - 2, h - 2, px(11), fill=bg, outline=borde or bg)
        x = px(11)
        if punto:
            r = px(3.5)
            self.create_oval(x, h / 2 - r, x + 2 * r, h / 2 + r, fill=fg, outline="")
            x += extra
        self.create_text(x, h / 2, anchor="w", text=texto, font=self.f, fill=fg)


class PildoraEstado(Chip):
    def __init__(self, padre):
        super().__init__(padre, "Detenido", TEXTO_SUAVE, GRIS_CLARO, BORDE, punto=True)

    def activo(self, si):
        if si:
            self.configurar("Activo", SUCCESS, SUCCESS_CONT, SUCCESS_BORDE, punto=True)
        else:
            self.configurar("Detenido", TEXTO_SUAVE, GRIS_CLARO, BORDE, punto=True)


class Tarjeta(tk.Canvas):
    """Tarjeta blanca con esquinas redondeadas; el contenido va en self.cuerpo."""

    def __init__(self, padre, borde=BORDE):
        super().__init__(padre, bg=padre["bg"], highlightthickness=0, bd=0)
        self.borde = borde
        self.pad = px(6)
        self.cuerpo = tk.Frame(self, bg=SURFACE)
        self._win = self.create_window(self.pad, self.pad, window=self.cuerpo, anchor="nw")
        self.cuerpo.bind("<Configure>", self._ajustar_alto)
        self.bind("<Configure>", self._redibujar)

    def _ajustar_alto(self, _e=None):
        req = self.cuerpo.winfo_reqheight() + 2 * self.pad
        if getattr(self, "_alto_req", None) != req:
            self._alto_req = req
            self.configure(height=req)

    def actualizar(self):
        """Recalcula el alto cuando cambia el contenido (ej. aparecen las URLs)."""
        self._ajustar_alto()
        alto = max(self.winfo_height() - 2 * self.pad, self.cuerpo.winfo_reqheight())
        self.itemconfigure(self._win, height=alto)

    def _redibujar(self, e):
        self.delete("fondo")
        redondeado(self, 1, 1, e.width - 2, e.height - 2, px(14), fill=SURFACE,
                   outline=self.borde, width=1, tags="fondo")
        self.tag_lower("fondo")
        alto = max(e.height - 2 * self.pad, self.cuerpo.winfo_reqheight())
        self.itemconfigure(self._win, width=e.width - 2 * self.pad, height=alto)


class Desplazable(tk.Frame):
    """Area con scroll vertical; el contenido se estira si sobra espacio."""

    def __init__(self, padre, bg):
        super().__init__(padre, bg=bg)
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.cv.yview,
                                style="Esart.Vertical.TScrollbar")
        self.cv.configure(yscrollcommand=self.sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        self.interior = tk.Frame(self.cv, bg=bg)
        self._win = self.cv.create_window(0, 0, window=self.interior, anchor="nw")
        self.interior.bind("<Configure>", lambda e: self._ajustar())
        self.cv.bind("<Configure>", lambda e: self._ajustar())

    def _ajustar(self):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        req = self.interior.winfo_reqheight()
        self.cv.itemconfigure(self._win, width=w, height=max(h, req))
        self.cv.configure(scrollregion=(0, 0, w, max(h, req)))
        if req > h + 1:
            if not self.sb.winfo_ismapped():
                self.sb.pack(side="right", fill="y", before=self.cv)
        elif self.sb.winfo_ismapped():
            self.sb.pack_forget()
            self.cv.yview_moveto(0)

    def rueda(self, e):
        if self.interior.winfo_reqheight() > self.cv.winfo_height() + 1:
            self.cv.yview_scroll(int(-e.delta / 120), "units")


# ----------------------------------------------------------------------------- interfaz
class App(tk.Tk):
    HOSTS = ("0.0.0.0", "127.0.0.1")

    def __init__(self):
        global ESCALA, ICONOS
        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nitido
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("esart.servidor")
            except Exception:
                pass
        super().__init__()
        ESCALA = self.winfo_fpixels("1i") / 96
        familias = set(tkfont.families(self))
        ICONOS = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in familias), None)

        self.title("ESART · Servidor Angular + Uvicorn")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        ancho, alto = min(px(1220), sw - px(40)), min(px(980), sh - px(90))
        self.geometry(f"{ancho}x{alto}+{max((sw - ancho) // 2, 0)}+{px(10)}")
        self.minsize(px(900), px(620))
        self.configure(bg=FONDO)
        self._imagenes()
        self._estilos()

        self.cola_log = queue.Queue()
        self.ang = ServidorAngular(self.cola_log.put)
        self.uvi = ServidorUvicorn(self.cola_log.put)

        cfg = self._cargar_config()
        self.v_dist = tk.StringVar(value=cfg.get("dist", ""))
        self.v_ang_host = tk.StringVar(value=cfg.get("ang_host", "0.0.0.0"))
        self.v_ang_port = tk.StringVar(value=str(cfg.get("ang_port", 4200)))
        self.v_proxy = tk.StringVar(value=cfg.get("proxy", "/api"))
        self.v_proxy_on = tk.BooleanVar(value=cfg.get("proxy_on", True))

        self.v_api = tk.StringVar(value=cfg.get("api", ""))
        self.v_modulo = tk.StringVar(value=cfg.get("modulo", "main:app"))
        self.v_python = tk.StringVar(value=cfg.get("python", sys.executable))
        self.v_uvi_host = tk.StringVar(value=cfg.get("uvi_host", "0.0.0.0"))
        self.v_uvi_port = tk.StringVar(value=str(cfg.get("uvi_port", 8000)))
        self.v_reload = tk.BooleanVar(value=cfg.get("reload", False))
        self.v_extra = tk.StringVar(value=cfg.get("extra", ""))

        self._construir()
        self._refrescar_estado()
        self.after(100, self._volcar_log)
        self.after(1000, self._vigilar_uvicorn)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ---------------------------------------------------------------- recursos
    def _imagenes(self):
        self.img = {}
        for nombre in ("escudo", "banner"):
            try:
                self.img[nombre] = tk.PhotoImage(file=str(ASSETS / f"{nombre}.png"))
            except (tk.TclError, OSError):
                self.img[nombre] = None
        ico = ASSETS / "esart.ico"
        try:
            if IS_WIN and ico.is_file():
                self.iconbitmap(default=str(ico))
            elif self.img["escudo"]:
                self.iconphoto(True, self.img["escudo"])
        except tk.TclError:
            pass

    def _estilos(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("Esart.TCombobox", fieldbackground=SURFACE, background=SURFACE,
                     foreground=PIZARRA, arrowcolor=TEXTO_SUAVE, bordercolor=OUTLINE,
                     lightcolor=SURFACE, darkcolor=SURFACE, padding=px(6), arrowsize=px(14),
                     selectbackground=SURFACE, selectforeground=PIZARRA)
        st.map("Esart.TCombobox", fieldbackground=[("readonly", SURFACE)],
               bordercolor=[("focus", PRIMARY)], lightcolor=[("focus", SURFACE)],
               arrowcolor=[("active", PRIMARY)], background=[("active", PRIMARY_CONT)])
        for nombre, trough, barra in (("Esart.Vertical.TScrollbar", FONDO, OUTLINE),
                                      ("Log.Vertical.TScrollbar", PIZARRA, "#334155")):
            st.configure(nombre, troughcolor=trough, background=barra, bordercolor=trough,
                         lightcolor=barra, darkcolor=barra, arrowcolor=TEXTO_SUAVE,
                         gripcount=0, arrowsize=px(12))
            st.map(nombre, background=[("active", mezclar(barra, PRIMARY, 0.35))])
        self.option_add("*TCombobox*Listbox.background", SURFACE)
        self.option_add("*TCombobox*Listbox.foreground", PIZARRA)
        self.option_add("*TCombobox*Listbox.selectBackground", PRIMARY_CONT)
        self.option_add("*TCombobox*Listbox.selectForeground", PRIMARY)
        self.option_add("*TCombobox*Listbox.font", (FUENTE, 10))

    # ---------------------------------------------------------------- config
    def _cargar_config(self):
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _guardar_config(self):
        cfg = {
            "dist": self.v_dist.get(), "ang_host": self.v_ang_host.get(),
            "ang_port": self.v_ang_port.get(), "api": self.v_api.get(),
            "proxy": self.v_proxy.get(), "proxy_on": self.v_proxy_on.get(),
            "modulo": self.v_modulo.get(), "python": self.v_python.get(),
            "uvi_host": self.v_uvi_host.get(), "uvi_port": self.v_uvi_port.get(),
            "reload": self.v_reload.get(), "extra": self.v_extra.get(),
        }
        try:
            CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except OSError:
            pass


    # ---------------------------------------------------------------- piezas
    def _entrada(self, padre, var, ancho=None):
        """Campo de texto con borde y margen interno (el borde se pinta azul al enfocar)."""
        marco = tk.Frame(padre, bg=SURFACE, highlightthickness=1, highlightbackground=OUTLINE,
                         highlightcolor=OUTLINE)
        e = tk.Entry(marco, textvariable=var, bg=SURFACE, fg=PIZARRA, insertbackground=PIZARRA,
                     relief="flat", bd=0, font=(FUENTE, 10), highlightthickness=0,
                     selectbackground=PRIMARY_CONT, selectforeground=PIZARRA)
        if ancho:
            e.configure(width=ancho)
        e.pack(fill="both", expand=True, padx=px(10))
        e.bind("<FocusIn>", lambda _e: marco.configure(highlightbackground=PRIMARY, highlightcolor=PRIMARY))
        e.bind("<FocusOut>", lambda _e: marco.configure(highlightbackground=OUTLINE, highlightcolor=OUTLINE))
        return marco

    def _spin(self, padre, var):
        return tk.Spinbox(padre, textvariable=var, from_=1, to=65535, width=7, bg=SURFACE,
                          fg=PIZARRA, insertbackground=PIZARRA, relief="flat",
                          font=(FUENTE, 10, "bold"), buttonbackground=GRIS_CLARO,
                          highlightthickness=1, highlightbackground=OUTLINE,
                          highlightcolor=PRIMARY, justify="center")

    def _combo(self, padre, var, valores=(), ancho=None):
        c = ttk.Combobox(padre, textvariable=var, values=valores, style="Esart.TCombobox",
                         font=(FUENTE, 10))
        if ancho:
            c.configure(width=ancho)
        return c

    def _check(self, padre, texto, var):
        return tk.Checkbutton(padre, text=texto, variable=var, bg=SURFACE, fg=PIZARRA,
                              activebackground=SURFACE, activeforeground=PRIMARY,
                              selectcolor=SURFACE, font=(FUENTE, 10), cursor="hand2",
                              highlightthickness=0, bd=0)

    def _campo(self, padre, etiqueta, ayuda=None):
        """Bloque con etiqueta arriba, fila para el control y texto de ayuda opcional."""
        f = tk.Frame(padre, bg=SURFACE)
        tk.Label(f, text=etiqueta, bg=SURFACE, fg=PIZARRA,
                 font=(FUENTE, 9, "bold")).pack(anchor="w", pady=(0, px(5)))
        fila = tk.Frame(f, bg=SURFACE)
        fila.pack(fill="x")
        if ayuda:
            tk.Label(f, text=ayuda, bg=SURFACE, fg=TEXTO_SUAVE, font=(FUENTE, 8),
                     justify="left").pack(anchor="w", pady=(px(4), 0))
        return f, fila

    def _icono_tile(self, padre, glifo, acento, letra):
        t = px(46)
        cv = tk.Canvas(padre, width=t, height=t, bg=padre["bg"], highlightthickness=0)
        redondeado(cv, 1, 1, t - 2, t - 2, px(12), fill=acento["cont"], outline=acento["borde"])
        if ICONOS:
            cv.create_text(t / 2, t / 2, text=glifo, fill=acento["c"], font=(ICONOS, 16))
        else:
            cv.create_text(t / 2, t / 2, text=letra, fill=acento["c"], font=(FUENTE, 15, "bold"))
        return cv

    def _cabecera_tarjeta(self, cuerpo, glifo, letra, titulo, subtitulo, acento, badge):
        cab = tk.Frame(cuerpo, bg=SURFACE)
        cab.pack(fill="x", padx=px(22), pady=(px(20), px(14)))
        self._icono_tile(cab, glifo, acento, letra).pack(side="left")
        txt = tk.Frame(cab, bg=SURFACE)
        txt.pack(side="left", padx=px(14))
        tk.Label(txt, text=titulo, bg=SURFACE, fg=PIZARRA,
                 font=(FUENTE, 13, "bold")).pack(anchor="w")
        tk.Label(txt, text=subtitulo, bg=SURFACE, fg=TEXTO_SUAVE,
                 font=(FUENTE, 9)).pack(anchor="w")
        der = tk.Frame(cab, bg=SURFACE)
        der.pack(side="right", anchor="n")
        if badge:
            Chip(der, badge, acento["c"], acento["cont"], acento["borde"]).pack(anchor="e")
        pildora = PildoraEstado(der)
        pildora.pack(anchor="e", pady=(px(6), 0))
        tk.Frame(cuerpo, bg=BORDE, height=1).pack(fill="x", padx=px(22))
        return pildora

    def _pie_tarjeta(self, cuerpo, acento, comando):
        pie = tk.Frame(cuerpo, bg=SURFACE)
        pie.pack(side="bottom", fill="x", padx=px(22), pady=(0, px(20)))
        tk.Frame(pie, bg=BORDE, height=1).pack(fill="x", pady=(0, px(14)))
        fila = tk.Frame(pie, bg=SURFACE)
        fila.pack(fill="x")
        boton = Boton(fila, "Iniciar", comando, SUCCESS, "solido", IC["play"], alto=40, tam=10)
        boton.pack(side="right", anchor="s")
        izq = tk.Frame(fila, bg=SURFACE)
        izq.pack(side="left", fill="x", expand=True)
        tk.Label(izq, text="URLS DE ACCESO", bg=SURFACE, fg=TEXTO_SUAVE,
                 font=(FUENTE, 8, "bold")).pack(anchor="w", pady=(0, px(4)))
        caja = tk.Frame(izq, bg=SURFACE)
        caja.pack(fill="x")
        return caja, boton

    # ---------------------------------------------------------------- layout
    def _construir(self):
        # --- encabezado institucional (foto de la escuela + escudo)
        alto_cab = px(108)
        cab = tk.Canvas(self, height=alto_cab, bg=PIZARRA, highlightthickness=0, bd=0)
        cab.pack(fill="x")
        if self.img["banner"]:
            cab.create_image(0, 0, anchor="nw", image=self.img["banner"])
        x = px(28)
        if self.img["escudo"]:
            cab.create_image(x, alto_cab / 2, anchor="w", image=self.img["escudo"])
            x += self.img["escudo"].width() + px(18)
        cab.create_text(x, alto_cab / 2 - px(22), anchor="w", text="ESCUELA DE ARTILLERÍA",
                        fill="#ffffff", font=(FUENTE, 17, "bold"))
        cab.create_text(x, alto_cab / 2 + px(4), anchor="w",
                        text="“General Carlos Julio Gil Colorado”",
                        fill=AZUL_CLARO, font=(FUENTE, 10, "bold italic"))
        cab.create_text(x, alto_cab / 2 + px(27), anchor="w",
                        text="Panel de servidores · Frontend Angular y API Uvicorn",
                        fill="#CBD5E1", font=(FUENTE, 9))
        f_chip = tkfont.Font(family=FUENTE, size=8, weight="bold")

        def chip_cabecera(e):
            cab.delete("chip")
            texto = "SERVIDOR LOCAL"
            w = f_chip.measure(texto) + px(40)
            x2, y1 = e.width - px(28), alto_cab / 2 - px(14)
            redondeado(cab, x2 - w, y1, x2, y1 + px(28), px(6), fill=PIZARRA,
                       outline=mezclar(AZUL_CLARO, PIZARRA, 0.45), tags="chip")
            r = px(4)
            cab.create_oval(x2 - w + px(12), y1 + px(14) - r, x2 - w + px(12) + 2 * r,
                            y1 + px(14) + r, fill=SECONDARY, outline="", tags="chip")
            cab.create_text(x2 - w + px(26), y1 + px(14), anchor="w", text=texto,
                            fill=AZUL_CLARO, font=f_chip, tags="chip")

        cab.bind("<Configure>", chip_cabecera)
        tk.Frame(self, bg=SECONDARY, height=px(3)).pack(fill="x")

        # --- pie institucional
        pie = tk.Frame(self, bg=SURFACE)
        pie.pack(side="bottom", fill="x")
        tk.Frame(pie, bg=BORDE, height=1).pack(fill="x")
        tk.Label(pie, text="ESART — Plataforma Institucional · Escuela de Artillería "
                           "“General Carlos Julio Gil Colorado” · Ejército Nacional de Colombia",
                 bg=SURFACE, fg=TEXTO_SUAVE, font=(FUENTE, 8)).pack(pady=px(8))

        # --- contenido con scroll
        self.area = Desplazable(self, FONDO)
        self.area.pack(fill="both", expand=True)
        self.bind_all("<MouseWheel>", self._rueda)
        raiz = self.area.interior
        cont = tk.Frame(raiz, bg=FONDO)
        cont.pack(fill="both", expand=True, padx=px(32), pady=(px(22), px(24)))
        cont.columnconfigure(0, weight=1, uniform="col")
        cont.columnconfigure(1, weight=1, uniform="col")
        cont.rowconfigure(2, weight=1)

        # --- titulo de pagina + acciones globales
        tit = tk.Frame(cont, bg=FONDO)
        tit.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, px(20)))
        miga = tk.Frame(tit, bg=FONDO)
        miga.pack(anchor="w")
        for i, (t, c) in enumerate((("Herramientas", TEXTO_SUAVE), ("Desarrollo", TEXTO_SUAVE),
                                    ("Servidores", PRIMARY))):
            if i:
                tk.Label(miga, text="›", bg=FONDO, fg=OUTLINE, font=(FUENTE, 9)).pack(side="left", padx=px(6))
            tk.Label(miga, text=t, bg=FONDO, fg=c,
                     font=(FUENTE, 9, "bold" if c == PRIMARY else "normal")).pack(side="left")
        fila_t = tk.Frame(tit, bg=FONDO)
        fila_t.pack(fill="x", pady=(px(4), 0))
        izq = tk.Frame(fila_t, bg=FONDO)
        izq.pack(side="left")
        tk.Label(izq, text="Servidores de Desarrollo", bg=FONDO, fg=PIZARRA,
                 font=(FUENTE, 20, "bold")).pack(anchor="w")
        tk.Label(izq, text="Publique el frontend y la API institucional desde un solo lugar.",
                 bg=FONDO, fg=TEXTO_SUAVE, font=(FUENTE, 10)).pack(anchor="w")
        Boton(fila_t, "Iniciar ambos", self._iniciar_ambos, SECONDARY, "solido", IC["play"],
              alto=42, tam=10).pack(side="right", anchor="s")
        Boton(fila_t, "Detener ambos", self._detener_ambos, ERROR, "borde", IC["stop"],
              alto=42, tam=10).pack(side="right", anchor="s", padx=(0, px(12)))

        # --- tarjeta Angular
        t_ang = Tarjeta(cont, ACENTO_ANG["borde"])
        t_ang.grid(row=1, column=0, sticky="nsew", padx=(0, px(10)), pady=(0, px(20)))
        ca = t_ang.cuerpo
        self.pill_ang = self._cabecera_tarjeta(ca, IC["codigo"], "A", "Frontend Angular",
                                               "Archivos estáticos de la carpeta dist",
                                               ACENTO_ANG, "ANGULAR · SPA")
        self.box_ang_urls, self.btn_ang = self._pie_tarjeta(ca, ACENTO_ANG, self._toggle_angular)
        campos = tk.Frame(ca, bg=SURFACE)
        campos.pack(fill="both", expand=True, padx=px(22), pady=(px(16), px(16)))
        g = {"fill": "x", "pady": (0, px(14))}

        f, fila = self._campo(campos, "Carpeta dist",
                              "Se detecta sola la subcarpeta browser/ de Angular 17+")
        f.pack(**g)
        self._entrada(fila, self.v_dist).pack(side="left", fill="x", expand=True, ipady=px(6))
        Boton(fila, "Examinar", self._elegir_dist, PRIMARY, "borde", IC["carpeta"],
              alto=36, tam=9).pack(side="left", padx=(px(10), 0))

        red = tk.Frame(campos, bg=SURFACE)
        red.pack(**g)
        red.columnconfigure(0, weight=1)
        f, fila = self._campo(red, "Host")
        f.grid(row=0, column=0, sticky="ew", padx=(0, px(14)))
        self._combo(fila, self.v_ang_host, self.HOSTS).pack(fill="x")
        f, fila = self._campo(red, "Puerto")
        f.grid(row=0, column=1, sticky="w")
        self._spin(fila, self.v_ang_port).pack(anchor="w", ipady=px(5))

        f, fila = self._campo(campos, "Proxy hacia la API",
                              "Prefijos separados por coma, igual que proxy.conf.json de ng serve")
        f.pack(**g)
        self._check(fila, "Redirigir a Uvicorn", self.v_proxy_on).pack(side="left")
        self._entrada(fila, self.v_proxy).pack(side="left", fill="x", expand=True,
                                               padx=(px(12), 0), ipady=px(6))

        # --- tarjeta Uvicorn
        t_uvi = Tarjeta(cont, ACENTO_UVI["borde"])
        t_uvi.grid(row=1, column=1, sticky="nsew", padx=(px(10), 0), pady=(0, px(20)))
        cu = t_uvi.cuerpo
        self.pill_uvi = self._cabecera_tarjeta(cu, IC["rayo"], "U", "API Uvicorn",
                                               "Backend Python · FastAPI / Starlette",
                                               ACENTO_UVI, "PYTHON · ASGI")
        self.box_uvi_urls, self.btn_uvi = self._pie_tarjeta(cu, ACENTO_UVI, self._toggle_uvicorn)
        campos = tk.Frame(cu, bg=SURFACE)
        campos.pack(fill="both", expand=True, padx=px(22), pady=(px(16), px(16)))

        f, fila = self._campo(campos, "Carpeta API",
                              "Se detectan el entorno virtual (.venv) y la app automáticamente")
        f.pack(**g)
        self._entrada(fila, self.v_api).pack(side="left", fill="x", expand=True, ipady=px(6))
        Boton(fila, "Examinar", self._elegir_api, SUCCESS, "borde", IC["carpeta"],
              alto=36, tam=9).pack(side="left", padx=(px(10), 0))

        f, fila = self._campo(campos, "Intérprete Python")
        f.pack(**g)
        self._entrada(fila, self.v_python).pack(side="left", fill="x", expand=True, ipady=px(6))
        Boton(fila, "Examinar", self._elegir_python, SUCCESS, "borde", IC["consola"],
              alto=36, tam=9).pack(side="left", padx=(px(10), 0))

        f, fila = self._campo(campos, "Aplicación (módulo:variable)")
        f.pack(**g)
        self.cmb_modulo = self._combo(fila, self.v_modulo)
        self.cmb_modulo.pack(side="left", fill="x", expand=True)
        Boton(fila, "Detectar", lambda: self._detectar_modulo(avisar=True), SUCCESS, "borde",
              IC["buscar"], alto=36, tam=9).pack(side="left", padx=(px(10), 0))

        red = tk.Frame(campos, bg=SURFACE)
        red.pack(**g)
        red.columnconfigure(2, weight=1)
        f, fila = self._campo(red, "Host")
        f.grid(row=0, column=0, sticky="w", padx=(0, px(14)))
        self._combo(fila, self.v_uvi_host, self.HOSTS, ancho=13).pack(fill="x")
        f, fila = self._campo(red, "Puerto")
        f.grid(row=0, column=1, sticky="w", padx=(0, px(14)))
        self._spin(fila, self.v_uvi_port).pack(anchor="w", ipady=px(5))
        f, fila = self._campo(red, "Argumentos extra")
        f.grid(row=0, column=2, sticky="ew")
        self._entrada(fila, self.v_extra).pack(fill="x", ipady=px(6))

        self._check(campos, "Recarga automática al guardar cambios (--reload)",
                    self.v_reload).pack(anchor="w")

        # --- registro
        t_log = Tarjeta(cont, BORDE)
        t_log.grid(row=2, column=0, columnspan=2, sticky="nsew")
        cl = t_log.cuerpo
        cab_l = tk.Frame(cl, bg=SURFACE)
        cab_l.pack(fill="x", padx=px(22), pady=(px(18), px(12)))
        self._icono_tile(cab_l, IC["lista"], ACENTO_LOG, "R").pack(side="left")
        txt = tk.Frame(cab_l, bg=SURFACE)
        txt.pack(side="left", padx=px(14))
        tk.Label(txt, text="Registro de actividad", bg=SURFACE, fg=PIZARRA,
                 font=(FUENTE, 13, "bold")).pack(anchor="w")
        tk.Label(txt, text="Peticiones recibidas y salida de ambos servidores", bg=SURFACE,
                 fg=TEXTO_SUAVE, font=(FUENTE, 9)).pack(anchor="w")
        Boton(cab_l, "Limpiar", self._limpiar_log, TEXTO_SUAVE, "borde", IC["borrar"],
              alto=36, tam=9).pack(side="right")
        leyenda = tk.Frame(cab_l, bg=SURFACE)
        leyenda.pack(side="right", padx=px(16))
        for t, c in (("Angular", AZUL_CLARO), ("Uvicorn", "#4ADE80"), ("Error", "#F87171")):
            Chip(leyenda, t, PIZARRA, mezclar(c, "#ffffff", 0.75), punto=True).pack(side="left", padx=px(3))

        caja = tk.Frame(cl, bg=PIZARRA)
        caja.pack(fill="both", expand=True, padx=px(22), pady=(0, px(20)))
        self.txt_log = tk.Text(caja, height=9, font=(FUENTE_MONO, 9), state="disabled",
                               bg=PIZARRA, fg="#CBD5E1", relief="flat", bd=0, padx=px(14),
                               pady=px(12), wrap="word", insertbackground="#ffffff",
                               selectbackground=PRIMARY, highlightthickness=0)
        sb = ttk.Scrollbar(caja, orient="vertical", command=self.txt_log.yview,
                           style="Log.Vertical.TScrollbar")
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)
        self.txt_log.tag_configure("ang", foreground=AZUL_CLARO)
        self.txt_log.tag_configure("uvi", foreground="#4ADE80")
        self.txt_log.tag_configure("err", foreground="#F87171")
        self.txt_log.tag_configure("info", foreground="#CBD5E1")
        self.tarjetas = (t_ang, t_uvi, t_log)

    def _rueda(self, e):
        try:
            clase = e.widget.winfo_class()
        except (AttributeError, tk.TclError):
            return
        if clase in ("Text", "Listbox", "TCombobox", "Spinbox"):
            return
        self.area.rueda(e)

    # ---------------------------------------------------------------- selectores
    def _elegir_dist(self):
        d = filedialog.askdirectory(title="Selecciona la carpeta dist de Angular",
                                    initialdir=self.v_dist.get() or str(BASE_DIR))
        if d:
            self.v_dist.set(d)
            r = resolver_dist(d)
            if r is None:
                messagebox.showwarning("Angular", "No se encontro index.html en esa carpeta.")
            elif str(r) != str(Path(d)):
                self.cola_log.put(f"[Angular] index.html encontrado en: {r}")
            prefijos = leer_proxy_conf(d)
            if prefijos:
                self.v_proxy.set(", ".join(prefijos))
                self.v_proxy_on.set(True)
                self.cola_log.put(f"[Angular] proxy.conf.json detectado: {', '.join(prefijos)}")

    def _elegir_api(self):
        d = filedialog.askdirectory(title="Selecciona la carpeta del proyecto API",
                                    initialdir=self.v_api.get() or str(BASE_DIR))
        if d:
            self.v_api.set(d)
            py = detectar_python(d)
            self.v_python.set(py)
            if py != sys.executable:
                self.cola_log.put(f"[Uvicorn] Entorno virtual detectado: {py}")
            self._detectar_modulo(avisar=False)

    def _detectar_modulo(self, avisar):
        apps = detectar_apps(self.v_api.get().strip())
        self.cmb_modulo["values"] = apps
        if apps:
            self.v_modulo.set(apps[0])
            self.cola_log.put("[Uvicorn] App detectada: " + ", ".join(apps))
        elif avisar:
            messagebox.showinfo("Uvicorn", "No se encontro ninguna app FastAPI/Starlette.\n"
                                           "Escribela a mano, ej. paquete.modulo:app")

    def _elegir_python(self):
        tipos = [("python.exe", "python*.exe"), ("Todos", "*.*")] if IS_WIN else [("Todos", "*")]
        f = filedialog.askopenfilename(title="Selecciona el ejecutable de Python", filetypes=tipos)
        if f:
            self.v_python.set(f)

    # ---------------------------------------------------------------- validacion
    def _leer_puerto(self, var, nombre):
        try:
            p = int(var.get())
            if 1 <= p <= 65535:
                return p
        except ValueError:
            pass
        messagebox.showerror(nombre, "Puerto invalido (1-65535).")
        return None

    def _puertos_distintos(self):
        if self.v_ang_port.get().strip() == self.v_uvi_port.get().strip():
            messagebox.showerror("Puertos", "Angular y Uvicorn no pueden usar el mismo puerto.")
            return False
        return True

    # ---------------------------------------------------------------- Angular
    def _toggle_angular(self):
        if self.ang.activo:
            self.ang.detener()
            self.cola_log.put("[Angular] detenido")
        else:
            self._iniciar_angular()
        self._refrescar_estado()

    def _iniciar_angular(self):
        if self.ang.activo:
            return True
        carpeta = resolver_dist(self.v_dist.get())
        if carpeta is None:
            messagebox.showerror("Angular", "Selecciona una carpeta dist valida (con index.html).")
            return False
        port = self._leer_puerto(self.v_ang_port, "Angular")
        if port is None or not self._puertos_distintos():
            return False
        host = self.v_ang_host.get().strip() or "0.0.0.0"
        prefijos = [p.strip() for p in self.v_proxy.get().replace(";", ",").split(",") if p.strip()]
        destino = None
        if self.v_proxy_on.get() and prefijos:
            uvi_port = self._leer_puerto(self.v_uvi_port, "Uvicorn")
            if uvi_port is None:
                return False
            uvi_host = self.v_uvi_host.get().strip()
            destino = ("127.0.0.1" if uvi_host in ("", "0.0.0.0", "localhost") else uvi_host, uvi_port)
        try:
            self.ang.iniciar(carpeta, host, port, prefijos, destino)
        except OSError as e:
            messagebox.showerror("Angular", f"No se pudo abrir el puerto {port}:\n{e}")
            return False
        self.cola_log.put(f"[Angular] sirviendo {carpeta} en " + "  ".join(urls_para(host, port)))
        if destino:
            self.cola_log.put(f"[Angular] proxy {', '.join(prefijos)} -> http://{destino[0]}:{destino[1]}")
        self._guardar_config()
        return True

    # ---------------------------------------------------------------- Uvicorn
    def _toggle_uvicorn(self):
        if self.uvi.activo:
            self.uvi.detener()
            self.cola_log.put("[Uvicorn] detenido")
        else:
            self._iniciar_uvicorn()
        self._refrescar_estado()

    def _iniciar_uvicorn(self):
        if self.uvi.activo:
            return True
        api = self.v_api.get().strip()
        if not api or not Path(api).is_dir():
            messagebox.showerror("Uvicorn", "Selecciona la carpeta del proyecto API.")
            return False
        python = self.v_python.get().strip() or sys.executable
        if not Path(python).is_file():
            messagebox.showerror("Uvicorn", f"No existe el ejecutable de Python:\n{python}")
            return False
        modulo = self.v_modulo.get().strip()
        if ":" not in modulo:
            messagebox.showerror("Uvicorn", "El modulo debe tener formato archivo:variable, ej. main:app")
            return False
        port = self._leer_puerto(self.v_uvi_port, "Uvicorn")
        if port is None or not self._puertos_distintos():
            return False
        host = self.v_uvi_host.get().strip() or "0.0.0.0"
        if not puerto_libre(host, port):
            messagebox.showerror("Uvicorn", f"El puerto {port} ya esta en uso.")
            return False
        try:
            self.uvi.iniciar(python, api, modulo, host, port, self.v_reload.get(), self.v_extra.get())
        except OSError as e:
            messagebox.showerror("Uvicorn", f"No se pudo iniciar:\n{e}")
            return False
        self._guardar_config()
        return True

    def _vigilar_uvicorn(self):
        # Si uvicorn muere solo (error en la app), actualizar la interfaz.
        if self.uvi.proc is not None and self.uvi.proc.poll() is not None:
            self.uvi.proc = None
            self._refrescar_estado()
        self.after(1000, self._vigilar_uvicorn)

    # ---------------------------------------------------------------- ambos
    def _iniciar_ambos(self):
        self._iniciar_angular()
        self._iniciar_uvicorn()
        self._refrescar_estado()

    def _detener_ambos(self):
        if self.ang.activo:
            self.ang.detener()
            self.cola_log.put("[Angular] detenido")
        if self.uvi.activo:
            self.uvi.detener()
            self.cola_log.put("[Uvicorn] detenido")
        self._refrescar_estado()

    # ---------------------------------------------------------------- estado / URLs
    def _pintar_urls(self, caja, urls, acento):
        for w in caja.winfo_children():
            w.destroy()
        if not urls:
            tk.Label(caja, text="Inicie el servidor para ver las direcciones de acceso.",
                     bg=SURFACE, fg=TEXTO_SUAVE, font=(FUENTE, 9, "italic")).pack(anchor="w", pady=px(4))
            return
        for u in urls:
            fila = tk.Frame(caja, bg=SURFACE)
            fila.pack(anchor="w", fill="x", pady=px(2))
            if ICONOS:
                tk.Label(fila, text=IC["globo"], bg=SURFACE, fg=acento["c"],
                         font=(ICONOS, 10)).pack(side="left", padx=(0, px(8)))
            lbl = tk.Label(fila, text=u, bg=SURFACE, fg=acento["c"], cursor="hand2",
                           font=(FUENTE, 10, "bold underline"))
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda _e, url=u: webbrowser.open(url))
            lbl.bind("<Enter>", lambda _e, w=lbl: w.configure(fg=mezclar(acento["c"], "#000000", 0.25)))
            lbl.bind("<Leave>", lambda _e, w=lbl: w.configure(fg=acento["c"]))
            Boton(fila, "", lambda url=u: self._copiar(url), TEXTO_SUAVE, "borde", IC["copiar"],
                  alto=28, tam=9).pack(side="left", padx=(px(10), 0))
            Boton(fila, "", lambda url=u: webbrowser.open(url), acento["c"], "borde", IC["abrir"],
                  alto=28, tam=9).pack(side="left", padx=(px(6), 0))

    def _copiar(self, texto):
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.cola_log.put(f"Copiado: {texto}")


    def _refrescar_estado(self):
        if self.ang.activo:
            port = self.ang.httpd.server_address[1]
            self.pill_ang.activo(True)
            self.btn_ang.configurar("Detener", IC["stop"], ERROR)
            self._pintar_urls(self.box_ang_urls, urls_para(self.v_ang_host.get().strip(), port), ACENTO_ANG)
        else:
            self.pill_ang.activo(False)
            self.btn_ang.configurar("Iniciar", IC["play"], SUCCESS)
            self._pintar_urls(self.box_ang_urls, [], ACENTO_ANG)

        if self.uvi.activo:
            port = int(self.v_uvi_port.get())
            urls = urls_para(self.v_uvi_host.get().strip(), port)
            urls.append(urls[0] + "/docs")
            self.pill_uvi.activo(True)
            self.btn_uvi.configurar("Detener", IC["stop"], ERROR)
            self._pintar_urls(self.box_uvi_urls, urls, ACENTO_UVI)
        else:
            self.pill_uvi.activo(False)
            self.btn_uvi.configurar("Iniciar", IC["play"], SUCCESS)
            self._pintar_urls(self.box_uvi_urls, [], ACENTO_UVI)
        self.after_idle(self._reacomodar)

    def _reacomodar(self):
        self.update_idletasks()
        for t in self.tarjetas:
            t.actualizar()
        self.update_idletasks()
        self.area._ajustar()

    # ---------------------------------------------------------------- log
    @staticmethod
    def _etiqueta_log(linea):
        low = linea.lower()
        if "error" in low or "traceback" in low or "exception" in low:
            return "err"
        if linea.startswith("[Angular]"):
            return "ang"
        if linea.startswith("[Uvicorn]"):
            return "uvi"
        return "info"

    def _volcar_log(self):
        lineas = []
        try:
            while True:
                lineas.append(self.cola_log.get_nowait())
        except queue.Empty:
            pass
        if lineas:
            self.txt_log.config(state="normal")
            for l in lineas:
                self.txt_log.insert("end", l + "\n", self._etiqueta_log(l))
            if int(self.txt_log.index("end-1c").split(".")[0]) > 3000:
                self.txt_log.delete("1.0", "1000.0")
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")
        self.after(100, self._volcar_log)

    def _limpiar_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")

    def _cerrar(self):
        self._guardar_config()
        self.ang.detener()
        self.uvi.detener()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
