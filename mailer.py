# -*- coding: utf-8 -*-
"""Envío de la orden por correo (SMTP) con PDF y fotos."""
import io
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from PIL import Image, ImageOps

import db
from constants import CHECKLIST_LABELS, ORDER_TYPES, STATUS_LABELS


def parse_destinatarios(texto):
    if not texto:
        return []
    for sep in (";", "\n", "\r", " "):
        texto = texto.replace(sep, ",")
    vistos, salida = set(), []
    for parte in texto.split(","):
        correo = parte.strip()
        if correo and "@" in correo and correo.lower() not in vistos:
            vistos.add(correo.lower())
            salida.append(correo)
    return salida


def configurado(cfg):
    return bool((cfg.get("smtp_host") or "").strip())


def _cuerpo_html(orden, proyecto, cliente, fotos_cid, settings):
    tipo = ORDER_TYPES.get(orden.get("type"), orden.get("type") or "")
    filas = [
        ("Cliente", (cliente or {}).get("name", "")),
        ("Proyecto / sitio", "%s - %s" % (proyecto.get("name", ""), proyecto.get("site", ""))),
        ("Rack / gabinete", orden.get("rack", "")),
        ("Técnico", orden.get("tech_name", "")),
        ("Fecha de ejecución", str(orden.get("performed_at", "")).replace("T", " ")),
        ("Recibe por el cliente", orden.get("receiver", "")),
        ("Tipo de servicio", tipo),
    ]
    filas_html = "".join(
        '<tr><td style="padding:6px 10px;background:#f1f5f9;border:1px solid #e2e8f0;'
        'font-size:12px;color:#64748b;width:38%%">%s</td>'
        '<td style="padding:6px 10px;border:1px solid #e2e8f0;font-size:13px;color:#0f172a">%s</td></tr>'
        % (k, v or "-") for k, v in filas
    )

    import json
    try:
        items = json.loads(orden.get("checklist") or "[]")
    except Exception:
        items = []
    checklist_html = ""
    for it in items:
        estado = it.get("status", "")
        color = "#16a34a" if estado == "ok" else ("#b45309" if estado == "obs" else "#64748b")
        nota = it.get("note") or ""
        checklist_html += (
            '<tr><td style="padding:5px 8px;border-bottom:1px solid #eef2f7;font-size:12px;color:#0f172a">%s</td>'
            '<td style="padding:5px 8px;border-bottom:1px solid #eef2f7;font-size:12px;color:%s;'
            'font-weight:600;white-space:nowrap">%s</td>'
            '<td style="padding:5px 8px;border-bottom:1px solid #eef2f7;font-size:11px;color:#64748b">%s</td></tr>'
            % (CHECKLIST_LABELS.get(it.get("key"), it.get("key")), color,
               STATUS_LABELS.get(estado, estado), nota)
        )

    fotos_html = ""
    if fotos_cid:
        celdas = "".join(
            '<div style="width:48%%;display:inline-block;margin:0 1%% 10px 0;vertical-align:top">'
            '<img src="cid:%s" style="width:100%%;border-radius:8px;border:1px solid #e2e8f0">'
            '<div style="font-size:10px;color:#94a3b8;margin-top:3px">%s</div></div>'
            % (cid, etiqueta) for cid, etiqueta in fotos_cid
        )
        fotos_html = (
            '<h3 style="font-size:14px;color:#0f172a;margin:22px 0 8px">Registro fotográfico</h3>'
            '<div>%s</div>' % celdas
        )

    bloques = ""
    for titulo, valor in (
        ("Trabajo realizado", orden.get("work")),
        ("Materiales y repuestos", orden.get("materials")),
        ("Observaciones y recomendaciones", orden.get("observations")),
    ):
        if (valor or "").strip():
            bloques += (
                '<h3 style="font-size:14px;color:#0f172a;margin:22px 0 8px">%s</h3>'
                '<div style="font-size:13px;color:#334155;line-height:1.55;white-space:pre-wrap">%s</div>'
                % (titulo, valor)
            )

    empresa = settings.get("company_name") or "Servicio Técnico"
    return """<!doctype html>
<html><body style="margin:0;padding:0;background:#f8fafc">
<div style="max-width:640px;margin:0 auto;padding:18px;font-family:Segoe UI,Arial,sans-serif">
  <div style="background:#0f172a;color:#fff;padding:18px 20px;border-radius:12px 12px 0 0">
    <div style="font-size:12px;letter-spacing:.08em;color:#94a3b8">%s</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px">Orden de Servicio %s</div>
    <div style="font-size:12px;color:#cbd5e1;margin-top:4px">%s</div>
  </div>
  <div style="background:#fff;padding:20px;border:1px solid #e2e8f0;border-top:0;border-radius:0 0 12px 12px">
    <p style="font-size:13px;color:#334155;margin:0 0 14px">
      Estimado(a), se adjunta la orden de servicio correspondiente a la mantención realizada.
    </p>
    <table style="width:100%%;border-collapse:collapse">%s</table>
    <h3 style="font-size:14px;color:#0f172a;margin:22px 0 8px">Checklist de mantención</h3>
    <table style="width:100%%;border-collapse:collapse">%s</table>
    %s
    %s
    <p style="font-size:12px;color:#64748b;margin-top:24px">
      Se adjunta el PDF firmado con el detalle completo de la actividad.
    </p>
    <p style="font-size:11px;color:#94a3b8;margin-top:18px;border-top:1px solid #e2e8f0;padding-top:10px">
      %s - Correo generado automáticamente.
    </p>
  </div>
</div>
</body></html>""" % (empresa, orden.get("code", ""), tipo, filas_html, checklist_html, bloques,
                     fotos_html, empresa)


def _miniatura(ruta, ancho=900):
    with Image.open(ruta) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width > ancho:
            im = im.resize((ancho, max(1, round(im.height * ancho / im.width))))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72, optimize=True)
        return buf.getvalue()


def _construir(orden, proyecto, cliente, fotos, pdf_path, settings):
    to = parse_destinatarios((proyecto or {}).get("recipients"))
    if not to and cliente and cliente.get("email"):
        to = parse_destinatarios(cliente.get("email"))
    cc = parse_destinatarios((proyecto or {}).get("cc"))
    if not to:
        return None, [], cc, "El proyecto no tiene destinatarios configurados."

    empresa = settings.get("company_name") or "Servicio Técnico"
    remitente = settings.get("from_email") or settings.get("smtp_user") or ""
    if not remitente:
        if configurado(settings):
            return None, to, cc, "Falta el correo remitente en la configuración."
        remitente = "ordenes@localhost"

    msg = EmailMessage()
    msg["Subject"] = "Orden de Servicio %s - %s" % (
        orden.get("code", ""), (cliente or {}).get("name", ""))
    msg["From"] = formataddr((empresa, remitente))
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)

    fotos_cid = []
    fotos_payload = []
    for i, (ruta, kind) in enumerate(fotos):
        if not os.path.isfile(ruta):
            continue
        try:
            data = _miniatura(ruta)
        except Exception:
            continue
        cid = "foto%d" % i
        etiqueta = {"antes": "Antes", "despues": "Después"}.get(kind, "Registro")
        fotos_cid.append((cid, etiqueta))
        fotos_payload.append((cid, data))

    html = _cuerpo_html(orden, proyecto, cliente, fotos_cid, settings)
    msg.set_content("Orden de servicio %s. Se adjunta el PDF con el detalle." % orden.get("code", ""))
    msg.add_alternative(html, subtype="html")

    for cid, data in fotos_payload:
        msg.get_payload()[1].add_related(
            data, maintype="image", subtype="jpeg", cid="<%s>" % cid)

    if pdf_path and os.path.isfile(pdf_path):
        with open(pdf_path, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf",
                               filename=os.path.basename(pdf_path))
    return msg, to, cc, ""


def _guardar_eml(msg, code):
    os.makedirs(db.OUTBOX, exist_ok=True)
    ruta = os.path.join(db.OUTBOX, "%s.eml" % code)
    with open(ruta, "wb") as f:
        f.write(bytes(msg))
    return ruta


def enviar(orden, proyecto, cliente, fotos, pdf_path, settings):
    """Devuelve (estado, detalle): estado en 'enviado' | 'simulado' | 'error'."""
    msg, to, cc, error = _construir(orden, proyecto, cliente, fotos, pdf_path, settings)
    if msg is None:
        return "error", error

    if not configurado(settings):
        ruta = _guardar_eml(msg, orden.get("code", "orden"))
        return "simulado", "SMTP no configurado. Correo guardado en %s" % ruta

    host = settings.get("smtp_host", "").strip()
    puerto = int(settings.get("smtp_port") or 587)
    seguridad = (settings.get("smtp_security") or "starttls").lower()
    usuario = settings.get("smtp_user", "").strip()
    clave = settings.get("smtp_password", "")

    try:
        if seguridad == "ssl":
            server = smtplib.SMTP_SSL(host, puerto, timeout=25,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, puerto, timeout=25)
            server.ehlo()
            if seguridad == "starttls":
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
        if usuario:
            server.login(usuario, clave)
        server.send_message(msg)
        server.quit()
        return "enviado", "Enviado a %s" % ", ".join(to + cc)
    except Exception as exc:
        return "error", "%s: %s" % (type(exc).__name__, exc)


def enviar_prueba(settings, destino):
    if not configurado(settings):
        return False, "SMTP no configurado."
    msg = EmailMessage()
    msg["Subject"] = "Prueba de configuración - Órdenes de Servicio"
    msg["From"] = formataddr((settings.get("company_name") or "Órdenes",
                              settings.get("from_email") or settings.get("smtp_user")))
    msg["To"] = destino
    msg.set_content("Este es un correo de prueba. La configuración SMTP funciona correctamente.")

    host = settings.get("smtp_host", "").strip()
    puerto = int(settings.get("smtp_port") or 587)
    seguridad = (settings.get("smtp_security") or "starttls").lower()
    try:
        if seguridad == "ssl":
            server = smtplib.SMTP_SSL(host, puerto, timeout=20,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, puerto, timeout=20)
            if seguridad == "starttls":
                server.starttls(context=ssl.create_default_context())
        if settings.get("smtp_user"):
            server.login(settings.get("smtp_user"), settings.get("smtp_password", ""))
        server.send_message(msg)
        server.quit()
        return True, "Correo de prueba enviado a %s" % destino
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
