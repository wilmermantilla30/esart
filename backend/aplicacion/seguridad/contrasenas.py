"""
Manejo de contraseñas con bcrypt directo (sin passlib: es incompatible con bcrypt 5.x).

Es el ÚNICO lugar del proyecto que genera o verifica hashes de contraseña.
La API, el administrador inicial y la herramienta herramientas/generar_hash.py
llaman a estas funciones en lugar de usar bcrypt por su cuenta.
"""

import bcrypt

# Costo de bcrypt: 12 rondas es el equilibrio habitual entre seguridad y tiempo
# de respuesta del login (alrededor de 0.2-0.3 s por verificación).
RONDAS_BCRYPT = 12

# bcrypt solo procesa los primeros 72 bytes, y bcrypt 5 rechaza entradas más largas.
LONGITUD_MAXIMA_CONTRASENA_BYTES = 72

# Hash de una contraseña aleatoria que nadie conoce. Se usa para verificar contra
# "algo" cuando el usuario no existe, así el login tarda lo mismo exista o no el
# usuario y no se puede averiguar qué usuarios existen midiendo el tiempo.
HASH_FICTICIO_PARA_TIEMPO_CONSTANTE = bcrypt.hashpw(b"usuario-inexistente", bcrypt.gensalt(RONDAS_BCRYPT))


def generar_hash_contrasena(contrasena: str) -> str:
    """Devuelve el hash bcrypt (con sal aleatoria) de una contraseña."""
    datos_contrasena = contrasena.encode("utf-8")
    if len(datos_contrasena) > LONGITUD_MAXIMA_CONTRASENA_BYTES:
        raise ValueError(f"La contraseña no puede superar {LONGITUD_MAXIMA_CONTRASENA_BYTES} bytes UTF-8.")
    return bcrypt.hashpw(datos_contrasena, bcrypt.gensalt(RONDAS_BCRYPT)).decode("utf-8")


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    """
    Indica si la contraseña corresponde al hash guardado.

    Nunca lanza excepción por datos raros (contraseña demasiado larga, hash
    dañado): en esos casos responde False, igual que una contraseña incorrecta,
    para que el login dé siempre el mismo error genérico.
    """
    datos_contrasena = contrasena.encode("utf-8")
    if len(datos_contrasena) > LONGITUD_MAXIMA_CONTRASENA_BYTES:
        # Aun así se gasta el tiempo de una verificación, para no delatar el motivo.
        bcrypt.checkpw(b"x", HASH_FICTICIO_PARA_TIEMPO_CONSTANTE)
        return False
    try:
        return bcrypt.checkpw(datos_contrasena, hash_guardado.encode("utf-8"))
    except ValueError:
        return False


def gastar_tiempo_de_verificacion() -> None:
    """
    Hace una verificación bcrypt inútil.

    Se llama cuando el usuario no existe, para que esa respuesta tarde lo mismo
    que la de un usuario existente con contraseña incorrecta.
    """
    bcrypt.checkpw(b"x", HASH_FICTICIO_PARA_TIEMPO_CONSTANTE)
