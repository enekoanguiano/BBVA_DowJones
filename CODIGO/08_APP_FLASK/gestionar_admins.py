"""
Gestión de usuarios desde la terminal (también se puede hacer desde /admin/usuarios).

    python gestionar_admins.py crear <usuario> [--rol admin|analista]   crea un usuario (por defecto admin)
    python gestionar_admins.py clave <usuario>        cambia la contraseña
    python gestionar_admins.py rol <usuario> <rol>    cambia el rol
    python gestionar_admins.py desbloquear <usuario>
    python gestionar_admins.py borrar <usuario>
    python gestionar_admins.py listar
    python gestionar_admins.py purgar [dias]          borra registros de más de N días (365 por defecto)

Las contraseñas se piden por teclado (no se muestran) y se guardan cifradas en instance/seguridad.db.
"""
import getpass
import os
import sys

from motor.auth import ROLES, Seguridad, a_hora_local

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.environ.get("SEGURIDAD_DB", os.path.join(BASE, "instance", "seguridad.db"))


def _pedir_clave():
    clave = getpass.getpass("Contraseña (mín. 10 caracteres, letras y números): ")
    if clave != getpass.getpass("Repite la contraseña: "):
        raise ValueError("Las contraseñas no coinciden.")
    return clave


def main(args):
    seg = Seguridad(RUTA_DB, ruta_json_antiguo=os.path.join(BASE, "admins.json"))
    orden = args[0] if args else ""
    if orden not in ("crear", "clave", "rol", "desbloquear", "borrar", "listar", "purgar"):
        print(__doc__)
        return 1
    try:
        if orden == "listar":
            filas = seg.usuarios()
            if not filas:
                print("No hay usuarios.")
            for u in filas:
                estado = "activo" if u["activo"] else "desactivado"
                print(f"{u['usuario']:<20} {ROLES.get(u['rol'], u['rol']):<14} {estado:<12} "
                      f"último acceso: {a_hora_local(u['ultimo_acceso'], '%d/%m/%Y %H:%M')}")
            return 0
        if orden == "purgar":
            dias = int(args[1]) if len(args) > 1 else 365
            n1, n2, n3 = seg.purgar(dias)
            print(f"Eliminados: {n1} conexiones, {n2} sesiones y {n3} registros de auditoría de más de {dias} días.")
            return 0

        if len(args) < 2:
            print(f"Falta el usuario: python gestionar_admins.py {orden} <usuario>")
            return 1
        usuario = args[1].strip().lower()

        if orden == "crear":
            rol = "admin"
            if "--rol" in args:
                rol = args[args.index("--rol") + 1]
            seg.crear(usuario, _pedir_clave(), rol=rol, creado_por="terminal")
            print(f"Usuario '{usuario}' creado con rol {ROLES[rol]}.")
        elif orden == "clave":
            seg.cambiar_clave(usuario, _pedir_clave())
            seg.cerrar_sesiones_de(usuario, "cambio_clave")
            print(f"Contraseña de '{usuario}' cambiada.")
        elif orden == "rol":
            if len(args) < 3:
                print("Indica el rol: admin o analista.")
                return 1
            seg.cambiar_rol(usuario, args[2])
            seg.cerrar_sesiones_de(usuario, "rol")
            print(f"'{usuario}' ahora es {ROLES[args[2]]}.")
        elif orden == "desbloquear":
            seg.desbloquear(usuario)
            print(f"'{usuario}' desbloqueado.")
        elif orden == "borrar":
            seg.borrar(usuario)
            print(f"Usuario '{usuario}' eliminado.")
        seg.auditar("terminal", f"{orden}_usuario", usuario)
    except (ValueError, IndexError) as e:
        print(e or "Faltan argumentos.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
