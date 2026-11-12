# -*- coding: utf-8 -*-
"""Generación del PDF de la orden de servicio."""
import os

from fpdf import FPDF

from constants import CHECKLIST_LABELS, ORDER_TYPES, STATUS_LABELS

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE, "static", "fonts")

AZUL = (15, 23, 42)
AZUL_CLARO = (29, 78, 216)
GRIS = (100, 116, 139)
GRIS_CLARO = (241, 245, 249)
BORDE = (226, 232, 240)
VERDE = (22, 163, 74)
AMBAR = (180, 83, 9)


def _t(valor):
    """Convierte el valor a texto (la fuente DejaVu soporta Unicode)."""
    if valor is None:
        return ""
    return str(valor).replace("\x00", "")


def _fecha(valor):
    if not valor:
        return "-"
    texto = str(valor).replace("T", " ")
    partes = texto.split(" ")
    if len(partes) >= 2:
        f = partes[0].split("-")
        if len(f) == 3:
            return "%s-%s-%s %s" % (f[2], f[1], f[0], partes[1][:5])
    return texto


class OrdenPDF(FPDF):
    def __init__(self, empresa):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.empresa = empresa
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(12, 12, 12)
        self.alias_nb_pages()

        regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
        bold = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
        italic = os.path.join(FONT_DIR, "DejaVuSans-Oblique.ttf")
        self.add_font("DejaVu", "", regular)
        self.add_font("DejaVu", "B", bold)
        if os.path.isfile(italic):
            self.add_font("DejaVu", "I", italic)
        else:
            self.add_font("DejaVu", "I", regular)

    def header(self):
        self.set_fill_color(*AZUL)
        self.rect(0, 0, 210, 26, style="F")

        logo = self.empresa.get("logo")
        if logo and os.path.isfile(logo):
            try:
                self.image(logo, x=12, y=6, h=14)
            except Exception:
                pass
        else:
            self.set_text_color(255, 255, 255)
            self.set_font("DejaVu", "B", 15)
            self.set_xy(12, 8)
            self.cell(110, 8, _t(self.empresa.get("company_name") or "ORDEN DE SERVICIO"))
            self.set_font("DejaVu", "", 8)
            self.set_xy(12, 16)
            self.cell(110, 5, _t(self.empresa.get("company_rut") or ""))

        self.set_text_color(255, 255, 255)
        self.set_font("DejaVu", "B", 11)
        self.set_xy(120, 8)
        self.cell(78, 6, "ORDEN DE SERVICIO", align="R")
        self.set_font("DejaVu", "", 8)
        self.set_xy(120, 15)
        self.cell(78, 5, _t(self.empresa.get("company_phone") or ""), align="R")
        self.set_y(32)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*BORDE)
        self.line(12, self.get_y(), 198, self.get_y())
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _t("Documento generado automáticamente por el sistema de órdenes de servicio."),
                  align="L")
        self.cell(0, 5, _t("Página %d de {nb}" % self.page_no()), align="R")

    # ------------------------------------------------------------------
    def ensure(self, alto):
        if self.get_y() + alto > 276:
            self.add_page()

    def titulo(self, numero, texto):
        self.ensure(14)
        self.ln(2)
        self.set_fill_color(*GRIS_CLARO)
        self.set_text_color(*AZUL)
        self.set_font("DejaVu", "B", 10)
        self.cell(0, 8, _t("  %s. %s" % (numero, texto)), fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def campo(self, etiqueta, valor):
        self.ensure(16)
        self.set_font("DejaVu", "B", 7.5)
        self.set_text_color(*GRIS)
        self.cell(0, 4, _t(etiqueta.upper()), new_x="LMARGIN", new_y="NEXT")
        self.set_font("DejaVu", "", 9.5)
        self.set_text_color(*AZUL)
        self.multi_cell(0, 5, _t(valor) or "-", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BORDE)
        self.set_y(self.get_y() - 0.5)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(3)


def build(path, orden, proyecto, cliente, fotos, firma=None, empresa=None):
    """Genera el PDF y devuelve la ruta."""
    empresa = dict(empresa or {})
    pdf = OrdenPDF(empresa)
    pdf.add_page()

    # Título / código
    pdf.set_text_color(*AZUL)
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 7, _t("Orden %s" % orden.get("code", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 8.5)
    pdf.set_text_color(*GRIS)
    tipo = ORDER_TYPES.get(orden.get("type"), orden.get("type") or "")
    pdf.cell(0, 5, _t("%s  |  Emitida: %s" % (tipo, _fecha(orden.get("created_at")))),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # 1. Datos
    pdf.titulo(1, "Datos del servicio")
    pdf.campo("Cliente", cliente.get("name") if cliente else "")
    pdf.campo("Proyecto / Sitio", "%s - %s" % (proyecto.get("name", ""), proyecto.get("site", ""))
              if proyecto else "")
    pdf.campo("Dirección", (proyecto or {}).get("site") or (cliente or {}).get("address"))
    pdf.campo("Rack / Gabinete", orden.get("rack"))
    pdf.campo("Técnico responsable", orden.get("tech_name"))
    pdf.campo("Fecha y hora de ejecución", _fecha(orden.get("performed_at")))
    pdf.campo("Recibe por el cliente", orden.get("receiver"))

    # 2. Checklist
    pdf.titulo(2, "Checklist de mantención")
    import json
    try:
        items = json.loads(orden.get("checklist") or "[]")
    except Exception:
        items = []
    if not items:
        pdf.set_font("DejaVu", "I", 9)
        pdf.set_text_color(*GRIS)
        pdf.cell(0, 6, _t("Sin checklist registrado."), new_x="LMARGIN", new_y="NEXT")
    for item in items:
        estado = item.get("status", "")
        nota = (item.get("note") or "").strip()
        alto = 6.5 + (5 if nota else 0)
        pdf.ensure(alto + 2)
        color = VERDE if estado == "ok" else (AMBAR if estado == "obs" else GRIS)
        pdf.set_font("DejaVu", "B", 8)
        pdf.set_text_color(*color)
        pdf.cell(30, 5.5, _t(STATUS_LABELS.get(estado, estado.upper())))
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(*AZUL)
        pdf.multi_cell(0, 5.5, _t(CHECKLIST_LABELS.get(item.get("key"), item.get("key"))),
                       new_x="LMARGIN", new_y="NEXT")
        if nota:
            pdf.set_font("DejaVu", "I", 8.5)
            pdf.set_text_color(*GRIS)
            pdf.set_x(42)
            pdf.multi_cell(0, 4.6, _t(nota), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*BORDE)
        pdf.line(12, pdf.get_y() + 0.5, 198, pdf.get_y() + 0.5)
        pdf.ln(1.8)

    # 3. Trabajo
    pdf.titulo(3, "Trabajo realizado")
    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_text_color(*AZUL)
    pdf.multi_cell(0, 5.2, _t(orden.get("work")) or "-", new_x="LMARGIN", new_y="NEXT")

    if (orden.get("materials") or "").strip():
        pdf.titulo(4, "Materiales y repuestos utilizados")
        pdf.set_font("DejaVu", "", 9.5)
        pdf.multi_cell(0, 5.2, _t(orden.get("materials")), new_x="LMARGIN", new_y="NEXT")

    if (orden.get("observations") or "").strip():
        pdf.titulo(5, "Observaciones y recomendaciones")
        pdf.set_font("DejaVu", "", 9.5)
        pdf.multi_cell(0, 5.2, _t(orden.get("observations")), new_x="LMARGIN", new_y="NEXT")

    # 6. Fotos
    if fotos:
        pdf.titulo(6, "Registro fotográfico")
        etiquetas = {"antes": "Antes", "despues": "Después", "otro": "Registro"}
        x0, y0 = 12, pdf.get_y()
        ancho, alto_max = 88, 62
        col = 0
        for ruta, kind in fotos:
            if not os.path.isfile(ruta):
                continue
            if col == 0:
                if y0 + alto_max + 12 > 276:
                    pdf.add_page()
                    y0 = pdf.get_y()
                col = 0
            try:
                from PIL import Image
                with Image.open(ruta) as im:
                    w, h = im.size
                alto = min(alto_max, ancho * h / max(1, w))
                x = x0 + col * (ancho + 6)
                pdf.image(ruta, x=x, y=y0, w=ancho, h=alto)
                pdf.set_font("DejaVu", "", 7.5)
                pdf.set_text_color(*GRIS)
                pdf.set_xy(x, y0 + alto + 1)
                pdf.cell(ancho, 4, _t(etiquetas.get(kind, "Registro")))
            except Exception:
                pass
            if col == 1:
                y0 = pdf.get_y() + 10
                col = 0
                pdf.set_y(y0)
            else:
                col = 1
        if col == 1:
            pdf.set_y(y0 + alto_max + 12)

    # 7. Firma
    if firma and os.path.isfile(firma):
        pdf.titulo(7, "Firma de conformidad")
        pdf.ensure(28)
        y = pdf.get_y()
        pdf.image(firma, x=12, y=y, h=18)
        pdf.set_draw_color(*GRIS)
        pdf.line(12, y + 19, 72, y + 19)
        pdf.set_font("DejaVu", "", 7.5)
        pdf.set_text_color(*GRIS)
        pdf.set_xy(12, y + 20)
        pdf.cell(60, 4, _t(orden.get("tech_name") or "Técnico"))
        pdf.ln(4)

    pdf.output(path)
    return path
