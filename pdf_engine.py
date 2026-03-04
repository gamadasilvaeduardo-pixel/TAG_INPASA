# pdf_engine.py
# -*- coding: utf-8 -*-

import io
import os
import base64

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm as U
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.utils import ImageReader

import qrcode
from PIL import Image
from xml.sax.saxutils import escape as xml_escape

# ---------- fallback logo ----------
LOGO_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAARgAAAB4CAYAAACD9l0bAAAACXBIWXMAAAsSAAALEgHS3X78AAAB"
    "R0lEQVR4nO3QoQ2DQBBF0Rm3pQJzT3EoJ2C0ahC+2UCRQk0xJb3p2L8B3hYrxQAAAAAAAAAAAOAD"
    "8w2m2b1S3y1Qkjt3P7H9e3iP7WJQmPz9b7w1f8tWqQ7v8z4h3e+gNw7R5fQeD6w0fQdD6w0fQdD6"
    "w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w0fQdD6w8cHAAAAAAAAAAAAAHB3"
    "+g3r8l22m7S3+o7c3n3r3mO9wAAAABJRU5ErkJggg=="
)

# ======================
# CONFIG — IDÊNTICO AO SEU MODELO (prints)
# ======================
DEFAULTS = {
    "gap_mm": 0.5,
    "font_tag": "Helvetica-Bold",
    "font_foot": "Helvetica-Bold",

    # TAG 50x100 (na sua UI aparece como W=100 H=50) 2x5
    "small": {
        "cols": 2, "rows": 5,
        "W": 100.0, "H": 50.0, "footer": 15.0,
        "pad": 4.0, "thick": 1.0,
        "qr": 18.0, "qr_margin": 2.0,
        "logo_w": 50.0,

        # igual seu print:
        "tag_fs_max": 32.0,
        "tag_fs_min": 14.0,

        "foot_fs_min": 8.0, "foot_fs_max": 14.0,
    },

    # TAG QUADRADA 150x150 — logo entre margem e QR (1x1)
    "big": {
        "cols": 1, "rows": 1,
        "W": 150.0, "H": 150.0, "footer": 46.0,
        "pad": 15.0, "thick": 1.8,
        "qr": 38.0, "qr_margin": 10.0,

        # ✅ seu padrão (não gigante): 85mm
        "logo_w": 85.0,

        # igual seu print:
        "tag_fs_max": 52.0,
        "tag_fs_min": 22.0,

        "foot_fs_min": 8.0, "foot_fs_max": 20.0,

        # logo entre margem e QR
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

# -------------------------------
# AUTO-FIT DO TAG
# - IGNORA QR (QR está abaixo)
# - respeita 2mm das bordas
# -------------------------------
def fit_tag_font_size(tag_text: str, font_name: str, fs_max: float, fs_min: float, max_width_pts: float) -> float:
    if not tag_text:
        return float(fs_min)

    fs = float(fs_max)
    step = 0.25

    while fs >= fs_min - 1e-9:
        w = pdfmetrics.stringWidth(tag_text, font_name, fs)
        if w <= max_width_pts + 0.01:
            return fs
        fs -= step

    return float(fs_min)

def draw_one_label(c, layout, cfg, tag_text, desc_text):
    W = layout["W"] * U
    H = layout["H"] * U
    foot = layout["footer"] * U
    pad = layout["pad"] * U
    qr_s = layout["qr"] * U
    qr_m = layout["qr_margin"] * U
    thick = layout["thick"] * U

    font_tag = cfg["font_tag"]   # Helvetica-Bold
    font_foot = cfg["font_foot"] # Helvetica-Bold

    # Moldura + rodapé
    c.setLineWidth(thick)
    c.rect(0, 0, W, H)
    c.line(0, foot, W, foot)

    avail = H - foot

    # QR (direita, embaixo)
    qx = W - qr_m - qr_s
    qy = foot + qr_m
    c.drawImage(ImageReader(qr_bytes(tag_text)), qx, qy, width=qr_s, height=qr_s, mask="auto")

    # ---------- TAG: central + auto-fit (2mm borda; ignora QR) ----------
    center_x = W / 2.0
    fs_max = float(layout.get("tag_fs_max", 56.0))
    fs_min = float(layout.get("tag_fs_min", 14.0))

    min_edge = 2.0 * U
    max_width = max(1.0, W - 2.0 * min_edge)  # não considera QR

    tag_fs = fit_tag_font_size(tag_text, font_tag, fs_max, fs_min, max_width)

    c.setFont(font_tag, tag_fs)
    ty = foot + avail - pad - tag_fs * 0.90
    if ty < foot + 2 * U:
        ty = foot + 2 * U
    c.drawCentredString(center_x, ty, tag_text)

    # ---------- LOGO (entre margem e QR quando configurado) ----------
    logo_bio = load_logo_image()
    try:
        img = Image.open(logo_bio)
        lw = float(layout["logo_w"]) * U
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

        # X: se "between", coloca entre margem esquerda e QR
        gap_txt = (2.0 if layout["W"] <= 110.0 else 4.0) * U
        use_between = float(layout.get("logo_between_left_and_qr", 0.0)) >= 0.5
        if use_between:
            area_left = (thick / 2.0) + gap_txt
            area_right = qx - gap_txt
            usable = max(0.0, area_right - area_left)
            if usable >= lw:
                x_logo = area_left + (usable - lw) / 2.0
            else:
                x_logo = area_left
        else:
            x_logo = (W - lw) / 2.0

        # Y: alinhar no centro vertical do QR (clamp)
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

    # ---------- Rodapé: central + auto-fit ----------
    fw = W - 2 * pad
    fh = foot - 2 * pad
    if fh < 4:
        return

    desc_safe = safe_paragraph_text(desc_text)

    style = ParagraphStyle(
        "foot",
        fontName=font_foot,
        fontSize=10,
        leading=12,
        alignment=1,
        wordWrap="CJK",
        splitLongWords=1,
    )

    fs_maxf = float(layout.get("foot_fs_max", 14.0))
    fs_minf = float(layout.get("foot_fs_min", 8.0))

    placed = False
    fs_try = fs_maxf
    while fs_try >= fs_minf - 1e-9:
        style.fontSize = fs_try
        style.leading = fs_try + 2
        p = Paragraph(desc_safe, style)
        _, h = p.wrap(fw, fh)
        if h <= fh + 0.1:
            y = pad + (fh - h) / 2.0
            p.drawOn(c, pad, y)
            placed = True
            break
        fs_try -= 0.5

    if not placed:
        style.fontSize = fs_minf
        style.leading = fs_minf + 2
        p = Paragraph(desc_safe, style)
        _, h = p.wrap(fw, fh)
        y = pad + max(0, (fh - h) / 2.0)
        p.drawOn(c, pad, y)

# -------------------------------
# Append sheets (canvas existente)
# -------------------------------
def _append_sheets_to_canvas(c, layout, cfg, items, gap_mm):
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

    idx = 0
    total = len(items)
    while idx < total:
        for r in range(rows):
            for cc in range(cols):
                x0 = (ml + cc * stepX) * U
                y0 = (A4H - mt - H - r * stepY) * U
                c.saveState()
                c.translate(x0, y0)
                if idx < total:
                    tag, desc = items[idx]
                    draw_one_label(c, layout, cfg, tag, desc)
                    idx += 1
                c.restoreState()
        c.showPage()

# -------------------------------
# PDF misto
# -------------------------------
def build_pdf_bytes_mixed(items_with_layout):
    """
    items_with_layout: lista de (tag, desc, layout_name) onde layout_name in {"small","big"}
    """
    cfg = DEFAULTS
    gap = cfg["gap_mm"]

    buckets = {"small": [], "big": []}
    for tag, desc, lay in items_with_layout:
        lay = (lay or "small").strip().lower()
        if lay not in buckets:
            lay = "small"
        buckets[lay].append((tag, desc))

    bio = io.BytesIO()
    A4W, A4H = 210.0, 297.0
    c = canvas.Canvas(bio, pagesize=(A4W * U, A4H * U))

    if buckets["small"]:
        _append_sheets_to_canvas(c, cfg["small"], cfg, buckets["small"], gap)
    if buckets["big"]:
        _append_sheets_to_canvas(c, cfg["big"], cfg, buckets["big"], gap)

    c.save()
    bio.seek(0)
    return bio.getvalue()

# ✅ compat (não quebra import nunca)
def build_pdf_bytes(items, layout_name="small"):
    return build_pdf_bytes_mixed([(t, d, layout_name) for (t, d) in items])