# -*- coding: utf-8 -*-
"""Órdenes de Servicio - Mantención de Rack.

App web móvil con mantenedor de clientes/proyectos, fotos, PDF y envío
automático por correo a los destinatarios configurados en cada proyecto.
"""
import base64
import binascii
import io
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime
from functools import wraps
from urllib.parse import urlsplit

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from PIL import Image, ImageOps
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import db
import mailer
import pdf as pdf_mod
from constants import (CHECKLIST, CHECKLIST_KEYS, CHECKLIST_LABELS, ORDER_TYPES,
                       STATUS_LABELS)

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "cambia-esta-clave-en-produccion"
app.config.update(
    MAX_CONTENT_LENGTH=48 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FORCE_HTTPS") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
)
# Detrás del proxy de Render/Railway (HTTPS y IP real del cliente).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

SETTING_KEYS = [
    "company_name", "company_rut", "company_phone", "company_address",
    "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_security",
    "from_email",
]

_attempts = {}


# ---------------------------------------------------------------------------
# Inicialización
# ---------------------------------------------------------------------------
def _bootstrap():
    db.init()
    fila = db.one("SELECT COUNT(*) AS c FROM users")
    if fila and fila["c"] == 0:
        correo = os.environ.get("ADMIN_EMAIL", "admin@ordenes.local").strip().lower()
        clave = os.environ.get("ADMIN_PASSWORD", "Admin1234")
        try:
            db.execute(
                "INSERT INTO users (name, email, password_hash, role, active, created_at) "
                "VALUES (?, ?, ?, 'admin', 1, ?)",
                ("Administrador", correo, generate_password_hash(clave), db.now_iso()),
            )
            print("=" * 64)
            print(" USUARIO ADMINISTRADOR CREADO")
            print(" Correo   : %s" % correo)
            print(" Clave    : %s" % clave)
            print(" Cambiala en Usuarios apenas ingreses.")
            print("=" * 64)
        except Exception:
            pass
    if not db.get_setting("company_name"):
        db.set_setting("company_name", os.environ.get("COMPANY_NAME", "Mi Empresa"))


_bootstrap()


# ---------------------------------------------------------------------------
# Utilidades de sesión / CSRF
# ---------------------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


@app.context_processor
def _ctx():
    return {
        "user": g.get("user"),
        "csrf_token": csrf_token,
        "app_name": "Órdenes de Servicio",
        "company": db.get_setting("company_name") or "Mi Empresa",
        "today": db.now().strftime("%d-%m-%Y"),
    }


@app.before_request
def _csrf_protect():
    if request.method != "POST":
        return None
    token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("_csrf"):
        if _wants_json():
            return jsonify({"ok": False, "error": "Sesión expirada. Recarga la página."}), 400
        abort(400)


def _wants_json():
    return (request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or ""))


@app.before_request
def _load_user():
    uid = session.get("uid")
    g.user = None
    if uid:
        fila = db.one("SELECT * FROM users WHERE id = ? AND active = 1", (uid,))
        if fila:
            g.user = dict(fila)
        else:
            session.pop("uid", None)


@app.after_request
def _headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not g.user:
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not g.user:
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return fn(*a, **kw)
    return wrapper


def _destino_seguro(valor):
    if not valor:
        return url_for("dashboard")
    partes = urlsplit(valor)
    if partes.scheme or partes.netloc or not valor.startswith("/"):
        return url_for("dashboard")
    return valor


# ---------------------------------------------------------------------------
# Salud del servicio (para Render/Railway)
# ---------------------------------------------------------------------------
@app.route("/salud")
def salud():
    return jsonify({"ok": True, "servicio": "ordenes-rack"})


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        correo = (request.form.get("email") or "").strip().lower()
        clave = request.form.get("password") or ""
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]
        ahora = time.time()
        marcas = [t for t in _attempts.get(ip, []) if ahora - t < 600]
        _attempts[ip] = marcas
        if len(marcas) >= 10:
            error = "Demasiados intentos. Espera unos minutos."
        else:
            fila = db.one("SELECT * FROM users WHERE lower(email) = ?", (correo,))
            if fila and fila["active"] and check_password_hash(fila["password_hash"], clave):
                session.clear()
                session["uid"] = fila["id"]
                session.permanent = True
                return redirect(_destino_seguro(request.args.get("next") or request.form.get("next")))
            _attempts[ip].append(ahora)
            error = "Correo o contraseña incorrectos."
    return render_template("login.html", error=error, next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Órdenes
# ---------------------------------------------------------------------------
def _proyectos_activos():
    return db.query(
        "SELECT p.*, c.name AS client_name, c.email AS client_email, c.address AS client_address "
        "FROM projects p JOIN clients c ON c.id = p.client_id "
        "WHERE p.active = 1 AND c.active = 1 ORDER BY c.name, p.name"
    )


@app.route("/")
@login_required
def dashboard():
    if g.user["role"] == "admin":
        ordenes = db.query(
            "SELECT o.*, p.name AS project_name, c.name AS client_name, u.name AS tech_name "
            "FROM orders o JOIN projects p ON p.id = o.project_id "
            "JOIN clients c ON c.id = p.client_id JOIN users u ON u.id = o.user_id "
            "ORDER BY o.id DESC LIMIT 200"
        )
    else:
        ordenes = db.query(
            "SELECT o.*, p.name AS project_name, c.name AS client_name, u.name AS tech_name "
            "FROM orders o JOIN projects p ON p.id = o.project_id "
            "JOIN clients c ON c.id = p.client_id JOIN users u ON u.id = o.user_id "
            "WHERE o.user_id = ? ORDER BY o.id DESC LIMIT 200", (g.user["id"],)
        )
    total = len(ordenes)
    mes = db.now().strftime("%Y-%m")
    del_mes = sum(1 for o in ordenes if str(o["created_at"]).startswith(mes.replace("-", "-")))
    enviadas = sum(1 for o in ordenes if o["email_status"] == "enviado")
    pendientes = sum(1 for o in ordenes if o["email_status"] != "enviado")
    return render_template("dashboard.html", ordenes=ordenes, total=total,
                           del_mes=del_mes, enviadas=enviadas, pendientes=pendientes)


@app.route("/orden/nueva", methods=["GET", "POST"])
@login_required
def order_new():
    proyectos = _proyectos_activos()
    if request.method == "POST":
        try:
            return _crear_orden(proyectos)
        except ValueError as exc:
            if _wants_json():
                return jsonify({"ok": False, "error": str(exc)}), 400
            flash(str(exc), "error")
    return render_template("order_form.html", proyectos=proyectos,
                           checklist=CHECKLIST, tipos=ORDER_TYPES,
                           ahora=db.now().strftime("%Y-%m-%dT%H:%M"))


def _crear_orden(proyectos):
    pid = request.form.get("project_id", type=int)
    proyecto = next((dict(p) for p in proyectos if p["id"] == pid), None)
    if not proyecto:
        raise ValueError("Selecciona un proyecto válido.")

    trabajo = (request.form.get("work") or "").strip()
    if len(trabajo) < 10:
        raise ValueError("Describe el trabajo realizado (mínimo 10 caracteres).")

    cliente = db.one("SELECT * FROM clients WHERE id = ?", (proyecto["client_id"],))
    if not cliente:
        raise ValueError("El cliente del proyecto no existe.")
    cliente = dict(cliente)

    tipo = request.form.get("type") if request.form.get("type") in ORDER_TYPES else "preventiva"
    realizado = (request.form.get("performed_at") or "").strip().replace("T", " ")
    if not realizado:
        realizado = db.now().strftime("%Y-%m-%d %H:%M")

    checklist = []
    for clave, etiqueta in CHECKLIST:
        estado = request.form.get("chk_%s" % clave, "na")
        if estado not in STATUS_LABELS:
            estado = "na"
        nota = (request.form.get("note_%s" % clave) or "").strip()[:300]
        checklist.append({"key": clave, "status": estado, "note": nota})

    fotos_antes = [f for f in request.files.getlist("photos_antes") if f and f.filename]
    fotos_despues = [f for f in request.files.getlist("photos_despues") if f and f.filename]
    if not fotos_antes and not fotos_despues:
        raise ValueError("Agrega al menos una foto del trabajo realizado.")

    codigo = _siguiente_codigo()
    while db.one("SELECT id FROM orders WHERE code = ?", (codigo,)):
        codigo = _siguiente_codigo()

    ahora = db.now_iso()
    oid = db.execute(
        "INSERT INTO orders (code, project_id, user_id, type, performed_at, rack, site, "
        "checklist, work, materials, observations, receiver, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (codigo, pid, g.user["id"], tipo, realizado,
         (request.form.get("rack") or "").strip(),
         (request.form.get("site") or proyecto.get("site") or "").strip(),
         json.dumps(checklist, ensure_ascii=False), trabajo,
         (request.form.get("materials") or "").strip(),
         (request.form.get("observations") or "").strip(),
         (request.form.get("receiver") or "").strip(), ahora),
    )

    carpeta = os.path.join(db.UPLOADS, codigo)
    os.makedirs(carpeta, exist_ok=True)
    rutas = []
    for archivo in fotos_antes:
        ruta = _guardar_foto(archivo, carpeta)
        if ruta:
            db.execute("INSERT INTO photos (order_id, filename, kind, created_at) VALUES (?, ?, ?, ?)",
                       (oid, os.path.basename(ruta), "antes", ahora))
            rutas.append((ruta, "antes"))
    for archivo in fotos_despues:
        ruta = _guardar_foto(archivo, carpeta)
        if ruta:
            db.execute("INSERT INTO photos (order_id, filename, kind, created_at) VALUES (?, ?, ?, ?)",
                       (oid, os.path.basename(ruta), "despues", ahora))
            rutas.append((ruta, "despues"))

    firma = _guardar_firma(request.form.get("firma"), carpeta)
    if firma:
        db.execute("UPDATE orders SET signature_file = ? WHERE id = ?", (os.path.basename(firma), oid))

    orden = dict(db.one("SELECT * FROM orders WHERE id = ?", (oid,)))
    orden["tech_name"] = g.user["name"]
    ruta_pdf = os.path.join(db.PDFS, "%s.pdf" % codigo)
    empresa = db.settings_dict(["company_name", "company_rut", "company_phone", "company_address"])
    empresa["logo"] = os.path.join(db.DATA_DIR, "logo.png")
    pdf_mod.build(ruta_pdf, orden, proyecto, cliente, rutas, firma, empresa)

    settings = db.settings_dict(SETTING_KEYS)
    estado, detalle = mailer.enviar(orden, proyecto, cliente, rutas, ruta_pdf, settings)
    db.execute(
        "UPDATE orders SET pdf_file = ?, email_status = ?, email_detail = ?, "
        "email_to = ?, email_cc = ? WHERE id = ?",
        (os.path.basename(ruta_pdf), estado, detalle,
         ", ".join(mailer.parse_destinatarios(proyecto.get("recipients"))) or cliente.get("email", ""),
         ", ".join(mailer.parse_destinatarios(proyecto.get("cc"))), oid),
    )

    if _wants_json():
        return jsonify({"ok": True, "redirect": url_for("order_view", oid=oid),
                        "email_status": estado, "email_detail": detalle})
    if estado == "error":
        flash("Orden guardada, pero el correo falló: %s" % detalle, "error")
    elif estado == "simulado":
        flash("Orden guardada. SMTP no configurado: el correo quedó en la bandeja de salida.", "warn")
    else:
        flash("Orden %s enviada correctamente." % codigo, "ok")
    return redirect(url_for("order_view", oid=oid))


def _siguiente_codigo():
    dia = db.now().strftime("%Y%m%d")
    fila = db.one("SELECT COUNT(*) AS c FROM orders WHERE code LIKE ?", ("OS-%s-%%" % dia,))
    n = (fila["c"] if fila else 0) + 1
    return "OS-%s-%04d" % (dia, n)


def _guardar_foto(archivo, carpeta):
    try:
        datos = archivo.read()
        if not datos or len(datos) > 20 * 1024 * 1024:
            return None
        imagen = Image.open(io.BytesIO(datos))
        imagen = ImageOps.exif_transpose(imagen).convert("RGB")
        imagen.thumbnail((1600, 1600), Image.LANCZOS)
        nombre = "%s.jpg" % uuid.uuid4().hex
        ruta = os.path.join(carpeta, nombre)
        imagen.save(ruta, "JPEG", quality=82, optimize=True)
        return ruta
    except Exception:
        return None


def _guardar_firma(data_url, carpeta):
    if not data_url or not data_url.startswith("data:image/png;base64,"):
        return None
    try:
        crudo = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        if len(crudo) > 3 * 1024 * 1024:
            return None
        imagen = Image.open(io.BytesIO(crudo)).convert("RGBA")
        fondo = Image.new("RGB", imagen.size, (255, 255, 255))
        fondo.paste(imagen, mask=imagen.split()[-1])
        ruta = os.path.join(carpeta, "firma.png")
        fondo.save(ruta, "PNG", optimize=True)
        return ruta
    except (binascii.Error, ValueError, OSError):
        return None


def _orden_con_permiso(oid):
    orden = db.one(
        "SELECT o.*, p.name AS project_name, p.site AS project_site, p.recipients, p.cc, "
        "p.client_id, c.name AS client_name, c.email AS client_email, "
        "c.contact AS client_contact, u.name AS tech_name "
        "FROM orders o JOIN projects p ON p.id = o.project_id "
        "JOIN clients c ON c.id = p.client_id JOIN users u ON u.id = o.user_id "
        "WHERE o.id = ?", (oid,))
    if not orden:
        abort(404)
    if g.user["role"] != "admin" and orden["user_id"] != g.user["id"]:
        abort(403)
    return dict(orden)


@app.route("/orden/<int:oid>")
@login_required
def order_view(oid):
    orden = _orden_con_permiso(oid)
    fotos = db.query("SELECT * FROM photos WHERE order_id = ? ORDER BY id", (oid,))
    try:
        items = json.loads(orden.get("checklist") or "[]")
    except Exception:
        items = []
    return render_template("order_view.html", orden=orden, fotos=fotos, items=items,
                           etiquetas=CHECKLIST_LABELS,
                           status_labels=STATUS_LABELS, tipos=ORDER_TYPES)


@app.route("/orden/<int:oid>/pdf")
@login_required
def order_pdf(oid):
    orden = _orden_con_permiso(oid)
    if not orden.get("pdf_file"):
        abort(404)
    ruta = os.path.join(db.PDFS, orden["pdf_file"])
    if not os.path.isfile(ruta):
        abort(404)
    return send_file(ruta, mimetype="application/pdf",
                     download_name="%s.pdf" % orden["code"])


@app.route("/foto/<int:fid>")
@login_required
def photo_file(fid):
    foto = db.one("SELECT * FROM photos WHERE id = ?", (fid,))
    if not foto:
        abort(404)
    orden = _orden_con_permiso(foto["order_id"])
    ruta = os.path.join(db.UPLOADS, orden["code"], foto["filename"])
    if not os.path.isfile(ruta):
        abort(404)
    return send_file(ruta, mimetype="image/jpeg")


@app.route("/firma/<int:oid>")
@login_required
def signature_file(oid):
    orden = _orden_con_permiso(oid)
    if not orden.get("signature_file"):
        abort(404)
    ruta = os.path.join(db.UPLOADS, orden["code"], orden["signature_file"])
    if not os.path.isfile(ruta):
        abort(404)
    return send_file(ruta, mimetype="image/png")


@app.route("/orden/<int:oid>/reenviar", methods=["POST"])
@login_required
def order_resend(oid):
    orden = _orden_con_permiso(oid)
    proyecto = dict(db.one("SELECT * FROM projects WHERE id = ?", (orden["project_id"],)))
    cliente = dict(db.one("SELECT * FROM clients WHERE id = ?", (orden["client_id"],)))
    fotos = [(os.path.join(db.UPLOADS, orden["code"], f["filename"]), f["kind"])
             for f in db.query("SELECT * FROM photos WHERE order_id = ? ORDER BY id", (oid,))]
    ruta_pdf = os.path.join(db.PDFS, orden["pdf_file"]) if orden.get("pdf_file") else None
    estado, detalle = mailer.enviar(orden, proyecto, cliente, fotos, ruta_pdf,
                                    db.settings_dict(SETTING_KEYS))
    db.execute("UPDATE orders SET email_status = ?, email_detail = ? WHERE id = ?",
               (estado, detalle, oid))
    flash("Correo reenviado." if estado == "enviado" else "No se pudo enviar: %s" % detalle,
          "ok" if estado == "enviado" else "error")
    return redirect(url_for("order_view", oid=oid))


# ---------------------------------------------------------------------------
# Mantenedor: clientes
# ---------------------------------------------------------------------------
@app.route("/admin/clientes")
@admin_required
def admin_clients():
    clientes = db.query(
        "SELECT c.*, (SELECT COUNT(*) FROM projects p WHERE p.client_id = c.id) AS proyectos "
        "FROM clients c ORDER BY c.active DESC, c.name")
    return render_template("admin_clients.html", clientes=clientes)


@app.route("/admin/clientes/nuevo", methods=["GET", "POST"])
@app.route("/admin/clientes/<int:cid>", methods=["GET", "POST"])
@admin_required
def admin_client_form(cid=None):
    cliente = dict(db.one("SELECT * FROM clients WHERE id = ?", (cid,))) if cid else None
    if cid and not cliente:
        abort(404)
    if request.method == "POST":
        nombre = (request.form.get("name") or "").strip()
        if not nombre:
            flash("El nombre del cliente es obligatorio.", "error")
        else:
            datos = (nombre, (request.form.get("rut") or "").strip(),
                     (request.form.get("contact") or "").strip(),
                     (request.form.get("email") or "").strip(),
                     (request.form.get("phone") or "").strip(),
                     (request.form.get("address") or "").strip(),
                     (request.form.get("notes") or "").strip())
            if cliente:
                db.execute("UPDATE clients SET name=?, rut=?, contact=?, email=?, phone=?, "
                           "address=?, notes=? WHERE id=?", datos + (cid,))
            else:
                db.execute("INSERT INTO clients (name, rut, contact, email, phone, address, notes, "
                           "active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                           datos + (db.now_iso(),))
            flash("Cliente guardado.", "ok")
            return redirect(url_for("admin_clients"))
    return render_template("admin_client_form.html", cliente=cliente)


@app.route("/admin/clientes/<int:cid>/estado", methods=["POST"])
@admin_required
def admin_client_toggle(cid):
    db.execute("UPDATE clients SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?", (cid,))
    return redirect(url_for("admin_clients"))


# ---------------------------------------------------------------------------
# Mantenedor: proyectos
# ---------------------------------------------------------------------------
@app.route("/admin/proyectos")
@admin_required
def admin_projects():
    proyectos = db.query(
        "SELECT p.*, c.name AS client_name, "
        "(SELECT COUNT(*) FROM orders o WHERE o.project_id = p.id) AS ordenes "
        "FROM projects p JOIN clients c ON c.id = p.client_id "
        "ORDER BY p.active DESC, c.name, p.name")
    return render_template("admin_projects.html", proyectos=proyectos)


@app.route("/admin/proyectos/nuevo", methods=["GET", "POST"])
@app.route("/admin/proyectos/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_project_form(pid=None):
    proyecto = dict(db.one("SELECT * FROM projects WHERE id = ?", (pid,))) if pid else None
    if pid and not proyecto:
        abort(404)
    clientes = db.query("SELECT * FROM clients WHERE active = 1 ORDER BY name")
    if request.method == "POST":
        nombre = (request.form.get("name") or "").strip()
        client_id = request.form.get("client_id", type=int)
        if not nombre or not client_id:
            flash("Cliente y nombre del proyecto son obligatorios.", "error")
        else:
            destinatarios = ", ".join(mailer.parse_destinatarios(request.form.get("recipients")))
            copia = ", ".join(mailer.parse_destinatarios(request.form.get("cc")))
            if not destinatarios:
                flash("Agrega al menos un correo destinatario.", "error")
            else:
                datos = (client_id, nombre,
                         (request.form.get("site") or "").strip(),
                         (request.form.get("racks") or "").strip(),
                         destinatarios, copia)
                if proyecto:
                    db.execute("UPDATE projects SET client_id=?, name=?, site=?, racks=?, "
                               "recipients=?, cc=? WHERE id=?", datos + (pid,))
                else:
                    db.execute("INSERT INTO projects (client_id, name, site, racks, recipients, cc, "
                               "active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                               datos + (db.now_iso(),))
                flash("Proyecto guardado.", "ok")
                return redirect(url_for("admin_projects"))
    return render_template("admin_project_form.html", proyecto=proyecto, clientes=clientes)


@app.route("/admin/proyectos/<int:pid>/estado", methods=["POST"])
@admin_required
def admin_project_toggle(pid):
    db.execute("UPDATE projects SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?", (pid,))
    return redirect(url_for("admin_projects"))


# ---------------------------------------------------------------------------
# Mantenedor: usuarios
# ---------------------------------------------------------------------------
@app.route("/admin/usuarios")
@admin_required
def admin_users():
    usuarios = db.query(
        "SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS ordenes "
        "FROM users u ORDER BY u.active DESC, u.name")
    return render_template("admin_users.html", usuarios=usuarios)


@app.route("/admin/usuarios/nuevo", methods=["GET", "POST"])
@app.route("/admin/usuarios/<int:uid>", methods=["GET", "POST"])
@admin_required
def admin_user_form(uid=None):
    usuario = dict(db.one("SELECT * FROM users WHERE id = ?", (uid,))) if uid else None
    if uid and not usuario:
        abort(404)
    if request.method == "POST":
        nombre = (request.form.get("name") or "").strip()
        correo = (request.form.get("email") or "").strip().lower()
        rol = request.form.get("role") if request.form.get("role") in ("admin", "tech") else "tech"
        clave = request.form.get("password") or ""
        if not nombre or not correo:
            flash("Nombre y correo son obligatorios.", "error")
        elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo):
            flash("El correo no es válido.", "error")
        else:
            existe = db.one("SELECT id FROM users WHERE lower(email) = ? AND id <> ?",
                            (correo, uid or 0))
            if existe:
                flash("Ya existe un usuario con ese correo.", "error")
            elif usuario:
                if clave:
                    db.execute("UPDATE users SET name=?, email=?, role=?, password_hash=? WHERE id=?",
                               (nombre, correo, rol, generate_password_hash(clave), uid))
                else:
                    db.execute("UPDATE users SET name=?, email=?, role=? WHERE id=?",
                               (nombre, correo, rol, uid))
                flash("Usuario actualizado.", "ok")
                return redirect(url_for("admin_users"))
            else:
                if len(clave) < 8:
                    flash("La contraseña debe tener al menos 8 caracteres.", "error")
                else:
                    db.execute("INSERT INTO users (name, email, password_hash, role, active, created_at) "
                               "VALUES (?, ?, ?, ?, 1, ?)",
                               (nombre, correo, generate_password_hash(clave), rol, db.now_iso()))
                    flash("Usuario creado.", "ok")
                    return redirect(url_for("admin_users"))
    return render_template("admin_user_form.html", usuario=usuario)


@app.route("/admin/usuarios/<int:uid>/estado", methods=["POST"])
@admin_required
def admin_user_toggle(uid):
    if uid == g.user["id"]:
        flash("No puedes desactivar tu propio usuario.", "error")
        return redirect(url_for("admin_users"))
    db.execute("UPDATE users SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?", (uid,))
    return redirect(url_for("admin_users"))


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
@app.route("/admin/config", methods=["GET", "POST"])
@admin_required
def admin_config():
    if request.method == "POST":
        for clave in SETTING_KEYS:
            if clave in request.form:
                valor = (request.form.get(clave) or "").strip()
                if clave == "smtp_password" and not valor:
                    continue
                db.set_setting(clave, valor)
        logo = request.files.get("logo")
        if logo and logo.filename:
            try:
                imagen = Image.open(logo.stream)
                imagen.thumbnail((600, 300), Image.LANCZOS)
                imagen.save(os.path.join(db.DATA_DIR, "logo.png"), "PNG")
                flash("Logo actualizado.", "ok")
            except Exception:
                flash("No se pudo leer la imagen del logo.", "error")
        flash("Configuración guardada.", "ok")
        return redirect(url_for("admin_config"))
    return render_template("admin_config.html", cfg=db.settings_dict(SETTING_KEYS))


@app.route("/admin/config/probar", methods=["POST"])
@admin_required
def admin_config_test():
    destino = (request.form.get("test_email") or "").strip()
    if not destino:
        flash("Escribe un correo de destino para la prueba.", "error")
    else:
        ok, detalle = mailer.enviar_prueba(db.settings_dict(SETTING_KEYS), destino)
        flash(detalle, "ok" if ok else "error")
    return redirect(url_for("admin_config"))


# ---------------------------------------------------------------------------
@app.template_filter("fecha")
def _fmt_fecha(valor):
    if not valor:
        return "-"
    texto = str(valor).replace("T", " ")
    try:
        f, h = texto.split(" ")[0], texto.split(" ")[1][:5]
        y, m, d = f.split("-")
        return "%s-%s-%s %s" % (d, m, y, h)
    except Exception:
        return texto


@app.template_filter("tipo")
def _fmt_tipo(valor):
    return ORDER_TYPES.get(valor, valor or "-")


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "8001"))
    app.run(host="0.0.0.0", port=puerto, debug=False, threaded=True)
