
import getpass
import secrets
import string

import bcrypt


def generar_contrasena(longitud=20):
    """Genera una contraseña aleatoria segura."""
    caracteres = (
        string.ascii_letters
        + string.digits
        + "!@#$%&*-_"
    )

    return "".join(
        secrets.choice(caracteres)
        for _ in range(longitud)
    )


def generar_hash(contrasena: str) -> str:
    """Genera un hash bcrypt con sal aleatoria."""
    datos = contrasena.encode("utf-8")

    if len(datos) > 72:
        raise ValueError(
            "La contraseña no puede superar 72 bytes UTF-8."
        )

    sal = bcrypt.gensalt(rounds=12)
    hash_generado = bcrypt.hashpw(datos, sal)

    return hash_generado.decode("utf-8")


def verificar_contrasena(
    contrasena: str,
    hash_guardado: str
) -> bool:
    """Comprueba una contraseña contra su hash."""
    return bcrypt.checkpw(
        contrasena.encode("utf-8"),
        hash_guardado.encode("utf-8")
    )


if __name__ == "__main__":
    print("=== SEGURIDAD ESART ===")
    print("1. Generar contraseña segura")
    print("2. Introducir mi propia contraseña")

    opcion = input("Seleccione opción: ").strip()

    if opcion == "1":
        contrasena = generar_contrasena()
        print("\nContraseña generada:", contrasena)

    elif opcion == "2":
        contrasena = getpass.getpass(
            "Ingrese la contraseña: "
        )

    else:
        raise SystemExit("Opción inválida")

    if not contrasena:
        raise SystemExit("La contraseña no puede estar vacía")

    hash_final = generar_hash(contrasena)

    print("\nHash bcrypt:")
    print(hash_final)

    print("\nVerificación:")
    print(verificar_contrasena(contrasena, hash_final))
