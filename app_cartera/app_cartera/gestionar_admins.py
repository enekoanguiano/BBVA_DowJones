"""
Gestión de administradores del simulador.

    python gestionar_admins.py crear <usuario>     crea o cambia la contraseña
    python gestionar_admins.py borrar <usuario>
    python gestionar_admins.py listar

La contraseña se pide por teclado (no se muestra) y se guarda cifrada en admins.json.
"""
import getpass
import os
import sys

from motor.auth import Admins

RUTA = os.environ.get("ADMINS_PATH",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "admins.json"))


def main(args):
    admins = Admins(RUTA)
    if not args or args[0] not in ("crear", "borrar", "listar"):
        print(__doc__)
        return 1
    if args[0] == "listar":
        usuarios = admins.usuarios()
        print("\n".join(usuarios) if usuarios else "No hay administradores.")
        return 0
    if len(args) < 2:
        print(f"Falta el usuario: python gestionar_admins.py {args[0]} <usuario>")
        return 1
    usuario = args[1]
    try:
        if args[0] == "borrar":
            admins.borrar(usuario)
            print(f"Administrador '{usuario}' eliminado.")
        else:
            clave = getpass.getpass("Contraseña (mín. 8 caracteres): ")
            if clave != getpass.getpass("Repite la contraseña: "):
                print("Las contraseñas no coinciden.")
                return 1
            admins.crear(usuario, clave)
            print(f"Administrador '{usuario.strip().lower()}' guardado.")
    except ValueError as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
