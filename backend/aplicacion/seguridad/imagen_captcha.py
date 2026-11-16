"""PNG fijo y acotado con fuente Aileron embebida en Pillow, sin buscar recursos externos."""

import io
import secrets

from PIL import Image, ImageDraw, ImageFont

ALFABETO = "ACDEFGHJKMNPQRTUVWXY34679"  # Sin 0/O, 1/I/L, 2/Z, 5/S, 8/B.
ANCHO, ALTO = 312, 96
MAXIMO_PNG = 65536


def generar_texto() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(6))


def generar_png(codigo: str) -> bytes:
    if len(codigo) != 6 or any(c not in ALFABETO for c in codigo):
        raise ValueError("Entrada de imagen no autorizada")
    imagen = Image.new("RGB", (ANCHO, ALTO), (241, 247, 250))
    dibujo = ImageDraw.Draw(imagen)
    for _ in range(260):
        x, y = secrets.randbelow(ANCHO), secrets.randbelow(ALTO)
        dibujo.point((x, y), fill=(150, secrets.randbelow(45) + 150, 190))
    fuente = ImageFont.load_default(size=43)
    for i, c in enumerate(codigo):
        letra = Image.new("RGBA", (48, 80), (0, 0, 0, 0))
        ImageDraw.Draw(letra).text((5, 10), c, font=fuente, fill=(15, 55 + secrets.randbelow(35), 100, 255))
        letra = letra.rotate(secrets.randbelow(17) - 8, resample=Image.Resampling.BICUBIC)
        imagen.paste(letra, (10 + i * 49, 5 + secrets.randbelow(8)), letra)
    for _ in range(3):
        y = secrets.randbelow(ALTO)
        dibujo.line(
            [(0, y), (ANCHO // 2, secrets.randbelow(ALTO)), (ANCHO, y)], fill=(125, 155, 175), width=1
        )
    salida = io.BytesIO()
    imagen.save(salida, format="PNG", compress_level=6)
    png = salida.getvalue()
    if len(png) > MAXIMO_PNG:
        raise ValueError("La imagen supera el límite permitido")
    return png
