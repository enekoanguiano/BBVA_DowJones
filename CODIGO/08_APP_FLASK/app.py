"""
Simulador de carteras – Reto 9
==============================
Aplicación Flask que, a partir de los tickers y pesos de una o varias carteras,
proyecta su comportamiento futuro con Monte Carlo (GBM correlacionado calibrado
sobre df_diario) y valora la call asiática del notebook con las redes RNN/GRU/LSTM.

Ejecutar:  python app.py      ->  http://127.0.0.1:5000
"""
import os

import numpy as np
from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for

from motor.auth import (ROLES, Seguridad, a_hora_local, auditar, clave_secreta, csrf_valido,
                        iniciar_sesion, ip_cliente, navegador, problemas_clave, proteger, token_csrf)
from motor.datos import cargar_precios
from motor.opcion import valorar
from motor.redes import GestorRedes
from motor.simulacion import calibrar, frontera, historico_cartera, simular_cartera

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.environ.get(
    "DATA_PATH",
    os.path.join(BASE, "..", "..", "DATOS", "TRANSFORMADOS", "df_diario.parquet")
)
MODELOS_DIR = os.environ.get(
    "MODELOS_DIR",
    os.path.join(BASE, "..", "..", "DATOS", "MODELOS")
)

MAX_SIMS = 50_000
MAX_CARTERAS = 4

app = Flask(__name__)
app.config.update(
    SECRET_KEY="equipomorado",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SEGURA") == "1",
)
if os.environ.get("DETRAS_DE_PROXY") == "1":
    # Detrás de Nginx u otro proxy: registrar la IP real del usuario (cabecera X-Forwarded-For)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
SEG = Seguridad(os.environ.get("SEGURIDAD_DB", os.path.join(BASE, "instance", "seguridad.db")),
                ruta_json_antiguo=os.path.join(BASE, "admins.json"))  # se importa una sola vez si existe
proteger(app, SEG)
app.add_template_filter(a_hora_local, "hora_local")

from panel import bp as panel_bp  # noqa: E402

app.register_blueprint(panel_bp)
PRECIOS = cargar_precios(DATA_PATH)
REDES = GestorRedes(MODELOS_DIR)


class ErrorEntrada(ValueError):
    pass


@app.errorhandler(ErrorEntrada)
@app.errorhandler(ValueError)
def _error(e):
    return jsonify({"error": str(e)}), 400


def _num(d, clave, defecto, minimo, maximo, tipo=float):
    try:
        v = tipo(d.get(clave, defecto))
    except (TypeError, ValueError):
        raise ErrorEntrada(f"'{clave}' no es un número válido.")
    if not (minimo <= v <= maximo):
        raise ErrorEntrada(f"'{clave}' debe estar entre {minimo} y {maximo}.")
    return v


def _tickers(lista):
    tks = [str(t).strip().upper() for t in (lista or []) if str(t).strip()]
    if not tks:
        raise ErrorEntrada("Indica al menos un ticker.")
    desconocidos = [t for t in tks if t not in PRECIOS.columns]
    if desconocidos:
        raise ErrorEntrada(f"Ticker(s) no disponibles: {', '.join(desconocidos)}. "
                           f"Disponibles: {', '.join(PRECIOS.columns)}")
    if len(set(tks)) != len(tks):
        raise ErrorEntrada("Hay tickers repetidos en la misma cartera.")
    return tks


def _pesos(pesos, n):
    if pesos is None or len(pesos) == 0:
        return np.full(n, 1.0 / n)
    if len(pesos) != n:
        raise ErrorEntrada("Debe haber un peso por ticker.")
    try:
        w = np.array([float(p) for p in pesos])
    except (TypeError, ValueError):
        raise ErrorEntrada("Los pesos deben ser números.")
    if (w < 0).any():
        raise ErrorEntrada("Los pesos no pueden ser negativos (solo posiciones largas).")
    if w.sum() <= 0:
        raise ErrorEntrada("La suma de los pesos debe ser positiva.")
    return w / w.sum()  # se normalizan a 100 %


@app.context_processor
def _plantillas():
    u = g.get("usuario")
    return {"csrf_token": token_csrf, "usuario_actual": u["usuario"] if u else None,
            "es_admin": bool(u and u["rol"] == "admin"), "ROLES": ROLES}


@app.after_request
def _cabeceras(resp):
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.endpoint != "static":
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# ------------------------------- Acceso ------------------------------------ #
@app.route("/login", methods=["GET", "POST"])
def login():
    if SEG.sesion(session.get("sid")):
        return redirect(url_for("index"))
    error, usuario = None, ""
    if not SEG.hay_admins():
        error = ("Todavía no hay administradores. Crea uno en la terminal con: "
                 "python gestionar_admins.py crear <usuario>")
    elif request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip().lower()
        ip = ip_cliente()
        espera = SEG.bloqueado(ip, usuario)
        if not csrf_valido(request.form.get("csrf")):
            error = "La sesión del formulario ha caducado. Inténtalo de nuevo."
        elif espera:
            SEG.registrar_conexion(usuario[:40], ip, navegador(), False, "demasiados_intentos")
            error = f"Demasiados intentos fallidos. Espera {espera // 60 + 1} min y vuelve a probar."
        elif SEG.autenticar(usuario, request.form.get("clave"), ip, navegador()):
            siguiente = request.args.get("siguiente", "")
            iniciar_sesion(SEG, usuario)
            # solo redirecciones internas
            return redirect(siguiente if siguiente.startswith("/") and not siguiente.startswith("//")
                            else url_for("index"))
        else:
            # mensaje genérico: no revela si el usuario existe, está desactivado o bloqueado
            error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error, usuario=usuario), (401 if error and request.method == "POST" else 200)


@app.post("/logout")
def logout():
    SEG.cerrar_sesion(session.get("sid"), "salida")
    SEG.registrar_conexion(session.get("usuario"), ip_cliente(), navegador(), True, "salida")
    session.clear()
    return redirect(url_for("login"))


@app.route("/cuenta/clave", methods=["GET", "POST"])
def cuenta_clave():
    u = g.usuario
    error = None
    if request.method == "POST":
        actual, nueva = request.form.get("actual", ""), request.form.get("nueva", "")
        reg = SEG.usuario(u["usuario"])
        if not SEG.autenticar_clave(reg, actual):
            error = "La contraseña actual no es correcta."
        elif nueva != request.form.get("repetir", ""):
            error = "Las dos contraseñas nuevas no coinciden."
        elif nueva == actual:
            error = "La nueva contraseña debe ser distinta de la actual."
        elif falta := problemas_clave(nueva):
            error = "La contraseña necesita " + ", ".join(falta) + "."
        else:
            SEG.cambiar_clave(u["usuario"], nueva)
            SEG.cerrar_sesiones_de(u["usuario"], "cambio_clave", excepto=session.get("sid"))
            auditar("cambio_clave_propia", u["usuario"])
            flash("Contraseña actualizada. Se han cerrado tus otras sesiones abiertas.")
            return redirect(url_for("index"))
    return render_template("cuenta_clave.html", error=error, obligatoria=bool(u["debe_cambiar"]))


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/tickers")
def api_tickers():
    info = []
    for t in PRECIOS.columns:
        s = PRECIOS[t].dropna()
        info.append({"ticker": t, "precio": float(s.iloc[-1]),
                     "desde": s.index[0].strftime("%Y-%m-%d"),
                     "hasta": s.index[-1].strftime("%Y-%m-%d")})
    return jsonify({
        "tickers": info,
        "fecha_datos": PRECIOS.index[-1].strftime("%Y-%m-%d"),
        "modelos": REDES.disponibles,
        "normalizacion": "exacta" if REDES.norm is not None else "calibrada",
    })


@app.post("/api/simular")
def api_simular():
    d = request.get_json(force=True, silent=True) or {}
    capital = _num(d, "capital", 10_000, 1, 1e12)
    horizonte = _num(d, "horizonte", 5, 0.25, 30)
    n_sims = _num(d, "n_sims", 10_000, 500, MAX_SIMS, int)
    anios = _num(d, "anios_hist", 5, 0.5, 50)
    drift = d.get("drift", "historico")
    if drift not in ("historico", "contraido", "neutral"):
        raise ErrorEntrada("drift debe ser 'historico', 'contraido' o 'neutral'.")
    rebalanceo = bool(d.get("rebalanceo", False))
    carteras = d.get("carteras") or []
    if not carteras:
        raise ErrorEntrada("No se ha definido ninguna cartera.")
    if len(carteras) > MAX_CARTERAS:
        raise ErrorEntrada(f"Como máximo {MAX_CARTERAS} carteras a la vez.")

    salida = []
    for i, c in enumerate(carteras):
        nombre = str(c.get("nombre") or f"Cartera {i + 1}")[:40]
        tks = _tickers(c.get("tickers"))
        w = _pesos(c.get("pesos"), len(tks))
        cal = calibrar(PRECIOS, tks, anios_hist=anios)
        res = simular_cartera(cal, w, capital, horizonte, n_sims, drift=drift,
                              rebalanceo=rebalanceo, semilla=i)
        res["nombre"] = nombre
        res["tickers"] = tks
        res["pesos"] = w.tolist()
        res["corr"] = np.round(cal["corr"], 3).tolist()
        res["historico"] = historico_cartera(cal, w)
        res["periodo_calibracion"] = [cal["fecha_ini"].strftime("%Y-%m-%d"),
                                      cal["fecha_fin"].strftime("%Y-%m-%d")]
        salida.append(res)
    auditar("simulacion", " | ".join(", ".join(f"{t} {p:.0%}" for t, p in zip(c["tickers"], c["pesos"]))
                                     for c in salida),
            f"capital={capital:g} horizonte={horizonte:g}a sims={n_sims} drift={drift} rebalanceo={rebalanceo}")
    return jsonify({"carteras": salida, "horizonte": horizonte, "drift": drift})


@app.post("/api/frontera")
def api_frontera():
    d = request.get_json(force=True, silent=True) or {}
    tks = _tickers(d.get("tickers"))
    if len(tks) < 2:
        raise ErrorEntrada("La frontera necesita al menos 2 activos.")
    anios = _num(d, "anios_hist", 5, 0.5, 50)
    cal = calibrar(PRECIOS, tks, anios_hist=anios)
    res = frontera(cal)
    res["tickers"] = tks
    auditar("frontera", ", ".join(tks), f"anios_hist={anios:g}")
    return jsonify(res)


@app.post("/api/opcion")
def api_opcion():
    d = request.get_json(force=True, silent=True) or {}
    tks = _tickers(d.get("tickers"))
    if len(tks) != 3:
        raise ErrorEntrada("Las redes del notebook trabajan con exactamente 3 activos.")
    anios = _num(d, "anios_hist", 5, 0.5, 50)
    n_sims = _num(d, "n_sims", 20_000, 1_000, MAX_SIMS, int)
    cal = calibrar(PRECIOS, tks, anios_hist=anios)
    auditar("valoracion_opcion", ", ".join(tks), f"sims={n_sims} anios_hist={anios:g}")
    return jsonify(valorar(cal, REDES, n_sims=n_sims))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=5000)
