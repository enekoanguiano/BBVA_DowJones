"""
Seguridad y gestión de usuarios.

Todo se guarda en una base SQLite (`instance/seguridad.db`, librería estándar, sin
dependencias nuevas):

- usuarios     cuentas con rol, estado, contraseña cifrada (hash scrypt de Werkzeug)
- conexiones   cada intento de acceso, correcto o fallido, y cada cierre de sesión
- sesiones     sesiones abiertas en el servidor: se puede ver quién está conectado y expulsarle
- auditoria    qué ha hecho cada usuario dentro de la aplicación

Si existe el antiguo `admins.json`, sus cuentas se importan automáticamente como
administradores la primera vez que arranca la app.
"""
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from flask import g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

ROLES = {
    "admin": "Administrador",   # usa el simulador y gestiona usuarios, conexiones y auditoría
    "analista": "Analista",     # solo usa el simulador
}

MAX_INTENTOS = 5            # fallos con el mismo usuario desde la misma IP...
BLOQUEO_SEG = 5 * 60        # ...bloquean esa combinación 5 minutos
MAX_FALLOS_CUENTA = 10      # fallos acumulados en una cuenta desde cualquier IP...
BLOQUEO_CUENTA_MIN = 15     # ...la bloquean 15 minutos (un admin puede desbloquearla)
MAX_FALLOS_IP = 30          # fallos desde una misma IP en 15 min, sea cual sea el usuario
INACTIVIDAD_SEG = 30 * 60   # la sesión caduca tras 30 min sin uso
_HASH_FALSO = generate_password_hash(secrets.token_hex(16))  # iguala tiempos si el usuario no existe

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    usuario          TEXT PRIMARY KEY,
    email            TEXT,
    hash             TEXT NOT NULL,
    rol              TEXT NOT NULL DEFAULT 'analista',
    activo           INTEGER NOT NULL DEFAULT 1,
    debe_cambiar     INTEGER NOT NULL DEFAULT 0,
    fallos           INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta  TEXT,
    ultimo_acceso    TEXT,
    ultima_ip        TEXT,
    clave_cambiada   TEXT,
    creado           TEXT NOT NULL,
    creado_por       TEXT
);
CREATE TABLE IF NOT EXISTS conexiones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT NOT NULL,
    usuario     TEXT,
    ip          TEXT,
    navegador   TEXT,
    correcto    INTEGER NOT NULL,
    evento      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_conexiones_fecha   ON conexiones(fecha);
CREATE INDEX IF NOT EXISTS ix_conexiones_usuario ON conexiones(usuario);
CREATE INDEX IF NOT EXISTS ix_conexiones_ip      ON conexiones(ip);
CREATE TABLE IF NOT EXISTS sesiones (
    sid             TEXT PRIMARY KEY,
    usuario         TEXT NOT NULL,
    ip              TEXT,
    navegador       TEXT,
    inicio          TEXT NOT NULL,
    ultima          TEXT NOT NULL,
    cerrada         TEXT,
    motivo_cierre   TEXT
);
CREATE INDEX IF NOT EXISTS ix_sesiones_abiertas ON sesiones(cerrada);
CREATE TABLE IF NOT EXISTS auditoria (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha    TEXT NOT NULL,
    usuario  TEXT,
    accion   TEXT NOT NULL,
    objeto   TEXT,
    detalle  TEXT,
    ip       TEXT
);
CREATE INDEX IF NOT EXISTS ix_auditoria_fecha ON auditoria(fecha);
"""

# Textos legibles para los códigos de evento
EVENTOS = {
    "acceso": "Acceso correcto",
    "salida": "Cierre de sesión",
    "clave_incorrecta": "Contraseña incorrecta",
    "usuario_inexistente": "Usuario inexistente",
    "usuario_desactivado": "Usuario desactivado",
    "cuenta_bloqueada": "Cuenta bloqueada",
    "demasiados_intentos": "Demasiados intentos",
}
MOTIVOS_CIERRE = {
    "salida": "Cerró sesión", "inactividad": "Inactividad", "admin": "Expulsado por un admin",
    "desactivado": "Usuario desactivado", "cambio_clave": "Cambio de contraseña",
    "reinicio": "Reinicio de la app", "rol": "Cambio de rol",
}


def ahora():
    """Fecha UTC como texto ordenable 'AAAA-MM-DD HH:MM:SS'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def hace(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


def a_hora_local(texto, formato="%d/%m/%Y %H:%M:%S"):
    """Convierte una fecha UTC guardada a la hora local del servidor para mostrarla."""
    if not texto:
        return "—"
    dt = datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime(formato)


def problemas_clave(clave):
    """Política de contraseñas. Devuelve la lista de requisitos que no cumple."""
    falta = []
    if len(clave or "") < 10:
        falta.append("al menos 10 caracteres")
    if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", clave or ""):
        falta.append("alguna letra")
    if not re.search(r"\d", clave or ""):
        falta.append("algún número")
    return falta


def _validar_usuario(usuario):
    usuario = (usuario or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{2,40}", usuario):
        raise ValueError("El usuario debe tener entre 2 y 40 caracteres: letras, números, punto, guion o guion bajo.")
    return usuario


class Seguridad:
    def __init__(self, ruta_db, ruta_json_antiguo=None):
        self.ruta = ruta_db
        os.makedirs(os.path.dirname(ruta_db) or ".", exist_ok=True)
        self._fallos = {}      # (ip, usuario) -> (n, instante)   en memoria, como antes
        self._fallos_ip = {}   # ip -> [instantes de fallo]
        self._lock = threading.Lock()
        with self._con() as c:
            c.executescript(ESQUEMA)
        if ruta_json_antiguo:
            self._importar_json(ruta_json_antiguo)

    @contextmanager
    def _con(self):
        con = sqlite3.connect(self.ruta, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _importar_json(self, ruta):
        if not os.path.exists(ruta):
            return
        with self._con() as c:
            if c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
                return
            with open(ruta, encoding="utf-8") as f:
                antiguos = json.load(f).get("administradores", {})
            for u, d in antiguos.items():
                c.execute("INSERT INTO usuarios (usuario, hash, rol, creado, creado_por) VALUES (?,?,?,?,?)",
                          (u, d["hash"], "admin", ahora(), "importado de admins.json"))
        os.replace(ruta, ruta + ".importado")

    def crear_admin_inicial(self):
        """Crea admin/admin solo si la base no tiene usuarios (instalación de prueba).

        La contraseña es provisional y debe cambiarse en el primer acceso.
        No recrea ni restablece la cuenta en arranques posteriores.
        """
        with self._con() as c:
            if c.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
                return False
            c.execute(
                """INSERT INTO usuarios
                   (usuario, hash, rol, debe_cambiar, creado, creado_por)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("admin", generate_password_hash("admin"), "admin", 1,
                 ahora(), "instalacion_inicial")
            )
        return True

    # ------------------------------------------------------------ usuarios
    def hay_admins(self):
        with self._con() as c:
            return c.execute("SELECT 1 FROM usuarios WHERE rol='admin' AND activo=1 LIMIT 1").fetchone() is not None

    def usuario(self, usuario):
        with self._con() as c:
            return c.execute("SELECT * FROM usuarios WHERE usuario=?", (usuario,)).fetchone()

    def usuarios(self):
        with self._con() as c:
            return c.execute("SELECT * FROM usuarios ORDER BY usuario").fetchall()

    def crear(self, usuario, clave, rol="analista", email=None, creado_por=None, debe_cambiar=False):
        usuario = _validar_usuario(usuario)
        if rol not in ROLES:
            raise ValueError("Rol no válido.")
        if falta := problemas_clave(clave):
            raise ValueError("La contraseña necesita " + ", ".join(falta) + ".")
        with self._con() as c:
            if c.execute("SELECT 1 FROM usuarios WHERE usuario=?", (usuario,)).fetchone():
                raise ValueError(f"Ya existe el usuario '{usuario}'.")
            c.execute("""INSERT INTO usuarios (usuario, email, hash, rol, debe_cambiar, clave_cambiada, creado, creado_por)
                         VALUES (?,?,?,?,?,?,?,?)""",
                      (usuario, (email or "").strip().lower() or None, generate_password_hash(clave), rol,
                       int(debe_cambiar), ahora(), ahora(), creado_por))
        return usuario

    def cambiar_clave(self, usuario, clave, debe_cambiar=False):
        if falta := problemas_clave(clave):
            raise ValueError("La contraseña necesita " + ", ".join(falta) + ".")
        with self._con() as c:
            n = c.execute("UPDATE usuarios SET hash=?, debe_cambiar=?, clave_cambiada=? WHERE usuario=?",
                          (generate_password_hash(clave), int(debe_cambiar), ahora(), usuario)).rowcount
        if not n:
            raise ValueError(f"No existe el usuario '{usuario}'.")

    def _quedaria_sin_admin(self, c, usuario):
        otros = c.execute("SELECT COUNT(*) FROM usuarios WHERE rol='admin' AND activo=1 AND usuario<>?",
                          (usuario,)).fetchone()[0]
        return otros == 0

    def cambiar_rol(self, usuario, rol):
        if rol not in ROLES:
            raise ValueError("Rol no válido.")
        with self._con() as c:
            if rol != "admin" and self._quedaria_sin_admin(c, usuario):
                raise ValueError("Debe quedar al menos un administrador activo.")
            c.execute("UPDATE usuarios SET rol=? WHERE usuario=?", (rol, usuario))

    def activar(self, usuario, activo):
        with self._con() as c:
            if not activo and self._quedaria_sin_admin(c, usuario):
                raise ValueError("Debe quedar al menos un administrador activo.")
            c.execute("UPDATE usuarios SET activo=? WHERE usuario=?", (int(activo), usuario))
        if not activo:
            self.cerrar_sesiones_de(usuario, "desactivado")

    def borrar(self, usuario):
        usuario = (usuario or "").strip().lower()
        with self._con() as c:
            fila = c.execute("SELECT rol FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
            if fila is None:
                raise ValueError(f"No existe el usuario '{usuario}'.")
            if fila["rol"] == "admin" and self._quedaria_sin_admin(c, usuario):
                raise ValueError("Debe quedar al menos un administrador activo.")
            c.execute("DELETE FROM usuarios WHERE usuario=?", (usuario,))
        self.cerrar_sesiones_de(usuario, "desactivado")

    def desbloquear(self, usuario):
        with self._con() as c:
            c.execute("UPDATE usuarios SET fallos=0, bloqueado_hasta=NULL WHERE usuario=?", (usuario,))
        with self._lock:
            for k in [k for k in self._fallos if k[1] == usuario]:
                self._fallos.pop(k)

    # ------------------------------------------------------------ acceso
    def _fallos_recientes_ip(self, ip):
        limite = time.time() - 15 * 60
        lista = [t for t in self._fallos_ip.get(ip, []) if t > limite]
        self._fallos_ip[ip] = lista
        return len(lista)

    def bloqueado(self, ip, usuario):
        """Segundos de espera si (ip, usuario) o la IP superan el límite de fallos; 0 si no."""
        with self._lock:
            if self._fallos_recientes_ip(ip) >= MAX_FALLOS_IP:
                return 15 * 60
            n, t = self._fallos.get((ip, usuario), (0, 0))
            if n >= MAX_INTENTOS:
                restante = BLOQUEO_SEG - (time.time() - t)
                if restante > 0:
                    return int(restante)
                self._fallos.pop((ip, usuario), None)
        return 0

    def autenticar(self, usuario, clave, ip, navegador):
        """Comprueba credenciales, aplica bloqueos y registra la conexión. Devuelve la fila del usuario o None."""
        usuario = (usuario or "").strip().lower()[:40]
        if self.bloqueado(ip, usuario):
            self.registrar_conexion(usuario, ip, navegador, False, "demasiados_intentos")
            return None
        reg = self.usuario(usuario)
        ok = check_password_hash(reg["hash"] if reg else _HASH_FALSO, clave or "") and reg is not None

        evento = "acceso"
        if reg is None:
            evento = "usuario_inexistente"
        elif not ok:
            evento = "clave_incorrecta"
        elif not reg["activo"]:
            evento, ok = "usuario_desactivado", False
        elif reg["bloqueado_hasta"] and reg["bloqueado_hasta"] > ahora():
            evento, ok = "cuenta_bloqueada", False

        with self._con() as c:
            if ok:
                c.execute("UPDATE usuarios SET fallos=0, bloqueado_hasta=NULL, ultimo_acceso=?, ultima_ip=? WHERE usuario=?",
                          (ahora(), ip, usuario))
            elif evento == "clave_incorrecta":
                fallos = reg["fallos"] + 1
                hasta = None
                if fallos >= MAX_FALLOS_CUENTA:
                    fallos, hasta = 0, (datetime.now(timezone.utc) + timedelta(minutes=BLOQUEO_CUENTA_MIN)
                                        ).strftime("%Y-%m-%d %H:%M:%S")
                c.execute("UPDATE usuarios SET fallos=?, bloqueado_hasta=COALESCE(?, bloqueado_hasta) WHERE usuario=?",
                          (fallos, hasta, usuario))
        with self._lock:
            if ok:
                self._fallos.pop((ip, usuario), None)
            else:
                n, _ = self._fallos.get((ip, usuario), (0, 0))
                self._fallos[(ip, usuario)] = (n + 1, time.time())
                self._fallos_ip.setdefault(ip, []).append(time.time())
        self.registrar_conexion(usuario, ip, navegador, ok, evento)
        return reg if ok else None

    @staticmethod
    def autenticar_clave(reg, clave):
        """Solo comprueba la contraseña (para confirmar la actual al cambiarla)."""
        return reg is not None and check_password_hash(reg["hash"], clave or "")

    def registrar_conexion(self, usuario, ip, navegador, correcto, evento):
        with self._con() as c:
            c.execute("INSERT INTO conexiones (fecha, usuario, ip, navegador, correcto, evento) VALUES (?,?,?,?,?,?)",
                      (ahora(), usuario, ip, (navegador or "")[:300], int(correcto), evento))

    # ------------------------------------------------------------ sesiones
    def abrir_sesion(self, usuario, ip, navegador):
        sid = secrets.token_urlsafe(32)
        with self._con() as c:
            c.execute("INSERT INTO sesiones (sid, usuario, ip, navegador, inicio, ultima) VALUES (?,?,?,?,?,?)",
                      (sid, usuario, ip, (navegador or "")[:300], ahora(), ahora()))
        return sid

    def sesion(self, sid):
        """Sesión abierta con los datos actuales del usuario, o None si no existe o está cerrada."""
        if not sid:
            return None
        with self._con() as c:
            return c.execute("""SELECT s.*, u.rol, u.activo, u.debe_cambiar, u.email
                                FROM sesiones s JOIN usuarios u ON u.usuario = s.usuario
                                WHERE s.sid=? AND s.cerrada IS NULL""", (sid,)).fetchone()

    def tocar_sesion(self, sid):
        with self._con() as c:
            c.execute("UPDATE sesiones SET ultima=? WHERE sid=?", (ahora(), sid))

    def cerrar_sesion(self, sid, motivo):
        with self._con() as c:
            c.execute("UPDATE sesiones SET cerrada=?, motivo_cierre=? WHERE sid=? AND cerrada IS NULL",
                      (ahora(), motivo, sid))

    def cerrar_sesiones_de(self, usuario, motivo, excepto=None):
        with self._con() as c:
            c.execute("UPDATE sesiones SET cerrada=?, motivo_cierre=? WHERE usuario=? AND cerrada IS NULL AND sid<>?",
                      (ahora(), motivo, usuario, excepto or ""))

    def cerrar_todas(self, motivo):
        with self._con() as c:
            c.execute("UPDATE sesiones SET cerrada=?, motivo_cierre=? WHERE cerrada IS NULL", (ahora(), motivo))

    def sesiones_activas(self):
        limite = hace(seconds=INACTIVIDAD_SEG)
        with self._con() as c:
            return c.execute("""SELECT s.*, u.rol FROM sesiones s JOIN usuarios u ON u.usuario = s.usuario
                                WHERE s.cerrada IS NULL AND s.ultima > ? ORDER BY s.ultima DESC""",
                             (limite,)).fetchall()

    def ultimas_sesiones(self, usuario, limite=20):
        with self._con() as c:
            return c.execute("SELECT * FROM sesiones WHERE usuario=? ORDER BY inicio DESC LIMIT ?",
                             (usuario, limite)).fetchall()

    # ------------------------------------------------------------ consultas para el panel
    def conexiones(self, usuario=None, ip=None, resultado=None, desde=None, hasta=None,
                   limite=50, desplazamiento=0, usuario_exacto=None):
        where, args = [], []
        if usuario_exacto:
            where.append("usuario = ?"); args.append(usuario_exacto)
        if usuario:
            where.append("usuario LIKE ?"); args.append(f"%{usuario.strip().lower()}%")
        if ip:
            where.append("ip = ?"); args.append(ip.strip())
        if resultado == "ok":
            where.append("correcto = 1")
        elif resultado == "fallo":
            where.append("correcto = 0")
        if desde:
            where.append("fecha >= ?"); args.append(_utc_desde_local(desde))
        if hasta:
            where.append("fecha < ?"); args.append(_utc_desde_local(hasta, dia_siguiente=True))
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        with self._con() as c:
            total = c.execute(f"SELECT COUNT(*) FROM conexiones {sql_where}", args).fetchone()[0]
            filas = c.execute(f"SELECT * FROM conexiones {sql_where} ORDER BY id DESC LIMIT ? OFFSET ?",
                              args + [limite, desplazamiento]).fetchall()
        return filas, total

    def ips_sospechosas(self, horas=24, minimo=5):
        with self._con() as c:
            return c.execute("""SELECT ip, COUNT(*) AS fallos, COUNT(DISTINCT usuario) AS usuarios, MAX(fecha) AS ultima
                                FROM conexiones WHERE correcto=0 AND evento<>'salida' AND fecha >= ?
                                GROUP BY ip HAVING COUNT(*) >= ? ORDER BY fallos DESC LIMIT 10""",
                             (hace(hours=horas), minimo)).fetchall()

    def resumen(self):
        h24 = hace(hours=24)
        with self._con() as c:
            q = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
            return {
                "conectados": q("SELECT COUNT(DISTINCT usuario) FROM sesiones WHERE cerrada IS NULL AND ultima > ?",
                                hace(seconds=INACTIVIDAD_SEG)),
                "accesos_24h": q("SELECT COUNT(*) FROM conexiones WHERE evento='acceso' AND fecha >= ?", h24),
                "fallos_24h": q("SELECT COUNT(*) FROM conexiones WHERE correcto=0 AND fecha >= ?", h24),
                "bloqueados": q("SELECT COUNT(*) FROM usuarios WHERE bloqueado_hasta > ?", ahora()),
                "usuarios": q("SELECT COUNT(*) FROM usuarios WHERE activo=1"),
                "simulaciones_24h": q("SELECT COUNT(*) FROM auditoria WHERE accion IN "
                                      "('simulacion','frontera','valoracion_opcion') AND fecha >= ?", h24),
            }

    def accesos_por_dia(self, dias=14):
        with self._con() as c:
            return c.execute("""SELECT substr(fecha,1,10) AS dia, SUM(correcto) AS ok,
                                       SUM(CASE WHEN correcto=0 THEN 1 ELSE 0 END) AS fallos
                                FROM conexiones WHERE evento<>'salida' AND fecha >= ?
                                GROUP BY dia ORDER BY dia""", (hace(days=dias),)).fetchall()

    # ------------------------------------------------------------ auditoría
    def auditar(self, usuario, accion, objeto=None, detalle=None, ip=None):
        with self._con() as c:
            c.execute("INSERT INTO auditoria (fecha, usuario, accion, objeto, detalle, ip) VALUES (?,?,?,?,?,?)",
                      (ahora(), usuario, accion, (objeto or "")[:200] or None, (detalle or "")[:1000] or None, ip))

    def auditoria(self, usuario=None, accion=None, limite=50, desplazamiento=0):
        where, args = [], []
        if usuario:
            where.append("usuario = ?"); args.append(usuario)
        if accion:
            where.append("accion = ?"); args.append(accion)
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        with self._con() as c:
            total = c.execute(f"SELECT COUNT(*) FROM auditoria {sql_where}", args).fetchone()[0]
            filas = c.execute(f"SELECT * FROM auditoria {sql_where} ORDER BY id DESC LIMIT ? OFFSET ?",
                              args + [limite, desplazamiento]).fetchall()
            acciones = [r[0] for r in c.execute("SELECT DISTINCT accion FROM auditoria ORDER BY accion")]
        return filas, total, acciones

    # ------------------------------------------------------------ mantenimiento
    def purgar(self, dias):
        """Borra conexiones, sesiones cerradas y auditoría de más de `dias` días (retención RGPD)."""
        limite = hace(days=dias)
        with self._con() as c:
            n1 = c.execute("DELETE FROM conexiones WHERE fecha < ?", (limite,)).rowcount
            n2 = c.execute("DELETE FROM sesiones WHERE cerrada IS NOT NULL AND cerrada < ?", (limite,)).rowcount
            n3 = c.execute("DELETE FROM auditoria WHERE fecha < ?", (limite,)).rowcount
        return n1, n2, n3


def _utc_desde_local(fecha_iso, dia_siguiente=False):
    """'2026-11-02' en hora local del servidor -> texto UTC comparable con las columnas."""
    try:
        d = datetime.strptime(fecha_iso, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Fecha no válida.")
    if dia_siguiente:
        d += timedelta(days=1)
    return d.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- Flask
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


def ip_cliente():
    return request.remote_addr or "?"


def navegador():
    return request.headers.get("User-Agent", "")


def auditar(accion, objeto=None, detalle=None):
    """Atajo para registrar una acción del usuario de la petición actual."""
    g.seguridad.auditar(session.get("usuario"), accion, objeto, detalle, ip_cliente())


def proteger(app, seg, rutas_libres=("login", "static")):
    """Exige sesión válida en todas las rutas salvo las libres y rol admin en /admin."""
    seg.cerrar_todas("reinicio")  # al arrancar, nadie sigue dentro (como hacía la versión anterior)

    @app.before_request
    def _exigir_login():
        g.seguridad = seg
        g.usuario = None
        if request.endpoint in rutas_libres:
            return None

        es_api = request.path.startswith("/api/")
        sid = session.get("sid")
        s = seg.sesion(sid)
        motivo = None
        if s is None:
            motivo = "sin_sesion"
        elif not s["activo"]:
            motivo = "desactivado"
        elif s["ultima"] < hace(seconds=INACTIVIDAD_SEG):
            motivo = "inactividad"

        if motivo:
            if s is not None:
                seg.cerrar_sesion(sid, motivo)
            session.clear()
            if es_api:
                return jsonify({"error": "Sesión caducada. Vuelve a iniciar sesión."}), 401
            return redirect(url_for("login", siguiente=request.path))

        g.usuario = s
        if s["ultima"] < hace(seconds=60):   # como mucho una escritura por minuto
            seg.tocar_sesion(sid)

        if request.method == "POST" and not csrf_valido(
                request.headers.get("X-CSRF-Token") or request.form.get("csrf")):
            if es_api:
                return jsonify({"error": "Token de seguridad no válido. Recarga la página."}), 403
            return render_template("error.html", titulo="Formulario caducado",
                                   mensaje="Recarga la página e inténtalo de nuevo."), 403

        # Contraseña provisional: hay que cambiarla antes de hacer nada más
        if s["debe_cambiar"] and request.endpoint not in ("cuenta_clave", "logout"):
            if es_api:
                return jsonify({"error": "Debes cambiar tu contraseña provisional."}), 403
            return redirect(url_for("cuenta_clave"))

        if request.path.startswith("/admin") and s["rol"] != "admin":
            auditar("acceso_denegado", request.path)
            return render_template("error.html", titulo="Sin permiso",
                                   mensaje="Esta sección es solo para administradores."), 403
        return None


def iniciar_sesion(seg, usuario):
    session.clear()
    session.permanent = False          # la cookie desaparece al cerrar el navegador
    session["usuario"] = usuario
    session["sid"] = seg.abrir_sesion(usuario, ip_cliente(), navegador())
    token_csrf()
