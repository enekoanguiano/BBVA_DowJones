"""
Panel de administración (/admin): conexiones, sesiones activas, usuarios y auditoría.
El acceso solo para el rol admin lo garantiza motor.auth.proteger.
"""
import csv
import io
import math
import secrets

from flask import Blueprint, Response, flash, g, redirect, render_template, request, session, url_for

from motor.auth import EVENTOS, MOTIVOS_CIERRE, ROLES, a_hora_local, ahora, auditar, problemas_clave

bp = Blueprint("panel", __name__, url_prefix="/admin")
POR_PAGINA = 50


@bp.app_context_processor
def _textos():
    return {"EVENTOS": EVENTOS, "MOTIVOS_CIERRE": MOTIVOS_CIERRE}


def _pagina():
    return max(request.args.get("pagina", 1, type=int), 1)


def _paginacion(total, pagina):
    return {"pagina": pagina, "paginas": max(math.ceil(total / POR_PAGINA), 1), "total": total}


def _csv(nombre, cabecera, filas):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")  # ';' y BOM para que Excel en español lo abra bien
    w.writerow(cabecera)
    w.writerows(filas)
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


def _clave_provisional():
    while True:
        clave = f"{secrets.token_urlsafe(6)}-{secrets.token_urlsafe(6)}"
        if not problemas_clave(clave):
            return clave


# ---------------------------------------------------------------- Resumen
@bp.get("/")
def resumen():
    seg = g.seguridad
    dias = seg.accesos_por_dia(14)
    maximo = max([d["ok"] + d["fallos"] for d in dias] or [1])
    ultimas, _ = seg.conexiones(limite=8)
    return render_template("panel/resumen.html", r=seg.resumen(), dias=dias, maximo=maximo,
                           sospechosas=seg.ips_sospechosas(), ultimas=ultimas)


# ---------------------------------------------------------------- Conexiones
@bp.get("/conexiones")
def conexiones():
    seg = g.seguridad
    f = {k: (request.args.get(k) or "").strip() for k in ("usuario", "ip", "resultado", "desde", "hasta")}
    filtros = dict(usuario=f["usuario"] or None, ip=f["ip"] or None, resultado=f["resultado"] or None,
                   desde=f["desde"] or None, hasta=f["hasta"] or None)
    try:
        if request.args.get("formato") == "csv":
            filas, total = seg.conexiones(**filtros, limite=100_000)
            auditar("exportar_conexiones", None, f"{total} filas; filtros={ {k: v for k, v in f.items() if v} }")
            return _csv("conexiones.csv", ["fecha", "usuario", "ip", "resultado", "evento", "navegador"],
                        [[a_hora_local(c["fecha"]), c["usuario"], c["ip"], "Correcto" if c["correcto"] else "Fallido",
                          EVENTOS.get(c["evento"], c["evento"]), c["navegador"]] for c in filas])
        pagina = _pagina()
        filas, total = seg.conexiones(**filtros, limite=POR_PAGINA, desplazamiento=(pagina - 1) * POR_PAGINA)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("panel.conexiones"))
    return render_template("panel/conexiones.html", filas=filas, f=f, pag=_paginacion(total, pagina),
                           sospechosas=seg.ips_sospechosas())


# ---------------------------------------------------------------- Sesiones activas
@bp.get("/sesiones")
def sesiones():
    return render_template("panel/sesiones.html", filas=g.seguridad.sesiones_activas())


@bp.post("/sesiones/<sid>/cerrar")
def cerrar_sesion(sid):
    seg = g.seguridad
    s = seg.sesion(sid)
    if s is None:
        flash("Esa sesión ya estaba cerrada.", "error")
    elif sid == session.get("sid"):
        flash("No puedes expulsarte a ti mismo; usa «Cerrar sesión».", "error")
    else:
        seg.cerrar_sesion(sid, "admin")
        auditar("expulsar_sesion", s["usuario"], f"ip={s['ip']}")
        flash(f"Sesión de {s['usuario']} cerrada.")
    return redirect(request.form.get("volver") or url_for("panel.sesiones"))


# ---------------------------------------------------------------- Usuarios
@bp.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    seg = g.seguridad
    if request.method == "POST":
        clave = _clave_provisional()
        try:
            nuevo = seg.crear(request.form.get("usuario"), clave, rol=request.form.get("rol", "analista"),
                              email=request.form.get("email"), creado_por=session.get("usuario"),
                              debe_cambiar=True)
        except ValueError as e:
            flash(str(e), "error")
        else:
            auditar("crear_usuario", nuevo, f"rol={request.form.get('rol')}")
            flash(f"Usuario {nuevo} creado. Contraseña provisional: {clave} "
                  "— cópiala ahora, no se volverá a mostrar. Tendrá que cambiarla al entrar.", "clave")
        return redirect(url_for("panel.usuarios"))
    return render_template("panel/usuarios.html", filas=seg.usuarios(), ahora=ahora())


@bp.get("/usuarios/<usuario>")
def usuario(usuario):
    seg = g.seguridad
    u = seg.usuario(usuario)
    if u is None:
        flash("Ese usuario no existe.", "error")
        return redirect(url_for("panel.usuarios"))
    conex, _ = seg.conexiones(usuario_exacto=usuario, limite=30)
    acciones, _, _ = seg.auditoria(usuario=usuario, limite=30)
    activas = {s["sid"] for s in seg.sesiones_activas()}
    return render_template("panel/usuario.html", u=u, conexiones=conex, acciones=acciones,
                           sesiones=seg.ultimas_sesiones(usuario), activas=activas, ahora=ahora())


@bp.post("/usuarios/<usuario>/<accion>")
def accion_usuario(usuario, accion):
    seg = g.seguridad
    yo = session.get("usuario")
    volver = url_for("panel.usuario", usuario=usuario)
    if seg.usuario(usuario) is None:
        flash("Ese usuario no existe.", "error")
        return redirect(url_for("panel.usuarios"))
    if usuario == yo and accion in ("rol", "desactivar", "borrar"):
        flash("No puedes cambiar tu propio rol, desactivarte ni borrarte.", "error")
        return redirect(volver)
    try:
        if accion == "rol":
            rol = request.form.get("rol")
            seg.cambiar_rol(usuario, rol)
            seg.cerrar_sesiones_de(usuario, "rol")
            auditar("cambiar_rol", usuario, f"nuevo rol={rol}")
            flash(f"{usuario} ahora es {ROLES[rol]}. Se han cerrado sus sesiones.")
        elif accion == "activar":
            seg.activar(usuario, True)
            auditar("activar_usuario", usuario)
            flash(f"{usuario} activado.")
        elif accion == "desactivar":
            seg.activar(usuario, False)
            auditar("desactivar_usuario", usuario)
            flash(f"{usuario} desactivado y desconectado.")
        elif accion == "desbloquear":
            seg.desbloquear(usuario)
            auditar("desbloquear_usuario", usuario)
            flash(f"{usuario} desbloqueado.")
        elif accion == "restablecer":
            clave = _clave_provisional()
            seg.cambiar_clave(usuario, clave, debe_cambiar=True)
            seg.desbloquear(usuario)
            seg.cerrar_sesiones_de(usuario, "cambio_clave")
            auditar("restablecer_clave", usuario)
            flash(f"Nueva contraseña provisional de {usuario}: {clave} "
                  "— cópiala ahora, no se volverá a mostrar.", "clave")
        elif accion == "cerrar_sesiones":
            seg.cerrar_sesiones_de(usuario, "admin", excepto=session.get("sid"))
            auditar("expulsar_sesiones", usuario)
            flash(f"Sesiones de {usuario} cerradas.")
        elif accion == "borrar":
            seg.borrar(usuario)
            auditar("borrar_usuario", usuario)
            flash(f"Usuario {usuario} eliminado. Su historial de conexiones se conserva.")
            return redirect(url_for("panel.usuarios"))
        else:
            flash("Acción desconocida.", "error")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(volver)


# ---------------------------------------------------------------- Auditoría
@bp.get("/auditoria")
def auditoria():
    seg = g.seguridad
    usuario = (request.args.get("usuario") or "").strip().lower() or None
    accion = request.args.get("accion") or None
    if request.args.get("formato") == "csv":
        filas, total, _ = seg.auditoria(usuario=usuario, accion=accion, limite=100_000)
        auditar("exportar_auditoria", None, f"{total} filas")
        return _csv("auditoria.csv", ["fecha", "usuario", "accion", "objeto", "detalle", "ip"],
                    [[a_hora_local(a["fecha"]), a["usuario"], a["accion"], a["objeto"], a["detalle"], a["ip"]]
                     for a in filas])
    pagina = _pagina()
    filas, total, acciones = seg.auditoria(usuario=usuario, accion=accion, limite=POR_PAGINA,
                                           desplazamiento=(pagina - 1) * POR_PAGINA)
    return render_template("panel/auditoria.html", filas=filas, acciones=acciones,
                           f={"usuario": usuario or "", "accion": accion or ""}, pag=_paginacion(total, pagina))


@bp.app_template_filter("navegador_corto")
def navegador_corto(ua):
    """'Mozilla/5.0 (Windows NT 10.0…) Chrome/130…' -> 'Chrome · Windows'"""
    ua = ua or ""
    nav = next((n for clave, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                   ("Chrome/", "Chrome"), ("Safari/", "Safari"), ("curl/", "curl"),
                                   ("python", "Script Python")) if clave in ua), "Otro")
    so = next((n for clave, n in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"),
                                  ("iPad", "iPad"), ("Mac OS", "macOS"), ("Linux", "Linux")) if clave in ua), "")
    return f"{nav} · {so}" if so else nav
