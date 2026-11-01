"""
Acceso restringido a administradores.

Las cuentas se guardan en `admins.json` con la contraseña cifrada (hash scrypt de
Werkzeug, nunca en texto plano). Se gestionan con `python gestionar_admins.py`.
"""
import json
import os
import secrets
import threading
import time

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

MAX_INTENTOS = 5          # intentos fallidos permitidos...
BLOQUEO_SEG = 5 * 60      # ...antes de bloquear 5 minutos
INACTIVIDAD_SEG = 30 * 60 # la sesión caduca tras 30 min sin uso
ARRANQUE = secrets.token_hex(8)  # cambia en cada arranque: invalida sesiones anteriores
_HASH_FALSO = generate_password_hash(secrets.token_hex(16))  # iguala tiempos si el usuario no existe


class Admins:
    def __init__(self, ruta):
        self.ruta = ruta
        self._lock = threading.Lock()
        self._fallos = {}  # clave (ip, usuario) -> [n_fallos, instante_bloqueo]

    # ----------------------------- almacenamiento -----------------------------
    def _leer(self):
        if not os.path.exists(self.ruta):
            return {}
        with open(self.ruta, encoding="utf-8") as f:
            return json.load(f).get("administradores", {})

    def _guardar(self, datos):
        tmp = self.ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"administradores": datos}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.ruta)

    def usuarios(self):
        return sorted(self._leer())

    def hay_admins(self):
        return bool(self._leer())

    def crear(self, usuario, clave):
        usuario = usuario.strip().lower()
        if not usuario or len(usuario) > 40:
            raise ValueError("El usuario debe tener entre 1 y 40 caracteres.")
        if len(clave) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        with self._lock:
            datos = self._leer()
            datos[usuario] = {"hash": generate_password_hash(clave),
                              "creado": time.strftime("%Y-%m-%d %H:%M")}
            self._guardar(datos)

    def borrar(self, usuario):
        with self._lock:
            datos = self._leer()
            if datos.pop(usuario.strip().lower(), None) is None:
                raise ValueError(f"No existe el administrador '{usuario}'.")
            self._guardar(datos)

    # ------------------------------ verificación ------------------------------
    def bloqueado(self, ip, usuario):
        n, t = self._fallos.get((ip, usuario), (0, 0))
        if n >= MAX_INTENTOS:
            restante = BLOQUEO_SEG - (time.time() - t)
            if restante > 0:
                return int(restante)
            self._fallos.pop((ip, usuario), None)
        return 0

    def verificar(self, ip, usuario, clave):
        usuario = (usuario or "").strip().lower()
        registro = self._leer().get(usuario)
        ok = check_password_hash(registro["hash"] if registro else _HASH_FALSO, clave or "")
        ok = ok and registro is not None
        if ok:
            self._fallos.pop((ip, usuario), None)
        else:
            n, _ = self._fallos.get((ip, usuario), (0, 0))
            self._fallos[(ip, usuario)] = (n + 1, time.time())
        return ok


def clave_secreta(carpeta):
    """SECRET_KEY de la variable de entorno o de un fichero generado una sola vez."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "secret_key")
    if not os.path.exists(ruta):
        with open(ruta, "w") as f:
            f.write(secrets.token_hex(32))
    with open(ruta) as f:
        return f.read().strip()


def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_valido(token):
    return bool(token) and secrets.compare_digest(token, session.get("csrf", ""))


def proteger(app, rutas_libres=("login", "static")):
    """Exige sesión de administrador en todas las rutas salvo las libres."""
    @app.before_request
    def _exigir_login():
        if request.endpoint in rutas_libres:
            return None
        ahora = time.time()
        caducada = (session.get("arranque") != ARRANQUE
                    or ahora - session.get("ultimo", 0) > INACTIVIDAD_SEG)
        if session.get("admin") and caducada:
            session.clear()
        if session.get("admin"):
            session["ultimo"] = ahora
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Sesión caducada. Vuelve a iniciar sesión."}), 401
            return redirect(url_for("login", siguiente=request.path))
        if request.method == "POST" and not csrf_valido(
                request.headers.get("X-CSRF-Token") or request.form.get("csrf")):
            return jsonify({"error": "Token de seguridad no válido. Recarga la página."}), 403
        return None



def iniciar_sesion(usuario):
    session.clear()
    session.permanent = False          # la cookie desaparece al cerrar el navegador
    session["admin"] = usuario
    session["arranque"] = ARRANQUE
    session["ultimo"] = time.time()
    token_csrf()
