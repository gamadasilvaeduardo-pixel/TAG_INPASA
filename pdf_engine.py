# pdf_engine.py
# -*- coding: utf-8 -*-

import io
import os
import base64

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm as U
from reportlab.lib.utils import ImageReader

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from xml.sax.saxutils import escape as xml_escape

import qrcode
from PIL import Image

# Logo fallback (bem simples, pode trocar por arquivo LOGO_INPASA.png)
LOGO_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAARgAAAB4CAYAAACD9l0bAAAACXBIWXMAAAsSAAALEgHS3X78AAAB"
    "R0lEQVR4nO3QoQ2DQBBF0Rm3pQJzT3EoJ2C0ahC+2UCRQk0xJb3p2L8B3hYrxQAAAAAAAAAAAOAD"
    "8w2m2b1S3y1Qkjt3P7H9e3iP7WJQmPz9b7w1f8tWqQ7v8z4h3e+gNw7R5fQeD6w0fQdD6w0fQdD6"
    "w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w8cHAAAAAAAAAAAAAHB3"
    "+g3r8l22m7S3+o7c3n3r3mO9wAAAABJRU5ErkJggg=="
)

DEFAULTS = {
    "gap_mm": 0.5,
    "font_tag": "Helvetica-Bold",
    "font_foot": "Helvetica-Bold",

    # SMALL (mesmo padrão do seu layout W=100, H=50, grid 2x5 A4)
    "small": {
        "cols": 2, "rows": 5,
        "W": 100.0, "H": 50.0, "footer": 15.0,
        "pad": 4.0, "thick": 1.0,
        "qr": 18.0, "qr_margin": 2.0,

        # TAG fonte variável: vai tentar subir até tag_fs_max e descer até tag_fs_min
        "tag_fs_max": 40.0,
        "tag_fs_min": 14.0,

        "foot_fs_min": 8.0, "foot_fs_max": 14.0,
    },

    # BIG (150x150) = seu “tag grande”
    "big": {
        "cols": 1, "rows": 1,
        "W": 150.0, "H": 150.0, "footer": 46.0,
        "pad": 15.0, "thick": 1.8,
        "qr": 38.0, "qr_margin": 10.0,

        # LOGO 85.0 (igual seu código original)
        "logo_w": 85.0,

        # TAG fonte variável
        "tag_fs_max": 56.0,
        "tag_fs_min": 22.0,

        "foot_fs_min": 8.0, "foot_fs_max": 20.0,

        # logo entre margem esquerda e QR (como seu modelo)
        "logo_between_left_and_qr": 1.0,
    }
}

def safe_paragraph_text(s: str) -> str:
    return xml_escape(s or "")

def _clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))

def qr_bytes(text, box_size=8, border=1):
    img = qrcode.make(
        text,
        box_size=box_size,
        border=border,
        error_correction=qrcode.constants.ERROR_CORRECT_M
    )
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

def load_logo_image():
    # tenta arquivo no repo primeiro
    here = os.path.dirname(os.path.abspath(__file__))
    fpath = os.path.join(here, "LOGO_INPASA.png")
    if os.path.exists(fpath):
        try:
            img = Image.open(fpath).convert("RGBA")
            bio = io.BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            return bio
        except Exception:
            pass
    return io.BytesIO(base64.b64decode(LOGO_PNG_B64))

def fit_font_size_for_text(c, font_name, text, fs_min, fs_max, max_width_pt):
    """
    Ajusta fonte do TAG para caber na largura máxima (sem cortar).
    Tenta do maior para o menor.
    """
    text = text or ""
    fs = float(fs_max)
    while fs >= float(fs_min) - 1e-9:
        w = c.stringWidth(text, font_name, fs)
        if w <= max_width_pt + 0.1:
            return fs
        fs -= 0.5
    return float(fs_min)

def draw_one_label(c, layout, cfg, tag_text, desc_text):
    W = layout["W"] * U
    H = layout["H"] * U
    foot = layout["footer"] * U
    pad = layout["pad"] * U
    qr_s = layout["qr"] * U
    qr_m = layout["qr_margin"] * U
    thick = layout["thick"] * U

    font_tag = cfg["font_tag"]
    font_foot = cfg["font_foot"]

    # Moldura + linha do rodapé
    c.setLineWidth(thick)
    c.rect(0, 0, W, H)
    c.line(0, foot, W, foot)

    avail = H - foot

    # QR (direita, mais baixo)
    qx = W - qr_m - qr_s
    qy = foot + qr_m
    c.drawImage(ImageReader(qr_bytes(tag_text)), qx, qy, width=qr_s, height=qr_s, mask="auto")

    # -------- TAG (auto-fit, Helvetica-Bold) --------
    # regra: manter pelo menos 2mm das bordas -> max_width = W - 4mm
    # (sem se preocupar com QR porque QR está mais baixo; TAG fica em cima)
    margin = 2.0 * U
    max_w = W - 2 * margin

    fs_max = float(layout.get("tag_fs_max", 56.0))
    fs_min = float(layout.get("tag_fs_min", 18.0))

    tag_fs = fit_font_size_for_text(
        c, font_tag, tag_text,
        fs_min=fs_min,
        fs_max=fs_max,
        max_width_pt=max_w
    )

    c.setFont(font_tag, tag_fs)

    # posição do TAG no topo (mesmo estilo do seu modelo)
    ty = foot + avail - pad - tag_fs * 0.90
    if ty < foot + 2 * U:
        ty = foot + 2 * U

    c.drawCentredString(W / 2.0, ty, tag_text)

    # -------- LOGO (somente big tem logo_w fixo) --------
    if layout.get("W") == 150.0 and layout.get("H") == 150.0:
        logo_bio = load_logo_image()
        try:
            img = Image.open(logo_bio)
            lw = float(layout.get("logo_w", 85.0)) * U  # 85mm fixo
            ar = img.height / img.width
            lh = lw * ar

            # área vertical útil (entre rodapé e o TAG)
            y_low = foot
            y_high = max(ty - 2 * U, y_low + 2 * U)
            max_h = max(4 * U, (y_high - y_low))
            if lh > max_h:
                scale = max_h / lh
                lw *= scale
                lh *= scale

            gap_txt = 4.0 * U
            use_between = float(layout.get("logo_between_left_and_qr", 1.0)) >= 0.5
            if use_between:
                area_left = (thick / 2.0) + gap_txt
                area_right = qx - gap_txt
                usable = max(0.0, area_right - area_left)
                x_logo = area_left + max(0.0, (usable - lw) / 2.0)
            else:
                x_logo = (W - lw) / 2.0

            # alinhar no centro vertical do QR
            qr_cy = qy + (qr_s / 2.0)
            y_logo = qr_cy - (lh / 2.0)
            y_logo = _clamp(y_logo, y_low + 1 * U, (y_high - lh))

            logo_bio.seek(0)
            c.drawImage(
                ImageReader(logo_bio),
                x_logo, y_logo,
                width=lw, height=lh,
                mask="auto",
                preserveAspectRatio=True
            )
        except Exception:
            pass

    # -------- Rodapé (auto-fit centralizado) --------
    fw = W - 2 * pad
    fh = foot - 2 * pad
    if fh < 4:
        return

    desc_safe = safe_paragraph_text((desc_text or "").upper())

    style = ParagraphStyle(
        "foot",
        fontName=font_foot,
        fontSize=10,
        leading=12,
        alignment=1,  # CENTER
        wordWrap="CJK",
        splitLongWords=1,
    )

    fs_max_f = float(layout.get("foot_fs_max", 14.0))
    fs_min_f = float(layout.get("foot_fs_min", 8.0))

    placed = False
    fs_try = fs_max_f
    while fs_try >= fs_min_f - 1e-9:
        style.fontSize = fs_try
        style.leading = fs_try + 2
        p = Paragraph(desc_safe, style)
        w, h = p.wrap(fw, fh)
        if h <= fh + 0.1:
            y = pad + (fh - h) / 2.0
            p.drawOn(c, pad, y)
            placed = True
            break
        fs_try -= 0.5

    if not placed:
        style.fontSize = fs_min_f
        style.leading = fs_min_f + 2
        p = Paragraph(desc_safe, style)
        w, h = p.wrap(fw, fh)
        y = pad + max(0, (fh - h) / 2.0)
        p.drawOn(c, pad, y)

def make_pdf_sheet_fill_bytes(layout, cfg, items, gap_mm):
    A4W, A4H = 210.0, 297.0
    cols, rows = int(layout["cols"]), int(layout["rows"])
    W, H = float(layout["W"]), float(layout["H"])
    g = float(gap_mm)
    t = float(layout["thick"])

    stepX = W + (g + t)
    stepY = H + (g + t)
    need_w = cols * W + (cols - 1) * (g + t)
    need_h = rows * H + (rows - 1) * (g + t)
    ml = (A4W - need_w) / 2.0
    mt = (A4H - need_h) / 2.0

    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=(A4W * U, A4H * U))

    idx = 0
    total = len(items)
    while idx < total:
        for r in range(rows):
            for cc in range(cols):
                if idx >= total:
                    break
                x0 = (ml + cc * stepX) * U
                y0 = (A4H - mt - H - r * stepY) * U
                c.saveState()
                c.translate(x0, y0)
                tag, desc = items[idx]
                draw_one_label(c, layout, cfg, tag, desc)
                c.restoreState()
                idx += 1
        c.showPage()

    c.save()
    bio.seek(0)
    return bio.getvalue()

def build_pdf_bytes_mixed(items_with_layout):
    """
    items_with_layout: list of tuples (tag, desc, layout_name)
    layout_name in {"small","big"}
    Gera 1 PDF (A4) com páginas separadas por layout.
    """
    cfg = {
        "gap_mm": DEFAULTS["gap_mm"],
        "font_tag": DEFAULTS["font_tag"],
        "font_foot": DEFAULTS["font_foot"],
    }

    small_items = [(t, d) for (t, d, lay) in items_with_layout if lay == "small"]
    big_items = [(t, d) for (t, d, lay) in items_with_layout if lay == "big"]

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(210 * U, 297 * U))

    def render_group(layout, group_items):
        if not group_items:
            return
        A4W, A4H = 210.0, 297.0
        cols, rows = int(layout["cols"]), int(layout["rows"])
        W, H = float(layout["W"]), float(layout["H"])
        g = float(DEFAULTS["gap_mm"])
        t = float(layout["thick"])

        stepX = W + (g + t)
        stepY = H + (g + t)
        need_w = cols * W + (cols - 1) * (g + t)
        need_h = rows * H + (rows - 1) * (g + t)
        ml = (A4W - need_w) / 2.0
        mt = (A4H - need_h) / 2.0

        idx = 0
        total = len(group_items)
        while idx < total:
            for r in range(rows):
                for cc in range(cols):
                    if idx >= total:
                        break
                    x0 = (ml + cc * stepX) * U
                    y0 = (A4H - mt - H - r * stepY) * U
                    c.saveState()
                    c.translate(x0, y0)
                    tag, desc = group_items[idx]
                    draw_one_label(c, layout, cfg, tag, desc)
                    c.restoreState()
                    idx += 1
            c.showPage()

    render_group(DEFAULTS["small"], small_items)
    render_group(DEFAULTS["big"], big_items)

    c.save()
    out.seek(0)
    return out.getvalue()
